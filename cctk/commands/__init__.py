"""Contains CLI commands exposed to the user."""

from pathlib import Path

import click

from cctk.constants import TOOLKIT_DESCRIPTION
from cctk.rt import CONSOLE
from cctk.types import AppConfig


# define the "root" command group which contains all commands and subgroups
@click.group(
	# display application description
	help = TOOLKIT_DESCRIPTION,

	# global context settings for Click
	context_settings = dict(
		# allow using -h in addition to --help
		help_option_names = ["-h", "--help"],
	),
)
@click.option("-R", "--repo", help="Specify the location of the challenge repository (instead of using the current working directory).")
@click.option("-v", "--verbose", is_flag=True, help="Show more verbose information.")
@click.pass_context
def root(ctx: click.Context, repo: str | None, verbose: bool):
	# ensure ctx.obj exists
	ctx.ensure_object(AppConfig)
	assert isinstance(ctx.obj, AppConfig)

	# store verbose setting
	ctx.obj.verbose = verbose

	# determine repo path
	if repo is None:
		# default to cwd
		ctx.obj.repo_path = Path(".")
	else:
		ctx.obj.repo_path = Path(repo)

	# log location of challenge repo
	CONSOLE.print(f"Using challenge repo at {str(ctx.obj.repo_path.resolve(strict=False))}")


# define submodules
__all__ = [
	"validate",
	"version",
]

# import submodules
from . import *
