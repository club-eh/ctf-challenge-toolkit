from typing import Literal

from pathlib import Path


class FileWalkerWarning:
	"""The base class that all FileWalker warnings inherit from."""
	__slots__ = (
		"type",
		"pattern",
	)

	def __init__(self, type: Literal["include", "exclude"], pattern: str):
		self.type = type
		self.pattern = pattern

class RedundantPatternWarning(FileWalkerWarning):
	"""Returned when a pattern is completely redundant (other patterns match every file that this pattern matches)"""

class MatchlessPatternWarning(FileWalkerWarning):
	"""Returned when a pattern doesn't match any files"""


class FileWalker:
	"""
	Walks through all descendants of a root directory, returning files that match any include pattern,
	but skipping those that match any exclude pattern.
	"""

	__slots__ = (
		"root",
		"include_patterns",
		"exclude_patterns",
		"_results",
		"_warnings",
	)

	def __init__(self, root: Path, include_patterns: list[str], exclude_patterns: list[str]):
		"""Build a new FileWalker with the given arguments.

		Args:
			root: The root directory to walk through. All files returned will be children of this path.
			include_patterns: A list of literal file paths and/or glob patterns to include, relative to the `root` directory.
			exclude_patterns: A list of literal file paths and/or glob patterns to exclude, relative to the `root` directory.
			Takes precedence over `include_patterns`.
		"""

		self.root = root
		self.include_patterns = include_patterns
		self.exclude_patterns = exclude_patterns

		self._results: list[Path] | None = None
		self._warnings: list[FileWalkerWarning] = list()

	def walk_with_warnings(self) -> tuple[list[Path], list[FileWalkerWarning]]:
		"""Walks through the filesystem, matching files as defined by the include and exclude patterns.
		See the class documentation for more details.

		Returns:
			list[Path]: A list of all resulting file paths.
			list[FileWalkerWarning]: A list of all warnings encountered during the walk.
		"""

		# return cached results if available
		if self._results is not None:
			return self._results, self._warnings

		# sanity check
		if not self.root.exists():
			raise FileNotFoundError("Root directory does not exist: '{}'")

		results: set[Path] = set()

		# process include patterns
		for pattern in self.include_patterns:
			matches = set(self.root.glob(pattern))

			if len(matches) == 0:
				self._warnings.append(MatchlessPatternWarning("include", pattern))
				continue

			prev_len = len(results)
			results.update(matches)

			if prev_len == len(results):
				self._warnings.append(RedundantPatternWarning("include", pattern))

		# process literal exclude patterns
		for pattern in self.exclude_patterns:
			literal_path = self.root / pattern
			if not literal_path.exists():
				# not a literal path, skip
				continue

			# expand all ancestor directories (down the tree)
			for ancestor in reversed(literal_path.parents):
				if ancestor in results:
					# remove ancestor
					results.remove(ancestor)
					# add ancestor's children
					results.update(ancestor.iterdir())

			# remove exact match if present
			if literal_path in results:
				results.remove(self.root / pattern)

		# expand all remaining paths
		for path in results.copy():
			if path.is_dir():
				results.update(p for p in path.glob("**/*") if p.is_file())
				results.remove(path)

		# TODO: apply glob exclude patterns

		# return results
		self._results = list(results)

		return self._results, self._warnings
