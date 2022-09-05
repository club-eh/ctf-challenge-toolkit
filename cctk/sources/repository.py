"""Interfaces for interacting with challenge repositories."""

from __future__ import annotations
from typing import Iterator

import decimal
from pathlib import Path

import attrs
import marshmallow

from cctk import tomllib
from cctk.constants import CHALLENGE_CONFIG_FILENAME, REPO_CONFIG_FILENAME
from cctk.schemas.formatting import format_validation_exception
from cctk.schemas.repository import ChallengeRepoConfigSchema
from cctk.validation import Severity, Source, ValidationBook, ValidationError


@attrs.define(frozen=True)
class ChallengeRepoConfig:
	categories: list[str]


	@classmethod
	def from_file(cls, book: ValidationBook, path: Path) -> ChallengeRepoConfig:
		pen = book.bind(None, Source(path))

		# attempt to load the repo config file
		try:
			with path.open(mode="rb") as fp:
				raw_data = tomllib.load(fp, parse_float = decimal.Decimal)
		except tomllib.TOMLDecodeError as exc:
			pen.issue(Severity.ERROR, "repo-config-invalid-toml", f"Failed to parse {REPO_CONFIG_FILENAME}: {exc}")
			raise ValidationError

		# validate with Marshmallow schema
		try:
			cleaned_data = ChallengeRepoConfigSchema().load(raw_data)
		except marshmallow.ValidationError as exc:
			pen.issue(Severity.ERROR, "repository-config-schema-failure",
				format_validation_exception(exc.messages, "Repository config file failed schema validation"))
			raise ValidationError

		# TODO: custom validation steps (for warnings and non-strict-schema issues)

		return cls(**cleaned_data)


class ChallengeRepo:
	"""Interface to a challenge repository."""

	def __init__(self, book: ValidationBook, path: Path) -> None:
		"""Initialize a new ChallengeRepo interface.

		Validates the challenge repository and its configuration.

		Args:
			book: The ValidationBook to report validation issues to.
			path: The path to the challenge repository.
		"""

		# store object attributes
		self.path = path
		self.config_path = path / REPO_CONFIG_FILENAME


		# NOTE: technically some of these issues don't have to be fatal, but it's not worth the special-casing to handle

		# sanity-check repo directory
		if not self.path.exists():
			book.issue(Severity.FATAL, None, Source(self.path), "repo-not-found", "Challenge repository directory does not exist")
		elif not self.path.is_dir():
			book.issue(Severity.FATAL, None, Source(self.path), "repo-not-directory", "Challenge repository directory exists but is not a directory")

		# sanity-check repo config file
		if not self.config_path.exists():
			book.issue(Severity.FATAL, None, Source(self.config_path), "repo-config-not-found", f"Challenge repository does not contain a {REPO_CONFIG_FILENAME} file")
		elif not self.config_path.is_file():
			book.issue(Severity.FATAL, None, Source(self.config_path), "repo-config-not-file", "Challenge repository config exists but is not a file")


		# load the repo config file (with validation)
		self.config = ChallengeRepoConfig.from_file(book, self.config_path)


	@property
	def categories(self) -> list[str]:
		"""Return a list of category IDs, as defined in the repo config file."""
		return self.config.categories

	def find_challenges(self) -> Iterator[str]:
		"""Collect and return a list of all challenges within this repository."""

		# iterate over all items within the directory
		for subpath in self.path.iterdir():
			# filter out non-directories
			if subpath.is_dir():
				# ignore directories without a challenge config
				if (subpath / CHALLENGE_CONFIG_FILENAME).exists():
					yield subpath.name
