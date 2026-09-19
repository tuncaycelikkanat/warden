# WARDEN Denetim ve Karne Modülü (System Audit & Scorecard)

## Mimari Tasarım Dokümanı

**Kapsam:** Bu belge, ana WARDEN mimari raporunu (bkz. `WARDEN-Gereksinim-Mimari-Raporu.md`) tamamlayan, **Faz 3 kapanış modülü** olarak konumlandırılan Denetim ve Karne (Audit & Scorecard) alt sistemini detaylandırır. Modül, ana sistemin bağımsız bir eklentisi değil, **mevcut servislerin (SecurityScanner, PackageIntegrityChecker, TechDebtTracker) tüm repo genelinde çalıştırılıp sonuçlarının birleştirildiği bir orkestrasyon katmanıdır.**

---

## İçindekiler

1. Motivasyon ve Konumlandırma
2. Gereksinimler
3. Mimari Genel Bakış
4. Bileşen Tasarımı
5. Puanlama Algoritması
6. Veri Modeli
7. Tetikleme Noktaları (CLI / VS Code / MCP)
8. LLM Executive Summary Tasarımı
9. Rapor Çıktı Formatı
10. Test Stratejisi
11. Risk Analizi

---

## 1. Motivasyon ve Konumlandırma

Ana WARDEN sistemi, dosya kaydetme veya commit anında **tek bir değişikliği** değerlendiren, olay-tetiklemeli (event-driven) bir güvence katmanıdır. Ancak geliştiricinin zaman zaman ihtiyaç duyduğu farklı bir soru vardır: *"Şu anda elimdeki bütün proje ne durumda?"* — özellikle bir projeyi devraldığında, uzun bir sürenin ardından geri döndüğünde veya bir sürüm (release) öncesinde.

Bu modül, olay-tetiklemeli mikro-kararlar yerine **isteğe bağlı, kapsamlı bir "sağlık raporu"** üretir. Teknik olarak yeni bir analiz motoru gerektirmez — var olan üç servisi (SecurityScanner, PackageIntegrityChecker, TechDebtTracker) tek dosya yerine **tüm repo** üzerinde paralel çalıştırıp, sonuçları kategorize edilmiş bir puan kartında birleştiren bir orkestrasyon katmanıdır. Bu nedenle geliştirme maliyeti düşüktür ve doğal olarak projenin en sonuna, "her şeyin birbirine bağlandığını gösteren kapanış modülü" olarak yerleştirilmiştir.

### 1.1 Ana Rapordan Farkı

| | Ana WARDEN (olay-tetiklemeli) | Denetim Modülü (isteğe bağlı, kapsamlı) |
|---|---|---|
| Tetikleme | Dosya kaydetme, commit | Kullanıcının açıkça istemesi |
| Kapsam | Tek dosya / tek diff | Tüm repo |
| Sıklık | Sürekli, arka planda | Nadiren (release öncesi, devralma sonrası) |
| Çıktı | Anlık uyarı (Problems paneli) | Kapsamlı rapor (Markdown/PDF) + puan kartı |

---

## 2. Gereksinimler

### 2.1 Fonksiyonel Gereksinimler

| No | Gereksinim | Öncelik |
|---|---|---|
| FR-A1 | Sistem, bir kullanıcı isteği üzerine ("audit" komutu, VS Code komutu veya MCP tool çağrısı) belirtilen repo'daki tüm ilgili dosyaları paralel olarak SecurityScanner'dan geçirebilmelidir. | Yüksek |
| FR-A2 | Sistem, `requirements.txt`/`pyproject.toml`/`package.json` dosyalarını ayrıştırıp, listelenen her bağımlılığı hem PackageIntegrityChecker'daki güven kontrolünden hem de bilinen zafiyet veritabanı (OSV.dev) sorgusundan geçirebilmelidir. | Yüksek |
| FR-A3 | Sistem, mevcut TechDebtTracker'ın en güncel snapshot'ını (churn, tekrar oranı, refactor oranı) denetim raporuna dahil edebilmelidir. | Orta |
| FR-A4 | Sistem, `radon` (döngüsel karmaşıklık) ve `ruff` (lint hata sayısı) araçlarını tüm repo üzerinde çalıştırıp Kod Karmaşıklığı ve Stil kategorileri için ham veri üretebilmelidir. | Orta |
| FR-A5 | Sistem, on ham veri kaynağını (bkz. Bölüm 5) 0-100 arası kategori puanlarına ve ağırlıklı bir genel puana dönüştürebilmelidir. | Yüksek |
| FR-A6 | Sistem, isteğe bağlı olarak (varsayılan kapalı), yalnızca bulgu **metadatasını** (dosya adı, kural adı, önem derecesi — ham kod içeriği değil) bir LLM'e göndererek yönetici özeti (executive summary) üretebilmelidir. | Düşük |
| FR-A7 | Sistem, denetim sonucunu bir Markdown raporu olarak diske yazabilmeli ve isteğe bağlı olarak PDF'e dönüştürebilmelidir. | Orta |
| FR-A8 | Denetim işlemi, VS Code Command Palette'ten ("WARDEN: Generate Project Scorecard"), CLI'dan (`warden audit`) ve MCP aracı (`run_full_audit`) olarak üç farklı yoldan tetiklenebilmelidir. | Yüksek |
| FR-A9 | Sistem, `git log`/`git diff` geçmişini `gitleaks` ile tarayarak, mevcut kodda görünmese bile geçmiş commit'lerde kalmış (silinmiş ama hâlâ Git tarihçesinde erişilebilir) API anahtarı/parola sızıntılarını tespit edebilmelidir. | Yüksek |
| FR-A10 | Sistem, `coverage.py` çıktısını okuyarak (varsa) test kapsama yüzdesini raporlayabilmeli; test/coverage verisi bulunamazsa bunu "ölçülemedi" olarak açıkça belirtmelidir. | Orta |
| FR-A11 | Sistem, `interrogate` ile docstring kapsama oranını ve README dosyasında kurulum/kullanım bölümlerinin varlığını kontrol ederek bir Dokümantasyon puanı üretebilmelidir. | Düşük |
| FR-A12 | Sistem, boş `except:` blokları, yakalanıp yutulan (swallow edilen) istisnalar ve ağ çağrılarında eksik timeout gibi dayanıklılık paternlerini basit bir AST taramasıyla tespit edebilmelidir. | Düşük |
| FR-A13 | Sistem, `jscpd` ile kod tekrarı oranını, TechDebtTracker'ın churn/refactor metriklerinden **ayrı bir kategori** olarak raporlayabilmelidir. | Orta |
| FR-A14 | Sistem, denetlenen projenin bağımlılıklarını, dizin yapısını ve yapılandırma dosyalarını inceleyerek bir **proje profili** çıkarmalı; önceden tanımlı bir kategori kataloğundan, o projeye özgü en fazla 5 ek kategoriyi (Katman 2) otomatik olarak seçebilmelidir. | Yüksek |
| FR-A15 | Katman 2 kategorilerinin seçimi, LLM'in serbest yorumuna değil, **versiyonlanmış ve denetlenebilir sinyal→kategori eşleme kurallarına** dayanmalı; her açılan kategori için "hangi sinyal nedeniyle açıldığı" raporda gösterilebilmelidir. | Yüksek |
| FR-A16 | Sistem, her kategori puanını **kaynağına göre etiketlemelidir**: mekanik ölçümle mi (⚙️) yoksa rubrik destekli LLM değerlendirmesiyle mi (🧠) üretildiği raporda açıkça ayırt edilmelidir. | Yüksek |
| FR-A17 | LLM tabanlı değerlendirme yapılan her kategori için, 3/6/9 puan seviyelerinin ne anlama geldiğini somut olarak tanımlayan **çapalı bir rubrik** (anchored rubric) kullanılmalı; LLM'den serbest puan vermesi değil, rubrik seviyelerinden birini gerekçesiyle seçmesi istenmelidir. | Yüksek |
| FR-A18 | Her denetim kaydı, o denetimde kullanılan kategori kümesini ve ağırlıklarını özetleyen bir **profil imzası** (`profile_signature`) içermelidir; zaman içindeki puan trendi yalnızca aynı imzaya sahip denetimler arasında karşılaştırılmalıdır. | Orta |

### 2.2 Fonksiyonel Olmayan Gereksinimler

| No | Gereksinim |
|---|---|
| NFR-A1 | Orta ölçekli bir repo (≈200 dosya) için tam denetim süresi 60 saniyenin altında kalmalıdır (paralel tarama ile). |
| NFR-A2 | LLM'e gönderilen veri, hiçbir koşulda ham kod satırı içermemeli — yalnızca kural adı, dosya yolu, satır numarası ve önem derecesi gibi metadata gönderilmelidir (ana rapordaki Bölüm 12 Gizlilik Tasarımı ile tutarlılık). |
| NFR-A3 | OSV.dev sorguları başarısız olursa (ağ hatası, rate limit), sistem zafiyet kontrolünü atlayıp bunu raporda açıkça "kontrol edilemedi" olarak belirtmeli; sessizce başarılı gibi davranmamalıdır. |

---

## 3. Mimari Genel Bakış

```
                          ┌────────────────────────┐
   "warden audit" /       │   AuditOrchestrator      │
   VS Code komutu /       │   Service                │
   MCP: run_full_audit ──►│                          │
                          └────────────┬─────────────┘
                                       │
                    ┌──────────────────▼──────────────────┐
                    │  1) ProjectProfilerService (4.8)      │
                    │  Bağımlılık/dizin/config sinyalleri → │
                    │  hangi dinamik kategoriler açılacak?  │
                    └──────────────────┬──────────────────┘
                                       │
          ┌────────────────────────────┴────────────────────────────┐
          ▼ (paralel)                                                ▼ (paralel)
┌──────────────────────────┐                    ┌──────────────────────────────┐
│ 2) KATMAN 1 — Çekirdek    │                    │ 3) KATMAN 2 — Dinamik         │
│ 10 mekanik servis         │                    │ RubricEvaluatorService (4.9)  │
│ (Semgrep, gitleaks,       │                    │ çapalı rubrik + kanıt paketi  │
│ OSV.dev, radon, ruff,     │                    │ ile 0-5 kategori              │
│ jscpd, git, coverage,     │                    │                               │
│ interrogate, AST)         │                    │ ⚙️ LLM YOK                     │
│ ⚙️ LLM YOK                 │                    │ 🧠 LLM burada devreye girer    │
└────────────┬─────────────┘                    └───────────────┬──────────────┘
             └────────────────────┬───────────────────────────---┘
                                  ▼
                     ┌─────────────────────────┐
                     │ 4) ScorecardAggregator    │
                     │ %60 çekirdek + %40 dinamik│
                     │ + profile_signature       │
                     └──────────┬──────────────┘
                                │
                    ┌───────────┴────────────┐
                    ▼ (isteğe bağlı)          ▼ (her zaman)
          ┌──────────────────┐      ┌──────────────────────┐
          │ LLM Executive     │      │ Markdown/PDF Report    │
          │ Summary (yalnızca │      │ Generator              │
          │ metadata gider)   │      │                        │
          └──────────┬────────┘      └───────────┬────────────┘
                     └──────────────────┬─────────┘
                                        ▼
                         audit_reports + audit_dynamic_categories
                         (SQLite) + rapor dosyası (disk)
```

Katman 1'deki on servis, önceki tasarımın genişletilmiş halidir: Kod Kalitesi ikiye ayrıldı (Karmaşıklık + Stil), Teknik Borç'tan Kod Tekrarı çıkarıldı ve dört yeni servis eklendi (SecretLeakScanner, TestCoverageAnalyzer, DocumentationAnalyzer, ResilienceAnalyzer). Katman 2 ise tamamen yeni bir katmandır — projeye göre değişen, rubrik destekli anlamsal değerlendirme.

Bu mimari, ana WARDEN raporundaki **Ports-and-Adapters** desenini takip eder: `AuditOrchestratorService`, mevcut servisleri doğrudan import edip çağırır (yeniden yazmaz), yalnızca "tüm repo üzerinde çalıştır, profile göre genişlet ve sonuçları birleştir" sorumluluğunu üstlenir. Her iki katmanın servisleri de kendi içinde paralel çalışır; bu nedenle kategori sayısının artması denetim süresini doğrusal olarak artırmaz (NFR-A1'deki 60 saniyelik hedef geçerliliğini korur).

---

## 4. Bileşen Tasarımı

### 4.1 AuditOrchestratorService

```python
class AuditOrchestratorService:
    async def run_full_audit(self, repo_path: Path) -> AuditReport:
        # 1) Profil çıkar — hangi dinamik kategoriler açılacak? (4.8)
        profile = await self._profiler.profile(repo_path)

        # 2) Katman 1 — çekirdek servisleri paralel çalıştır (mekanik, LLM yok)
        files = self._discover_source_files(repo_path)
        core_results = dict(zip(CORE_KEYS, await asyncio.gather(
            self._security.scan_files(files),
            self._secret_leak.scan_history(repo_path),
            self._deps.check_manifest(repo_path),
            self._complexity.analyze(repo_path),
            self._lint.analyze(repo_path),
            self._duplication.analyze(repo_path),
            self._debt.get_latest_snapshot(repo_path),
            self._coverage.analyze(repo_path),
            self._docs.analyze(repo_path),
            self._resilience.analyze(repo_path),
        )))

        # 3) Katman 2 — seçilen her kategori için çapalı rubrik değerlendirmesi (4.9)
        dynamic_verdicts = dict(zip(
            [c.key for c in profile.dynamic_categories],
            await asyncio.gather(*[
                self._rubric.evaluate(c.key, self._collect_evidence(c, repo_path, core_results))
                for c in profile.dynamic_categories
            ]),
        ))

        # 4) İki katmanı birleştir
        scorecard = ScorecardAggregator.aggregate(core_results, dynamic_verdicts, profile)

        return AuditReport(
            repo_path=str(repo_path),
            profile=profile,
            scorecard=scorecard,
            raw_findings=core_results,
            dynamic_verdicts=dynamic_verdicts,
        )
```

**Tasarım Notu:** Bu servis, on alt servisi *doğrudan çağırır* — yeni bir güvenlik kuralı veya puanlama mantığı yazmaz. Katman 1 tamamen mekaniktir (hiçbir LLM çağrısı içermez); LLM yalnızca 3. adımda, kanıt paketine ve çapalı rubriğe bağlı kalarak devreye girer. Bu ayrım, hem gizlilik hem de puan enflasyonu açısından tasarımın omurgasıdır.

### 4.2 DependencyHealthService (Yeni Bileşen — OSV.dev Entegrasyonu)

Ana rapordaki `PackageIntegrityCheckerService`den farkı: o servis *kurulum anında tek bir paketi* kontrol ederken, bu servis *tüm manifest dosyasını* tarar ve ayrıca **bilinen CVE/zafiyet veritabanını** (OSV.dev — Google'ın işlettiği, ücretsiz, API anahtarı gerektirmeyen açık kaynak zafiyet veritabanı) sorgular.

```python
class DependencyHealthService:
    async def check_manifest(self, repo_path: Path) -> DependencyHealthResult:
        packages = self._parse_manifest(repo_path)  # requirements.txt / pyproject.toml
        results = []
        for pkg in packages:
            integrity = await self._integrity_checker.check(pkg.name, pkg.ecosystem)
            vulns = await self._query_osv(pkg.name, pkg.version, pkg.ecosystem)
            results.append(PackageAuditEntry(
                name=pkg.name,
                integrity_verdict=integrity,
                known_vulnerabilities=vulns,
            ))
        return DependencyHealthResult(entries=results)

    async def _query_osv(self, name: str, version: str, ecosystem: str) -> list[Vulnerability]:
        # POST https://api.osv.dev/v1/query — ücretsiz, key gerektirmez
        payload = {"package": {"name": name, "ecosystem": ecosystem}, "version": version}
        response = await self._http.post("https://api.osv.dev/v1/query", json=payload)
        return [Vulnerability.from_osv(v) for v in response.json().get("vulns", [])]
```

**Önemli fark:** Bu, ana raporun sohbet içinde bahsedilen "eski/terk edilmiş paket" tespitinden bir adım öteye geçer — **gerçek, bilinen güvenlik açıklarını (CVE)** de yakalar. Bu, jüri karşısında "sadece heuristik değil, gerçek bir zafiyet veritabanına dayanıyor" diyebilmen için önemli bir fark.

### 4.3 CodeComplexityService & LintStyleService (Yeni Bileşenler — önceki tek CodeQualityAnalyzer'ın ayrıştırılmış hali)

```python
class CodeComplexityService:
    async def analyze(self, repo_path: Path) -> ComplexityResult:
        complexity = await self._run_radon(repo_path)
        return ComplexityResult(
            avg_complexity=complexity.average,
            high_complexity_files=complexity.files_above_threshold(10),
        )

class LintStyleService:
    async def analyze(self, repo_path: Path) -> LintResult:
        issues = await self._run_ruff(repo_path)
        return LintResult(error_count=len(issues), issues_by_rule=self._group_by_rule(issues))
```

**Tasarım Notu:** Bilinçli olarak "vibe coding standartlarına uyum" gibi öznel bir ölçüt yerine, **radon'un döngüsel karmaşıklık skoru** ve **ruff'un lint hata sayısı** gibi tamamen nesnel, sektörde kabul görmüş metrikler kullanılmıştır. Bu, "bu standardı kim belirledi?" sorusuna karşı savunulabilir bir temel sağlar. İkisinin ayrı kategori olarak sunulması, karmaşık ama temiz-stilli bir kod tabanı ile basit ama dağınık bir kod tabanı arasındaki farkı gizlemeden gösterir.

### 4.4 SecretLeakScannerService (Yeni Bileşen — Git Geçmişi Taraması)

Ana rapordaki `SecurityScannerService`den farkı: o servis *çalışma anındaki dosya içeriğini* tarar, bu servis ise **`gitleaks` ile tüm Git commit geçmişini** tarar — bir geliştirici bir API anahtarını commit edip bir sonraki commit'te sildiğinde bile, anahtar Git tarihçesinde kalıcı olarak erişilebilir kalır. Bu, tek dosya taramasının yapısal olarak göremeyeceği bir risk sınıfıdır.

```python
class SecretLeakScannerService:
    async def scan_history(self, repo_path: Path) -> SecretLeakResult:
        raw = await self._run_subprocess(["gitleaks", "detect", "--source", str(repo_path), "--report-format", "json"])
        findings = json.loads(raw)
        return SecretLeakResult(
            leaked_secrets=[LeakedSecret.from_gitleaks(f) for f in findings],
        )
```

### 4.5 TestCoverageAnalyzerService (Yeni Bileşen)

```python
class TestCoverageAnalyzerService:
    async def analyze(self, repo_path: Path) -> CoverageResult:
        report = await self._run_coverage(repo_path)  # coverage.py, --format=json
        if report is None:
            return CoverageResult(measured=False, coverage_pct=None)
        return CoverageResult(measured=True, coverage_pct=report.total_percent)
```

**Not (NFR-A ile tutarlılık):** Eğer projede hiç test/coverage yapılandırması yoksa, sistem bunu sessizce "0/100" olarak cezalandırmaz — "ölçülemedi" olarak işaretler ve genel puana dahil etmez (ağırlığı diğer kategorilere orantılı dağıtılır). Bu, henüz test yazmamış erken aşama projelerde adaletsiz bir ceza puanı verilmesini önler.

### 4.6 DocumentationAnalyzerService (Yeni Bileşen)

```python
class DocumentationAnalyzerService:
    async def analyze(self, repo_path: Path) -> DocumentationResult:
        docstring_coverage = await self._run_interrogate(repo_path)
        readme_check = self._check_readme_sections(repo_path)  # kurulum/kullanım bölümü var mı?
        return DocumentationResult(
            docstring_coverage_pct=docstring_coverage,
            has_readme_setup_section=readme_check.has_setup,
            has_readme_usage_section=readme_check.has_usage,
        )
```

### 4.7 ResilienceAnalyzerService (Yeni Bileşen — Basit AST Taraması)

Hazır bir araç yerine, projede zaten kullanılan Python `ast` modülüyle basit bir tarama: boş `except:` blokları, yakalanıp hiçbir şey yapılmadan geçilen (`except: pass`) istisnalar, ve `requests`/`httpx` çağrılarında `timeout` parametresi eksikliği gibi paternler.

```python
class ResilienceAnalyzerService:
    async def analyze(self, repo_path: Path) -> ResilienceResult:
        findings = []
        for file in self._python_files(repo_path):
            tree = ast.parse(file.read_text())
            findings += self._find_bare_except(tree, file)
            findings += self._find_missing_timeout(tree, file)
        return ResilienceResult(findings=findings)
```

**Dürüst sınır:** Bu servis, Semgrep gibi olgun bir motor değil, kendi yazdığın basit bir AST taraması olduğundan yanlış pozitif oranı diğer servislere göre daha yüksek olabilir — bu nedenle en düşük ağırlığa (bkz. Bölüm 5) sahiptir ve raporda "deneysel" olarak işaretlenmesi önerilir.

### 4.8 ProjectProfilerService (Yeni Bileşen — Dinamik Kategori Seçimi)

**Motivasyon:** Her projeye aynı on kategoriyle not vermek, bazı projelerde anlamsız kalır. Bir kripto ticaret motorunun "kantitatif mantığı", bir Minecraft modunun "oyun içi performansı", bir web uygulamasının "frontend deneyimi" — bunlar sabit bir kategori listesine sığmaz. Bu servis, denetimden **önce** çalışır ve projeye özgü ek kategorileri belirler.

**Kritik tasarım kararı:** Kategori seçimi LLM'in serbest yorumuna bırakılmaz. Bunun yerine, **versiyonlanmış bir sinyal→kategori eşleme kataloğu** kullanılır; böylece "bu kategori neden açıldı?" sorusunun cevabı bir kural olur, bir model kaprisi değil (FR-A15).

```python
CATEGORY_CATALOG = {
    "frontend_ux": {
        "label": "💻 Frontend & Kullanıcı Deneyimi",
        "signals": [
            DependencySignal(any_of=["react", "vue", "svelte", "next"]),
            FilePatternSignal(any_of=["**/*.tsx", "**/*.vue"], min_count=5),
        ],
    },
    "devops_deployment": {
        "label": "🚀 DevOps & Dağıtım",
        "signals": [FilePatternSignal(any_of=["Dockerfile", "docker-compose*.yml", "fly.toml", "render.yaml"])],
    },
    "quantitative_logic": {
        "label": "📈 Kantitatif & Matematiksel Mantık",
        "signals": [
            DependencySignal(any_of=["numba", "scipy", "optuna", "pandas-ta"]),
            DirectorySignal(any_of=["**/backtesting/", "**/optimization/"]),
        ],
    },
    "llm_integration": {
        "label": "🤖 LLM Entegrasyonu & Prompt Güvenliği",
        "signals": [
            DependencySignal(any_of=["anthropic", "openai", "google-genai", "ollama"]),
            DirectorySignal(any_of=["**/agents/", "**/prompts/"]),
        ],
    },
    "architectural_discipline": {
        "label": "🏗️ Mimari Disiplin (Katmanlı/DDD)",
        "signals": [DirectorySignal(all_of=["**/domain/", "**/entities/"])],
    },
    "api_design": {
        "label": "🔌 API Tasarımı",
        "signals": [DependencySignal(any_of=["fastapi", "flask", "django", "express"])],
    },
    "concurrency_safety": {
        "label": "🔀 Eşzamanlılık & Yarış Durumu Güvenliği",
        "signals": [SourcePatternSignal(any_of=["asyncio.gather", "threading.Lock", "multiprocessing"])],
    },
}

class ProjectProfilerService:
    MAX_DYNAMIC_CATEGORIES = 5

    async def profile(self, repo_path: Path) -> ProjectProfile:
        matched = []
        for key, spec in CATEGORY_CATALOG.items():
            hits = [s for s in spec["signals"] if s.matches(repo_path)]
            if hits:
                matched.append(MatchedCategory(key=key, label=spec["label"], evidence=hits))

        # En güçlü eşleşen ilk N kategori (kanıt sayısına göre sıralanır)
        matched.sort(key=lambda m: len(m.evidence), reverse=True)
        selected = matched[: self.MAX_DYNAMIC_CATEGORIES]

        return ProjectProfile(
            dynamic_categories=selected,
            signature=self._compute_signature(selected),   # FR-A18
            catalog_version=CATALOG_VERSION,
        )
```

**Kategori sayısı neden 5 ile sınırlı?** Kategori sayısı arttıkça her birinin ağırlığı düşer ve karne "her şey ortalama" görünümüne kayar. Beş sınırı, Katman 2'nin toplam %40'lık payının anlamlı parçalara bölünmesini sağlar.

### 4.9 RubricEvaluatorService (Yeni Bileşen — Çapalı Değerlendirme)

Katman 2'deki kategoriler (mimari disiplin, kantitatif mantık, LLM güvenliği gibi) hiçbir araçla mekanik olarak ölçülemez — bunlar anlamsal yargı gerektirir. Ancak LLM'e doğrudan "bu projeye kaç puan verirsin?" sorulduğunda, sistematik olarak **cömert davranma eğilimi** (puan enflasyonu) gösterir; sonuçta her projeye 8-9 veren bir karne hiçbir bilgi taşımaz.

Bu servis, bu sorunu **çapalı rubrik (anchored rubric)** ile çözer: LLM'den serbest bir sayı değil, önceden tanımlı seviyelerden birini **kanıt göstererek** seçmesi istenir.

```python
RUBRICS = {
    "architectural_discipline": {
        3: "Katman ayrımı yok; iş mantığı, veri erişimi ve sunum aynı dosyalarda karışık.",
        6: "Katmanlar isimlendirilmiş ama sızıntı var (ör. domain katmanı doğrudan ORM/HTTP'ye bağımlı).",
        9: "Katmanlar net ayrılmış, bağımlılıklar tek yöne akıyor, domain dış dünyadan izole.",
    },
    "quantitative_logic": {
        3: "Sabit eşikli, doğrulanmamış hesaplamalar; geçmiş veri testi yok.",
        6: "Backtest var ama tek dönemde; aşırı uyumlama (overfitting) önlemi yok.",
        9: "Walk-forward doğrulama, parametre duyarlılık analizi ve çoklu metrikli uygunluk fonksiyonu mevcut.",
    },
    "llm_integration": {
        3: "Prompt'lar kodda gömülü, harici metin doğrudan prompt'a enjekte ediliyor, hata yönetimi yok.",
        6: "Prompt'lar ayrıştırılmış, temel hata yönetimi var; ancak enjeksiyon savunması veya maliyet kontrolü eksik.",
        9: "Prompt sanitizasyonu, sağlayıcı yedeklemesi (fallback), maliyet/gecikme takibi ve denetim logu mevcut.",
    },
    # ... katalogdaki her Katman 2 kategorisi için bir rubrik tanımlanır
}

class RubricEvaluatorService:
    async def evaluate(self, category_key: str, evidence: CategoryEvidence) -> RubricVerdict:
        rubric = RUBRICS[category_key]
        prompt = self._build_prompt(rubric, evidence)   # kanıt: dosya listesi, metrikler, bulgu özetleri
        raw = await self._llm.complete(prompt, response_format="json")
        verdict = RubricVerdict.parse(raw)              # {"level": 6, "justification": "...", "cited_evidence": [...]}

        if verdict.level not in rubric:
            raise InvalidRubricLevel(category_key, verdict.level)
        return verdict
```

**Enflasyona karşı ek önlem:** LLM'den seçtiği seviyeyi **hangi somut kanıta dayandırdığını** (dosya yolu, metrik değeri, bulgu kimliği) belirtmesi istenir; kanıt gösteremediği bir seviyeyi seçemez. Ayrıca ara değerler (4, 5, 7, 8) yalnızca iki çapa arasında gerekçelendirilebilirse kullanılır.

**Gizlilik notu:** Bu servise giden kanıt paketi, Bölüm 8'deki kuralla aynı kısıta tabidir — dosya yolları, metrik değerleri ve bulgu özetleri gönderilir, **ham kod satırları gönderilmez**.

---

## 5. Puanlama Algoritması

### 5.1 İki Katmanlı Yapı

Karne iki katmandan oluşur: her projede sabit olan **mekanik çekirdek** (%60) ve projeye göre değişen **dinamik katman** (%40).

```
┌──────────────────────────────────────────────────────────┐
│ KATMAN 1 — ÇEKİRDEK (sabit, %60)                          │
│ Araç destekli, tekrarlanabilir, LLM yargısı içermez        │
│ ⚙️ Güvenlik · Sızıntı · Bağımlılık · Karmaşıklık · Stil ·   │
│    Tekrar · Teknik Borç · Test · Dokümantasyon · Hata      │
└──────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────┐
│ KATMAN 2 — PROJEYE ÖZGÜ (dinamik, %40)                    │
│ ProjectProfiler'ın seçtiği 0-5 kategori,                   │
│ RubricEvaluator ile çapalı olarak puanlanır                │
│ 🧠 Örn. bir ticaret motoru → Kantitatif Mantık, DevOps,     │
│    Frontend/UX, LLM Entegrasyonu                            │
│    Örn. küçük bir CLI aracı → hiçbiri (katman boş kalır,   │
│    ağırlık Katman 1'e devredilir)                           │
└──────────────────────────────────────────────────────────┘
```

### 5.2 Katman 1 — Çekirdek Kategoriler (toplam %60)

| Kategori | Ağırlık | Veri Kaynağı | Servis | Kaynak |
|---|---|---|---|---|
| 🛡️ Güvenlik | %12 | Semgrep tabanlı statik tarama | SecurityScanner (mevcut, tüm repo) | ⚙️ |
| 🔐 Gizli Bilgi Sızıntısı | %5 | Git geçmişi taraması | SecretLeakScannerService (4.4) | ⚙️ |
| 📦 Bağımlılık Sağlığı | %7 | Paket yaşı/güveni + OSV.dev CVE | DependencyHealthService (4.2) | ⚙️ |
| 🏗️ Kod Karmaşıklığı | %6 | Döngüsel karmaşıklık | CodeComplexityService (4.3) | ⚙️ |
| 🧹 Stil & Lint Tutarlılığı | %5 | Lint hata sayısı | LintStyleService (4.3) | ⚙️ |
| 🔁 Kod Tekrarı | %5 | Kopya kod oranı | (mevcut `jscpd` entegrasyonu) | ⚙️ |
| 📉 Teknik Borç (Churn) | %5 | Commit geçmişi analizi | TechDebtTracker (ana rapor 5.3.5) | ⚙️ |
| 🧪 Test Kapsamı | %7 | coverage.py | TestCoverageAnalyzerService (4.5) | ⚙️ |
| 📖 Dokümantasyon | %5 | Docstring + README kontrolü | DocumentationAnalyzerService (4.6) | ⚙️ |
| ⚠️ Hata Yönetimi & Dayanıklılık | %3 | Basit AST taraması | ResilienceAnalyzerService (4.7) | ⚙️ |

### 5.3 Katman 2 — Dinamik Kategoriler (toplam %40)

Seçilen kategori sayısı N ise, %40'lık pay bu N kategori arasında eşit bölünür (N=4 → her biri %10; N=0 → %40 Katman 1'e orantılı devredilir).

| Örnek Kategori | Ne zaman açılır | Kaynak |
|---|---|---|
| 📈 Kantitatif & Matematiksel Mantık | numba/scipy/optuna bağımlılığı veya backtest/optimization dizini | 🧠 |
| 💻 Frontend & Kullanıcı Deneyimi | react/vue/svelte bağımlılığı + 5'ten fazla `.tsx`/`.vue` dosyası | 🧠 |
| 🚀 DevOps & Dağıtım | Dockerfile/compose/fly.toml/render.yaml varlığı | 🧠 |
| 🤖 LLM Entegrasyonu & Prompt Güvenliği | anthropic/openai/google-genai bağımlılığı + agents/prompts dizini | 🧠 |
| 🏗️ Mimari Disiplin (Katmanlı/DDD) | domain/ + entities/ dizin yapısı | 🧠 |
| 🔌 API Tasarımı | fastapi/flask/django/express bağımlılığı | 🧠 |
| 🔀 Eşzamanlılık Güvenliği | asyncio.gather/threading.Lock/multiprocessing kullanımı | 🧠 |

### 5.4 Birleştirme Algoritması

```python
class ScorecardAggregator:
    CORE_WEIGHTS = {
        "security": 0.12, "secret_leak": 0.05, "dependencies": 0.07,
        "complexity": 0.06, "lint_style": 0.05, "duplication": 0.05,
        "tech_debt": 0.05, "test_coverage": 0.07,
        "documentation": 0.05, "resilience": 0.03,
    }   # toplam 0.60
    DYNAMIC_LAYER_WEIGHT = 0.40

    @staticmethod
    def aggregate(core_results: dict, dynamic_verdicts: dict, profile: ProjectProfile) -> Scorecard:
        scores, weights = {}, {}

        # Katman 1 — mekanik puanlama, LLM yok
        for key, weight in ScorecardAggregator.CORE_WEIGHTS.items():
            result = core_results.get(key)
            if result is None or getattr(result, "measured", True) is False:
                continue   # "ölçülemedi": ağırlık yeniden dağıtılır
            scores[key] = ScorecardAggregator._score_core(key, result)
            weights[key] = weight

        # Katman 2 — rubrik seviyesi 0-100'e ölçeklenir
        n = len(dynamic_verdicts)
        if n:
            per_category = ScorecardAggregator.DYNAMIC_LAYER_WEIGHT / n
            for key, verdict in dynamic_verdicts.items():
                scores[key] = verdict.level * 10        # rubrik 0-10 → 0-100
                weights[key] = per_category

        # Eksik/ölçülemeyen kategorilerin ağırlığı kalanlara orantılı dağıtılır
        total = sum(weights.values())
        overall = sum(scores[k] * (weights[k] / total) for k in scores)

        return Scorecard(
            category_scores=scores,
            category_weights=weights,
            overall=round(overall, 1),
            profile_signature=profile.signature,     # FR-A18
        )
```

### 5.5 Ağırlık ve Tasarım Gerekçeleri

**Neden %60/%40?** Çekirdeğin çoğunluğu elinde tutması, karnenin tekrarlanabilir ve projeler arası kıyaslanabilir kalmasını sağlar; dinamik katman ise karnenin o projeye gerçekten hitap etmesini sağlar. Dinamik katman çoğunluğu alsaydı, iki farklı denetim arasındaki puan farkının ne kadarının gerçek değişimden, ne kadarının kategori seçimindeki kaymadan geldiği belirsizleşirdi.

**Çekirdek içindeki dağılım:** Güvenlik (%12) ve Gizli Bilgi Sızıntısı (%5) birlikte en büyük payı oluşturur — WARDEN'ın var oluş nedeni öncelikle güvenliktir. Test Kapsamı (%7) yüksek tutulmuştur çünkü vibe coding literatüründeki en sık bulgulardan biri AI'nın test yazmayı atlama eğilimidir. Hata Yönetimi (%3) en düşük ağırlıktadır çünkü altyapısı (4.7) en az olgun, en yüksek yanlış-pozitif riskli servistir.

**Karşılaştırılabilirlik kısıtı (FR-A18):** Dinamik kategoriler proje değiştikçe — hatta aynı projede zaman içinde, yeni bir bağımlılık eklendiğinde — değişebilir. Bu nedenle her denetim kaydı bir `profile_signature` taşır ve **puan trendi yalnızca aynı imzaya sahip denetimler arasında çizilir.** İmza değiştiğinde trend grafiğinde bir kesme çizgisi gösterilir; farklı imzalı iki genel puanı doğrudan kıyaslamak metodolojik olarak hatalıdır.

**Genişlemeye Açık Kategoriler (Faz 4 / Vizyon):** Performans Profilleme (gerçek çalışma zamanı ölçümü gerektirir) ve Erişilebilirlik (frontend'e özgü, ayrı bir araç zinciri ister) katalog dışında bırakılmıştır.

**Not:** Bu ağırlıklar sabit bir "doğru cevap" değildir — savunmada "neden bu ağırlıklar?" sorusuna yukarıdaki gerekçelerle cevap verebilir, pilot kullanım sonrası kalibre edebilirsin.

---


## 6. Veri Modeli

```sql
-- Denetim başlığı: çekirdek kategoriler sabit sütunlarda, dinamik olanlar ayrı tabloda
CREATE TABLE audit_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,

    -- Katman 1 (çekirdek, her denetimde aynı)
    security_score REAL,
    secret_leak_score REAL,
    dependency_score REAL,
    complexity_score REAL,
    lint_style_score REAL,
    duplication_score REAL,
    tech_debt_score REAL,
    test_coverage_score REAL,
    documentation_score REAL,
    resilience_score REAL,

    overall_score REAL,
    profile_signature TEXT NOT NULL,  -- FR-A18: kategori kümesi + ağırlıkların özeti (hash)
    catalog_version TEXT NOT NULL,    -- hangi kategori kataloğu sürümüyle üretildi
    raw_findings_json TEXT,           -- tüm ham bulgular, JSON serileştirilmiş
    executive_summary TEXT,           -- LLM özeti (üretildiyse), aksi halde NULL
    report_file_path TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Katman 2: projeye göre değişen kategoriler, satır bazlı (şema değişmeden genişler)
CREATE TABLE audit_dynamic_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    audit_report_id INTEGER NOT NULL REFERENCES audit_reports(id) ON DELETE CASCADE,
    category_key TEXT NOT NULL,        -- ör. "quantitative_logic"
    category_label TEXT NOT NULL,      -- ör. "📈 Kantitatif & Matematiksel Mantık"
    weight REAL NOT NULL,
    rubric_level INTEGER,              -- LLM'in seçtiği çapa seviyesi (0-10)
    score REAL,                        -- 0-100'e ölçeklenmiş hali
    justification TEXT,                -- LLM'in gerekçesi
    cited_evidence_json TEXT,          -- gerekçenin dayandığı somut kanıtlar
    trigger_signals_json TEXT          -- FR-A15: bu kategori hangi sinyal(ler) nedeniyle açıldı
);

CREATE INDEX idx_audit_signature ON audit_reports(repo_path, profile_signature, created_at);
```

**Tasarım Notu:** Dinamik kategoriler sabit sütunlar yerine ayrı bir tabloda satır olarak tutulur — böylece kategori kataloğuna yeni bir kategori eklendiğinde veritabanı şeması değiştirilmek zorunda kalmaz.

Bu yapı, zaman içinde birden fazla denetim çalıştırıldığında **puan trendinin** izlenmesine de imkân tanır. Ancak trend sorgusu, `profile_signature` üzerinden filtrelenmelidir (bkz. Bölüm 5.5): imza değiştiyse, iki genel puan doğrudan kıyaslanabilir değildir ve arayüzde bu noktada bir kesme çizgisi gösterilir.

---

## 7. Tetikleme Noktaları

### 7.1 CLI
```bash
warden audit --repo /path/to/project --output report.md --with-summary
```

### 7.2 VS Code Komutu
Command Palette → **"WARDEN: Generate Project Scorecard"** → ilerleme çubuğu gösterilir (60 saniyeye kadar sürebileceğinden `withProgress` API'si kullanılır) → tamamlandığında rapor bir webview'de açılır.

### 7.3 MCP Aracı

```json
{
  "name": "run_full_audit",
  "description": "Projenin tamamı için güvenlik, bağımlılık, kod kalitesi ve teknik borç denetimi yapar; kategori bazlı bir puan kartı döner.",
  "input_schema": {
    "type": "object",
    "properties": {
      "repo_path": {"type": "string"},
      "include_executive_summary": {"type": "boolean", "default": false}
    },
    "required": ["repo_path"]
  }
}
```

Bu araç sayesinde Claude Code/Antigravity'ye "release'den önce tam bir denetim yap" dedirtebilirsin; ajan bu aracı çağırıp sonucu değerlendirebilir.

---

## 8. LLM Executive Summary Tasarımı

**Varsayılan olarak kapalıdır** (FR-A6, NFR-A2). Kullanıcı açıkça istediğinde devreye girer ve **yalnızca bulgu metadatası** gönderilir — asla ham kod satırı değil:

```json
{
  "security": {"critical": 2, "medium": 5, "top_issues": ["sql-string-concat (auth.py:42)", "hardcoded-secret (config.py:12)"]},
  "dependencies": {"vulnerable_packages": ["requests==2.25.0 (CVE-2023-XXXXX)"]},
  "code_quality": {"avg_complexity": 8.2, "lint_errors": 34},
  "tech_debt": {"churn_score": 0.71, "duplication_pct": 12.4}
}
```

LLM'e gönderilen prompt, bu özet JSON'u insan diline çevirip önceliklendirilmiş bir "önce şunları düzelt" listesi üretmesini ister. Bu tasarım, ana rapordaki Bölüm 12 (Güvenlik ve Gizlilik Tasarımı) ile tam tutarlıdır.

---

## 9. Rapor Çıktı Formatı

Rapor iskeleti, salt bir puan tablosu değil; okuyanın projeyi tanımadan da durumu kavrayabileceği bir yapıdadır. Bölüm sırası sabittir:

1. Başlık + genel puan
2. **İki katmanlı karne tablosu** (Kaynak sütunu ile — FR-A16)
3. Proje profili (hangi dinamik kategoriler neden açıldı — FR-A15)
4. Öncelikli bulgular (önem sırasına göre)
5. Güçlü yönler
6. Eksikler / teknik borçlar
7. Somut aksiyon önerileri
8. (İsteğe bağlı) LLM Yönetici Özeti

### Örnek Çıktı

```markdown
# WARDEN Proje Karnesi — crypto-mas
**Tarih:** 2026-08-20 · **Katalog:** v1.2 · **Profil İmzası:** `a3f2c9`

## Genel Puan: 79.6/100 🟢

### Katman 1 — Çekirdek (her projede ölçülür)

| Kategori | Puan | Durum | Kaynak |
|---|---|---|---|
| 🛡️ Güvenlik | 88/100 | 🟢 | ⚙️ Ölçüldü (Semgrep) |
| 🔐 Gizli Bilgi Sızıntısı | 95/100 | 🟢 | ⚙️ Ölçüldü (gitleaks) |
| 📦 Bağımlılık Sağlığı | 74/100 | 🟡 | ⚙️ Ölçüldü (OSV.dev) |
| 🏗️ Kod Karmaşıklığı | 81/100 | 🟢 | ⚙️ Ölçüldü (radon) |
| 🧹 Stil & Lint Tutarlılığı | 77/100 | 🟡 | ⚙️ Ölçüldü (ruff) |
| 🔁 Kod Tekrarı | 90/100 | 🟢 | ⚙️ Ölçüldü (jscpd) |
| 📉 Teknik Borç | 85/100 | 🟢 | ⚙️ Ölçüldü (git geçmişi) |
| 🧪 Test Kapsamı | 58/100 | 🔴 | ⚙️ Ölçüldü (coverage.py) |
| 📖 Dokümantasyon | 71/100 | 🟡 | ⚙️ Ölçüldü (interrogate) |
| ⚠️ Hata Yönetimi (deneysel) | 66/100 | 🟡 | ⚙️ Ölçüldü (AST) |

### Katman 2 — Bu Projeye Özgü

| Kategori | Puan | Durum | Kaynak |
|---|---|---|---|
| 📈 Kantitatif & Matematiksel Mantık | 90/100 | 🟢 | 🧠 Değerlendirildi (rubrik sv. 9) |
| 🤖 LLM Entegrasyonu & Prompt Güvenliği | 80/100 | 🟢 | 🧠 Değerlendirildi (rubrik sv. 8) |
| 🏗️ Mimari Disiplin (Katmanlı/DDD) | 90/100 | 🟢 | 🧠 Değerlendirildi (rubrik sv. 9) |
| 🚀 DevOps & Dağıtım | 70/100 | 🟡 | 🧠 Değerlendirildi (rubrik sv. 7) |

> ⚙️ = araçla mekanik ölçüm · 🧠 = çapalı rubrik üzerinden değerlendirme

## Proje Profili
Bu denetimde 4 dinamik kategori açıldı:
- **Kantitatif Mantık** ← `numba`, `optuna` bağımlılıkları + `engine/optimization/` dizini
- **LLM Entegrasyonu** ← `google-genai` bağımlılığı + `engine/llm_committee/` dizini
- **Mimari Disiplin** ← `domain/` + `domain/entities/` dizin yapısı
- **DevOps & Dağıtım** ← `Dockerfile`, `docker-compose.yml`, `fly.toml`

## Öncelikli Bulgular
1. **[Kritik]** `auth.py:42` — SQL sorgusu string birleştirme ile oluşturuluyor.
2. **[Yüksek]** `requests==2.25.0` paketinde bilinen bir zafiyet (CVE-2023-XXXXX) var.
3. **[Yüksek]** Test kapsamı %41 — `services/order_execution.py` hiç test edilmemiş.
4. **[Orta]** Git geçmişinde 1 ifşa olmuş API anahtarı — **rotasyon** önerilir.

## Güçlü Yönler
- Rubrik sv. 9: Walk-forward doğrulama ve parametre duyarlılık analizi mevcut.
- Rubrik sv. 9: Domain katmanı ORM/HTTP bağımlılığı içermiyor.

## Eksikler & Teknik Borçlar
- Test kapsamı kritik yürütme yollarında yetersiz.
- DevOps: Dockerfile mevcut ama veritabanı/cache servisleri compose'a dahil değil.

## Somut Aksiyon Önerileri
1. `order_execution.py` için birim test yaz (en yüksek puan kazanımı burada).
2. `requests` paketini güncelle.
3. İfşa olan API anahtarını iptal et ve yenile.
```

(Kullanıcı isteğe bağlı olarak `--with-summary` bayrağıyla, raporun sonuna LLM tarafından üretilmiş bir "Yönetici Özeti" paragrafı da ekletebilir.)

---


## 10. Test Stratejisi

| Test Türü | Kapsam |
|---|---|
| Birim testleri | ScorecardAggregator'ın puanlama formülünün doğruluğu (bilinen girdi → beklenen çıktı), her kategori için ayrı ayrı |
| Entegrasyon testi | AuditOrchestratorService'in sekiz alt servisi doğru şekilde paralel çağırdığının doğrulanması |
| OSV.dev entegrasyon testi | Bilinen zafiyetli bir paket (ör. eski bir `requests` sürümü) için gerçek API'den zafiyet dönüp dönmediğinin doğrulanması |
| gitleaks entegrasyon testi | Kasıtlı olarak eski bir commit'e gizli anahtar eklenmiş test repo'sunda sızıntının tespit edildiğinin doğrulanması |
| Coverage/Documentation testi | coverage/docstring verisi olmayan bir projede "ölçülemedi" durumunun doğru işlendiğinin, ağırlık normalizasyonunun doğru çalıştığının doğrulanması |
| ResilienceAnalyzer doğruluk testi | Bilinçli olarak boş `except`/eksik timeout içeren test dosyalarında yakalama oranı; yanlış pozitif oranının makul kalması |
| ProjectProfiler testi | Farklı sentetik repo yapılarında (frontend'li, Docker'lı, LLM'li, hiçbiri olmayan) doğru dinamik kategorilerin açıldığının ve 5 sınırının aşılmadığının doğrulanması |
| Rubrik determinizm testi | Aynı kanıt paketiyle RubricEvaluator birkaç kez çalıştırıldığında seçilen seviyenin ±1 bandında kalması (aşırı oynaklık, rubriğin yetersiz çapalandığını gösterir) |
| **Puan enflasyonu kalibrasyon testi** | Bilinçli olarak farklı kalite seviyelerinde hazırlanmış 3 referans repo (zayıf/orta/iyi) üzerinde denetim çalıştırılıp, puanların gerçekten ayrıştığının doğrulanması — hepsi 8+ alıyorsa rubrik/ağırlıklar yeniden kalibre edilmelidir |
| Profil imzası testi | Bir repo'ya yeni bir bağımlılık eklendiğinde imzanın değiştiğinin ve trend sorgusunun iki imzayı karıştırmadığının doğrulanması |
| Uçtan uca test | Kendi Crypto MAS/Omni-Agent repo'larından biri üzerinde tam denetim çalıştırılıp her iki katmanın da raporda eksiksiz üretildiğinin doğrulanması |
| Performans testi | NFR-A1'deki 60 saniye sınırının, artık profiler + rubrik LLM çağrılarıyla birlikte ~200 dosyalık bir repo'da hâlâ karşılandığının ölçümü |

---

## 11. Risk Analizi

| Risk | Olasılık | Etki | Azaltma |
|---|---|---|---|
| **Puan enflasyonu** — LLM'in Katman 2'de sistematik olarak cömert davranıp her projeye 8-9 vermesi, karneyi bilgisiz hale getirmesi | **Yüksek** | **Yüksek** | Çapalı rubrik (4.9); LLM'den kanıt göstermeden seviye seçememesi; 3 referans repo ile kalibrasyon testi (Bölüm 10); mekanik kategorilerde LLM'e hiç puan verdirilmemesi |
| Dinamik kategori seçiminin denetimler arası karşılaştırılabilirliği bozması | Orta | Orta | `profile_signature` ile trend segmentasyonu (FR-A18, Bölüm 5.5); imza değişiminde arayüzde kesme çizgisi |
| Kategori kataloğunun eksik/hatalı sinyal eşlemesi nedeniyle alakasız kategori açması | Orta | Düşük | Sinyallerin versiyonlanması; raporda "bu kategori hangi sinyalle açıldı" gösterimi (FR-A15), böylece hatalı eşleme kullanıcı tarafından görülebilir |
| OSV.dev API'sinin rate-limit'e takılması (çok sayıda paket sorgusu) | Orta | Orta | İstekler arasında küçük gecikme (throttling) eklenmesi; sonuçların yerel önbellekte (24 saat) tutulması |
| Büyük repo'larda 60 saniyelik hedefin aşılması (artık 8 alt servis + LLM çağrıları) | Orta | Düşük | Dosya sayısı bir eşiği aşarsa "tahmini süre" uyarısı; en yavaş servis (gitleaks tam geçmiş taraması) için atlanabilir bayrak; Katman 2 rubrik çağrılarının paralel yapılması |
| Puanlama ağırlıklarının keyfi görünmesi (akademik savunmada eleştiri konusu olabilir) | Düşük | Orta | Bölüm 5.5'teki gerekçelerin rapora/sunuma açıkça eklenmesi; pilot veriyle kalibrasyon |
| ResilienceAnalyzer'ın (kendi yazılmış AST kuralı) yüksek yanlış pozitif üretmesi | Orta | Düşük | En düşük ağırlık (%3) verilmesi ve raporda "deneysel" etiketiyle sunulması (bkz. 4.7) |
| Rubrik değerlendirmesinin LLM sağlayıcısına bağımlı olması (sağlayıcı değişince puanların kayması) | Orta | Orta | Rubrik seviyelerinin sağlayıcıdan bağımsız, somut metinlerle çapalanması; raporda kullanılan model sürümünün kaydedilmesi |
