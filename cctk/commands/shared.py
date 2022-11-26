"""Shared code for parsing, interpreting, validating, etc."""

from pathlib import Path

from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text

from cctk.rt import CONSOLE
from cctk.sources.challenge import Challenge
from cctk.sources.repository import ChallengeRepo
from cctk.types import AppConfig
from cctk.validation import FatalValidationError, Severity, ValidationBook, ValidationError


class DeploySource:
	"""Represents the local sources used for a deployment."""

	def __init__(
		self,
		book: ValidationBook,
		repo_path: Path,
		challenge_ids: list[str] | None = None,
		skip_ids: list[str] = [],
		verbose: bool = False,
	):
		"""Initialize a new DeploySource instance.

		Performs validation on loaded data.

		Args:
			repo_path: Local path to the challenge repository.
			challenge_ids (optional): A tuple of challenge IDs to deploy. If None, all challenges found in the repository will be selected for deployment.
		"""

		# apply skip IDs to provided challenge IDs (if provided)
		challenge_ids = None if challenge_ids is None else [c for c in challenge_ids if c not in skip_ids]

		# initialize object attributes
		self._book = book
		self._repo_path = repo_path
		self._skip_ids = skip_ids
		# holds the IDs of challenges we failed to load
		self._failed_challenges = set()
		# record whether we were given a list of challenges or not
		self._challenges_specified = challenge_ids is not None


		# log location of challenge repo
		CONSOLE.print(f"Using challenge repo at {str(repo_path.resolve(strict=False))}")

		# load + validate challenge repo
		with CONSOLE.status("Validating challenge repository"):
			self.repo = ChallengeRepo(book, repo_path)
		if verbose:
			CONSOLE.print("Done validating challenge repository", style="dim")

		# find challenges if required
		if not self._challenges_specified:
			challenge_ids = list()
			skip_counter = 0
			for cid in self.repo.find_challenges():
				if cid in skip_ids:
					skip_counter += 1
				else:
					challenge_ids.append(cid)
			if skip_counter == 0:
				CONSOLE.print(f"Found {len(challenge_ids)} challenges in the repository")
			else:
				CONSOLE.print(f"Found {len(challenge_ids)} challenges in the repository (skipped {skip_counter})")
		else:
			assert challenge_ids is not None
			CONSOLE.print(f"Validating {len(challenge_ids)} challenge{'s' if len(challenge_ids) > 1 else ''}")
		if verbose:
			CONSOLE.print(f"Challenge IDs: {challenge_ids}", style="dim")

		with CONSOLE.status("Validating challenges") as status:
			# create map to store challenges
			self.challenges: dict[str, Challenge] = dict()

			for challenge_id in challenge_ids:
				try:
					self.challenges[challenge_id] = Challenge(self.repo, book, repo_path / challenge_id, challenge_id)
				except ValidationError:
					# we handle these validation errors later, when deployment checks whether all challenges loaded successfully
					self._failed_challenges.add(challenge_id)

		# store challenge IDs
		self._challenge_ids = challenge_ids


	def rich_repo_summary(self, table: Table) -> Table:
		"""Fill a table with information about the loaded challenge repository."""

		table.add_row("Challenge Categories: ", Pretty(self.repo.categories))

		return table

	def rich_challenge_summary(self, table: Table) -> Table:
		"""Fill a table with a summary of all loaded challenges."""

		for header in ["ID", "Difficulty", "Category", "Name", "Tags"]:
			table.add_column(header)

		for challenge in sorted(self.challenges.values()):
			difficulty = challenge.config.difficulty.value

			highest_issue_severity = Severity.NOTICE
			for issue in self._book.get_issues(challenge.challenge_id):
				if highest_issue_severity < issue.severity:
					highest_issue_severity = issue.severity

			if highest_issue_severity > Severity.NOTICE:
				severity_style = f"validation.issue.{highest_issue_severity.as_string()}"
			else:
				severity_style = "green3"

			table.add_row(
				Text(challenge.challenge_id, style=severity_style),
				Text(difficulty, style=f"challenge.difficulty.{difficulty}"),
				challenge.config.category,
				challenge.config.name,
				str(challenge.config.tags),
				#style = "green3",
			)

		return table


def do_validation(app_cfg: AppConfig, challenges: tuple[str], skip_ids: tuple[str]) -> tuple[DeploySource, ValidationBook]:
	"""Executes user-visible validation, used by both `validate` and `deploy` commands."""

	# handled by command group; assertion is for type checking
	assert app_cfg.repo_path is not None

	# initialize validation book
	validation_book = ValidationBook()

	# load repo and challenge data
	try:
		deploy_source = DeploySource(
			validation_book,
			app_cfg.repo_path,
			list(challenges) if len(challenges) > 0 else None,
			list(skip_ids),
			app_cfg.verbose,
		)
	except (FatalValidationError, ValidationError):
		raise SystemExit(1)

	# generate summary tables
	summary_items: list[RenderableType] = [
		deploy_source.rich_challenge_summary(Table(title=Text.assemble(("Loaded Challenges", "cyan underline"), ""), title_justify="left", box=box.MINIMAL)),
		"",
		validation_book.rich_issue_summary(Table(title=Text.assemble(("Validation Issues", "orange3 underline"), ""), title_justify="left", box=box.MINIMAL)),
	]
	if app_cfg.verbose:
		# add repository info section
		summary_items.insert(0, Text("Repository Config", style="cyan underline"))
		summary_items.insert(1, Padding(deploy_source.rich_repo_summary(Table.grid()), (1, 0, 0, 1)))
		summary_items.insert(2, "")

	# print summary
	CONSOLE.print(
		# newline to separate summary from previous output
		"",
		# panel containing tables
		Panel(Group(*summary_items), title="Summary", expand=False, border_style="cyan"),
	)

	return deploy_source, validation_book
