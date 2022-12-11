import io

import anyio
import attrs
from cattrs.preconf.json import make_converter
import httpx

from .models import *


API_TIMEOUT = 10.0


class CTFdAPI:
	"""Interface to the API of an online CTFd instance."""

	@attrs.define
	class _Cache:
		"""Internal typed cache."""
		challenges: dict[int, Challenge] = attrs.field(factory=dict)
		tags: dict[int, ChallengeTags] = attrs.field(factory=dict)
		hints: dict[int, ChallengeHints] = attrs.field(factory=dict)
		flags: dict[int, ChallengeFlags] = attrs.field(factory=dict)
		files: dict[int, ChallengeFiles] = attrs.field(factory=dict)

	# cattrs JSON converter
	converter = make_converter()

	def __init__(self, url: str, api_token: str) -> None:
		self._url = url
		self._token = api_token
		self._cache = self._Cache()

		# store default HTTP headers
		self._headers = {
			# request JSON for responses
			"Accept": "application/json",
			# literally required for API requests to work at all (wtf)
			"Content-Type": "application/json",
			# add API token to all requests
			"Authorization": f"Token {self._token}",
		}

		# create shared HTTP client
		self._client = httpx.AsyncClient(
			http2 = True,
			# set base URL for all requests
			base_url = self._url,
			# configure default timeout for each request
			timeout = API_TIMEOUT,
		)

	async def aclose(self):
		"""Close the underlying HTTP client, cleaning up resources."""
		await self._client.aclose()


	async def get_challenge(self, challenge_id: int) -> Challenge | None:
		"""Get info for a challenge on the live CTFd instance.

		Args:
			challenge_id (int): The ID of the challenge to return info for.

		Returns:
			A Challenge object if the challenge exists, None otherwise.
		"""

		# use cache if available
		try:
			return self._cache.challenges[challenge_id]
		except KeyError:
			pass

		# make the API request
		resp = await self._client.get(f"/api/v1/challenges/{challenge_id}", headers=self._headers)

		# return None if challenge does not exist
		if resp.status_code == 404:
			return None
		# throw an exception for failures
		resp.raise_for_status()

		# parse JSON response
		raw = resp.json()

		# sanity check (if status code is 200, success *should* be True)
		assert raw["success"]

		# structure the data
		structured = self.converter.structure(raw["data"], Challenge)

		# cache + return
		self._cache.challenges[challenge_id] = structured
		return structured

	async def create_challenge(self, challenge: Challenge):
		"""Create a new CTFd challenge.

		Do *not* call this method for existing challenges; use `update_challenge` for that.

		Args:
			challenge (Challenge): The data to apply to the live CTFd instance.
		"""

		# drop cache entry if it exists
		self._cache.challenges.pop(challenge.id, None)

		# make the API request
		resp = await self._client.post(f"/api/v1/challenges", json=self.converter.unstructure(challenge), headers=self._headers)

		# throw an exception for failures
		resp.raise_for_status()
		assert resp.json()["success"]  # if status code == 200, success *should* be True

	async def delete_challenge(self, challenge_id: int):
		"""Delete an existing CTFd challenge.

		Args:
			challenge_id (int): The ID of the challenge to delete.
		"""

		# drop cache entry if it exists
		self._cache.challenges.pop(challenge_id, None)

		# make the API request
		resp = await self._client.delete(f"/api/v1/challenges/{challenge_id}", headers=self._headers)
		# throw an exception for failures
		resp.raise_for_status()

	async def update_challenge(self, challenge: Challenge, dry_run: bool = False):
		"""Update an existing CTFd challenge.

		Do *not* call this method for new challenges; use `create_challenge` for that.

		Args:
			challenge (Challenge): The data to apply to the live CTFd instance.
			dry_run (bool): If True, skip making any changes.

		Returns:
			True if changes were / would be made, False otherwise.
		"""

		# get pre-existing challenge
		initial_chal = await self.get_challenge(challenge.id)

		# set target challenge visibility to match existing challenge
		if initial_chal is not None:
			challenge.state = initial_chal.state

		# determine if we need to change anything
		if challenge == initial_chal:
			# no changes required
			return False
		elif dry_run:
			# this is a dry-run, skip making changes
			return True

		# drop cache entry if it exists
		self._cache.challenges.pop(challenge.id, None)

		# make the API request
		resp = await self._client.patch(f"/api/v1/challenges/{challenge.id}", json=self.converter.unstructure(challenge), headers=self._headers)

		# throw an exception for failures
		resp.raise_for_status()
		assert resp.json()["success"]  # if status code == 200, success *should* be True

		return True


	async def get_tags(self, challenge_id: int) -> ChallengeTags:
		"""Get tags of an existing CTFd challenge.

		Args:
			challenge_id (int): The ID of the challenge to return info for.
		"""

		# use cache if available
		try:
			return self._cache.tags[challenge_id]
		except KeyError:
			pass

		# make the API request
		resp = await self._client.get(f"/api/v1/challenges/{challenge_id}/tags", headers=self._headers)
		# throw an exception for failures
		resp.raise_for_status()

		# parse JSON response
		raw = resp.json()

		# sanity check (if status code is 200, success *should* be True)
		assert raw["success"]

		# structure the data
		structured = self.converter.structure({"id": challenge_id, "tags": raw["data"]}, ChallengeTags)

		# cache + return
		self._cache.tags[challenge_id] = structured
		return structured

	async def _create_tag(self, challenge_id: int, tag_value: str):
		resp = await self._client.post(f"/api/v1/tags", json={"challenge_id": challenge_id, "value": tag_value}, headers=self._headers)
		resp.raise_for_status()

	async def _delete_tag(self, tag_id: int):
		resp = await self._client.delete(f"/api/v1/tags/{tag_id}", headers=self._headers)
		resp.raise_for_status()

	async def update_tags(self, target_tags: ChallengeTags, dry_run: bool = False) -> bool:
		"""Replace all tags on a challenge with the given tags.

		Args:
			target_tags (ChallengeTags): The challenge tags that should exist.
			dry_run (bool): If True, skip making any changes.

		Returns:
			True if changes were / would be made, False otherwise.
		"""

		# get pre-existing tags
		initial_tags = await self.get_tags(target_tags.id)

		# determine if we need to change anything
		if target_tags.matches_values_of(initial_tags):
			# no changes required
			return False
		elif dry_run:
			# this is a dry-run, skip making changes
			return True

		# drop cache entry if it exists
		self._cache.tags.pop(target_tags.id, None)

		# delete all pre-existing tags (in parallel)
		async with anyio.create_task_group() as tg:
			for tag in initial_tags.tags:
				tg.start_soon(self._delete_tag, tag.id)

		# create target tags (serially, so the order is preserved -_-)
		for tag in target_tags.tags:
			await self._create_tag(target_tags.id, tag.value)

		return True


	async def get_hints(self, challenge_id: int) -> ChallengeHints:
		"""Get hints of an existing CTFd challenge.

		Args:
			challenge_id (int): The ID of the challenge to return info for.
		"""

		# use cache if available
		try:
			return self._cache.hints[challenge_id]
		except KeyError:
			pass

		# make the API request
		resp = await self._client.get(f"/api/v1/challenges/{challenge_id}/hints", headers=self._headers)
		# throw an exception for failures
		resp.raise_for_status()

		# parse JSON response
		raw = resp.json()

		# sanity check (if status code is 200, success *should* be True)
		assert raw["success"]

		# structure the data
		structured = self.converter.structure({"id": challenge_id, "hints": raw["data"]}, ChallengeHints)

		# cache + return
		self._cache.hints[challenge_id] = structured
		return structured

	async def _create_hint(self, challenge_id: int, hint_content: str):
		resp = await self._client.post(f"/api/v1/hints", json={"challenge_id": challenge_id, "content": hint_content}, headers=self._headers)
		resp.raise_for_status()

	async def _delete_hint(self, hint_id: int):
		resp = await self._client.delete(f"/api/v1/hints/{hint_id}", headers=self._headers)
		resp.raise_for_status()

	async def update_hints(self, target_hints: ChallengeHints, dry_run: bool = False) -> bool:
		"""Replace all hints on a challenge with the given hints.

		Args:
			target_hints (ChallengeHints): The challenge hints that should exist.
			dry_run (bool): If True, skip making any changes.

		Returns:
			True if changes were / would be made, False otherwise.
		"""

		# get pre-existing hints
		initial_hints = await self.get_hints(target_hints.id)

		# determine if we need to change anything
		if target_hints.matches_values_of(initial_hints):
			# no changes required
			return False
		elif dry_run:
			# this is a dry-run, skip making changes
			return True

		# drop cache entry if it exists
		self._cache.hints.pop(target_hints.id, None)

		# delete all pre-existing hints (in parallel)
		async with anyio.create_task_group() as tg:
			for hint in initial_hints.hints:
				tg.start_soon(self._delete_hint, hint.id)

		# create target hints (serially, so the order is preserved -_-)
		for hint in target_hints.hints:
			await self._create_hint(target_hints.id, hint.content)

		return True


	async def get_flags(self, challenge_id: int) -> ChallengeFlags:
		"""Get flags of an existing CTFd challenge.

		Args:
			challenge_id (int): The ID of the challenge to return info for.
		"""

		# use cache if available
		try:
			return self._cache.flags[challenge_id]
		except KeyError:
			pass

		# make the API request
		resp = await self._client.get(f"/api/v1/challenges/{challenge_id}/flags", headers=self._headers)
		# throw an exception for failures
		resp.raise_for_status()

		# parse JSON response
		raw = resp.json()

		# sanity check (if status code is 200, success *should* be True)
		assert raw["success"]

		# structure the data
		structured = self.converter.structure({"id": challenge_id, "flags": raw["data"]}, ChallengeFlags)

		# cache + return
		self._cache.flags[challenge_id] = structured
		return structured

	async def _create_flag(self, challenge_id: int, flag_content: str):
		resp = await self._client.post(f"/api/v1/flags", json={"challenge_id": challenge_id, "content": flag_content}, headers=self._headers)
		resp.raise_for_status()

	async def _delete_flag(self, flag_id: int):
		resp = await self._client.delete(f"/api/v1/flags/{flag_id}", headers=self._headers)
		resp.raise_for_status()

	async def update_flags(self, target_flags: ChallengeFlags, dry_run: bool = False) -> bool:
		"""Replace all flags on a challenge with the given flags.

		Args:
			target_flags (ChallengeFlags): The challenge flags that should exist.
			dry_run (bool): If True, skip making any changes.

		Returns:
			True if changes were / would be made, False otherwise.
		"""

		# get pre-existing flags
		initial_flags = await self.get_flags(target_flags.id)

		# determine if we need to change anything
		if target_flags.matches_values_of(initial_flags):
			# no changes required
			return False
		elif dry_run:
			# this is a dry-run, skip making changes
			return True

		# drop cache entry if it exists
		self._cache.flags.pop(target_flags.id, None)

		# delete all pre-existing flags (in parallel)
		async with anyio.create_task_group() as tg:
			for flag in initial_flags.flags:
				tg.start_soon(self._delete_flag, flag.id)

		# create target flags (serially, so the order is preserved -_-)
		for flag in target_flags.flags:
			await self._create_flag(target_flags.id, flag.content)

		return True


	async def get_files(self, challenge_id: int) -> ChallengeFiles:
		"""Get files of an existing CTFd challenge.

		Args:
			challenge_id (int): The ID of the challenge to return info for.
		"""

		# use cache if available
		try:
			return self._cache.files[challenge_id]
		except KeyError:
			pass

		# make the API request
		resp = await self._client.get(f"/api/v1/challenges/{challenge_id}/files", headers=self._headers)
		# throw an exception for failures
		resp.raise_for_status()

		# parse JSON response
		raw = resp.json()

		# sanity check (if status code is 200, success *should* be True)
		assert raw["success"]

		# structure the data
		structured = self.converter.structure({
			"id": challenge_id,
			"files": [{**item, "filename": item['location'].rsplit('/', 1)[-1]} for item in raw["data"]],
		}, ChallengeFiles)

		# cache + return
		self._cache.files[challenge_id] = structured
		return structured

	async def _create_file(self, challenge_id: int, filename: str, content_hash: str, file_data: io.BytesIO):
		resp = await self._client.post(f"/api/v1/files",
			data={
				"type": "challenge",
				"challenge_id": challenge_id,
				"content_label": content_hash,
			},
			files={"file": (filename, file_data)},
			headers={ k : v for k, v in self._headers.items() if k != "Content-Type" },
		)
		resp.raise_for_status()

	async def _delete_file(self, file_id: int):
		resp = await self._client.delete(f"/api/v1/files/{file_id}", headers=self._headers)
		resp.raise_for_status()

	async def update_files(self, target_files: ChallengeFiles, dry_run: bool = False) -> bool:
		"""Replace all files on a challenge with the given files.

		Args:
			target_files (ChallengeFiles): The challenge files that should exist.
			dry_run (bool): If True, skip making any changes.

		Returns:
			True if changes were / would be made, False otherwise.
		"""

		def _file_attributes(files: ChallengeFiles) -> set[tuple[str, str]]:
			return set((file.filename, file.content_label) for file in files.files)

		# get pre-existing files
		initial_files = await self.get_files(target_files.id)

		# determine if we need to add/remove anything
		if _file_attributes(initial_files) == _file_attributes(target_files):
			# no changes required
			return False
		elif dry_run:
			# this is a dry-run, skip making changes
			return True

		# drop cache entry if it exists
		self._cache.flags.pop(target_files.id, None)

		# remove any files that shouldn't exist
		for file_attrs in _file_attributes(initial_files) - _file_attributes(target_files):
			# get file ID
			file_id = None
			for initial_file in initial_files.files:
				if (initial_file.filename, initial_file.content_label) == file_attrs:
					file_id = initial_file.id
					break
			assert file_id is not None

			# delete file
			await self._delete_file(file_id)

		# upload missing files
		for file_attrs in _file_attributes(target_files) - _file_attributes(initial_files):
			# get File object
			file = None
			for tgt_file in target_files.files:
				if (tgt_file.filename, tgt_file.content_label) == file_attrs:
					file = tgt_file
			assert file is not None
			assert file.data is not None

			# upload file
			await self._create_file(target_files.id, file.filename, file.content_label, file.data)

		return True
