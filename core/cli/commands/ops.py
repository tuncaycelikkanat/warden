"""Operational and administrative CLI command handlers for WARDEN."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from core.infra.database import create_db_and_tables, engine
from core.models.audit import AuditReport
from core.services.badge_service import BadgeGeneratorService
from core.services.git_hook_service import GitHookService
from core.services.metrics_service import MetricsCollectorService
from core.services.watcher import LiveWatcherService

logger = logging.getLogger(__name__)


def run_serve_command(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Boots FastAPI REST API and web dashboard server."""
    import uvicorn

    uvicorn.run("core.main:app", host=host, port=port, reload=reload)


def run_milestone_command(audit_id: int, label: str, clear: bool) -> None:
    """Marks or clears a milestone flag on a stored audit report."""
    create_db_and_tables()
    with Session(engine) as session:
        report = session.exec(select(AuditReport).where(AuditReport.id == audit_id)).first()
        if not report:
            print(f"[!] Audit ID {audit_id} bulunamadı.")
            sys.exit(1)

        if clear:
            report.is_milestone = False
            report.milestone_label = None
            session.add(report)
            session.commit()
            print(f"[✓] Audit #{audit_id} milestone işareti kaldırıldı.")
        else:
            report.is_milestone = True
            report.milestone_label = label
            session.add(report)
            session.commit()
            print(f"[✓] Audit #{audit_id} milestone olarak işaretlendi: '{label}'")
            print("    Karşılaştırma raporları artık bu audit'i referans olarak kullanacak.")


def run_metrics_command(as_json: bool = False) -> None:
    """Exports WARDEN operational and quality metrics to stdout."""
    create_db_and_tables()
    collector = MetricsCollectorService()
    if as_json:
        data = collector.collect_metrics_data()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(collector.generate_prometheus_exposition())


def run_hook_command(args: Any) -> None:
    """Dispatches git hook management and execution commands."""
    service = GitHookService()
    repo_path = Path(args.target).resolve()

    if not getattr(args, "hook_action", None):
        print("[!] Lütfen bir hook eylemi belirtin: install, uninstall, run")
        sys.exit(1)

    if args.hook_action == "install":
        ok = service.install(repo_path, hook_type=args.hook_type, min_score=args.min_score)
        if ok:
            print(f"[✓] WARDEN Git Hook ({args.hook_type}) başarıyla kuruldu: {repo_path}/.git/hooks/")
        else:
            print(f"[!] Git Hook kurulumu başarısız: {repo_path} geçerli bir git deposu mu?")
            sys.exit(1)

    elif args.hook_action == "uninstall":
        ok = service.uninstall(repo_path, hook_type=args.hook_type)
        if ok:
            print(f"[✓] WARDEN Git Hook ({args.hook_type}) kaldırıldı.")
        else:
            print("[!] Hook kaldırılamadı.")
            sys.exit(1)

    elif args.hook_action == "run":
        if args.hook_type == "pre-commit":
            passed, msg = service.run_pre_commit(repo_path)
            print(msg)
            if not passed:
                sys.exit(1)
        elif args.hook_type == "pre-push":
            passed, msg = asyncio.run(service.run_pre_push(repo_path, min_score=args.min_score))
            print(msg)
            if not passed:
                sys.exit(1)


def run_watch_command(target: str, min_score: int | None = None, debounce: float = 0.8) -> None:
    """Runs continuous real-time filesystem watcher for immediate audit feedback."""
    p = Path(target).resolve()
    watcher = LiveWatcherService(
        target_path=p,
        min_score=min_score,
        debounce_seconds=debounce,
    )
    watcher.start()


def run_badge_command(score: float | None, grade: str | None, label: str, output: str | None) -> None:
    """Generates an SVG vector badge and saves to file."""
    badge_score = score
    badge_grade = grade

    if badge_score is None and badge_grade is None:
        create_db_and_tables()
        with Session(engine) as session:
            latest = session.exec(select(AuditReport).order_by(AuditReport.id.desc())).first()  # type: ignore[union-attr]
            if latest:
                badge_score = latest.total_score
                badge_grade = latest.grade

    svg_content = BadgeGeneratorService.generate_svg(label=label, score=badge_score, grade=badge_grade)
    out_file = output or "warden-score.svg"
    out_path = Path(out_file).resolve()
    out_path.write_text(svg_content, encoding="utf-8")
    print(f"[✓] Vektörel SVG rozeti kaydedildi: {out_path}")
    val = f"{int(badge_score)}/100 ({badge_grade})" if badge_score is not None else (badge_grade or "Verified")
    print(f"    Rozet Metni: {label} | {val}")
    print(f"    Markdown Kullanımı: [![{label}]({out_file})](https://github.com/tuncaycelikkanat/warden)")


def run_init_command(
    target: str = ".",
    agent: str = "all",
    overwrite: bool = False,
    as_json: bool = False,
) -> None:
    """Initializes AI coding agent guardrails, MCP configs, and warden.config.yaml."""
    from core.services.agent_init_service import AgentInitService

    service = AgentInitService()
    res = service.initialize(repo_path=target, agent=agent, overwrite=overwrite)
    if as_json:
        print(json.dumps(res.to_dict(), indent=2, ensure_ascii=False))
        return

    print(f"[✓] WARDEN AI Agent Kalkanı kuruldu: {res.target_dir}")
    print(f"    Yapılandırılan Ajanlar: {', '.join(res.agents_configured)}")
    for f in res.files_written:
        print(f"    • Oluşturulan/Güncellenen: {f}")

