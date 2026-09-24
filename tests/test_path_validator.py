"""Tests for path traversal and audit target validation."""

from pathlib import Path

import pytest

from core.utils.path_validator import validate_audit_path


class TestValidateAuditPath:
    """Tests for validate_audit_path()."""

    def test_valid_temp_directory(self, tmp_path: Path) -> None:
        """A real directory should resolve and be returned cleanly."""
        result = validate_audit_path(str(tmp_path))
        assert result == tmp_path.resolve()
        assert result.is_dir()

    def test_nonexistent_path_raises(self, tmp_path: Path) -> None:
        """A path that doesn't exist should raise ValueError."""
        with pytest.raises(ValueError, match="bulunamadı"):
            validate_audit_path(str(tmp_path / "does_not_exist"))

    def test_file_path_raises(self, tmp_path: Path) -> None:
        """Passing a file instead of a directory should raise ValueError."""
        f = tmp_path / "file.py"
        f.write_text("x = 1")
        with pytest.raises(ValueError, match="dizin olmalıdır"):
            validate_audit_path(str(f))

    @pytest.mark.parametrize("forbidden_path", [
        "/etc",
        "/etc/passwd",
        "/proc",
        "/sys",
        "/dev",
        "/root",
        "/boot",
        "/lib",
    ])
    def test_forbidden_paths_raise(self, forbidden_path: str) -> None:
        """System directories should always be rejected."""
        with pytest.raises(ValueError, match="yasaklı"):
            validate_audit_path(forbidden_path)

    def test_non_git_repo_warns_but_does_not_raise(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Non-git directories should produce a warning but not raise."""
        import logging
        with caplog.at_level(logging.WARNING):
            result = validate_audit_path(str(tmp_path))
        assert result == tmp_path.resolve()
        assert "Git deposu değil" in caplog.text

    def test_git_repo_no_warning(self, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
        """Directories with a .git folder should not produce warnings."""
        (tmp_path / ".git").mkdir()
        import logging
        with caplog.at_level(logging.WARNING):
            result = validate_audit_path(str(tmp_path))
        assert result == tmp_path.resolve()
        assert "Git deposu değil" not in caplog.text

    def test_relative_path_resolved(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Relative paths should be resolved to absolute before validation."""
        monkeypatch.chdir(tmp_path.parent)
        result = validate_audit_path(tmp_path.name)
        assert result.is_absolute()
