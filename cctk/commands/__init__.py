"""Contains CLI commands exposed to the user."""

from pathlib import Path

import asyncclick as click

from cctk.constants import TOOLKIT_DESCRIPTION
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
	# create app config object
	app_cfg = ctx.ensure_object(AppConfig)

	# store verbose setting
	app_cfg.verbose = verbose

	# determine repo path
	if repo is None:
		# default to cwd
		app_cfg.repo_path = Path(".")
	else:
		app_cfg.repo_path = Path(repo)


# define submodules
__all__ = [
	"deploy",
	"validate",
	"version",
]

# import submodules
from . import *
