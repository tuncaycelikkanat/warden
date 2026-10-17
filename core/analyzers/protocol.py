"""Core analyzer protocol and contextual data contracts for WARDEN.

Defines the pluggable analyzer interface and standardized result containers
allowing mechanical (Layer 1) scanners and 3rd-party community plugins to be
discovered, configured, and orchestrated uniformly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AnalysisContext:
    """Execution context supplied to all analyzers."""

    repo_path: Path
    source_files: list[Path] = field(default_factory=list)
    full_history: bool = False
    config: Any = None


@dataclass
class AnalyzerOutput:
    """Standardized output produced by an analyzer."""

    key: str
    data: Any
    summary: dict[str, Any] = field(default_factory=dict)
    extra_data: dict[str, Any] = field(default_factory=dict)
    measured: bool = True
    error: str | None = None


@runtime_checkable
class AnalyzerPlugin(Protocol):
    """Protocol that all WARDEN Layer 1 analyzers must implement."""

    @property
    def key(self) -> str:
        """Unique key identifying this analyzer (matches layer1_data key)."""
        ...

    @property
    def display_name(self) -> str:
        """Human-readable display name for logs and dashboards."""
        ...

    async def run(self, ctx: AnalysisContext) -> AnalyzerOutput:
        """Executes analysis asynchronously and returns standardized output."""
        ...
