from marshmallow import fields, Schema, validate

from . import validate_unique, VALIDATORS_STRING_ID


class ChallengeRepoConfigScoring(Schema):
	"""Marshmallow schema for the [scoring] section of the challenge repo config."""

	expected_player_count = fields.Integer(required=True, strict=True)

	# TODO: proper validation of difficulty keys
	initial = fields.Dict(keys=fields.String(), values=fields.Integer(strict=True), required=True)
	final = fields.Dict(keys=fields.String(), values=fields.Integer(strict=True), required=True)
	decay = fields.Dict(keys=fields.String(), values=fields.Float(validate=validate.Range(0, 1)), required=True)


class ChallengeRepoConfigSchema(Schema):
	"""Marshmallow schema for the challenge repo config file."""

	categories = fields.List(
		fields.String(validate=VALIDATORS_STRING_ID),
		required = True,
		validate = validate_unique,
	)

	scoring = fields.Nested(ChallengeRepoConfigScoring, required=True)

	url = fields.String(required=False, load_default=None, validate=validate.URL(schemes=["http", "https"]))
