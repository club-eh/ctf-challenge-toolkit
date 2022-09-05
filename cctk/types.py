"""Data-centered types."""

from pathlib import Path

import attrs


@attrs.define
class AppConfig:
	"""Holds application configuration (as set from Click)."""

	# Whether to output verbose messages
	verbose: bool = False

	# Path to the challenge repository to use.
	repo_path: Path | None = None
