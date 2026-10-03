"""Circular Dependency & Import Graph Analyzer using NetworkX.

Analyzes module-level import relationships via AST to construct directed dependency
graphs, detect cyclic imports (A -> B -> A or multi-hop loops), and synthesize
architectural decoupling suggestions and Mermaid diagrams.
"""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import networkx as nx

from core.utils.file_discovery import discover_source_files

logger = logging.getLogger(__name__)


@dataclass
class CircularCycle:
    """Represents an identified circular import cycle between modules."""

    cycle_path: list[str]
    length: int
    break_suggestion: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "cycle_path": self.cycle_path,
            "length": self.length,
            "break_suggestion": self.break_suggestion,
        }


@dataclass
class CircularDependencyReport:
    """Aggregated report of codebase import relationships and circular cycles."""

    total_modules_analyzed: int
    total_import_edges: int
    cycles_count: int
    has_cycles: bool
    cycles: list[CircularCycle] = field(default_factory=list)
    strongly_connected_components: list[list[str]] = field(default_factory=list)
    mermaid_diagram: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_modules_analyzed": self.total_modules_analyzed,
            "total_import_edges": self.total_import_edges,
            "cycles_count": self.cycles_count,
            "has_cycles": self.has_cycles,
            "cycles": [c.to_dict() for c in self.cycles],
            "strongly_connected_components": self.strongly_connected_components,
            "mermaid_diagram": self.mermaid_diagram,
        }


class CircularDependencyDetector:
    """Inspects Python source AST and models module dependency graphs via NetworkX."""

    def _file_to_module_name(self, file_path: Path, repo_path: Path) -> str:
        """Converts a repository file path to a dotted Python module name."""
        rel = file_path.relative_to(repo_path)
        parts = list(rel.parts)
        parts[-1] = parts[-1].removesuffix(".py")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts)

    def _resolve_relative_import(self, current_module: str, relative_module: str | None, level: int) -> str:
        """Resolves relative import level (. or ..) against current module path."""
        parts = current_module.split(".")
        if level > len(parts):
            base_parts = []
        else:
            base_parts = parts[: len(parts) - level]

        if relative_module:
            base_parts.append(relative_module)
        return ".".join(base_parts)

    def build_import_graph(self, repo_path: Path) -> tuple[nx.DiGraph, dict[str, Path]]:
        """
        Scans all Python files in the repository and builds a directed import graph.
        Edge (A -> B) means module A imports module B.
        """
        repo_path = repo_path.resolve()
        source_files = discover_source_files(repo_path)
        py_files = [
            f for f in source_files
            if f.suffix.lower() == ".py" and not any(p in ("tests", "fixtures", ".venv") for p in f.parts)
        ]

        module_map: dict[str, Path] = {}
        for f in py_files:
            mod_name = self._file_to_module_name(f, repo_path)
            if mod_name:
                module_map[mod_name] = f

        G = nx.DiGraph()
        for mod_name in module_map:
            G.add_node(mod_name)

        # Parse AST for imports in each file
        for mod_name, file_path in module_map.items():
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(content, filename=str(file_path))
            except Exception as err:
                logger.debug(f"Failed to parse {file_path} for imports: {err}")
                continue

            for node in ast.walk(tree):
                # 1. import X
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        target = alias.name
                        # Check if target or prefix is an internal module
                        matching_mod = self._match_internal_module(target, module_map)
                        if matching_mod and matching_mod != mod_name:
                            G.add_edge(mod_name, matching_mod)

                # 2. from X import Y
                elif isinstance(node, ast.ImportFrom):
                    target_mod: str | None = None
                    if node.level and node.level > 0:
                        # Relative import
                        target_mod = self._resolve_relative_import(mod_name, node.module, node.level)
                    elif node.module:
                        target_mod = node.module

                    if target_mod:
                        matching_mod = self._match_internal_module(target_mod, module_map)
                        if matching_mod and matching_mod != mod_name:
                            G.add_edge(mod_name, matching_mod)

        return G, module_map

    def _match_internal_module(self, imported_name: str, module_map: dict[str, Path]) -> str | None:
        """Finds closest matching internal module for an imported string."""
        if imported_name in module_map:
            return imported_name

        # If imported_name is a package/symbol inside a module, find longest matching prefix
        parts = imported_name.split(".")
        for i in range(len(parts) - 1, 0, -1):
            candidate = ".".join(parts[:i])
            if candidate in module_map:
                return candidate

        return None

    def analyze(self, repo_path: Path) -> CircularDependencyReport:
        """Finds circular import cycles, strongly connected components, and architectural suggestions."""
        G, _module_map = self.build_import_graph(repo_path)
        total_modules = G.number_of_nodes()
        total_edges = G.number_of_edges()

        # Find all simple elementary cycles
        try:
            raw_cycles = list(nx.simple_cycles(G))
        except Exception:
            raw_cycles = []

        cycles: list[CircularCycle] = []
        for rc in raw_cycles:
            cycle_closed = rc + [rc[0]]
            length = len(rc)

            # Generate architectural decoupling recommendation
            if length == 2:
                sug = (
                    f"Direct 2-way circular dependency between '{rc[0]}' and '{rc[1]}'. "
                    f"Extract shared data models/interfaces to a separate module, or use function-level lazy import."
                )
            else:
                sug = (
                    f"Multi-hop circular cycle of {length} modules ({' -> '.join(cycle_closed)}). "
                    f"Invert dependencies using Dependency Injection or move shared utilities to lower-level layer."
                )

            cycles.append(
                CircularCycle(
                    cycle_path=cycle_closed,
                    length=length,
                    break_suggestion=sug,
                )
            )

        # Strongly connected components (tight clusters of >1 node)
        sccs = [list(c) for c in nx.strongly_connected_components(G) if len(c) > 1]

        # Generate Mermaid diagram
        mermaid_code = self._generate_mermaid(cycles, G)

        return CircularDependencyReport(
            total_modules_analyzed=total_modules,
            total_import_edges=total_edges,
            cycles_count=len(cycles),
            has_cycles=len(cycles) > 0,
            cycles=cycles,
            strongly_connected_components=sccs,
            mermaid_diagram=mermaid_code,
        )

    def _generate_mermaid(self, cycles: list[CircularCycle], G: nx.DiGraph) -> str:
        """Generates Mermaid graph representation for cyclic module dependencies."""
        if not cycles:
            return "```mermaid\ngraph TD\n    Clean[No Circular Dependencies Detected]\n```"

        lines = ["```mermaid", "graph TD"]
        seen_edges: set[tuple[str, str]] = set()

        for c in cycles[:6]:
            for i in range(len(c.cycle_path) - 1):
                u = c.cycle_path[i]
                v = c.cycle_path[i + 1]
                edge = (u, v)
                if edge not in seen_edges:
                    seen_edges.add(edge)
                    u_safe = u.replace(".", "_").replace("-", "_")
                    v_safe = v.replace(".", "_").replace("-", "_")
                    lines.append(f"    {u_safe} -->|circular| {v_safe}")

        # Highlight cyclic nodes in red
        all_cyclic_nodes = {node for c in cycles for node in c.cycle_path}
        for node in list(all_cyclic_nodes)[:10]:
            safe_node = node.replace(".", "_").replace("-", "_")
            lines.append(f"    style {safe_node} fill:#E74C3C,stroke:#333,stroke-width:2px,color:#fff")

        lines.append("```")
        return "\n".join(lines)
