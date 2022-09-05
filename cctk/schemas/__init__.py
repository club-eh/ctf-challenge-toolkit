"""Contains Marshmallow schemas and supporting code."""

from marshmallow import validate, ValidationError


# common validators for string IDs (lowercase alphanumeric with hyphens and underscores)
VALIDATORS_STRING_ID = [
	# IDs should be at least 2 characters long (assuming a single character cannot convey enough information)
	validate.Length(min=2),
	validate.Regexp(r"^[a-z0-9\-\_]*$", error="Must contain only lowercase alphanumeric characters, hyphens, and underscores."),
]


def validate_unique(data: list):
	"""Marshmallow validator to ensure that a list does not contain duplicate items."""
	if len(set(data)) != len(data):
		raise ValidationError("Items must be unique.")
