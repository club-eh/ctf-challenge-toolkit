import asyncclick as click

from cctk.commands import root
from cctk.commands.shared import do_validation
from cctk.types import AppConfig


@root.command()
@click.option("-s", "--skip", "skip_ids", metavar="CHALLENGE_ID", multiple=True, help="IDs of challenges to ignore.")
@click.argument("challenges", nargs=-1)
@click.pass_context
def validate(ctx: click.Context, challenges: tuple[str], skip_ids: tuple[str]):
	"""Validate challenge definitions.

	Can validate either specific challenges, or the entire repository.

	CHALLENGES are the IDs of the challenges to validate.
	If none are specified, validation is performed on all challenges in the repository.
	"""

	do_validation(
		app_cfg=ctx.ensure_object(AppConfig),
		challenges=challenges,
		skip_ids=skip_ids,
	)
