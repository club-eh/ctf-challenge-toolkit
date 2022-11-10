import enum

import click
from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from cctk.commands import root
from cctk.commands.shared import DeploySource
from cctk.rt import CONSOLE
from cctk.types import AppConfig
from cctk.validation import (FatalValidationError, ValidationBook,
                             ValidationError)


class ValidationMode(enum.Enum):
	REPOSITORY = "repo"
	CHALLENGES = "challenges"


@root.command()
@click.argument("challenges", nargs=-1)
@click.pass_context
def validate(ctx: click.Context, challenges: tuple[str]):
	"""Validate challenge definitions.

	Can validate either specific challenges, or the entire repository.

	CHALLENGES are the IDs of the challenges to validate.
	If none are specified, validation is performed on all challenges in the repository.
	"""

	app_cfg: AppConfig = ctx.ensure_object(AppConfig)
	assert app_cfg.repo_path is not None

	# initialize validation book
	validation_book = ValidationBook()

	# load repo and challenge data
	try:
		deploy_source = DeploySource(validation_book, app_cfg.repo_path, list(challenges) if len(challenges) > 0 else None, ctx.obj.verbose)
	except (FatalValidationError, ValidationError):
		raise SystemExit(1)

	# generate summary tables
	summary_items: list[RenderableType] = [
		deploy_source.rich_challenge_summary(Table(title=Text.assemble(("Loaded Challenges", "cyan underline"), ""), title_justify="left", box=box.MINIMAL)),
		"",
		validation_book.rich_issue_summary(Table(title=Text.assemble(("Validation Issues", "orange3 underline"), ""), title_justify="left", box=box.MINIMAL)),
	]
	if app_cfg.verbose:
		# add repository info section
		summary_items.insert(0, Text("Repository Config", style="cyan underline"))
		summary_items.insert(1, Padding(deploy_source.rich_repo_summary(Table.grid()), (1, 0, 0, 1)))
		summary_items.insert(2, "")

	# print summary
	CONSOLE.print(
		# newline to separate summary from previous output
		"",
		# panel containing tables
		Panel(Group(*summary_items), title="Summary", expand=False, border_style="cyan"),
	)
