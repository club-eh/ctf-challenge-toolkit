import os

import anyio
import asyncclick as click
from rich import box
from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from cctk.commands import root
from cctk.commands.shared import DeployTarget, do_validation
from cctk.ctfd.api import CTFdAPI
from cctk.rt import CONSOLE
from cctk.types import AppConfig
from cctk.validation import Severity


# constants to control # of challenges to operate on concurrently
CONCURRENT_READS = 5
CONCURRENT_WRITES = 3


@root.command()
@click.option("-u", "--url", help="URL of the CTFd instance to deploy to (overrides repo config).")
@click.option("-t", "--token", "api_token", help="API token for the CTFd instance (overrides env variable).")
@click.option("-s", "--skip", "skip_ids", metavar="CHALLENGE_ID", multiple=True, help="IDs of challenges to ignore.")
@click.argument("challenges", nargs=-1)
@click.pass_context
async def deploy(ctx: click.Context, url: str | None, api_token: str | None, challenges: tuple[str], skip_ids: tuple[str]):
	"""Deploy challenges to a live CTFd instance.

	Can deploy either specific challenges, or all challenges in the entire repository.

	CHALLENGES are the IDs of the challenges to deploy.
	If none are specified, all challenges in the repository are deployed.
	"""

	app_cfg: AppConfig = ctx.ensure_object(AppConfig)

	# conduct validation of local sources, and display results to user
	deploy_src, validation_book = do_validation(app_cfg, challenges, skip_ids)

	# exit if any validation errors occurred
	if any(issue.severity >= Severity.ERROR for issue in validation_book.get_issues(None)):
		CONSOLE.print("Errors have occurred during validation; deployment cannot continue.", style="validation.issue.error")
		raise SystemExit(1)


	# get CTFd URL (CLI, env variable, repo config, prompt user)
	if url is None:
		try:
			# retrieve from environment variable
			url = os.environ["CTFD_URL"]
		except KeyError:
			# retrieve from repository config
			url = deploy_src.repo.url
			if url is None:
				# last resort: ask user directly
				url = Prompt.ask("Enter the CTFd URL (including the scheme, excluding any path)", console=CONSOLE)

	# get CTFd API token (CLI, env variable, prompt user)
	if api_token is None:
		try:
			# retrieve from environment variable
			api_token = os.environ["CTFD_API_TOKEN"]
		except KeyError:
			# request CTFd API token from user
			api_token = Prompt.ask("Enter a CTFd API token to continue (input will be hidden)", console=CONSOLE, password=True)

	# initialize CTFd API interface
	api = CTFdAPI(url, api_token)
	# initialize DeployTarget
	deploy_tgt = DeployTarget(api, verbose=app_cfg.verbose)

	# retrieve CTFd state
	semaphore = anyio.Semaphore(CONCURRENT_READS)
	progress = Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), TimeElapsedColumn(), console=CONSOLE)
	progress.start()
	try:
		async with anyio.create_task_group() as tg:
			for challenge in deploy_src.challenges.values():
				tg.start_soon(deploy_tgt.get_challenge_info, semaphore, progress, challenge.challenge_id)
	finally:
		progress.stop()

	# determine required changes
	required_changes = deploy_tgt.compare_against_sources(deploy_src)

	# generate change table
	changes_table: RenderableType
	if len(required_changes):
		changes_table = deploy_tgt.rich_change_summary(required_changes, Table(title=Text.assemble(("Pending Changes", "cyan underline"), ""), title_justify="left", box=box.MINIMAL))
	else:
		changes_table = Text("No changes are required!", style="green3")

	# display required changes
	CONSOLE.print(
		# panel containing tables
		Panel(Group(changes_table), title="Deploy Summary", expand=False, border_style="cyan"),
	)

	# exit if no changes to be made
	if not len(required_changes):
		return

	# ask user if they want to make the displayed changes
	if not Confirm.ask("Do you want to apply these changes?"):
		return

	# apply the changes
	semaphore = anyio.Semaphore(CONCURRENT_WRITES)
	progress = Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), TimeElapsedColumn(), console=CONSOLE)
	progress.start()
	try:
		async with anyio.create_task_group() as tg:
			for challenge_id, changes in required_changes.items():
				tg.start_soon(deploy_tgt.apply_changes_to_challenge, semaphore, progress, deploy_src, challenge_id, changes)
	finally:
		progress.stop()
