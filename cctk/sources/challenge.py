from __future__ import annotations

import decimal
from pathlib import Path

import attrs
import marshmallow

from cctk import tomllib
from cctk.constants import CHALLENGE_CONFIG_FILENAME
from cctk.schemas.challenge import ChallengeConfigSchema, ChallengeDifficulty
from cctk.schemas.formatting import format_validation_exception
from cctk.sources.repository import ChallengeRepo
from cctk.validation import Severity, Source, ValidationBook, ValidationError


@attrs.define(frozen=True)
class ContainerConfig:
	id: str
	# Path to Containerfile
	build: str
	# Map of ports to expose (key is ID, value is port number)
	ports: dict[str, int]


@attrs.define(frozen=True)
class ChallengeConfig:
	id: str
	name: str
	category: str
	difficulty: ChallengeDifficulty
	description: str | None
	tags: list[str]

	flag: str
	points: int

	hints: list[str]

	dynamic: dict[str, ContainerConfig] | None


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

		# rebuild dictionary to match constructor parameters
		final_data = {
			"id": clean_meta["id"],
			"category": clean_meta["category"],
			"difficulty": clean_meta["difficulty"],
			"tags": clean_meta["tags"],

			"flag": clean_scoring["flag"],

			# collapse list of hint structures
			"hints": [hint["content"] for hint in cleaned_data.get("hints", [])],

			"dynamic": cleaned_data.get("dynamic", None),
		}

		del cleaned_data

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


		# build the object, so typing works for further validation checks
		config = cls(**final_data)


		# error on challenge ID mismatch
		if config.id != challenge_id:
			pen.issue(Severity.ERROR, "challenge-config-id-mismatch", f"Challenge config ID does not match directory name ({final_data['id']!r} != {challenge_id!r})")
			validation_error = True

		# error on invalid category
		if config.category not in repo.categories:
			pen.issue(Severity.ERROR, "challenge-config-category-invalid", f"Challenge category is invalid ({final_data['category']!r} must match one of the repository-defined categories)")
			validation_error = True

		# warn on undefined difficulty
		if config.difficulty == ChallengeDifficulty.UNDEFINED:
			pen.warn("challenge-config-difficulty-undefined", "Challenge difficulty is set to 'undefined'")

		# TODO: (more) custom validation steps (for warnings and non-strict-schema issues)

		if validation_error:
			raise ValidationError

		return config


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
