"""Security and supply-chain CLI command handlers for WARDEN."""

from __future__ import annotations

import logging
from pathlib import Path

from core.services.dependency_graph_analyzer import DependencyGraphAnalyzer
from core.services.entropy_analyzer import EntropyAnalyzerService
from core.services.sbom_generator import SBOMGeneratorService
from core.services.typosquatting_detector import TyposquattingDetector

logger = logging.getLogger(__name__)


def run_check_attack_surface(target: str, top: int) -> None:
    """Runs networkx PageRank and blast radius attack surface analysis."""
    p = Path(target).resolve()
    print(f"[*] Analyzing dependency graph and attack surface for {p} using networkx...")
    analyzer = DependencyGraphAnalyzer()
    report = analyzer.analyze(p, top_n=top)

    print(f"[+] Toplam Paket: {report.total_packages} (Doğrudan: {report.direct_packages_count}, Dolaylı: {report.transitive_packages_count})")
    print(f"[+] Bağımlılık Kenarları: {report.total_edges} · Graf Yoğunluğu: %{round(report.graph_density * 100, 2)}")

    print("\n--- En Kritik Bağımlılıklar (PageRank Skoru) ---")
    for node in report.critical_dependencies:
        scope_str = "DOĞRUDAN" if node.is_direct else "DOLAYLI"
        print(f"  #{node.criticality_rank} {node.name} ({node.version}) [{scope_str}] - PageRank: {node.pagerank_score:.4f}, Tahribat Yarıçapı (Blast Radius): {node.blast_radius} bileşen")

    print("\n--- En Yüksek Tahribat Yarıçapı (En Çok Bileşenin Bağlı Olduğu Paketler) ---")
    for node in report.high_blast_radius_nodes[:5]:
        print(f"  - {node.name}: {node.blast_radius} bileşen bu pakete bağımlı")


def run_check_typosquatting(package_name: str) -> None:
    """Checks a candidate package name for typosquatting attacks."""
    print(f"[*] Checking '{package_name}' for typosquatting attacks against top PyPI packages...")
    detector = TyposquattingDetector()
    match = detector.detect(package_name)

    if not match:
        print(f"[✓] '{package_name}' temiz görünüyor (Bilinen bir popüler paket taklidi tespit edilmedi).")
    else:
        print("[🚨] TYPOSQUATTING TESPİT EDİLDİ!")
        print(f"    - Şüpheli Paket: {match.suspect_package}")
        print(f"    - Hedef Alınan Popüler Paket: {match.target_package}")
        print(f"    - Benzerlik Skoru: %{round(match.similarity_score * 100, 1)}")
        print(f"    - Kullanılan Teknik: {match.technique}")
        print(f"    - Risk Seviyesi: {match.risk_level}")
        print(f"    - Detay: {match.reason}")


def run_generate_sbom(target: str, output: str | None) -> None:
    """Generates CycloneDX v1.5 JSON SBOM for the target repository."""
    p = Path(target).resolve()
    print(f"[*] Analyzing manifests and generating CycloneDX v1.5 SBOM for {p} ...")
    service = SBOMGeneratorService()
    bom = service.generate_sbom(p)
    print(f"[+] CycloneDX SBOM başarıyla oluşturuldu: {len(bom.components)} bileşen tespit edildi.")
    for comp in bom.components[:10]:
        print(f"    - {comp.name} ({comp.version}) [{comp.scope}] -> {comp.purl}")
    if len(bom.components) > 10:
        print(f"    ... ve {len(bom.components) - 10} diğer bileşen")

    if output:
        out_path = Path(output).resolve()
        service.export_json(p, output_path=out_path)
        print(f"[✓] CycloneDX SBOM dosyaya kaydedildi: {out_path}")
    else:
        print("\n--- CycloneDX v1.5 JSON Önizleme ---")
        preview = bom.to_json(indent=2)[:600]
        print(preview + ("\n... [tam çıktıyı kaydetmek için --output belirtin]" if len(bom.to_json()) > 600 else ""))


def run_scan_entropy(target: str, max_findings: int) -> None:
    """Scans repository files for high-entropy secrets."""
    p = Path(target).resolve()
    print(f"[*] Scanning {p} using Shannon entropy analysis for potential secrets...")
    analyzer = EntropyAnalyzerService()
    findings = analyzer.scan_repository(p, max_findings=max_findings)

    if not findings:
        print("[✓] Kod tabanında şüpheli yüksek entropili sır bulunamadı (Temiz).")
        return

    print(f"[⚠️] {len(findings)} yüksek entropili dize / potansiyel sır tespit edildi:")
    for f in findings:
        print(f"    - [{f.confidence}] {f.file}:{f.line} -> {f.variable_name} ({f.masked_value}) - H={f.entropy_score:.2f} [{f.charset_type}]")


def run_check_hallucinations(target: str = ".", as_json: bool = False) -> None:
    """Scans repository for AI-hallucinated imports, methods, and keyword arguments."""
    import json
    import sys

    from core.services.hallucination_detector import HallucinatedAPIDetector

    detector = HallucinatedAPIDetector()
    result = detector.scan_repository(Path(target).resolve())

    if as_json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"[*] AI Halüsinasyon & Sembol Doğrulama Taraması ({result.files_scanned} dosya)...")
        if not result.findings:
            print(f"[✓] Halüsinasyon API veya uydurma sembol bulunmadı! Skor: {result.score}/100")
        else:
            print(f"[🚨] {len(result.findings)} AI HALÜSİNASYON API BULGUSU TESPİT EDİLDİ (Skor: {result.score}/100):")
            for f in result.findings:
                print(f"    - [{f.severity}] {f.file}:{f.line} ({f.hallucination_type}) -> {f.symbol}")
                print(f"      Açıklama: {f.explanation}")
                print(f"      Öneri: {f.suggestion}")

    if result.findings:
        sys.exit(1)

