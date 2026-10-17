"""CLI ArgumentParser configuration and subparser registration for WARDEN."""

from __future__ import annotations

import argparse
from typing import Any


def register_core_subparsers(subparsers: Any) -> None:
    """Registers core lifecycle CLI commands (audit, serve, milestone, metrics, hook, watch, badge)."""
    # Subcommand: audit
    audit_parser = subparsers.add_parser(
        "audit",
        help="Hedef projede tam kapsamlı denetim (Layer 1 + Layer 2) çalıştırır ve rapor üretir",
        description="Hedef projede 16 mekanik analizör ve LLM mimari rubriklerini çalıştırır.",
    )
    audit_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Denetlenecek projenin yolu (Varsayılan: mevcut dizin '.')",
    )
    audit_parser.add_argument(
        "--path",
        default=None,
        help="Hedef proje yolu flag alternatifi (örn: --path /path/to/repo)",
    )
    audit_parser.add_argument(
        "--min-score",
        type=int,
        default=None,
        help="CI/CD için minimum başarı eşiği (Skor bu değerin altındaysa exit code 1 döner)",
    )
    audit_parser.add_argument(
        "--full-history",
        action="store_true",
        default=False,
        help="Git geçmişinin tamamını tara (Varsayılan: son 6 ay)",
    )
    audit_parser.add_argument(
        "--incremental",
        action="store_true",
        default=False,
        help="Sadece değişen veya eklenen dosyaları tara (hızlı artımlı denetim)",
    )
    audit_parser.add_argument(
        "--since-commit",
        default=None,
        help="Artımlı denetim için referans commit veya dal (örn: HEAD~1, origin/main)",
    )
    audit_parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        default=False,
        help="Secret sızıntısı, SAST ERROR veya zafiyetli bağımlılık varsa exit code 2 ile başarısız ol",
    )
    audit_parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Çıktı formatı. 'json' modunda stdout yalnızca makine-okunur JSON içerir, loglar stderr'e gider",
    )

    # Subcommand: serve
    serve_parser = subparsers.add_parser(
        "serve",
        help="FastAPI REST API ve MCP arka uç sunucusunu başlatır",
        description="FastAPI REST API sunucusunu başlatır (Swagger UI: http://localhost:8000/docs).",
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="Bağlanılacak host adresi (Varsayılan: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Dinlenecek port numarası (Varsayılan: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Canlı yeniden yükleme modunu etkinleştirir")

    # Subcommand: milestone
    milestone_parser = subparsers.add_parser(
        "milestone",
        help="Bir audit raporunu referans baseline olarak işaretler",
        description="Belirtilen audit ID'sini milestone olarak işaretler; karşılaştırma raporlarında bu kullanılır.",
    )
    milestone_parser.add_argument("audit_id", type=int, help="Milestone yapılacak audit rapor ID'si")
    milestone_parser.add_argument("--label", default="baseline", help="Milestone etiketi (Varsayılan: 'baseline')")
    milestone_parser.add_argument("--clear", action="store_true", help="Mevcut milestone işaretini kaldırır")

    # Subcommand: metrics
    metrics_parser = subparsers.add_parser(
        "metrics",
        help="WARDEN operasyonel ve kalite metriklerini Prometheus / OpenMetrics formatında çıktılar (G6)",
        description="Prometheus scraping ve izlenebilirlik için metrikleri plain-text veya JSON formatında sunar.",
    )
    metrics_parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Metrikleri Prometheus exposition yerine JSON formatında çıktılar",
    )

    # Subcommand: hook
    hook_parser = subparsers.add_parser(
        "hook",
        help="Git hook (pre-commit & pre-push) kalite kapısı yönetimi (H3)",
        description="Akıllı git kancalarını kurar, kaldırır veya çalıştırır.",
    )
    hook_subparsers = hook_parser.add_subparsers(dest="hook_action", help="Hook eylemi")

    install_parser = hook_subparsers.add_parser("install", help="Git kancalarını .git/hooks dizinine kurar")
    install_parser.add_argument("target", nargs="?", default=".", help="Hedef git reposu yolu (Varsayılan: '.')")
    install_parser.add_argument(
        "--hook-type",
        choices=["pre-commit", "pre-push", "all"],
        default="all",
        help="Kurulacak hook türü (Varsayılan: all)",
    )
    install_parser.add_argument(
        "--min-score",
        type=int,
        default=80,
        help="Pre-push için minimum kabul skoru (Varsayılan: 80)",
    )

    uninstall_parser = hook_subparsers.add_parser("uninstall", help="Kurulu WARDEN git kancalarını kaldırır")
    uninstall_parser.add_argument("target", nargs="?", default=".", help="Hedef git reposu yolu (Varsayılan: '.')")
    uninstall_parser.add_argument(
        "--hook-type",
        choices=["pre-commit", "pre-push", "all"],
        default="all",
        help="Kaldırılacak hook türü (Varsayılan: all)",
    )

    run_parser = hook_subparsers.add_parser("run", help="Belirtilen git kancasını manuel çalıştırır")
    run_parser.add_argument("target", nargs="?", default=".", help="Hedef git reposu yolu (Varsayılan: '.')")
    run_parser.add_argument(
        "--hook-type",
        choices=["pre-commit", "pre-push"],
        required=True,
        help="Çalıştırılacak hook türü",
    )
    run_parser.add_argument(
        "--min-score",
        type=int,
        default=80,
        help="Pre-push için minimum kalite skoru (Varsayılan: 80)",
    )

    # Subcommand: watch
    watch_parser = subparsers.add_parser(
        "watch",
        help="Dosya değişikliklerini sürekli izleyerek gerçek zamanlı anlık denetim yapar",
        description="Kod tabanındaki dosya kayıtlarını otomatik yakalayarak anlık skor deltası ve kalite karnesi üretir.",
    )
    watch_parser.add_argument("target", nargs="?", default=".", help="İzlenecek proje dizini (Varsayılan: '.')")
    watch_parser.add_argument("--min-score", type=int, default=None, help="Kalite kapısı minimum skor eşiği")
    watch_parser.add_argument("--debounce", type=float, default=0.8, help="Kaydetme sonrası bekleme süresi saniye (Varsayılan: 0.8)")

    # Subcommand: badge
    badge_parser = subparsers.add_parser(
        "badge",
        help="README için shields.io uyumlu dinamik SVG skor rozeti üretir",
        description="Veritabanındaki son audit skorundan veya belirtilen skordan README için vektörel SVG rozet üretir.",
    )
    badge_parser.add_argument("--score", type=float, default=None, help="Doğrudan skor belirt (örn: 95.0)")
    badge_parser.add_argument("--grade", default=None, help="Doğrudan not belirt (örn: A+)")
    badge_parser.add_argument("--label", default="WARDEN", help="Rozet sol etiket metni")
    badge_parser.add_argument("--output", "-o", default=None, help="SVG dosyasının kaydedileceği yol (Varsayılan: warden-score.svg)")

    # Subcommand: init
    init_parser = subparsers.add_parser(
        "init",
        help="Claude Code, Cursor ve Windsurf için yerel AI Agent Kalkanı, hook ve MCP ayarlarını otomatik kurar",
        description="Projeye warden.config.yaml, .claude/settings.json, .cursor/mcp.json ve .cursor/rules/warden-governance.mdc kurar.",
    )
    init_parser.add_argument("target", nargs="?", default=".", help="Hedef proje dizini (Varsayılan: '.')")
    init_parser.add_argument(
        "--agent",
        choices=["claude", "cursor", "windsurf", "all"],
        default="all",
        help="Kurulacak AI kodlama ajanı tipi (Varsayılan: all)",
    )
    init_parser.add_argument("--overwrite", action="store_true", default=False, help="Mevcut dosyaların üzerine yaz")
    init_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")


def register_testing_subparsers(subparsers: Any) -> None:
    """Registers testing and verification CLI commands."""
    prop_parser = subparsers.add_parser(
        "generate-property-tests",
        help="Proje AST analizinden Hypothesis tabanlı property-based test taslakları üretir (D3)",
        description="Fonksiyon imzaları ve tip ipuçlarını inceleyerek idempotence, boundedness ve roundtrip testleri sentezler.",
    )
    prop_parser.add_argument("target", nargs="?", default=".", help="Hedef projenin yolu (Varsayılan: '.')")
    prop_parser.add_argument("--output", "-o", default=None, help="Üretilen test dosyasının kaydedileceği yol")
    prop_parser.add_argument("--max-tests", type=int, default=15, help="Maksimum üretilecek property test sayısı (Varsayılan: 15)")

    mutate_parser = subparsers.add_parser(
        "mutate",
        help="AST Mutasyon Testi ile test paketinin mutant öldürme skorunu ve kör noktalarını analiz eder (D1)",
        description="Kaynak kodda yapay hatalar türeterek testlerin bu hataları yakalayıp yakalamadığını ölçer.",
    )
    mutate_parser.add_argument("target", nargs="?", default=".", help="Hedef kaynak dosya veya dizin yolu (Varsayılan: '.')")
    mutate_parser.add_argument("--test-path", default=None, help="Koşulacak spesifik test dosyası veya dizini")
    mutate_parser.add_argument("--max-mutants", type=int, default=15, help="Test edilecek maksimum mutant sayısı (Varsayılan: 15)")
    mutate_parser.add_argument("--timeout", type=float, default=8.0, help="Her bir mutant testi için zaman aşımı saniyesi (Varsayılan: 8.0)")
    mutate_parser.add_argument("--dry-run", action="store_true", default=False, help="Testleri çalıştırmadan yalnızca potansiyel mutantları haritala")
    mutate_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")
    mutate_parser.add_argument("--output", "-o", default=None, help="Sonuç raporunu JSON dosyasına kaydet")

    bdd_parser = subparsers.add_parser(
        "bdd",
        help="Python testlerinden Given-When-Then BDD/Gherkin senaryoları ve dokümantasyon üretir (D4)",
        description="Python AST ile testleri analiz ederek standart .feature ve Markdown senaryo kataloğu üretir.",
    )
    bdd_parser.add_argument("target", nargs="?", default="tests", help="Taranacak test dizini veya test dosyası (Varsayılan: 'tests')")
    bdd_parser.add_argument("--feature-dir", "-f", default=None, help="Cucumber/Behave uyumlu .feature dosyalarının kaydedileceği dizin")
    bdd_parser.add_argument("--output", "-o", default=None, help="Markdown senaryo kataloğunun kaydedileceği dosya")
    bdd_parser.add_argument("--enrich-llm", action="store_true", default=False, help="LLM ile senaryo başlıklarını ve kullanıcı hikayelerini zenginleştir")
    bdd_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")

    bench_parser = subparsers.add_parser(
        "bench",
        aliases=["benchmark"],
        help="Statik analiz detektörlerinin Precision, Recall ve F1-score metriklerini ölçer",
        description="Ground-truth etiketli benchmark veriseti üzerinde secret_entropy, missing_timeout, bare_except, silent_swallow ve ai_slop detektörlerini değerlendirir.",
    )
    bench_parser.add_argument("--output", "-o", default=None, help="Benchmark sonuçlarının kaydedileceği JSON dosya yolu")
    bench_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları doğrudan JSON olarak stdout'a yazdır")


def register_security_subparsers(subparsers: Any) -> None:
    """Registers supply-chain, secret leakage, and attack surface CLI commands."""
    sbom_parser = subparsers.add_parser(
        "generate-sbom",
        help="Proje bağımlılıkları için CycloneDX v1.5 JSON SBOM üretir (E4)",
        description="Supply chain güvenliği için CycloneDX v1.5 JSON Software Bill of Materials (SBOM) manifesti üretir.",
    )
    sbom_parser.add_argument("target", nargs="?", default=".", help="Hedef projenin yolu (Varsayılan: '.')")
    sbom_parser.add_argument("--output", "-o", default=None, help="SBOM çıktısının kaydedileceği dosya yolu")

    entropy_parser = subparsers.add_parser(
        "scan-entropy",
        help="Shannon entropisi ile kaynak kodundaki potansiyel sır ve API anahtarlarını tarar (E5)",
        description="AST analizi ve Shannon entropi metriği ile kod tabanındaki yüksek rastgelelikli sırları tespit eder.",
    )
    entropy_parser.add_argument("target", nargs="?", default=".", help="Hedef projenin yolu (Varsayılan: '.')")
    entropy_parser.add_argument("--max-findings", type=int, default=25, help="Maksimum listelenecek bulgu sayısı (Varsayılan: 25)")

    attack_parser = subparsers.add_parser(
        "check-attack-surface",
        help="Proje bağımlılık grafını analiz ederek PageRank kritikliği ve saldırı yüzeyini hesaplar (E1)",
        description="networkx ile bağımlılık grafı kurarak en kritik paketleri, blast radius ve topolojiyi inceler.",
    )
    attack_parser.add_argument("target", nargs="?", default=".", help="Hedef projenin yolu (Varsayılan: '.')")
    attack_parser.add_argument("--top", type=int, default=10, help="Listelenecek en kritik paket sayısı (Varsayılan: 10)")

    typo_parser = subparsers.add_parser(
        "check-typosquatting",
        help="Paket adını PyPI popüler kütüphanelerine karşı typosquatting testine tabi tutar (E2)",
        description="Jaro-Winkler, Levenshtein, permütasyon ve homoglyph teknikleri ile typosquatting analizi yapar.",
    )
    typo_parser.add_argument("package_name", help="Denetlenecek şüpheli paket adı (örn: reqeusts, colorma)")

    halluc_parser = subparsers.add_parser(
        "check-hallucinations",
        help="AI tarafından uydurulan (halüsinasyon) standart kütüphane sembollerini, metodları ve argümanları tespit eder",
        description="AST ve sembol tablosu doğrulaması ile var olmayan importları ve uydurma API çağrılarını yakalar.",
    )
    halluc_parser.add_argument("target", nargs="?", default=".", help="Hedef projenin yolu (Varsayılan: '.')")
    halluc_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")


def register_architecture_subparsers(subparsers: Any) -> None:
    """Registers architectural metrics, forecasting, and export CLI commands."""
    cycles_parser = subparsers.add_parser(
        "check-cycles",
        help="Proje modülleri arasındaki döngüsel bağımlılıkları (circular imports) tespit eder (F4)",
        description="networkx ile import grafı kurarak dairesel bağımlılık döngülerini ve çözüm önerilerini raporlar.",
    )
    cycles_parser.add_argument("target", nargs="?", default=".", help="Hedef projenin yolu (Varsayılan: '.')")

    bound_parser = subparsers.add_parser(
        "check-boundaries",
        help="warden.config.yaml içindeki katman sınır sözleşmelerini (architecture_boundaries) AST ile denetler",
        description="Katmanlar arası yasaklı importları (örn. API -> raw DB) milisaniyeler içinde yakalar.",
    )
    bound_parser.add_argument("target", nargs="?", default=".", help="Hedef projenin yolu (Varsayılan: '.')")
    bound_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")

    ck_parser = subparsers.add_parser(
        "check-ck",
        help="Chidamber & Kemerer (CK) nesne yönelimli mimari karmaşıklık metriklerini ve mimari kokuları hesaplar (F1/F2)",
        description="WMC, DIT, NOC, CBO, RFC ve LCOM metrikleriyle God Class, Brain Class ve High Coupling kokularını tespit eder.",
    )
    ck_parser.add_argument("target", nargs="?", default="core", help="Taranacak dizin veya paket (Varsayılan: 'core')")
    ck_parser.add_argument("--top", type=int, default=15, help="Listelenecek en karmaşık sınıf sayısı (Varsayılan: 15)")
    ck_parser.add_argument("--smells-only", action="store_true", default=False, help="Yalnızca mimari kokusu olan sınıfları listele")
    ck_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")
    ck_parser.add_argument("--output", "-o", default=None, help="CK metrik raporunu JSON dosyasına kaydet")

    sarif_parser = subparsers.add_parser(
        "export-sarif",
        help="Denetim bulgularını OASIS SARIF v2.1.0 formatında dışa aktarır (I4)",
        description="GitHub Code Scanning ve CI/CD için SARIF formatında statik analiz raporu üretir.",
    )
    sarif_parser.add_argument("target", nargs="?", default=".", help="Hedef proje yolu (Varsayılan: '.')")
    sarif_parser.add_argument("--output", "-o", default="warden-results.sarif", help="Çıktı SARIF dosya yolu")
    sarif_parser.add_argument("--audit-id", type=int, default=None, help="Mevcut bir veritabanı audit ID'sinden üret")

    pdf_parser = subparsers.add_parser(
        "export-pdf",
        help="Denetim sonuçları için kurumsal PDF Executive Summary raporu üretir (I1)",
        description="Yönetici düzeyinde renkli rozetler, metrik tabloları ve aksiyon önerileri içeren PDF raporu üretir.",
    )
    pdf_parser.add_argument("target", nargs="?", default=".", help="Hedef proje yolu (Varsayılan: '.')")
    pdf_parser.add_argument("--output", "-o", default="warden-executive-report.pdf", help="Çıktı PDF dosya yolu")
    pdf_parser.add_argument("--audit-id", type=int, default=None, help="Mevcut bir veritabanı audit ID'sinden üret")

    query_parser = subparsers.add_parser(
        "query",
        help="Dashboard ve denetim verilerini doğal dil ile sorgular (Text-to-SQL) (G1)",
        description="Doğal dildeki soruları güvenli SQL sorgularına çevirerek veritabanında çalıştırır.",
    )
    query_parser.add_argument("query", help="Sorulacak doğal dil sorusu")
    query_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")
    query_parser.add_argument("--provider", default=None, help="Kullanılacak LLM sağlayıcısı (gemini, openai, ollama vb.)")

    classify_parser = subparsers.add_parser(
        "classify",
        help="Proje arketipini (FastAPI, Django, CLI, ML, Library) ve dinamik kalite ağırlıklarını analiz eder (C1)",
        description="Deponun mimari özelliklerini analiz ederek proje arketipini ve özelleştirilmiş kalite ağırlıklarını gösterir.",
    )
    classify_parser.add_argument("target", nargs="?", default=".", help="Hedef proje dizini (Varsayılan: '.')")
    classify_parser.add_argument("--weights", action="store_true", default=False, help="Dinamik ağırlıklandırma tablosunu detaylı göster")
    classify_parser.add_argument("--override", action="append", default=None, help="Ağırlık ezme")
    classify_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")

    forecast_parser = subparsers.add_parser(
        "forecast",
        help="Denetim geçmişi üzerinden gelecek kod kalitesi ve teknik borç trendini tahminler (C3)",
        description="Holt's Linear Exponential Smoothing ile gelecek denetim puanlarını ve erken uyarıları hesaplar.",
    )
    forecast_parser.add_argument("target", nargs="?", default=".", help="Hedef proje yolu (Varsayılan: '.')")
    forecast_parser.add_argument("--horizon", type=int, default=5, help="Gelecek tahmin adım sayısı (Varsayılan: 5)")
    forecast_parser.add_argument("--dimension", default="total", choices=["total", "all"], help="Tahmin edilecek boyut ('total' veya 'all')")
    forecast_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")
    forecast_parser.add_argument("--output", "-o", default=None, help="Tahmin raporunu JSON dosyasına kaydet")

    anomaly_parser = subparsers.add_parser(
        "anomaly",
        help="Proje denetim skorlarındaki çok değişkenli korelasyon, kovaryans ve yapısal anomalileri tespit eder (C4)",
        description="Mahalanobis kovaryans mesafesi, Autoencoder rekonstrüksiyon hatası ve Isolation Forest ile kök neden analizi yapar.",
    )
    anomaly_parser.add_argument("target", nargs="?", default=".", help="Hedef proje yolu veya denetim ID (Varsayılan: '.')")
    anomaly_parser.add_argument("--audit-id", type=int, default=None, help="Spesifik bir denetim ID'sini analiz et")
    anomaly_parser.add_argument("--method", default="hybrid", choices=["hybrid", "mahalanobis", "autoencoder", "isolation_forest"], help="Kullanılacak anomali algoritması (Varsayılan: 'hybrid')")
    anomaly_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")
    anomaly_parser.add_argument("--output", "-o", default=None, help="Anomali raporunu JSON dosyasına kaydet")

    pr_parser = subparsers.add_parser(
        "pr-review",
        help="GitHub Pull Request için otomatik kalite kapısı, özet yorum ve inline inceleme yürütür (G4)",
        description="PR diff ve kod kalitesini denetler, GitHub API üzerinden upsert özet yorumu ve inline kod incelemesi yapar.",
    )
    pr_parser.add_argument("target", nargs="?", default=".", help="Hedef depo yolu (Varsayılan: '.')")
    pr_parser.add_argument("--pr", type=int, default=1, help="Pull Request numarası (Varsayılan: 1)")
    pr_parser.add_argument("--owner", default="owner", help="GitHub repo sahibi / organizasyon")
    pr_parser.add_argument("--repo", default="repo", help="GitHub repo adı")
    pr_parser.add_argument("--min-score", type=int, default=80, help="Minimum kalite kapısı eşiği (Varsayılan: 80)")
    pr_parser.add_argument("--post", action="store_true", default=False, help="GitHub API ile PR'a yorum ve inceleme gönder")
    pr_parser.add_argument("--token", default=None, help="GitHub API token")
    pr_parser.add_argument("--output", "-o", default=None, help="İnceleme Markdown raporunu dosyaya kaydet")
    pr_parser.add_argument("--init-workflow", action="store_true", default=False, help=".github/workflows/warden-pr-review.yml dosyasını oluştur")
    pr_parser.add_argument("--json", action="store_true", default=False, help="Sonuçları JSON formatında yazdır")


def build_argument_parser() -> argparse.ArgumentParser:
    """Builds and configures root ArgumentParser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="warden",
        description="🛡️ WARDEN: Autonomous Security & Architectural Quality Governance Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Örnek Kullanımlar:
  warden audit .                     # Mevcut dizindeki projeyi denetle
  warden audit /path/to/repo         # Belirtilen dizindeki projeyi denetle
  warden audit . --min-score 85      # Skor 85'in altındaysa hata döndür (CI/CD Quality Gate)
  warden serve --port 8000           # REST API & Swagger UI sunucusunu başlat
  warden --version                   # Sürüm bilgisini göster
        """,
    )
    parser.add_argument("--version", "-v", action="version", version="WARDEN v0.1.0")

    subparsers = parser.add_subparsers(dest="command", help="Kullanılabilir komutlar")
    register_core_subparsers(subparsers)
    register_testing_subparsers(subparsers)
    register_security_subparsers(subparsers)
    register_architecture_subparsers(subparsers)
    return parser
