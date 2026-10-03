"""Unit tests for CircularDependencyDetector (networkx circular import detector)."""

from __future__ import annotations

from pathlib import Path

from core.services.circular_dependency_detector import (
    CircularDependencyDetector,
    CircularDependencyReport,
)


class TestCircularDependencyDetector:
    """Tests for CircularDependencyDetector."""

    def setup_method(self):
        self.detector = CircularDependencyDetector()

    def test_direct_two_way_circular_dependency(self, tmp_path: Path):
        """Test detecting direct 2-way circular import: a -> b -> a."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        # module a imports module b
        (pkg / "mod_a.py").write_text(
            "from mypkg.mod_b import b_func\n\ndef a_func(): pass\n",
            encoding="utf-8",
        )
        # module b imports module a
        (pkg / "mod_b.py").write_text(
            "from mypkg.mod_a import a_func\n\ndef b_func(): pass\n",
            encoding="utf-8",
        )

        report = self.detector.analyze(tmp_path)
        assert isinstance(report, CircularDependencyReport)
        assert report.has_cycles is True
        assert report.cycles_count >= 1

        cycle = report.cycles[0]
        assert cycle.length == 2
        assert "mod_a" in cycle.cycle_path[0] or "mod_b" in cycle.cycle_path[0]
        assert "Extract shared" in cycle.break_suggestion

        # Mermaid output should highlight circular edge
        assert "```mermaid" in report.mermaid_diagram
        assert "circular" in report.mermaid_diagram

    def test_multi_hop_circular_dependency(self, tmp_path: Path):
        """Test detecting 3-way circular import: a -> b -> c -> a."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        (pkg / "service_a.py").write_text("import mypkg.service_b\n", encoding="utf-8")
        (pkg / "service_b.py").write_text("import mypkg.service_c\n", encoding="utf-8")
        (pkg / "service_c.py").write_text("import mypkg.service_a\n", encoding="utf-8")

        report = self.detector.analyze(tmp_path)
        assert report.has_cycles is True
        assert report.cycles_count >= 1
        assert report.cycles[0].length == 3

    def test_clean_dag_no_cycles(self, tmp_path: Path):
        """Test clean acyclic dependency tree: a -> b -> c (no backward edge)."""
        pkg = tmp_path / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        (pkg / "handler.py").write_text("from mypkg.service import run_service\n", encoding="utf-8")
        (pkg / "service.py").write_text("from mypkg.repository import fetch_data\n", encoding="utf-8")
        (pkg / "repository.py").write_text("def fetch_data(): return []\n", encoding="utf-8")

        report = self.detector.analyze(tmp_path)
        assert report.has_cycles is False
        assert report.cycles_count == 0
        assert "No Circular Dependencies Detected" in report.mermaid_diagram

    def test_relative_imports_resolution(self, tmp_path: Path):
        """Test resolving relative imports (. and ..) in subpackages."""
        pkg = tmp_path / "app"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")

        sub = pkg / "sub"
        sub.mkdir()
        (sub / "__init__.py").write_text("", encoding="utf-8")

        (pkg / "core_mod.py").write_text("from .sub.helper import do_help\n", encoding="utf-8")
        (sub / "helper.py").write_text("from ..core_mod import do_core\n", encoding="utf-8")

        report = self.detector.analyze(tmp_path)
        assert report.has_cycles is True
        assert report.cycles_count >= 1
