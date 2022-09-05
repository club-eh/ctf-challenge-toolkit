from marshmallow import fields, Schema, validate

from . import VALIDATORS_STRING_ID


class ChallengeConfigMeta(Schema):
	id = fields.String(required=True, validate=VALIDATORS_STRING_ID)
	name = fields.String(required=False)  # not required for development
	category = fields.String(required=True, validate=VALIDATORS_STRING_ID)
	difficulty = fields.String(required=True, validate=validate.OneOf(["undefined", "easy", "medium", "hard"]))  # 'undefined' is only for development
	description = fields.String(required=False)  # not required for development
	tags = fields.List(fields.String(), required=False, load_default=[])


class ChallengeConfigHint(Schema):
	content = fields.String(required=True)


class ChallengeConfigScoring(Schema):
	flag = fields.String(required=True)
	# NOTE: subject to change (scoring might be determined by difficulty)
	points = fields.Integer(strict=True)


class ChallengeConfigSchema(Schema):
	"""Marshmallow schema for the challenge config file."""

	meta = fields.Nested(ChallengeConfigMeta, required=True)
	scoring = fields.Nested(ChallengeConfigScoring, required=True)
	hints = fields.List(fields.Nested(ChallengeConfigHint), required=False)
