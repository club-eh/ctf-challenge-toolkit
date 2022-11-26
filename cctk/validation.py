"""Validation of local sources"""

from __future__ import annotations

import enum
from itertools import chain
from pathlib import Path

import attrs
from rich.columns import Columns
from rich.console import RenderableType
from rich.table import Table
from rich.text import Text

from cctk.rt import CONSOLE


class ValidationError(Exception):
	"""Exception raised when a validation error occurs (should be caught by validation caller)."""

class FatalValidationError(ValidationError):
	"""Exception raised when a fatal validation error occurs."""

class Severity(enum.IntEnum):
	"""Represents the severity of a validation issue."""
	FATAL = 50
	ERROR = 40
	WARNING = 30
	NOTICE = 25

	def as_string(self) -> str:
		return self.name.lower()

@attrs.define
class Source:
	"""Metadata regarding the source of an error."""
	path: Path
	line: int | None = None
	col: int | None = None

	def __str__(self) -> str:
		# TODO: rich formatting? (unless line/col is never used)
		if self.line is None:
			return str(self.path)
		elif self.col is None:
			return f"{str(self.path)}:{self.line}"
		else:
			return f"{str(self.path)}:{self.line}:{self.col}"

@attrs.define(frozen=True)
class Issue:
	severity: Severity
	challenge_id: str | None
	source: Source
	code: str
	message: RenderableType


class ValidationBook:
	"""Handles recording and reporting of validation issues."""

	TEXT_ISSUE_PREFIXES = {
		Severity.FATAL: Text("Fatal validation error", "validation.issue.fatal"),
		Severity.ERROR: Text("Validation error", "validation.issue.error"),
		Severity.WARNING: Text("Validation warning", "validation.issue.warning"),
		Severity.NOTICE: Text("Validation notice", "validation.issue.notice"),
	}
	TEXT_TARGET_REPO = Text("challenge repository", "validation.target")


	def __init__(self):
		self._issues: dict[str | None, list[Issue]] = dict()

	def _record_issue(self, issue: Issue):
		try:
			self._issues[issue.challenge_id].append(issue)
		except KeyError:
			self._issues[issue.challenge_id] = [issue]

	def _display_issue(self, issue: Issue):
		"""Display the validation issue to the user."""

		issue_prefix = self.TEXT_ISSUE_PREFIXES[issue.severity]

		if issue.challenge_id is None:
			validation_target = self.TEXT_TARGET_REPO
		else:
			validation_target = Text.assemble("challenge ", (f"{issue.challenge_id}", "validation.target"))

		issue_location = Text.assemble("[location: ", Text(f"{issue.source}", "validation.location"), "]")
		issue_location.stylize("dim")

		CONSOLE.print(
			# display issue header
			Text.assemble(issue_prefix, " from ", validation_target, " ", issue_location),
			# display specific message (indented with "arrow")
			Columns([" └─ ", issue.message], padding=0),
		)

	def bind(self, challenge_id: str | None, source: Source) -> ValidationBoundPen:
		return ValidationBoundPen(self, challenge_id, source)

	def issue(self, severity: Severity, challenge_id: str | None, source: Source, code: str, message: RenderableType):
		"""Raise a validation issue.

		Args:
			severity: The severity of the validation issue.
			challenge_id: The challenge ID of the challenge (or None if this issue applies to the challenge repo itself).
			location: A string detailing the source of the issue.
			code: A short kebab-case ID for this specific validation issue.
			message: A human-friendly description of the validation issue.
		"""

		issue = Issue(severity, challenge_id, source, code, message)

		# record the issue
		self._record_issue(issue)
		
		# display to user
		self._display_issue(issue)

		# raise exception on fatal issues
		if severity == Severity.FATAL:
			raise FatalValidationError

	def get_issues(self, challenge_id: str | None = None) -> list[Issue]:
		"""Return a list of all issues raised for the given challenge (or for all challenges if None)."""

		if challenge_id is None:
			return list(chain.from_iterable(self._issues.values()))
		else:
			return list(self._issues.get(challenge_id, []))

	def rich_issue_summary(self, table: Table) -> Table | Text:
		"""Generate a rich text summary of all recorded issues (or an "all clear" if no issues were found)."""

		if len(self._issues) == 0:
			return Text("No validation issues have occurred.", style="green3")

		ISSUE_COUNT_SEPARATOR = Text(", ")

		# sort challenges according to highest severity issues
		challenge_issues: dict[Severity, dict[str, list[Issue]]] = { s : dict() for s in Severity }
		for challenge_id, issues in self._issues.items():
			if challenge_id is None:
				continue

			max_severity = Severity.NOTICE
			for issue in issues:
				if issue.severity > max_severity:
					max_severity = issue.severity

			challenge_issues[max_severity][challenge_id] = issues

		table.add_column("Challenge ID", ratio=2)
		table.add_column("Issues", ratio=5)

		for max_severity, severity_challenges in sorted(challenge_issues.items(), reverse=True):
			for challenge_id, issues in sorted(severity_challenges.items()):
				issue_count_strings = []
				for severity in Severity:
					issue_count = len([issue for issue in issues if issue.severity == severity])
					if issue_count > 0:
						issue_count_strings.append(Text(
							f"{issue_count} {severity.name.lower()}",
							style=f"validation.issue.{severity.name.lower()}",
						))
						issue_count_strings.append(ISSUE_COUNT_SEPARATOR)

				table.add_row(
					Text(challenge_id, style=f"validation.issue.{max_severity.name.lower()}"),
					Text.assemble(
						# total issue count
						Text(f"{len(issues)} issue{'s' if len(issues) > 1 else ''}"),
						" (",
						# issue severity breakdown
						*issue_count_strings[:-1],
						")",
					),
				)

		return table

class ValidationBoundPen:
	"""Like a bound logger, but for validation issues."""

	def __init__(self, book: ValidationBook, challenge_id: str | None, source: Source):
		self._book = book
		self.challenge_id = challenge_id
		self.source = source

	def issue(self, severity: Severity, code: str, message: RenderableType):
		"""Raise a validation issue with a bound context.

		Args:
			severity: The severity of the validation issue.
			code: A short kebab-case ID for this specific validation issue.
			message: A human-friendly description of the validation issue.
		"""

		return self._book.issue(severity, self.challenge_id, self.source, code, message)

	def warn(self, code: str, message: RenderableType):
		"""Raise a validation warning with a bound context.

		Args:
			code: A short kebab-case ID for this specific validation issue.
			message: A human-friendly description of the validation issue.
		"""

		return self._book.issue(Severity.WARNING, self.challenge_id, self.source, code, message)
