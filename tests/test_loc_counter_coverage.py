"""Coverage-targeted unit tests for core/services/shared/loc_counter.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.services.shared.loc_counter import count_source_lines


def test_count_source_lines_basic(tmp_path: Path):
    file1 = tmp_path / "mod1.py"
    file1.write_text("a = 1\n\nb = 2\n", encoding="utf-8")
    loc = count_source_lines(tmp_path)
    assert loc == 2


def test_count_source_lines_relative_to_value_error(tmp_path: Path):
    file1 = tmp_path / "mod1.py"
    file1.write_text("a = 1\n", encoding="utf-8")

    orig_relative_to = Path.relative_to

    def faulty_relative_to(self, other, *args, **kwargs):
        if self.name == "mod1.py":
            raise ValueError("Forced error")
        return orig_relative_to(self, other, *args, **kwargs)

    with patch.object(Path, "relative_to", faulty_relative_to):
        loc = count_source_lines(tmp_path)
        # Even with ValueError on relative_to, rel falls back to p and still counts
        assert loc == 1


def test_count_source_lines_file_read_exception(tmp_path: Path):
    file1 = tmp_path / "unreadable.py"
    file1.write_text("x = 10\n", encoding="utf-8")

    orig_open = Path.open

    def faulty_open(self, *args, **kwargs):
        if self.name == "unreadable.py":
            raise PermissionError("Denied")
        return orig_open(self, *args, **kwargs)

    with patch.object(Path, "open", faulty_open):
        loc = count_source_lines(tmp_path)
        assert loc == 0


def test_count_source_lines_outer_exception():
    faulty_path = MagicMock(spec=Path)
    faulty_path.rglob.side_effect = RuntimeError("Directory scan failure")
    loc = count_source_lines(faulty_path)
    assert loc == 0
