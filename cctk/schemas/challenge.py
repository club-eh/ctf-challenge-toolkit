import enum

from marshmallow import fields, Schema

from . import VALIDATORS_STRING_ID


class ChallengeDifficulty(enum.Enum):
	UNDEFINED = "undefined"
	EASY = "easy"
	MEDIUM = "medium"
	HARD = "hard"


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


class ChallengeConfigSchema(Schema):
	"""Marshmallow schema for the challenge config file."""

	meta = fields.Nested(ChallengeConfigMeta, required=True)
	scoring = fields.Nested(ChallengeConfigScoring, required=True)
	hints = fields.List(fields.Nested(ChallengeConfigHint), required=False)
