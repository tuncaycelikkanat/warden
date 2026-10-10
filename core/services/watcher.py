"""Live filesystem watcher service for continuous real-time code quality auditing."""

import asyncio
import datetime
import threading
import time
from pathlib import Path
from typing import ClassVar

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from core.services.orchestrator import AuditOrchestrator


class _AuditChangeHandler(FileSystemEventHandler):
    """Debounced file system event handler that triggers incremental audits upon code edits."""

    WATCHED_EXTENSIONS: ClassVar[set[str]] = {
        ".py", ".js", ".ts", ".jsx", ".tsx",
        ".json", ".yaml", ".yml", ".toml",
        "Dockerfile", ".env.example",
    }

    IGNORE_DIRS: ClassVar[set[str]] = {
        ".git", ".venv", "venv", "node_modules",
        "__pycache__", ".mypy_cache", ".pytest_cache",
        ".ruff_cache", "dist", "build", ".idea",
        ".vscode", "warden_reports",
    }

    def __init__(self, watcher: "LiveWatcherService") -> None:
        super().__init__()
        self.watcher = watcher
        self._timer: threading.Timer | None = None
        self._lock = threading.Lock()
        self._last_modified_path: str = ""

    def on_any_event(self, event: FileSystemEvent) -> None:
        """Filters filesystem events and debounces audit invocations."""
        if event.is_directory:
            return

        src_path = str(event.src_path)
        p = Path(src_path)

        # Ignore non-code files and metadata directories
        if any(part in self.IGNORE_DIRS for part in p.parts):
            return

        if p.name.startswith(".") and not p.name.startswith(".env"):
            return

        if p.suffix not in self.WATCHED_EXTENSIONS and p.name not in self.WATCHED_EXTENSIONS:
            return

        # Debounce rapid save events (e.g. IDE auto-formatters saving multiple files)
        with self._lock:
            self._last_modified_path = str(p.relative_to(self.watcher.target_path) if p.is_relative_to(self.watcher.target_path) else p.name)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(self.watcher.debounce_seconds, self._on_debounce_trigger)
            self._timer.daemon = True
            self._timer.start()

    def _on_debounce_trigger(self) -> None:
        """Executes the incremental audit after debounce interval elapses."""
        with self._lock:
            changed_path = self._last_modified_path
        self.watcher.run_incremental_pass(trigger_file=changed_path)


class LiveWatcherService:
    """Continuously monitors repository files and computes real-time quality score delta."""

    def __init__(
        self,
        target_path: str | Path = ".",
        min_score: int | None = None,
        debounce_seconds: float = 0.8,
    ) -> None:
        self.target_path = Path(target_path).resolve()
        self.min_score = min_score
        self.debounce_seconds = debounce_seconds
        self.orchestrator = AuditOrchestrator()
        self.last_score: float | None = None
        self.last_grade: str | None = None
        self.audit_count: int = 0
        self._is_auditing = False
        self._audit_lock = threading.Lock()

    def run_incremental_pass(self, trigger_file: str = "") -> None:
        """Executes a single incremental audit pass and outputs the live scorecard."""
        with self._audit_lock:
            if self._is_auditing:
                return
            self._is_auditing = True

        try:
            now_str = datetime.datetime.now().strftime("%H:%M:%S")
            start_t = time.time()

            # Execute incremental audit
            data = asyncio.run(
                self.orchestrator.run_full_audit(
                    self.target_path,
                    incremental=True,
                )
            )
            elapsed = time.time() - start_t
            self.audit_count += 1

            sc = data.get("scorecard", {})
            score = float(sc.get("total_score", 0.0))
            grade = str(sc.get("grade", "F"))
            l1 = float(sc.get("layer1_score", 0.0))
            l2 = float(sc.get("layer2_score", -1.0))

            # Compute score delta
            delta_str = ""
            if self.last_score is not None:
                diff = score - self.last_score
                if diff > 0:
                    delta_str = f" [▲ +{diff:.1f} pts]"
                elif diff < 0:
                    delta_str = f" [▼ {diff:.1f} pts]"
                else:
                    delta_str = " [= No change]"

            # Status indicators
            status_icon = "🟢" if score >= 85 else ("🟡" if score >= 70 else "🔴")
            gate_ok = self.min_score is None or score >= self.min_score
            gate_badge = "✅ PASSED" if gate_ok else f"❌ FAILED (Threshold: {self.min_score})"

            file_info = f"File: {trigger_file}" if trigger_file else "Initial Scan"

            # Print terminal scorecard card
            print("\n" + "═" * 78)
            print(f"👁️  WARDEN LIVE WATCH #{self.audit_count} — [{now_str}] — {file_info} ({elapsed:.2f}s)")
            print("═" * 78)
            print(f"{status_icon} Total Quality Score: {score:.1f}/100 ({grade}){delta_str}  │  Quality Gate: {gate_badge}")
            print(f"   • Layer 1 (Mechanical): {l1:.1f}/100")
            if l2 >= 0:
                print(f"   • Layer 2 (LLM Rubric): {l2:.1f}/100")

            # Check for regressions
            if self.last_score is not None and score < self.last_score - 3.0:
                print(f"\n🚨 [REGRESSION WARNING] Score dropped sharply: {self.last_score:.1f} ➔ {score:.1f} (-{self.last_score - score:.1f} pts)!")

            if not gate_ok:
                print(f"⚠️  [GATE ALERT] Score {score:.1f} is strictly below required threshold {self.min_score}!")

            # Vibe-coding preview
            vibe = data.get("vibe_coding", {})
            vibe_findings = vibe.get("total_findings_count", 0)
            if vibe_findings > 0:
                print(f"🤖 Vibe-Coding Residue: {vibe_findings} issues detected (AI didactic slop or prompt traces)")
            else:
                print("🤖 Vibe-Coding Hygiene: Clean ✓ (No AI comments or prompt leaks)")

            print("═" * 78)
            print("👀 Watching for file changes... (Press Ctrl+C to exit)\n")

            self.last_score = score
            self.last_grade = grade

        except Exception as exc:
            print(f"[!] Error during incremental live audit: {exc}")
        finally:
            with self._audit_lock:
                self._is_auditing = False

    def start(self) -> None:
        """Starts the filesystem observer loop and runs the baseline audit."""
        print("═" * 78)
        print("🛡️  WARDEN LIVE CODE WATCHER INITIALIZING")
        print(f"📁 Repository: {self.target_path}")
        print(f"🎯 Quality Gate: {self.min_score if self.min_score is not None else 'None'}")
        print("═" * 78)
        print("[*] Running initial baseline audit...")

        # Run initial baseline pass
        self.run_incremental_pass(trigger_file="[Baseline Scan]")

        handler = _AuditChangeHandler(self)
        observer = Observer()
        observer.schedule(handler, str(self.target_path), recursive=True)
        observer.start()

        try:
            while observer.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\n[✓] WARDEN Live Watcher terminated by user. Total audits completed:", self.audit_count)
            observer.stop()
        observer.join()
