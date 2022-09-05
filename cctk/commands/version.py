import click

from cctk.commands import root
from cctk.constants import TOOLKIT_VERSION


@root.command()
def version():
	"""Display the installed toolkit version."""
	click.echo(f"CTF Challenge ToolKit {TOOLKIT_VERSION}")
