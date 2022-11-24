#!/usr/bin/env python3

import anyio

from .commands import root as entrypoint


# run the main Click entrypoint, under a custom event loop w/ uvloop
anyio.run(entrypoint(), backend="trio")
