from __future__ import annotations

import decimal
import functools
import hashlib
import io
from itertools import chain
import os
from pathlib import Path
import tarfile

import attrs
import marshmallow

from cctk import tomllib
from cctk.constants import CHALLENGE_CONFIG_FILENAME
from cctk.schemas.challenge import ChallengeConfigSchema, ChallengeDifficulty
from cctk.schemas.formatting import format_validation_exception
from cctk.sources.repository import ChallengeRepo
from cctk.util.filewalker import FileWalker, MatchlessPatternWarning, RedundantPatternWarning
from cctk.validation import Severity, Source, ValidationBook, ValidationBoundPen, ValidationError


@attrs.define(frozen=True)
class StaticConfig:
	# whether to archive all files into a tarball (defaults to true)
	# ignored if only one file exists
	make_archive: bool = True
	# list of glob patterns to include
	include_patterns: list[str] = attrs.field(factory=list)
	# list of glob patterns to exclude
	exclude_patterns: list[str] = attrs.field(factory=list)
	# list of prefixes to remove from paths
	rm_prefixes: list[str] = attrs.field(factory=list)


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
	flags: list[str]
	hints: list[str]

	static: StaticConfig
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

		# rebuild dictionary to match constructor parameters
		final_data = {
			"id": clean_meta["id"],
			"category": clean_meta["category"],
			"difficulty": clean_meta["difficulty"],
			"tags": clean_meta["tags"],

			# collapse list of hint structures
			"hints": [hint["content"] for hint in cleaned_data.get("hints", [])],

			# construct StaticConfig object
			"static": StaticConfig(**cleaned_data.get("static", {})),

			# construct ContainerConfig objects for dynamic sections (if provided)
			"dynamic": None if cleaned_data.get("dynamic") is None else
				{ cid : ContainerConfig(id=cid, **cconfig) for cid, cconfig in cleaned_data["dynamic"].items() },
		}

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

		if "flag" in clean_meta and len(clean_meta["flags"]):
			pen.issue(Severity.ERROR, "challenge-config-flag-mutex",
				"Challenge config specified both 'flag' and 'flags' mutually-exclusive fields")
			raise ValidationError
		elif "flag" in clean_meta:
			final_data["flags"] = [clean_meta["flag"]]
		elif len(clean_meta["flags"]):
			final_data["flags"] = clean_meta["flags"]
		else:
			pen.warn("challenge-config-missing-flag", "Challenge config does not specify any flags")
			final_data["flags"] = []

		# build + return the object
		return cls(**final_data)


@attrs.define()
class StaticFileEntry:
	content_hash: str
	data: io.BytesIO


@functools.total_ordering
class Challenge:
	"""Interface to a challenge directory."""

	def __repr__(self) -> str:
		return f"<Challenge id={self.challenge_id!r} config={self.config!r}>"

	def __lt__(self, other: "Challenge") -> bool:
		"""Comparison operator, implemented for sorting.

		Sorts first by category, then by difficulty, then by ID.
		"""

		if self.config.category < other.config.category:
			return True
		elif self.config.category > other.config.category:
			return False
		elif self.config.difficulty < other.config.difficulty:
			return True
		elif self.config.difficulty > other.config.difficulty:
			return False
		else:
			return self.config.id < other.config.id

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

		# init caches
		self._static_files: dict[str, StaticFileEntry] | None = None


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

		if self.config.static is not None:
			# error on invalid static patterns
			for pattern in chain(self.config.static.include_patterns, self.config.static.exclude_patterns):
				if pattern.startswith("/"):
					pen.issue(Severity.ERROR, "challenge-static-pattern-absolute", f"Config contains absolute static pattern (cannot start with '/'): {pattern!r}")
					encountered_error = True
				elif pattern.endswith("/"):
					pen.issue(Severity.ERROR, "challenge-static-pattern-dironly", f"Config contains invalid static pattern (cannot end with '/'): {pattern!r}")
					encountered_error = True

			# validate static files
			if self._get_matched_static_files(pen)[1]:
				encountered_error = True


		# TODO: (more) custom validation steps (for warnings and non-strict-schema issues)

		if encountered_error:
			raise ValidationError

	def _get_matched_static_files(self, pen: ValidationBoundPen | None = None) -> tuple[list[Path], bool]:
		"""
		Apply the static include and exclude patterns to the challenge directory, and return all matching filepaths.

		Also checks for validation issues, reported to the given pen (optional).

		Args:
			pen (optional): The ValidationBoundPen to report validation issues to.

		Returns:
			list[Path]: A list of all matched filepaths.
			bool: True if a validation error occurred, False otherwise.
		"""

		# use cached FileWalker if available, create one otherwise
		self._static_fw: FileWalker
		try:
			fw = self._static_fw
		except AttributeError:
			fw = self._static_fw = FileWalker(
				self.path,
				self.config.static.include_patterns,
				self.config.static.exclude_patterns,
			)

		results, warnings = fw.walk_with_warnings()

		if pen is not None:
			for warning in warnings:
				match warning:
					case MatchlessPatternWarning(type="include", pattern=pattern):
						pen.warn("challenge-static-include-matchless",
							f"Static include pattern did not match anything: {pattern!r}")
					case RedundantPatternWarning(type=type, pattern=pattern):
						pen.warn("challenge-static-pattern-redundant",
							f"Static {type} pattern is redundant: {pattern!r}")
					case _:
						raise Exception(f"Unknown FileWalkerWarning: {warning!r}")

		return results, False

	def _get_all_static_files(self) -> list[Path]:
		"""
		Return paths of all static files.

		Includes files from:
		- `include_patterns` + `exclude_patterns` (without `rm_prefixes` applied)
		- `<challenge dir>/static`

		Returns:
			list[Path]: A list of all static filepaths (relative to challenge directory).
		"""

		self._static_file_list: list[Path]
		try:
			return self._static_file_list
		except AttributeError:
			pass

		# get pattern-matched paths
		pattern_paths, _ = self._get_matched_static_files()

		# get files from `static/`
		static_paths: list[Path] = list()
		for dirpath, _dirnames, filenames in os.walk(self.path / "static"):
			static_paths.extend((Path(dirpath) / filename for filename in filenames))

		# store combined list in cache
		self._static_file_list = pattern_paths + static_paths

		# strip prefixes (make paths relative to challenge directory)
		self._static_file_list = [abs_path.relative_to(self.path) for abs_path in self._static_file_list]

		# sort to maintain determinism
		self._static_file_list.sort()

		# return results
		return self._static_file_list

	def get_tag_list(self) -> list[str]:
		"""Return the list of actual CTFd tags (including auto-added tags)."""

		return [self.config.difficulty.as_tag(), *self.config.tags]

	def load_static_files(self) -> dict[str, StaticFileEntry]:
		"""Loads all static files into memory.

		If required, files will be packed into an archive.

		Returns:
			A dictionary of filenames to file entries.
		"""

		# return cache if available
		if self._static_files is not None:
			return self._static_files

		# determine whether we want to upload an archive of the files
		if len(self._get_all_static_files()) > 1:
			make_archive = self.config.static.make_archive
		else:
			make_archive = False

		# last-ditch effort to prevent insanity
		if not make_archive and len(self._get_all_static_files()) > 25:
			raise AssertionError("cowardly refusing to upload over 25 individual files!")

		# initialize in-memory file dict
		file_contents: dict[str, io.BytesIO] = dict()

		if make_archive:
			# create raw in-memory file
			archive_buf = io.BytesIO()
			# create TarFile
			archive = tarfile.open(fileobj=archive_buf, mode='w')

			# define TarInfo filter
			def filter_tarinfo(info: tarfile.TarInfo) -> tarfile.TarInfo:
				# clear unneeded information
				info.uid = 0
				info.gid = 0
				info.uname = ""
				info.gname = ""
				info.mtime = 0
				info.pax_headers = dict()

				# remove prefixes from filepath (uses the shortest resulting filepath)
				final_name = info.name
				for prefix in [*self.config.static.rm_prefixes, "static"]:
					candidate_name = info.name.removeprefix(prefix).removeprefix("/")
					if len(candidate_name) < len(final_name):
						final_name = candidate_name
				info.name = final_name

				return info

			# add files
			for filepath in self._get_all_static_files():
				archive.add(self.path / filepath, filepath, recursive=False, filter=filter_tarinfo)

			# finalize the archive
			archive.close()

			# add archive to file list
			file_contents[f"{self.challenge_id}.tar"] = archive_buf
		else:
			# read files into memory
			for filepath in self._get_all_static_files():
				file_contents[filepath.name] = io.BytesIO((self.path / filepath).read_bytes())

		# generate hashes + pack into final dict
		results = {
			filename : StaticFileEntry(
				content_hash=hashlib.sha256(data.getbuffer()).hexdigest(),
				data=data,
			)
			for filename, data in file_contents.items()
		}

		# cache + return
		self._static_files = results
		return self._static_files

	def drop_static_files(self):
		"""Drop cached static files from memory."""
		self._static_files = None

	@functools.cache
	def get_dynamic_scoring_params(self, repo: ChallengeRepo) -> dict[str, int]:
		"""Returns the dynamic scoring parameters for this challenge (`initial`, `final`, and `decay`).

		All values are derived from this challenge's difficulty and the repo scoring configuration.
		"""

		return {
			"initial": repo.config.scoring.initial[self.config.difficulty.value],
			"final": repo.config.scoring.final[self.config.difficulty.value],
			"decay": repo.config.scoring.decay[self.config.difficulty.value] * repo.config.scoring.expected_player_count,
		}
