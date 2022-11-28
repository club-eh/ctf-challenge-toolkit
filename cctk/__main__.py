#!/usr/bin/env python3

from .commands import root as _cli_root

# hack to silence trio's annoying RuntimeWarning regarding our custom sys.excepthook (from rich)
import sys
_old_hook = sys.excepthook
sys.excepthook = sys.__excepthook__
import trio
sys.excepthook = _old_hook


def entrypoint():
	"""Run the main Click entrypoint using the Trio backend."""
	_cli_root(_anyio_backend="trio")

entrypoint()
