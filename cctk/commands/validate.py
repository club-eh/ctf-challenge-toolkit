import enum

import click
from rich.console import Group
from rich.panel import Panel

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

	# print summary
	CONSOLE.print(
		"",
		Panel(Group(
			deploy_source.rich_challenge_summary(),
			validation_book.rich_issue_summary(),
		), title="Summary", expand=False, border_style="cyan"),
	)
