#!/usr/bin/env python3

from .commands import root as _cli_root

def entrypoint():
	"""Run the main Click entrypoint using the Trio backend."""
	_cli_root(_anyio_backend="trio")

entrypoint()
