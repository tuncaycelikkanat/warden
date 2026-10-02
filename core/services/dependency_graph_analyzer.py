"""Dependency Attack Surface & Criticality Graph Analyzer using NetworkX.

Constructs directed dependency graph models from project manifests and lockfiles
(uv.lock, requirements.txt, pyproject.toml) to evaluate:
- PageRank Centrality: Identifies the most critical and central supply chain packages.
- Blast Radius / Cascading Failure: Computes how many upstream packages and application
  components are compromised if a specific dependency is vulnerable.
- Attack Surface Topology: Direct vs transitive exposure metrics and Mermaid diagrams.
"""

from __future__ import annotations

import logging
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

from core.services.dependency_health import DependencyHealthService

logger = logging.getLogger(__name__)


@dataclass
class DependencyCriticalityNode:
    """Represents a dependency node with graph centrality and attack surface metrics."""

    name: str
    version: str
    pagerank_score: float
    blast_radius: int        # Number of upstream components dependent on this package
    in_degree: int           # How many packages directly depend on this
    out_degree: int          # How many packages this package depends on
    is_direct: bool = False
    criticality_rank: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "pagerank_score": round(self.pagerank_score, 4),
            "blast_radius": self.blast_radius,
            "in_degree": self.in_degree,
            "out_degree": self.out_degree,
            "is_direct": self.is_direct,
            "criticality_rank": self.criticality_rank,
        }


@dataclass
class AttackSurfaceReport:
    """Aggregated attack surface analysis report for the repository."""

    total_packages: int
    direct_packages_count: int
    transitive_packages_count: int
    total_edges: int
    graph_density: float
    critical_dependencies: list[DependencyCriticalityNode] = field(default_factory=list)
    high_blast_radius_nodes: list[DependencyCriticalityNode] = field(default_factory=list)
    mermaid_diagram: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_packages": self.total_packages,
            "direct_packages_count": self.direct_packages_count,
            "transitive_packages_count": self.transitive_packages_count,
            "total_edges": self.total_edges,
            "graph_density": round(self.graph_density, 4),
            "critical_dependencies": [d.to_dict() for d in self.critical_dependencies],
            "high_blast_radius_nodes": [d.to_dict() for d in self.high_blast_radius_nodes],
            "mermaid_diagram": self.mermaid_diagram,
        }


class DependencyGraphAnalyzer:
    """Constructs and analyzes supply-chain dependency graphs using NetworkX."""

    def __init__(self) -> None:
        self._dep_service = DependencyHealthService()

    def build_graph(self, repo_path: Path) -> tuple[nx.DiGraph, set[str], dict[str, str]]:
        """
        Builds a directed dependency graph where edge (A -> B) means package A depends on B.
        Returns: (DiGraph, direct_dependencies_set, version_map)
        """
        repo_path = repo_path.resolve()
        G = nx.DiGraph()
        direct_deps: set[str] = set()
        version_map: dict[str, str] = {}

        # 1. First parse direct manifests to establish direct root dependencies
        manifest_res = self._dep_service._parse_manifest(repo_path)
        for pkg in manifest_res.packages:
            pname = pkg.get("name", "").strip().lower().replace("_", "-")
            if pname:
                direct_deps.add(pname)
                if pkg.get("version"):
                    version_map[pname] = pkg["version"]

        # Also inspect pyproject.toml dependencies if present
        pyproject_path = repo_path / "pyproject.toml"
        if pyproject_path.exists():
            try:
                data = tomllib.loads(pyproject_path.read_text(encoding="utf-8", errors="ignore"))
                project_name = data.get("project", {}).get("name", repo_path.name).lower().replace("_", "-")
                for d in data.get("project", {}).get("dependencies", []):
                    # Extract package name before any version specifier
                    match = d.split(";")[0].split("<")[0].split(">")[0].split("=")[0].split("[")[0].strip().lower().replace("_", "-")
                    if match:
                        direct_deps.add(match)
            except Exception as err:
                logger.debug(f"Failed to parse pyproject in graph analyzer: {err}")

        # 2. Check for lockfile (uv.lock) for transitive relations
        uv_lock = repo_path / "uv.lock"
        if uv_lock.exists():
            try:
                data = tomllib.loads(uv_lock.read_text(encoding="utf-8", errors="ignore"))
                packages = data.get("package", [])
                for pkg in packages:
                    name = pkg.get("name", "").lower().replace("_", "-")
                    if not name:
                        continue
                    version = pkg.get("version", "unknown")
                    version_map[name] = version
                    G.add_node(name, version=version)

                    # Add dependency edges: name -> dep
                    for dep in pkg.get("dependencies", []):
                        dep_name = dep.get("name", "").lower().replace("_", "-")
                        if dep_name:
                            G.add_edge(name, dep_name)
            except Exception as err:
                logger.debug(f"Failed to parse uv.lock: {err}")

        # Fallback if no lockfile edges: connect root direct dependencies
        if G.number_of_nodes() == 0:
            for d in direct_deps:
                G.add_node(d, version=version_map.get(d, "unpinned"))

        # Add root project node
        root_name = repo_path.name.lower().replace("_", "-")
        G.add_node(root_name, version="root")
        for d in direct_deps:
            if d in G:
                G.add_edge(root_name, d)

        return G, direct_deps, version_map

    def analyze(self, repo_path: Path, top_n: int = 10) -> AttackSurfaceReport:
        """Runs PageRank, blast radius, and connectivity analysis on dependency network."""
        G, direct_deps, version_map = self.build_graph(repo_path)
        total_nodes = G.number_of_nodes()
        total_edges = G.number_of_edges()

        if total_nodes <= 1:
            return AttackSurfaceReport(
                total_packages=0,
                direct_packages_count=0,
                transitive_packages_count=0,
                total_edges=0,
                graph_density=0.0,
            )

        root_name = repo_path.resolve().name.lower().replace("_", "-")

        # Exclude root project node from dependency rankings
        pkg_nodes = [n for n in G.nodes() if n != root_name]

        # 1. Compute PageRank
        # When A -> B (A depends on B), in standard PageRank we want B to receive centrality
        # because many packages depend on it.
        try:
            pagerank_scores = nx.pagerank(G, alpha=0.85)
        except Exception:
            pagerank_scores = {n: 1.0 / max(1, total_nodes) for n in G.nodes()}

        # 2. Compute Blast Radius (ancestors in graph: all components that depend on this node)
        blast_radii: dict[str, int] = {}
        for n in pkg_nodes:
            try:
                # nx.ancestors(G, n): nodes from which n can be reached
                ancestors = nx.ancestors(G, n)
                blast_radii[n] = len(ancestors)
            except Exception:
                blast_radii[n] = 0

        # Construct dependency node records
        node_records: list[DependencyCriticalityNode] = []
        for n in pkg_nodes:
            is_dir = n in direct_deps
            ver = version_map.get(n, G.nodes[n].get("version", "unknown"))
            pr = pagerank_scores.get(n, 0.0)
            br = blast_radii.get(n, 0)
            in_deg = G.in_degree(n)
            out_deg = G.out_degree(n)

            node_records.append(
                DependencyCriticalityNode(
                    name=n,
                    version=ver,
                    pagerank_score=pr,
                    blast_radius=br,
                    in_degree=in_deg,
                    out_degree=out_deg,
                    is_direct=is_dir,
                )
            )

        # Sort by PageRank (criticality)
        node_records.sort(key=lambda x: x.pagerank_score, reverse=True)
        for i, node in enumerate(node_records, start=1):
            node.criticality_rank = i

        critical_deps = node_records[:top_n]

        # Top blast radius
        high_blast = sorted(node_records, key=lambda x: x.blast_radius, reverse=True)[:top_n]

        density = nx.density(G)
        transitive_count = max(0, len(pkg_nodes) - len(direct_deps))

        # 3. Generate Mermaid diagram for top critical dependencies
        mermaid_code = self._generate_mermaid_diagram(G, critical_deps, root_name)

        return AttackSurfaceReport(
            total_packages=len(pkg_nodes),
            direct_packages_count=len(direct_deps),
            transitive_packages_count=transitive_count,
            total_edges=total_edges,
            graph_density=density,
            critical_dependencies=critical_deps,
            high_blast_radius_nodes=high_blast,
            mermaid_diagram=mermaid_code,
        )

    def _generate_mermaid_diagram(
        self,
        G: nx.DiGraph,
        top_nodes: list[DependencyCriticalityNode],
        root_name: str,
    ) -> str:
        """Generates a Mermaid graph diagram showing top dependencies and relationships."""
        relevant_nodes = {node.name for node in top_nodes[:8]}
        relevant_nodes.add(root_name)

        lines = ["```mermaid", "graph TD"]

        # Subgraph edges
        edge_count = 0
        for u, v in G.edges():
            if u in relevant_nodes and v in relevant_nodes:
                lines.append(f"    {u.replace('-', '_')} --> {v.replace('-', '_')}")
                edge_count += 1
                if edge_count >= 15:
                    break

        # Node styling
        lines.append(f"    style {root_name.replace('-', '_')} fill:#4A90E2,stroke:#333,stroke-width:2px,color:#fff")
        for node in top_nodes[:3]:
            safe_name = node.name.replace("-", "_")
            lines.append(f"    style {safe_name} fill:#E74C3C,stroke:#333,stroke-width:2px,color:#fff")

        lines.append("```")
        return "\n".join(lines)
