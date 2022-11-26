import anyio
import attrs
from cattrs.preconf.json import make_converter
import httpx

from .models import *


API_TIMEOUT = 3.0


class CTFdAPI:
	"""Interface to the API of an online CTFd instance."""

	@attrs.define
	class _Cache:
		"""Internal typed cache."""
		challenges: dict[int, Challenge] = attrs.field(factory=dict)
		tags: dict[int, ChallengeTags] = attrs.field(factory=dict)

	# cattrs JSON converter
	converter = make_converter()

	def __init__(self, url: str, api_token: str) -> None:
		self._url = url
		self._token = api_token
		self._cache = self._Cache()

		# create shared HTTP client
		self._client = httpx.AsyncClient(
			http2 = True,
			# set base URL for all requests
			base_url = self._url,
			headers = {
				# request JSON for responses
				"Accept": "application/json",
				# literally required for API requests to work at all (wtf)
				"Content-Type": "application/json",
				# add API token to all requests
				"Authorization": f"Token {self._token}",
			},
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
		resp = await self._client.get(f"/api/v1/challenges/{challenge_id}")

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
		resp = await self._client.post(f"/api/v1/challenges", json=self.converter.unstructure(challenge))

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
		resp = await self._client.delete(f"/api/v1/challenges/{challenge_id}")
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
		resp = await self._client.patch(f"/api/v1/challenges/{challenge.id}", json=self.converter.unstructure(challenge))

		# throw an exception for failures
		resp.raise_for_status()
		assert resp.json()["success"]  # if status code == 200, success *should* be True

		return True


	async def get_tags(self, challenge_id: int) -> ChallengeTags:
		"""Get tags for an existing CTFd challenge.

		Args:
			challenge_id (int): The ID of the challenge to return info for.
		"""

		# use cache if available
		try:
			return self._cache.tags[challenge_id]
		except KeyError:
			pass

		# make the API request
		resp = await self._client.get(f"/api/v1/challenges/{challenge_id}/tags")
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
		resp = await self._client.post(f"/api/v1/tags", json={"challenge_id": challenge_id, "value": tag_value})
		resp.raise_for_status()

	async def _delete_tag(self, tag_id: int):
		resp = await self._client.delete(f"/api/v1/tags/{tag_id}")
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
