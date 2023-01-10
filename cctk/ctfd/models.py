"""Representations of CTFd API requests and responses."""

import enum
import io

import attrs


class ChallengeState(enum.Enum):
	"""Challenge visibility"""
	HIDDEN = "hidden"
	VISIBLE = "visible"

class ChallengeType(enum.Enum):
	"""Challenge instance type"""
	STANDARD = "standard"
	DYNAMIC = "dynamic"


@attrs.define
class Challenge:
	"""Model for reading/writing base challenges.

	- (read) `GET /challenges/{challenge_id}`
	- (create) `POST /challenges`
	- (update) `PATCH /challenges/{challenge_id}`
	"""

	# Numeric ID (database index)
	id: int
	# Display name
	name: str
	# Challenge category
	category: str
	# Dynamic scoring parameters
	initial: int
	minimum: int
	decay: int
	# Description (Markdown/HTML)
	description: str = ""
	# Player visibility
	state: ChallengeState = ChallengeState.HIDDEN
	# Maximum number of attempts allowed (zero means unlimited)
	max_attempts: int = 0
	# CTFd challenge type
	type: ChallengeType = ChallengeType.DYNAMIC
	# (optional) Connection info to show players
	connection_info: str | None = None
	# (optional) ID of challenge to point players to after solving this challenge
	next_id: int | None = None


@attrs.define
class ChallengeTags:
	"""Model for reading/writing challenge tags.

	- (read) `GET /challenges/{challenge_id}/tags`
	- (create) `POST /tags`
	- (delete) `DELETE /tags/{tag_id}`
	"""

	@attrs.define
	class Tag:
		"""An individual challenge tag."""
		value: str
		id: int | None = None

	# Numeric challenge ID (database index)
	id: int
	# List of tag objects
	tags: list[Tag]

	def as_str_list(self) -> list[str]:
		return list(tag.value for tag in self.tags)

	def matches_values_of(self, other: "ChallengeTags") -> bool:
		"""Checks whether this list of tags matches another list of tags."""
		# compare list length
		if len(self.tags) != len(other.tags):
			return False
		# compare tag values
		for a, b in zip(self.tags, other.tags):
			if a.value != b.value:
				return False
		# no differences found
		return True


@attrs.define
class ChallengeHints:
	"""Model for reading/writing challenge hints.

	- (read) `GET /challenges/{challenge_id}/hints`
	- (create) `POST /hints`
	- (delete) `DELETE /hints/{hint_id}`
	"""

	@attrs.define
	class Hint:
		"""An individual challenge hint."""
		content: str
		id: int | None = None

	# Numeric challenge ID (database index)
	id: int
	# List of hint objects
	hints: list[Hint]

	def as_str_list(self) -> list[str]:
		return list(hint.content for hint in self.hints)

	def matches_values_of(self, other: "ChallengeHints") -> bool:
		"""Checks whether this list of hints matches another list of hints."""
		# compare list length
		if len(self.hints) != len(other.hints):
			return False
		# compare tag values
		for a, b in zip(self.hints, other.hints):
			if a.content != b.content:
				return False
		# no differences found
		return True


@attrs.define
class ChallengeFlags:
	"""Model for reading/writing challenge flags.

	- (read) `GET /challenges/{challenge_id}/flags`
	- (create) `POST /flags`
	- (delete) `DELETE /flags/{flag_id}`
	"""

	@attrs.define
	class Flag:
		"""An individual challenge flag."""
		content: str
		id: int | None = None
		type: str | None = "static"

	# Numeric challenge ID (database index)
	id: int
	# List of flag objects
	flags: list[Flag]

	def as_str_list(self) -> list[str]:
		return list(flag.content for flag in self.flags)

	def matches_values_of(self, other: "ChallengeFlags") -> bool:
		"""Checks whether this list of flags matches another list of flags."""
		# compare list length
		if len(self.flags) != len(other.flags):
			return False
		# compare tag types and values
		for a, b in zip(self.flags, other.flags):
			if a.type != b.type:
				return False
			if a.content != b.content:
				return False
		# no differences found
		return True


@attrs.define
class ChallengeFiles:
	"""Model for reading/writing challenge files.

	- (read) `GET /challenges/{challenge_id}/files`
	- (create) `POST /files`
	- (delete) `DELETE /files/{file_id}`
	"""

	@attrs.define(eq=False)  # eq=False enables hash-by-id
	class File:
		"""An individual challenge file."""
		filename: str
		content_label: str
		data: io.BytesIO | None = None
		id: int | None = None

	# Numeric challenge ID (database index)
	id: int
	# List of file objects
	files: list[File]

	def as_str_set(self) -> set[File]:
		"""Returns a set of the file entries."""
		return set(self.files)
