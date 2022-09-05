import click

from cctk.constants import TOOLKIT_VERSION
from cctk.commands import root


@root.command()
def version():
	"""Display the installed toolkit version."""
	click.echo(f"CTF Challenge ToolKit {TOOLKIT_VERSION}")
