"""Utilities for formatting Marshmallow validation exceptions."""

from typing import Any

from io import StringIO

from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.pretty import Pretty
from rich.text import Text


def collapse_to_dotted(messages: dict[str, Any]) -> dict[str, str | list[str]]:
	"""Recursively collapses a nested dictionary into a single dictionary of key-value pairs (adding dots as separators)."""

	def _collapse_layer(dict_in: dict[str, Any], dict_out: dict[str, Any], prefix: str):
		for key, val in dict_in.items():
			if isinstance(val, dict):
				_collapse_layer(val, dict_out, f"{prefix}{key}.")
			else:
				dict_out[prefix + str(key)] = val

	out: dict[str, Any] = dict()
	_collapse_layer(messages, out, "")
	return out


def format_validation_exception_old(messages: list[str] | dict[str, str | list[str]]) -> RenderableType:
	"""Format Marshmallow validation error messages into a rich console renderable."""
	sio = StringIO()
	if isinstance(messages, dict):
		for err_key, err_msg in messages.items():
			if isinstance(err_msg, list):
				sio.write(f"{err_key}: {err_msg}\n")
			else:
				sio.write(f"{err_key}: {err_msg}\n")
	else:
		for err_msg in messages:
			sio.write(f"{err_msg}\n")

	# return built string without the trailing newline
	return sio.getvalue()[:-1]


def format_validation_exception(messages: list[str] | dict[str, str | list[str]], title: str) -> RenderableType:
	"""Format Marshmallow validation error messages into a rich console renderable."""

	STYLE_ERR_KEY = "cyan3"
	STYLE_ERR_MSG = "yellow3"

	items: list[RenderableType] = list()

	if isinstance(messages, dict):
		for err_key, err_msg in sorted(collapse_to_dotted(messages).items()):
			t = Text.assemble(
				(err_key, STYLE_ERR_KEY),
				": ",
				Text(str(err_msg)),
			)
			t.highlight_regex("'.+?'", STYLE_ERR_MSG)
			items.append(t)
	else:
		for err_msg in messages:
			items.append(Pretty(err_msg))

	return Group(title, Padding(Group(*items), (0,0,0,2)))
