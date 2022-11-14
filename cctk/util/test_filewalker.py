"""Tests for the filewalker submodule."""

from .filewalker import *


def generate_filetree(tmp_path: Path, directories: list[str], files: list[str]):
	for subpath in directories:
		(tmp_path / subpath).mkdir(parents=True)

	for subpath in files:
		(tmp_path / subpath).parent.mkdir(parents=True, exist_ok=True)
		(tmp_path / subpath).touch()


class TestFileWalker:
	def test_empty(self, tmp_path: Path):
		generate_filetree(tmp_path, [], [])

		results, warnings = FileWalker(tmp_path, ["**/*"], []).walk_with_warnings()

		assert len(results) == 0

		assert len(warnings) == 1
		assert isinstance(warnings[0], MatchlessPatternWarning)

	def test_simple(self, tmp_path: Path):
		generate_filetree(tmp_path, [
			"a/fileless/directory",
			"a/b1/c2/dir",
		], [
			"a/b1/c1/d0",
			"a/b1/c2/d1",
			"a/b2/c1/d2",
			"a/b2/c2/d3",
			"top_level_file1",
			"top_level_file2",
		])

		results, warnings = FileWalker(
			tmp_path,
			include_patterns=[
				"a",
				"top_level_file2",
			],
			exclude_patterns=[
				"a/b1/c1/d0",
				"a/b2/c1/d2",
				"a/b2/c2/non-existent",
			]
		).walk_with_warnings()

		assert sorted(results) == sorted([
			tmp_path / Path("a/b1/c2/d1"),
			tmp_path / Path("a/b2/c2/d3"),
			tmp_path / Path("top_level_file2"),
		])

		assert len(warnings) == 0

