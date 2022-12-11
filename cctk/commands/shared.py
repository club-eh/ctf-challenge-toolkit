"""Shared code for parsing, interpreting, validating, etc."""

import enum
from pathlib import Path

import anyio
from rich import box
from rich.console import Group, RenderableType
from rich.padding import Padding
from rich.panel import Panel
from rich.pretty import Pretty
from rich.progress import Progress
from rich.table import Table
from rich.text import Text

from cctk.ctfd import Challenge as RemoteChallenge
from cctk.ctfd import ChallengeFiles, ChallengeFlags, ChallengeHints, ChallengeTags, CTFdAPI
from cctk.rt import CONSOLE
from cctk.sources.challenge import Challenge as LocalChallenge
from cctk.sources.repository import ChallengeRepo
from cctk.types import AppConfig
from cctk.util import challenge_id_hash
from cctk.validation import FatalValidationError, Severity, ValidationBook, ValidationError


class ChallengeChanges(enum.Flag):
	"""Simple representation of the changes required to bring a live challenge in line with its intended state."""

	CREATE_NEW = enum.auto()
	"""Special flag meaning the entire challenge needs to be created."""

	NAME = enum.auto()
	DESCRIPTION = enum.auto()
	CATEGORY = enum.auto()
	POINTS = enum.auto()

	TAGS = enum.auto()
	HINTS = enum.auto()
	FLAGS = enum.auto()
	FILES = enum.auto()


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
			self.challenges: dict[str, LocalChallenge] = dict()

			for challenge_id in challenge_ids:
				try:
					self.challenges[challenge_id] = LocalChallenge(self.repo, book, repo_path / challenge_id, challenge_id)
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


class DeployTarget:
	def __init__(self, api: CTFdAPI, verbose: bool = False):
		self.api = api
		self.verbose = verbose

		self.challenges: dict[str, RemoteChallenge | None] = dict()
		self.tags: dict[str, ChallengeTags | None] = dict()
		self.hints: dict[str, ChallengeHints | None] = dict()
		self.flags: dict[str, ChallengeFlags | None] = dict()
		self.files: dict[str, ChallengeFiles | None] = dict()

	async def get_challenge_info(self, semaphore: anyio.Semaphore, progress: Progress, challenge_id: str):
		"""Retrieve all live challenge information for a specific challenge."""

		cid_hash = challenge_id_hash(challenge_id)

		if self.verbose:
			desc_suffix = f"live challenge data for [{cid_hash}] {challenge_id}"
		else:
			desc_suffix = f"live challenge data for {challenge_id}"

		async with semaphore:
			tid = progress.add_task("Retrieving " + desc_suffix, total=None)

			# base challenge data
			self.challenges[challenge_id] = await self.api.get_challenge(challenge_id_hash(challenge_id))

			# associated data (tags, hints, flags, files)
			if self.challenges[challenge_id] is not None:
				self.tags[challenge_id] = await self.api.get_tags(cid_hash)
				self.hints[challenge_id] = await self.api.get_hints(cid_hash)
				self.flags[challenge_id] = await self.api.get_flags(cid_hash)
				self.files[challenge_id] = await self.api.get_files(cid_hash)
			else:
				self.tags[challenge_id] = None
				self.hints[challenge_id] = None
				self.flags[challenge_id] = None
				self.files[challenge_id] = None

			progress.update(tid, description="Retrieved " + desc_suffix, total=1, completed=1)
			progress.stop_task(tid)

	async def apply_changes_to_challenge(self, semaphore: anyio.Semaphore, progress: Progress, deploy_src: DeploySource, challenge_id: str, changes: ChallengeChanges):
		"""Apply specified changes to the target CTFd instance."""

		cid_hash = challenge_id_hash(challenge_id)

		if self.verbose:
			chal_desc = f"[{cid_hash}] {challenge_id}"
		else:
			chal_desc = challenge_id

		async with semaphore:
			tid = progress.add_task(f"Applying changes to {chal_desc}", total=None)

			src_chal = deploy_src.challenges[challenge_id]
			intended_chal = RemoteChallenge(
				id=cid_hash,
				name=src_chal.config.name,
				description=src_chal.config.description,
				category=src_chal.config.category,
				value=src_chal.config.points,
			)

			if ChallengeChanges.CREATE_NEW in changes:
				progress.update(tid, description=f"Creating new challenge: {chal_desc}")
				# create the entire challenge from scratch
				await self.api.create_challenge(intended_chal)
			else:
				progress.update(tid, description=f"Updating existing challenge: {chal_desc}")
				# update challenge to match intended state
				await self.api.update_challenge(intended_chal)

			# update tags
			progress.update(tid, description=f"Updating tags for {chal_desc}")
			await self.api.update_tags(ChallengeTags(cid_hash, [ChallengeTags.Tag(v) for v in src_chal.get_tag_list()]))

			# update hints
			progress.update(tid, description=f"Updating hints for {chal_desc}")
			await self.api.update_hints(ChallengeHints(cid_hash, [ChallengeHints.Hint(v) for v in src_chal.config.hints]))

			# update flags
			progress.update(tid, description=f"Updating flags for {chal_desc}")
			await self.api.update_flags(ChallengeFlags(cid_hash, [ChallengeFlags.Flag(src_chal.config.flag)]))

			# update files
			progress.update(tid, description=f"Updating files for {chal_desc}")
			await self.api.update_files(ChallengeFiles(cid_hash, [
				ChallengeFiles.File(filename, entry.content_hash, entry.data)
				for filename, entry in src_chal.load_static_files().items()
			]))

			# finalize status message
			progress.update(tid, description=f"Applied changes to {chal_desc}", total=1, completed=1)
			progress.stop_task(tid)


	def compare_against_sources(self, deploy_src: DeploySource) -> dict[str, ChallengeChanges]:
		"""Compare the given live state against the local, intended state.

		Args:
			deploy_src: The DeploySource representing the live CTFd state.

		Returns:
			A dict mapping challenge IDs to `ChallengeChanges` objects describing the differences.
		"""

		changes = dict()

		for cid, tgt_chal in self.challenges.items():
			src_chal = deploy_src.challenges[cid]

			# check if the entire challenge needs to be created
			if tgt_chal is None:
				changes[cid] = ChallengeChanges.CREATE_NEW
				continue

			# create flag object for this challenge
			changes[cid] = ChallengeChanges(0)

			# compare base challenge data
			if tgt_chal.name != src_chal.config.name:
				changes[cid] |= ChallengeChanges.NAME
			if tgt_chal.description != src_chal.config.description:
				changes[cid] |= ChallengeChanges.DESCRIPTION
			if tgt_chal.category != src_chal.config.category:
				changes[cid] |= ChallengeChanges.CATEGORY
			if tgt_chal.value != src_chal.config.points:
				changes[cid] |= ChallengeChanges.POINTS

			# compare challenge tags
			if self.tags[cid].as_str_list() != src_chal.get_tag_list():  # type: ignore[union-attr]
				changes[cid] |= ChallengeChanges.TAGS

			# compare challenge hints
			if self.hints[cid].as_str_list() != src_chal.config.hints:  # type: ignore[union-attr]
				changes[cid] |= ChallengeChanges.HINTS

			# compare challenge flags
			if self.flags[cid].as_str_list() != [src_chal.config.flag]:  # type: ignore[union-attr]
				changes[cid] |= ChallengeChanges.FLAGS

			# compare challenge files
			existing_fileset = set((entry.filename, entry.content_label) for entry in self.files[cid].as_str_set())  # type: ignore[union-attr]
			target_fileset = set((name, entry.content_hash) for name, entry in src_chal.load_static_files().items())
			if existing_fileset != target_fileset:
				changes[cid] |= ChallengeChanges.FILES
			else:
				# drop files from memory (we don't need them anymore)
				src_chal.drop_static_files()
			del existing_fileset, target_fileset

			# remove empty changesets
			if changes[cid] == ChallengeChanges(0):
				del changes[cid]

		return changes

	def rich_change_summary(self, changes: dict[str, ChallengeChanges], table: Table) -> Table:
		"""Fill a table with a summary of all required changes to the live challenges."""

		for header in ["ID", "Changes (green -> create; yellow -> modify)"]:
			table.add_column(header)

		for cid, chal_changes in sorted(changes.items()):
			changelist: list[str | Text] = list()
			for change in ChallengeChanges:
				if change in chal_changes:
					changelist.append({
						ChallengeChanges.CREATE_NEW: Text("Create new challenge", style="changes.create"),
						ChallengeChanges.NAME: Text("Name", style="changes.update"),
						ChallengeChanges.DESCRIPTION: Text("Description", style="changes.update"),
						ChallengeChanges.CATEGORY: Text("Category", style="changes.update"),
						ChallengeChanges.POINTS: Text("Points", style="changes.update"),
						ChallengeChanges.TAGS: Text("Tags", style="changes.update"),
						ChallengeChanges.HINTS: Text("Hints", style="changes.update"),
						ChallengeChanges.FLAGS: Text("Flags", style="changes.update"),
						ChallengeChanges.FILES: Text("Files", style="changes.update"),
					}[change])
					changelist.append(", ")
			changelist.pop()
			table.add_row(Text(cid, style="green3"), Text.assemble(*changelist))

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
		Panel(Group(*summary_items), title="Validation Summary", expand=False, border_style="cyan"),
	)

	return deploy_source, validation_book
