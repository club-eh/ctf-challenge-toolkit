import enum
import functools
from functools import total_ordering

from marshmallow import fields, Schema

from . import VALIDATORS_STRING_ID


@total_ordering
class ChallengeDifficulty(enum.Enum):
	UNDEFINED = "undefined"
	EASY = "easy"
	MEDIUM = "medium"
	HARD = "hard"

	@functools.cache
	def as_tag(self) -> str:
		"""Returns the tag value meant to be displayed to players."""
		return self.value.title()

	def _to_int(self) -> int:
		"""Used for ordering only."""
		return [
			ChallengeDifficulty.UNDEFINED,
			ChallengeDifficulty.EASY,
			ChallengeDifficulty.MEDIUM,
			ChallengeDifficulty.HARD,
		].index(self)

	def __lt__(self, other: "ChallengeDifficulty") -> int:
		return self._to_int() < other._to_int()


class ChallengeConfigMeta(Schema):
	"""Marshmallow schema for the [meta] section of the challenge config."""

	id = fields.String(required=True, validate=VALIDATORS_STRING_ID)
	name = fields.String(required=False)  # not required for development
	category = fields.String(required=True, validate=VALIDATORS_STRING_ID)
	difficulty = fields.Enum(ChallengeDifficulty, by_value=True, required=True)
	description = fields.String(required=False)  # not required for development
	tags = fields.List(fields.String(), required=False, load_default=[])


class ChallengeConfigHint(Schema):
	"""Marshmallow schema for the [[hints]] sections of the challenge config."""

	content = fields.String(required=True)


class ChallengeConfigScoring(Schema):
	"""Marshmallow schema for the [scoring] section of the challenge config."""

	flag = fields.String(required=True)
	# NOTE: subject to change (scoring might be determined by difficulty)
	points = fields.Integer(strict=True)


class ChallengeConfigStatic(Schema):
	"""Marshmallow schema for the [static] section of the challenge config."""

	include_patterns = fields.List(fields.String(), required=False, load_default=[], data_key="include")
	exclude_patterns = fields.List(fields.String(), required=False, load_default=[], data_key="exclude")
	rm_prefixes = fields.List(fields.String(), required=False, load_default=[])


class ChallengeConfigDynamic(Schema):
	"""Marshmallow schema for the [dynamic.*] sections of the challenge config."""

	build = fields.String(required=True)
	ports = fields.Dict(keys=fields.String(validate=VALIDATORS_STRING_ID), values=fields.Integer(), required=True)


class ChallengeConfigSchema(Schema):
	"""Marshmallow schema for the challenge config file."""

	meta = fields.Nested(ChallengeConfigMeta, required=True)
	scoring = fields.Nested(ChallengeConfigScoring, required=True)
	hints = fields.List(fields.Nested(ChallengeConfigHint), required=False)
	static = fields.Nested(ChallengeConfigStatic, required=False)
	dynamic = fields.Dict(keys=fields.String(validate=VALIDATORS_STRING_ID), values=fields.Nested(ChallengeConfigDynamic), required=False)
