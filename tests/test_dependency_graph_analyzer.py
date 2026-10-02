"""Unit tests for DependencyGraphAnalyzer (networkx attack surface and PageRank)."""

from __future__ import annotations

from pathlib import Path

import networkx as nx

from core.services.dependency_graph_analyzer import (
    AttackSurfaceReport,
    DependencyGraphAnalyzer,
)


class TestDependencyGraphAnalyzer:
    """Tests for DependencyGraphAnalyzer."""

    def setup_method(self):
        self.analyzer = DependencyGraphAnalyzer()

    def test_build_graph_from_requirements(self, tmp_path: Path):
        """Test building dependency graph from requirements.txt."""
        req_content = (
            "fastapi==0.110.0\n"
            "uvicorn==0.28.0\n"
            "pydantic==2.8.0\n"
        )
        (tmp_path / "requirements.txt").write_text(req_content, encoding="utf-8")

        G, direct_deps, version_map = self.analyzer.build_graph(tmp_path)
        assert isinstance(G, nx.DiGraph)
        assert "fastapi" in direct_deps
        assert "uvicorn" in direct_deps
        assert "pydantic" in direct_deps

        root_name = tmp_path.name.lower().replace("_", "-")
        assert G.has_node(root_name)
        assert G.has_edge(root_name, "fastapi")

    def test_analyze_attack_surface_metrics(self, tmp_path: Path):
        """Test PageRank and attack surface calculation."""
        # Create a mock uv.lock with dependency chain:
        # root -> web_app -> orm -> core_db
        # root -> worker -> core_db
        uv_lock_content = (
            'version = 1\n'
            '[[package]]\n'
            'name = "core-db"\n'
            'version = "1.0.0"\n\n'
            '[[package]]\n'
            'name = "orm"\n'
            'version = "2.0.0"\n'
            'dependencies = [{ name = "core-db" }]\n\n'
            '[[package]]\n'
            'name = "web-app"\n'
            'version = "0.5.0"\n'
            'dependencies = [{ name = "orm" }]\n\n'
            '[[package]]\n'
            'name = "worker"\n'
            'version = "0.1.0"\n'
            'dependencies = [{ name = "core-db" }]\n'
        )
        (tmp_path / "uv.lock").write_text(uv_lock_content, encoding="utf-8")
        (tmp_path / "requirements.txt").write_text("web-app\nworker\n", encoding="utf-8")

        report = self.analyzer.analyze(tmp_path, top_n=5)
        assert isinstance(report, AttackSurfaceReport)
        assert report.total_packages == 4
        assert report.direct_packages_count == 2
        assert report.transitive_packages_count == 2
        assert len(report.critical_dependencies) > 0

        # core-db is depended upon by orm and worker, so it should have high blast radius
        core_db_node = next(n for n in report.critical_dependencies if n.name == "core-db")
        assert core_db_node.blast_radius >= 2

        # Verify Mermaid diagram generated
        assert "```mermaid" in report.mermaid_diagram
        assert "graph TD" in report.mermaid_diagram

    def test_empty_repository_handling(self, tmp_path: Path):
        """Test that directory with no manifests returns zeroed report gracefully."""
        report = self.analyzer.analyze(tmp_path)
        assert report.total_packages == 0
        assert report.total_edges == 0
        assert report.direct_packages_count == 0
