from marshmallow import fields, Schema

from . import validate_unique, VALIDATORS_STRING_ID


class ChallengeRepoConfigSchema(Schema):
	"""Marshmallow schema for the challenge repo config file."""

	categories = fields.List(
		fields.String(validate=VALIDATORS_STRING_ID),
		required = True,
		validate = validate_unique,
	)
