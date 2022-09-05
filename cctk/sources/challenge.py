from __future__ import annotations
from typing import Literal

import decimal
import enum
from pathlib import Path

import attrs
import marshmallow

from cctk import tomllib
from cctk.constants import CHALLENGE_CONFIG_FILENAME
from cctk.sources.repository import ChallengeRepo
from cctk.schemas.challenge import ChallengeConfigSchema
from cctk.schemas.formatting import format_validation_exception
from cctk.validation import (Severity, Source, ValidationBook,
                             ValidationError)


class ChallengeDifficulty(enum.Enum):
	UNDEFINED = "undefined"
	EASY = "easy"
	MEDIUM = "medium"
	HARD = "hard"

ChallengeDifficultyStr = Literal["undefined", "easy", "medium", "hard"]


@attrs.define(frozen=True)
class ChallengeConfig:
	id: str
	name: str
	category: str
	difficulty: ChallengeDifficultyStr
	description: str | None
	tags: list[str]

	flag: str
	points: int

	hints: list[str]


	@classmethod
	def from_file(cls, repo: ChallengeRepo, book: ValidationBook, path: Path, challenge_id: str) -> ChallengeConfig:
		pen = book.bind(challenge_id, Source(path))

		validation_error = False

		# attempt to load the challenge config file
		try:
			with path.open(mode="rb") as fp:
				raw_data = tomllib.load(fp, parse_float = decimal.Decimal)
		except tomllib.TOMLDecodeError as exc:
			pen.issue(Severity.ERROR, "challenge-config-invalid-toml", f"Failed to parse {CHALLENGE_CONFIG_FILENAME}: {exc}")
			raise ValidationError

		# validate with Marshmallow schema
		try:
			cleaned_data = ChallengeConfigSchema().load(raw_data)
		except marshmallow.ValidationError as exc:
			pen.issue(Severity.ERROR, "challenge-config-schema-failure",
				format_validation_exception(exc.messages, "Challenge config file failed schema validation"))
			raise ValidationError

		# partially destructure
		clean_meta = cleaned_data["meta"]
		clean_scoring = cleaned_data["scoring"]
		clean_hints = cleaned_data.get("hints", [])
		del cleaned_data

		# rebuild dictionary to match constructor parameters
		final_data = {
			"id": clean_meta["id"],
			"category": clean_meta["category"],
			"difficulty": clean_meta["difficulty"],
			"tags": clean_meta["tags"],

			"flag": clean_scoring["flag"],
		}

		if "name" in clean_meta:
			final_data["name"] = clean_meta["name"]
		else:
			pen.warn("challenge-config-missing-name", "Challenge config does not specify a name; using challenge ID")
			final_data["name"] = clean_meta["id"]

		if "description" in clean_meta:
			final_data["description"] = clean_meta["description"]
		else:
			pen.warn("challenge-config-missing-description", "Challenge config does not specify a description")
			final_data["description"] = None

		if "points" in clean_scoring:
			final_data["points"] = clean_scoring["points"]
		else:
			pen.warn("challenge-config-missing-points", "Challenge config does not specify a point value; defaulting to 0")
			final_data["points"] = 0

		# collapse list of hint structures
		final_data["hints"] = [hint["content"] for hint in clean_hints]


		# error on challenge ID mismatch
		if final_data["id"] != challenge_id:
			pen.issue(Severity.ERROR, "challenge-config-id-mismatch", f"Challenge config ID does not match directory name ({final_data['id']!r} != {challenge_id!r})")
			validation_error = True

		# error on undefined category
		if final_data["category"] not in repo.categories:
			pen.issue(Severity.ERROR, "challenge-", f"Challenge category is invalid ({final_data['category']!r} must match one of the repository-defined categories)")
			validation_error = True

		# warn on undefined difficulty
		if final_data["difficulty"] == "undefined":
			pen.warn("challenge-config-difficulty-undefined", "Challenge difficulty is set to 'undefined'")

		# TODO: (more) custom validation steps (for warnings and non-strict-schema issues)

		if validation_error:
			raise ValidationError

		return cls(**final_data)


class Challenge:
	"""Interface to a challenge directory."""

	def __init__(self, repo: ChallengeRepo, book: ValidationBook, path: Path, challenge_id: str):
		"""Initialize a new Challenge interface.

		Validates the challenge directories and configuration files.

		Args:
			book: The ValidationBook to report validation issues to.
			path: The path to the challenge directory.
			challenge_id: The ID of this challenge.
		"""

		# store object attributes
		self.path = path
		self.config_path = path / CHALLENGE_CONFIG_FILENAME
		self.challenge_id = challenge_id


		# sanity-check challenge directory
		if not self.path.exists():
			book.issue(Severity.FATAL, challenge_id, Source(self.path), "challenge-not-found", "Challenge directory does not exist")
		elif not self.path.is_dir():
			book.issue(Severity.FATAL, challenge_id, Source(self.path), "challenge-not-directory", "Challenge directory exists but is not a directory")

		# sanity-check challenge config file
		if not self.config_path.exists():
			book.issue(Severity.FATAL, challenge_id, Source(self.config_path), "challenge-config-not-found", f"Challenge directory does not contain a {CHALLENGE_CONFIG_FILENAME} file")
		elif not self.config_path.is_file():
			book.issue(Severity.FATAL, challenge_id, Source(self.config_path), "challenge-config-not-file", "Challenge config exists but is not a file")


		# load the config file (with validation)
		self.config = ChallengeConfig.from_file(repo, book, self.config_path, challenge_id)


	def __repr__(self) -> str:
		return f"<Challenge id={self.challenge_id!r} config={self.config!r}>"
