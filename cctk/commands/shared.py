"""Shared code for parsing / interpreting / validating."""

from pathlib import Path

from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text

from cctk.rt import CONSOLE
from cctk.sources.challenge import Challenge
from cctk.sources.repository import ChallengeRepo
from cctk.validation import Severity, ValidationBook, ValidationError


class DeploySource:
	"""Represents the local sources used for a deployment."""

	def __init__(self, book: ValidationBook, repo_path: Path, challenge_ids: list[str] | None = None, verbose: bool = False):
		"""Initialize a new DeploySource instance.

		Performs validation on loaded data.

		Args:
			repo_path: Local path to the challenge repository.
			challenge_ids (optional): A tuple of challenge IDs to deploy. If None, all challenges found in the repository will be selected for deployment.
		"""

		# initialize object attributes
		self._book = book
		self._repo_path = repo_path
		self._challenge_ids = challenge_ids
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
			challenge_ids = list(self.repo.find_challenges())
			CONSOLE.print(f"Found {len(challenge_ids)} challenges in the repository")
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


	def rich_repo_summary(self, table: Table) -> Table:
		"""Fill a table with information about the loaded challenge repository."""

		table.add_row("Challenge Categories: ", Pretty(self.repo.categories))

		return table

	def rich_challenge_summary(self, table: Table) -> Table:
		"""Fill a table with a summary of all loaded challenges."""

		for header in ["ID", "Difficulty", "Category", "Name", "Tags"]:
			table.add_column(header)

		for challenge in self.challenges.values():
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
