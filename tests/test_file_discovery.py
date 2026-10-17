"""Regression tests for source file discovery.

Guards against filename-based scan evasion: a file must never be skipped
just because of its name (e.g. ``dummy_*.py``), only because of its location
in a well-known non-source directory.
"""

from pathlib import Path

from core.utils.file_discovery import discover_source_files


def test_dummy_prefixed_files_are_not_silently_skipped(tmp_path: Path) -> None:
    evasive = tmp_path / "dummy_payload.py"
    evasive.write_text("exec(input())\n")

    assert evasive in discover_source_files(tmp_path)


def test_dependency_and_cache_dirs_are_excluded(tmp_path: Path) -> None:
    for excluded in ("node_modules", ".venv", "__pycache__", "fixtures"):
        d = tmp_path / excluded
        d.mkdir()
        (d / "mod.py").write_text("x = 1\n")
    kept = tmp_path / "app.py"
    kept.write_text("x = 1\n")

    assert discover_source_files(tmp_path) == [kept]


def test_only_supported_extensions_are_returned(tmp_path: Path) -> None:
    for name in ("a.py", "b.js", "c.ts", "d.md", "e.txt"):
        (tmp_path / name).write_text("")

    found = {p.name for p in discover_source_files(tmp_path)}
    assert found == {"a.py", "b.js", "c.ts"}
