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
from cctk.validation import Severity, Source, ValidationBook, ValidationError, ValidationBoundPen


@attrs.define(frozen=True)
class StaticConfig:
	# list of glob patterns to include
	include_patterns: list[str]
	# list of glob patterns to exclude
	exclude_patterns: list[str]
	# list of prefixes to remove from paths
	rm_prefixes: list[str]


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

	static: StaticConfig | None
	dynamic: dict[str, ContainerConfig] | None


	@classmethod
	def from_file(cls, config_path: Path, pen: ValidationBoundPen) -> ChallengeConfig:
		"""Create a new ChallengeConfig object from a `challenge.toml` file. Includes minimal validation.

		Args:
			config_path (Path): Path to the `challenge.toml` to load.
			pen (ValidationBoundPen): The bound pen to report validation issues to.

		Raises:
			ValidationError: If any errors are encountered while parsing the `challenge.toml` file.
		"""

		# attempt to load the challenge config file
		try:
			with config_path.open(mode="rb") as fp:
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
		}

		# construct StaticConfig object, if config provided
		final_data["static"] = None if cleaned_data.get("static") is None else StaticConfig(**cleaned_data["static"])

		# construct ContainerConfig objects for dynamic sections
		if cleaned_data.get("dynamic") is not None:
			final_data["dynamic"] = {
				cid : ContainerConfig(id=cid, **cconfig)
				for cid, cconfig in cleaned_data["dynamic"].items()
			}
		else:
			final_data["dynamic"] = None

		del cleaned_data

		# add fields that need extra validation
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

		# build + return the object
		return cls(**final_data)


class Challenge:
	"""Interface to a challenge directory."""

	def __repr__(self) -> str:
		return f"<Challenge id={self.challenge_id!r} config={self.config!r}>"

	def __init__(self, repo: ChallengeRepo, book: ValidationBook, path: Path, challenge_id: str):
		"""Initialize a new Challenge interface.

		Validates the challenge directories and configuration files.

		Args:
			book: The ValidationBook to report validation issues to.
			path: The path to the challenge directory.
			challenge_id: The ID of this challenge.
		"""

		# store object attributes
		self.repo = repo
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


		# create bound pen for issues related to the config
		cfg_pen = book.bind(challenge_id, Source(self.config_path))

		# load the config file (with minimal validation)
		self.config = ChallengeConfig.from_file(self.config_path, cfg_pen)

		# validate the challenge config
		self._validate_config(cfg_pen)


	def _validate_config(self, pen: ValidationBoundPen):
		"""Conducts a series of validation checks on the loaded ChallengeConfig
		and its corresponding challenge directory.

		Args:
			pen (ValidationBoundPen): A bound pen to report validation issues to.

		Raises:
			ValidationError: If any validation errors were found.
		"""

		encountered_error = False

		# error on challenge ID mismatch
		if self.config.id != self.challenge_id:
			pen.issue(Severity.ERROR, "challenge-config-id-mismatch", f"Challenge config ID does not match directory name ({self.config.id!r} != {self.challenge_id!r})")
			encountered_error = True

		# error on invalid category
		if self.config.category not in self.repo.categories:
			pen.issue(Severity.ERROR, "challenge-config-category-invalid", f"Challenge category is invalid ({self.config.category!r} must match one of the repository-defined categories)")
			encountered_error = True

		# warn on undefined difficulty
		if self.config.difficulty == ChallengeDifficulty.UNDEFINED:
			pen.warn("challenge-config-difficulty-undefined", "Challenge difficulty is set to 'undefined'")

		if self.config.dynamic is not None:
			# error if dynamic section exists but not directory
			if not (self.path / "dynamic").is_dir():
				pen.issue(Severity.ERROR, "challenge-dynamic-dir-missing", "Config contains dynamic section but `dynamic` subdirectory not found")
				encountered_error = True

			# error on missing container build files
			for container_id, container_cfg in self.config.dynamic.items():
				containerfile = self.path / "dynamic" / container_cfg.build
				if not containerfile.exists():
					pen.issue(Severity.ERROR, "challenge-dynamic-build-file-missing", f"Missing container build file for {container_id!r}: {str(containerfile)!r} not found")
					encountered_error = True

		else:
			# warn if dynamic directory exists but not config section
			if (self.path / "dynamic").is_dir():
				pen.issue(Severity.WARNING, "challenge-dynamic-section-missing", "Config does not contain dynamic section but `dynamic` subdirectory exists")


		# TODO: (more) custom validation steps (for warnings and non-strict-schema issues)

		if encountered_error:
			raise ValidationError
