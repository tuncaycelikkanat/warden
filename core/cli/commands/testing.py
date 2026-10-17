"""Testing and verification CLI command handlers for WARDEN."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from core.services.bdd_scenario_generator import BDDScenarioGeneratorService
from core.services.mutation_tester import MutationTesterService
from core.services.property_test_generator import PropertyTestGenerator

logger = logging.getLogger(__name__)


def run_mutate_command(
    target: str,
    test_path: str | None = None,
    max_mutants: int = 15,
    timeout: float = 8.0,
    dry_run: bool = False,
    as_json: bool = False,
    output_file: str | None = None,
) -> None:
    """Executes mutation testing or dry-run discovery and displays findings."""
    target_path = Path(target)
    test_p = Path(test_path) if test_path else None
    service = MutationTesterService(repo_path=Path("."))

    report = service.run_mutation_testing(
        target_path=target_path,
        test_path=test_p,
        max_mutants=max_mutants,
        timeout=timeout,
        dry_run=dry_run,
    )

    data = report.to_dict()

    if output_file:
        out_p = Path(output_file)
        out_p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        if not as_json:
            print(f"[✓] Mutasyon raporu kaydedildi: {output_file}")

    if as_json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    mode_str = "DRY-RUN (Haritalama)" if dry_run else "CANLI İCRA (Öldürme Testi)"
    print("\n" + "=" * 60)
    print(f"🧬 WARDEN AST MUTASYON TESTİ — {mode_str}")
    print("=" * 60)
    print(f"📁 Hedef Yol         : {report.target_path}")
    print(f"🔍 Keşfedilen Mutant : {report.total_mutants_discovered}")
    print(f"🧪 Test Edilen Mutant: {report.mutants_tested}")
    if not dry_run:
        print(f"🎯 Öldürülen (Killed): {report.killed} ✅")
        print(f"⚠️  Kurtulan (Survived): {report.survived} ❌")
        print(f"⏱️  Zaman Aşımı (Timeout): {report.timed_out}")
        print(f"💥 Hata (Errored)    : {report.errored}")
        print(f"🏆 Mutasyon Skoru    : %{report.mutation_score:.1f}")
    print(f"⏱️  Toplam Süre       : {report.execution_time_seconds:.3f} sn")
    print("-" * 60)

    if report.mutants:
        print("📋 Mutant Adayları (Örneklem):")
        for m in report.mutants[:15]:
            status_icon = "⚪" if dry_run else ("✅" if m.status in ("KILLED", "TIMEOUT") else "❌")
            print(f"  {status_icon} [{m.operator_category.upper()}] L{m.line_number}: {m.original_snippet}  -->  {m.mutated_snippet}")
            if not dry_run and m.killer_test:
                print(f"      Öldüren Test: {m.killer_test}")
    print("=" * 60 + "\n")


def run_bdd_command(
    target: str,
    feature_dir: str | None = None,
    output_file: str | None = None,
    enrich_llm: bool = False,
    provider: str | None = None,
    as_json: bool = False,
) -> None:
    """Executes AST-based BDD scenario extraction and exports Gherkin/Markdown catalogs."""
    p = Path(target)
    if not p.exists():
        print(f"[!] Hata: Belirtilen test yolu bulunamadı: {p}")
        return

    if not as_json:
        print(f"[*] Analyzing tests in '{p}' using AST BDD scenario extractor...")
    service = BDDScenarioGeneratorService()
    report = service.generate_from_path(
        target_path=p,
        enrich_with_llm=enrich_llm,
        provider_name=provider,
    )

    if as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return

    print("\n" + "=" * 68)
    print("🥒 WARDEN BDD & GHERKIN SENARYO DOKÜMANTASYON MOTORU (D4)")
    print("=" * 68)
    print(f"📁 Hedef Test Yolu     : {p.resolve()}")
    print(f"📦 Çıkarılan Özellikler: {report.total_features} Features")
    print(f"🎯 Davranış Senaryoları: {report.total_scenarios} Scenarios")
    print(f"⚡ Toplam Adım (Steps) : {report.total_steps} Given-When-Then steps")
    print("-" * 68)

    # Preview first 3 features
    print("🔍 BDD SENARYO ÖNİZLEMESİ:")
    for feat in report.features[:3]:
        print(f"\n  📦 Feature: {feat.feature_name} ({len(feat.scenarios)} senaryo)")
        for sc in feat.scenarios[:2]:
            tag_str = " ".join(f"@{t}" for t in sc.tags)
            print(f"    🎯 Scenario: {sc.name} [{tag_str}]")
            for step in sc.steps[:4]:
                print(f"       {step.step_type} {step.text}")
            if len(sc.steps) > 4:
                print(f"       ... (+{len(sc.steps) - 4} adım)")
        if len(feat.scenarios) > 2:
            print(f"    ... (+{len(feat.scenarios) - 2} diğer senaryo)")

    if len(report.features) > 3:
        print(f"\n  ... ve {len(report.features) - 3} diğer test özelliği")

    if feature_dir:
        exported = service.export_feature_files(report, feature_dir)
        print(f"\n[✓] {len(exported)} adet Behave/Cucumber '.feature' dosyası kaydedildi: {Path(feature_dir).resolve()}")

    if output_file:
        md_path = service.export_markdown_report(report, output_file)
        print(f"[✓] Markdown BDD senaryo kataloğu kaydedildi: {md_path.resolve()}")

    print("\n" + "=" * 68 + "\n")


def run_generate_property_tests(target: str, output: str | None, max_tests: int) -> None:
    """Scans repository and synthesizes Hypothesis property-based tests."""
    p = Path(target).resolve()
    print(f"[*] Analyzing Python AST in {p} for Property-Based Test invariants...")
    generator = PropertyTestGenerator()
    report = generator.scan_repository(p, max_templates=max_tests)

    print(f"[+] {report.candidate_functions_count} fonksiyon için Hypothesis property testi üretildi:")
    for t in report.templates:
        print(f"    - {t.target_function} ({t.invariant_type}) -> {t.file_path}")

    if output and report.full_test_suite_code:
        out_path = Path(output).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report.full_test_suite_code, encoding="utf-8")
        print(f"[✓] Test taslağı dosyaya yazıldı: {out_path}")
    elif not output and report.full_test_suite_code:
        print("\n--- Üretilen Test Taslağı (Önizleme) ---")
        preview = report.full_test_suite_code[:600]
        print(preview + ("\n... [kalanı görmek için --output belirtin]" if len(report.full_test_suite_code) > 600 else ""))


def run_bench_command(output: str | None = None, as_json: bool = False) -> None:
    """Executes the detector benchmarking suite and displays metrics."""
    from benchmarks.runner import BenchmarkRunner

    runner = BenchmarkRunner()
    report = runner.run_suite()

    if output:
        out_p = Path(output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        if not as_json:
            print(f"[+] Benchmark sonuçları kaydedildi: {output}")

    if as_json:
        print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
        return

    print("\n==================== WARDEN DETECTOR BENCHMARK ====================")
    print(report.format_table())
    print("===================================================================\n")
    if report.failures:
        print(f"⚠️  {len(report.failures)} Sınıflandırma Hatası:")
        for f in report.failures:
            print(f"  - [{f['type']}] ({f['category']}) {f['id']}: {f['description']}")
    else:
        print("🎯 Tüm kategorilerde %100 Precision & Recall!")
