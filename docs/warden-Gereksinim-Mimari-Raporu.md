# warden: Vibe Coding Ortamları için Bütünleşik Kod Kalitesi ve Güvenlik Güvence Sistemi

## Gereksinim Analizi ve Mimari Tasarım Raporu

**Belge Türü:** Bitirme Projesi Teknik Tasarım Raporu
**Sürüm:** 1.0
**Kurum:** Erciyes Üniversitesi, Yazılım Mühendisliği Bölümü

---

## İçindekiler

1. Giriş
2. Problem Tanımı ve Motivasyon
3. İlgili Çalışmaların ve Mevcut Çözümlerin Analizi
4. Gereksinim Analizi
5. Sistem Mimarisi
6. Veri Modeli
7. API Tasarımı
8. MCP Sunucu Tasarımı
9. Editör ve Araç Entegrasyonları
10. Senaryo Akışları (Sıra Diyagramları)
11. Teknoloji Yığını ve Gerekçelendirme
12. Güvenlik ve Gizlilik Tasarımı
13. Test Stratejisi
14. Faz Planı ve Yol Haritası
15. Risk Analizi
16. Başarı Kriterleri ve Değerlendirme Metrikleri
17. Sonuç ve Öneriler
18. Ekler

---

## 1. Giriş

### 1.1 Amaç

Bu belge, **warden** adı verilen sistemin gereksinim analizini ve mimari tasarımını detaylı biçimde ortaya koymaktadır. warden, "vibe coding" olarak adlandırılan, geliştiricilerin büyük dil modeli (LLM) tabanlı araçlarla (Cursor, GitHub Copilot, Claude Code, Google Antigravity vb.) doğal dil komutlarıyla kod ürettiği ve bu kodu detaylı biçimde incelemeden kabul etme eğiliminde olduğu geliştirme paradigmasının doğurduğu güvenlik, kalite ve mühendislik yetkinliği risklerini azaltmayı hedefleyen, editörden ve yapay zekâ sağlayıcısından bağımsız çalışabilen bir kod kalitesi güvence sistemidir.

### 1.2 Kapsam

Bu rapor şu bileşenleri kapsar:

- Sorunun nicel ve nitel gerekçelendirilmesi
- Fonksiyonel ve fonksiyonel olmayan gereksinimlerin tam listesi
- Katmanlı sistem mimarisi (Core Engine, entegrasyon adaptörleri)
- Veri modeli ve API sözleşmeleri
- Model Context Protocol (MCP) üzerinden ajan entegrasyonu tasarımı
- VS Code, IntelliJ IDEA, Claude Code ve Google Antigravity ile entegrasyon stratejileri
- Test, güvenlik ve yol haritası planları

### 1.3 Belge İçinde Kullanılan Kısaltmalar

| Kısaltma | Açıklama |
|---|---|
| LLM | Large Language Model (Büyük Dil Modeli) |
| MCP | Model Context Protocol |
| FR | Functional Requirement (Fonksiyonel Gereksinim) |
| NFR | Non-Functional Requirement (Fonksiyonel Olmayan Gereksinim) |
| CI/CD | Continuous Integration / Continuous Deployment |
| AST | Abstract Syntax Tree |
| SAST | Static Application Security Testing |
| IDE | Integrated Development Environment |
| API | Application Programming Interface |

---

## 2. Problem Tanımı ve Motivasyon

### 2.1 Vibe Coding Paradigmasının Yükselişi

2025-2026 döneminde yazılım geliştirme pratiği köklü bir değişim geçirmiştir. Geliştiriciler artık kodun büyük bir kısmını satır satır yazmak yerine, doğal dil talimatlarıyla bir yapay zekâ ajanına ürettirmekte ve üretilen kodu "işe yarıyor mu" testinden geçirip kabul etmektedir. Bu yaklaşım — literatürde "vibe coding" olarak adlandırılır — geliştirme hızını önemli ölçüde artırmış, ancak beraberinde sistematik ve ölçülebilir riskler getirmiştir.

### 2.2 Sorunun Nicel Boyutu

Yapılan sektör araştırmaları ve bağımsız güvenlik testleri, bu paradigmanın somut zafiyetlerini ortaya koymaktadır:

- Beş popüler vibe coding aracı ile geliştirilen on beş özdeş test uygulamasında toplam 69 güvenlik açığı tespit edilmiş, bunların altısı kritik seviyede sınıflandırılmıştır (eksik güvenlik başlıkları, veritabanı yapılandırma hataları, girdi doğrulama eksiklikleri, istemci tarafında API anahtarı ifşası, güvensiz bağımlılıklar ve yalnızca istemci tarafı kimlik doğrulaması gibi kategorilerde).
- Bağımsız kod inceleme platformlarının analizlerine göre, yapay zekâ ile ortak yazılan kodda insan tarafından yazılan koda kıyasla yaklaşık 1,7 kat daha fazla kritik hata tespit edilmektedir.
- Geliştiricilerin önemli bir kısmı, yapay zekânın ürettiği kodu üretime almadan önce tam olarak incelemediğini bildirmektedir.
- LLM'lerin var olmayan (halüsinasyon) paket isimleri önerme oranı ticari modellerde belirli bir yüzdeye, açık kaynak modellerde ise daha yüksek bir orana ulaşmaktadır; kötü niyetli aktörler bu öngörülebilir hayali isimleri önceden kayıt ettirerek "slopsquatting" adı verilen bir tedarik zinciri saldırısı gerçekleştirebilmektedir.
- Kod tabanı sağlığı metriklerinde, aynı dosyanın kısa aralıklarla tekrar tekrar değiştirilmesi (kod çalkalanması) ve kod tekrarında belirgin bir artış gözlemlenmekte, buna karşılık refactoring (yeniden yapılandırma) oranında düşüş yaşanmaktadır.
- Bazı deneysel çalışmalarda, yapay zekâ araçlarının geliştiriciyi "hızlandırdığı hissi" yarattığı, ancak üretilen kodu hata ayıklamaya harcanan sürenin kimi zaman kodu sıfırdan yazmaktan daha uzun olabildiği bulgusuna ulaşılmıştır.

### 2.3 Sorunun Kök Nedenleri

1. **Doğrulama açığı:** Geliştirme hızı, insan gözden geçirme kapasitesini aşmıştır. Bir geliştirici dakikada onlarca satır kod üretebiliyorken, aynı hızda anlamlı bir güvenlik/mimari incelemesi yapamamaktadır.
2. **Araç ekosisteminin parçalılığı:** Her vibe coding aracı (Cursor, Copilot, Claude Code, Antigravity) kendi kapalı ekosisteminde çalışmakta; ortak, taşınabilir bir güvence katmanı bulunmamaktadır.
3. **Geleneksel CI/CD test paketlerinin yetersizliği:** Mevcut test süitleri insan hızındaki geliştirme döngüsü için tasarlanmıştır; AI hızındaki üretim-tüketim döngüsünü yakalayacak gerçek zamanlı bir katman eksiktir.
4. **Farkındalık eksikliği:** Geliştiriciler, zaman içinde temel mühendislik yetkinliklerinin ne ölçüde AI'ya devredildiğinin farkında değildir; bu durum uzun vadede bir "yetkinlik erozyonu" riski taşımaktadır.

### 2.4 Projenin Konumlandırılması

warden, yukarıdaki dört kök nedenin her birine karşılık gelen bir bileşen tasarlayarak, bunları **tek, editör-bağımsız bir çekirdek motor** etrafında birleştirmeyi hedefler. Bu sayede geliştirici hangi aracı kullanırsa kullansın (VS Code, IntelliJ, Claude Code, Antigravity, düz terminal), aynı güvence seviyesinden faydalanabilir.

---

## 3. İlgili Çalışmaların ve Mevcut Çözümlerin Analizi

| Araç/Çözüm | Kapsadığı Alan | warden'dan Farkı |
|---|---|---|
| Semgrep, Bandit, ESLint-security | Statik güvenlik analizi (SAST) | Tekil dil/kural motoru; vibe coding'e özgü davranışsal paternleri (AI kabul oranı, çoklu-ajan görüş çatışması) hedeflemez |
| CodeRabbit, Codacy | Otomatik PR/code review | Tekil-ajan mimarisi; farklı uzmanlık rollerinin (güvenlik/performans/mimari) paralel ve çelişen görüş üretip sentezlenmesi mimarisi yoktur |
| Snyk, Dependabot | Bağımlılık güvenlik taraması | Var olan gerçek paketlerin bilinen zafiyetlerini tarar; henüz yayınlanmamış "hayali paket" tuzaklarını (slopsquatting) hedef almaz |
| GitClear (analitik raporlama) | Kod çalkalanması/refactoring analitiği | Salt raporlama; gerçek zamanlı editör içi müdahale veya ajan-seviyeli engelleme sunmaz |
| RescueTime ve benzeri üretkenlik araçları | Genel aktivite takibi | Kod-yazarlığı kaynağını (AI mi insan mı ürettiği) ayırt etmez |

**Sonuç:** Piyasada bu beş kategorinin her biri için ayrı ayrı noktasal çözümler bulunmakla birlikte, bunları **tek bir editör-bağımsız çekirdek üzerinde, hem geleneksel IDE'ler hem de agent-first platformlarla (MCP üzerinden) konuşacak şekilde birleştiren** bütünleşik bir sistem tespit edilmemiştir. warden'ın özgün değeri buradadır.

---

## 4. Gereksinim Analizi

### 4.1 Paydaş Analizi

| Paydaş | İlgi Alanı |
|---|---|
| Bireysel geliştirici (birincil kullanıcı) | Kendi kod tabanında güvenlik/kalite güvencesi, kişisel yetkinlik farkındalığı |
| Takım lideri / teknik lider | Ekip genelinde teknik borç ve güvenlik açığı görünürlüğü |
| Açık kaynak katkıcısı | PR'larda otomatik ön-inceleme |
| Akademik danışman / jüri | Ölçülebilir, doğrulanabilir mühendislik katkısı |

### 4.2 Fonksiyonel Gereksinimler

| No | Gereksinim | Öncelik |
|---|---|---|
| FR-1 | Sistem, bir dosya kaydedildiğinde veya bir kod bloğu bir AI aracı tarafından üretildiğinde, değişen kod parçasını statik güvenlik kurallarına (OWASP Top-10 alt kümesi: SQL injection, XSS, hardcoded credential, eksik input validation, güvensiz yetkilendirme) göre otomatik olarak taramalıdır. | Yüksek |
| FR-2 | Sistem, bir paket kurulum komutu (`pip install`, `npm install`, vb.) tespit edildiğinde, önerilen paket adını ilgili paket kayıt sunucusuyla (PyPI, npm) çapraz kontrol etmeli; paketin yayın tarihi, indirme sayısı ve popüler bir pakete olan isim benzerliği gibi sinyalleri değerlendirerek şüpheli/"hayali" paketleri işaretlemelidir. | Yüksek |
| FR-3 | Sistem, bir kod farkını (diff) insan diline çevirerek özetlemeli; değişikliğin ne yaptığını, hangi risk kategorisine girdiğini (düşük/orta/yüksek) ve hangi test senaryolarının eksik olabileceğini belirtmelidir. | Orta |
| FR-4 | Sistem, yüksek riskli (örn. kimlik doğrulama, ödeme, veri silme içeren) değişikliklerde, farklı uzmanlık rolleri (Güvenlik, Performans, Mimari, Test) üstlenen paralel yapay zekâ ajanlarını çalıştırıp; çelişen görüşlerini bir hakem ajan aracılığıyla sentezleyerek tek bir konsolide rapor üretmelidir. | Orta |
| FR-5 | Sistem, bir Git deposunun zaman içindeki commit geçmişini analiz ederek kod çalkalanması (aynı dosyanın kısa aralıklarla tekrar değişmesi), kod tekrarı oranı ve refactoring sıklığı metriklerini hesaplamalı ve haftalık/aylık trend raporu üretmelidir. | Orta |
| FR-6 | Sistem, geliştiricinin kod tabanındaki AI-üretimi/insan-üretimi satır oranını ve AI önerilerini değişiklik yapmadan kabul etme oranını izlemeli ve zaman içindeki değişimi bir panelde göstermelidir. | Düşük |
| FR-7 | Sistem, VS Code üzerinde bir eklenti aracılığıyla; tarama sonuçlarını Problems panelinde, teknik borç/kişisel metrik trendlerini ise bir yan panel (webview) üzerinde göstermelidir. | Yüksek |
| FR-8 | Sistem, bir MCP sunucusu aracılığıyla; `security_scan`, `check_package`, `explain_diff`, `run_review_board` adlı araçları dışa açmalı; bu araçlar Claude Code ve Google Antigravity gibi MCP-uyumlu ajanlar tarafından doğrudan çağrılabilmelidir. | Yüksek |
| FR-9 | Sistem, bir Git pre-commit/pre-push hook'u aracılığıyla; herhangi bir editör eklentisi kurulu olmasa dahi, commit anında temel güvenlik ve paket kontrolünü çalıştırabilmelidir. | Yüksek |
| FR-10 | Sistem, kritik/yüksek riskli bulgularda geliştiriciden açık onay istemeli; düşük riskli bulguları ise yalnızca bilgilendirme amaçlı göstermelidir (yanlış pozitif yorgunluğunu önlemek için). | Orta |
| FR-11 | Sistem, IntelliJ IDEA üzerinde VS Code eklentisiyle işlevsel olarak eşdeğer (tarama sonucu gösterimi, panel) bir eklenti sunmalıdır. | Düşük (Faz 3) |

### 4.3 Fonksiyonel Olmayan Gereksinimler

| No | Gereksinim | Açıklama |
|---|---|---|
| NFR-1 | Gizlilik | Kod içeriği, kullanıcının açık onayı olmadan hiçbir üçüncü taraf buluta gönderilmemelidir; statik analiz ve paket kontrolü tamamen yerel/registry-sorgu düzeyinde kalmalıdır. |
| NFR-2 | Gecikme | Kaydetme/commit anındaki temel tarama (FR-1, FR-2), kullanıcı deneyimini bozmayacak şekilde 2 saniyenin altında sonuç dönmelidir. |
| NFR-3 | Genişletilebilirlik | Yeni bir güvenlik kuralı veya yeni bir editör adaptörü, çekirdek motor kodunu değiştirmeden eklenebilmelidir (eklenti/plugin mimarisi). |
| NFR-4 | Taşınabilirlik | Çekirdek motor, Windows, macOS ve Linux üzerinde ek bağımlılık kurulumu gerektirmeden (Docker veya tekil binary ile) çalışabilmelidir. |
| NFR-5 | Düşük yanlış pozitif oranı | Güvenlik tarayıcısının yanlış pozitif oranı, kullanıcı güvenini korumak için pilot testlerde %15'in altında tutulmalıdır. |
| NFR-6 | Kullanılabilirlik | Editör eklentileri, ek yapılandırma gerektirmeden (sıfır konfigürasyon ile) çalışır durumda kurulabilmelidir. |
| NFR-7 | Dayanıklılık | Bir AI sağlayıcısı (ör. bir LLM API'si) erişilemez olduğunda, sistem devre kesici (circuit breaker) deseniyle alternatif sağlayıcıya veya yerel kural tabanlı analize düşmelidir. |

### 4.4 Kullanım Senaryoları (Use Case'ler)

**UC-1: Güvenlik açığı olan kodun anlık yakalanması**
- **Aktör:** Bireysel geliştirici
- **Ön koşul:** VS Code eklentisi kurulu ve Core Engine çalışıyor
- **Akış:** Geliştirici, Claude Code veya Copilot ile bir API endpoint'i ürettirir → dosya kaydedilir → warden eklentisi diff'i Core Engine'e gönderir → Security Scanner modülü SQL sorgusunun parametreli olmadığını tespit eder → Problems panelinde "Yüksek Risk: SQL Injection potansiyeli" uyarısı gösterilir → geliştirici düzeltmeden önce commit edemez (isteğe bağlı sıkı mod) veya bilgilendirilerek devam eder.

**UC-2: Hayali paket kurulumunun engellenmesi**
- **Aktör:** Bireysel geliştirici
- **Akış:** AI ajanı `pip install fastapi-auth-utils-pro` önerir → geliştirici terminalde komutu çalıştırmadan önce (Git hook veya terminal wrapper aracılığıyla) warden paketi PyPI'da sorgular → paketin bir hafta önce yayınlandığını ve sıfır indirmesi olduğunu tespit eder → kurulum öncesi uyarı gösterir.

**UC-3: Claude Code ajanının kendi kendine güvenlik kontrolü çağırması**
- **Aktör:** Claude Code ajanı (MCP istemcisi)
- **Akış:** Ajan bir kimlik doğrulama modülü üretir → görev tanımında "üretim sonrası güvenlik kontrolü yap" talimatı bulunduğundan, ajan MCP üzerinden `security_scan` aracını çağırır → Core Engine sonucu JSON olarak döner → ajan sonucu değerlendirip gerekirse kodu kendiliğinden düzeltir.

**UC-4: Haftalık teknik borç raporunun incelenmesi**
- **Aktör:** Bireysel geliştirici / takım lideri
- **Akış:** Kullanıcı VS Code yan panelini açar → Teknik Borç Radarı modülünün ürettiği haftalık grafik gösterilir (kod çalkalanması artışı, azalan refactoring oranı) → kullanıcı hangi dosyaların risk taşıdığını görür.

### 4.5 Kısıtlar ve Varsayımlar

- Proje kapsamında yalnızca Python ve JavaScript/TypeScript kod tabanları için güvenlik kuralları hedeflenecektir (dil kapsamı, bitirme projesi zaman kısıtı nedeniyle sınırlandırılmıştır).
- MCP protokolünün Claude Code ve Antigravity tarafındaki uygulamasının, bu raporun yazıldığı tarihteki genel kullanılabilirlik durumuna bağlı olarak değişebileceği varsayılmaktadır; entegrasyon adaptörü bu nedenle soyutlanmış bir arayüz (adapter pattern) üzerinden tasarlanmıştır.
- IntelliJ eklentisi, farklı bir platform (JVM/Kotlin) gerektirdiğinden Faz 3'e ertelenmiştir; MVP kapsamı dışındadır.

---

## 5. Sistem Mimarisi

### 5.1 Mimari Stil

Sistem, **katmanlı mimari (layered architecture)** ile **hexagonal/ports-and-adapters** desenini birleştiren bir yaklaşımla tasarlanmıştır. Merkezde iş mantığını barındıran editör-bağımsız bir Core Engine bulunur; bu çekirdek, dış dünyayla yalnızca tanımlı "port"lar (REST API, MCP sunucusu, CLI) üzerinden konuşur. Her editör/araç, bu portlara bağlanan ince bir "adaptör" olarak modellenir.

```
┌──────────────────────────────────────────────────────────────────────┐
│                         SUNUM / ENTEGRASYON KATMANI                   │
│                                                                        │
│   VS Code Eklentisi   IntelliJ Eklentisi   Claude Code/Antigravity     │
│   (TypeScript)        (Kotlin, Faz 3)      (MCP İstemcisi)             │
│         │                    │                     │                  │
│         │  REST/WebSocket    │  REST/WebSocket     │  MCP (JSON-RPC)   │
└─────────┼────────────────────┼─────────────────────┼──────────────────┘
          │                    │                     │
┌─────────▼────────────────────▼─────────────────────▼──────────────────┐
│                           PORT KATMANI (API Gateway)                   │
│         FastAPI uygulaması: REST endpoint'leri + MCP sunucu wrapper    │
└─────────────────────────────────┬───────────────────────────────────--┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                         UYGULAMA / İŞ MANTIĞI KATMANI                 │
│  ┌────────────────┐ ┌──────────────────┐ ┌────────────────────────┐  │
│  │ SecurityScanner │ │ PackageIntegrity │ │ DiffExplainer          │  │
│  │ Service         │ │ Checker Service  │ │ Service                │  │
│  └────────────────┘ └──────────────────┘ └────────────────────────┘  │
│  ┌────────────────┐ ┌──────────────────┐                             │
│  │ ReviewBoard     │ │ TechDebtTracker  │                             │
│  │ Orchestrator    │ │ Service          │                             │
│  └────────────────┘ └──────────────────┘                             │
└─────────────────────────────────┬─────────────────────────────────--─┘
                                   │
┌──────────────────────────────────▼──────────────────────────────────┐
│                          ALTYAPI KATMANI                              │
│  ┌───────────────┐ ┌────────────────┐ ┌───────────────────────────┐  │
│  │ SQLite         │ │ Git Erişim     │ │ LLM Provider Router        │  │
│  │ (yerel depo)   │ │ Katmanı        │ │ (Anthropic/OpenAI/Ollama,  │  │
│  │                │ │ (GitPython)    │ │ Circuit Breaker'lı)         │  │
│  └───────────────┘ └────────────────┘ └───────────────────────────┘  │
└───────────────────────────────────────────────────────────────────--─┘
```

### 5.2 Katman Sorumlulukları

**Sunum/Entegrasyon Katmanı:** Kullanıcının doğrudan etkileşimde bulunduğu yüzeyler. Bu katmandaki her bileşen "aptaldır" (dumb client) — iş mantığı içermez, yalnızca kullanıcı olaylarını (dosya kaydetme, commit, ajan tool çağrısı) yakalayıp Port Katmanı'na iletir ve sonucu görselleştirir.

**Port Katmanı:** Dış dünyaya açılan tek kapı. FastAPI üzerine kurulu bir API Gateway; hem geleneksel REST/WebSocket isteklerini hem de MCP JSON-RPC çağrılarını aynı iş mantığı servislerine yönlendirir. Bu katman sayesinde yeni bir editör desteği eklemek, yalnızca yeni bir ince istemci yazmayı gerektirir — çekirdek değişmez.

**Uygulama/İş Mantığı Katmanı:** Beş bağımsız servisten oluşur (detayları Bölüm 5.3'te). Her servis, tek bir sorumluluğa sahiptir (Single Responsibility Principle) ve birbirinden bağımsız test edilebilir.

**Altyapı Katmanı:** Kalıcılık (SQLite), Git geçmişine erişim ve LLM sağlayıcı yönlendirmesi gibi teknik detayları soyutlar. LLM Provider Router, AI Caddy projesinde kullanılan **ProviderRouter + CircuitBreaker** desenini temel alır: birincil sağlayıcı (ör. Anthropic API) erişilemez olduğunda otomatik olarak ikincil sağlayıcıya (ör. yerel Ollama modeli) geçiş yapar.

### 5.3 Core Engine Bileşenlerinin Detaylı Tasarımı

#### 5.3.1 SecurityScannerService

**Sorumluluk:** Verilen bir kod parçasını (dosya veya diff) statik analiz kurallarına göre tarar.

**İç Mimari:**
- Temel motor olarak açık kaynak **Semgrep** kütüphanesi kullanılır (sıfırdan bir AST parser yazmak yerine, olgun bir statik analiz motoru üzerine özelleştirilmiş kural seti eklenir).
- `rules/vibe_coding/` dizini altında, vibe coding'e özgü ek kurallar tanımlanır:
  - `hardcoded-secret.yaml`
  - `sql-string-concat.yaml`
  - `missing-input-validation.yaml`
  - `client-side-only-auth.yaml`
  - `disabled-security-check.yaml` (örn. `# TODO: re-enable CSRF` gibi yorum satırı ile devre dışı bırakılmış kontrolleri de yakalar)

**Arayüz (Python, basitleştirilmiş):**

```python
class SecurityScannerService:
    def __init__(self, rule_engine: SemgrepEngine, rule_dir: Path):
        self.rule_engine = rule_engine
        self.rule_dir = rule_dir

    async def scan_diff(self, diff: CodeDiff) -> ScanResult:
        """
        diff: değişen dosya yolu + eklenen/silinen satırlar
        return: ScanResult(findings: List[Finding], risk_level: RiskLevel)
        """
        findings = await self.rule_engine.run(diff.changed_files, self.rule_dir)
        risk_level = self._aggregate_risk(findings)
        return ScanResult(findings=findings, risk_level=risk_level)

    def _aggregate_risk(self, findings: list[Finding]) -> RiskLevel:
        if any(f.severity == "critical" for f in findings):
            return RiskLevel.HIGH
        if any(f.severity == "medium" for f in findings):
            return RiskLevel.MEDIUM
        return RiskLevel.LOW
```

#### 5.3.2 PackageIntegrityCheckerService

**Sorumluluk:** Kurulum önerilen bir paketin gerçekliğini ve güvenilirliğini doğrular.

**Algoritma:**
1. Paket adı, ekosisteme göre (PyPI/npm) ilgili registry API'sine sorgulanır.
2. Paket bulunamazsa → doğrudan `SUSPICIOUS_NOT_FOUND` etiketiyle işaretlenir.
3. Paket bulunursa şu sinyaller değerlendirilir:
   - Yayın tarihi (30 günden yeni ise +risk puanı)
   - Toplam indirme sayısı (eşik değerin altında ise +risk puanı)
   - Levenshtein mesafesi ile popüler paket isimlerine (top 5000 PyPI/npm paketi, yerel önbellekte tutulur) benzerlik (typosquatting sinyali)
4. Toplam risk puanı bir eşiği aşarsa kullanıcıya uyarı gösterilir.

```python
class PackageIntegrityCheckerService:
    async def check(self, package_name: str, ecosystem: Ecosystem) -> PackageVerdict:
        metadata = await self.registry_client.fetch(package_name, ecosystem)
        if metadata is None:
            return PackageVerdict(status="NOT_FOUND", risk="HIGH")

        score = 0
        if metadata.age_days < 30:
            score += 2
        if metadata.downloads < self.MIN_DOWNLOAD_THRESHOLD:
            score += 2
        similar = self.popular_index.closest_match(package_name)
        if similar and similar.distance <= 2:
            score += 3  # olası typosquatting

        return PackageVerdict.from_score(score)
```

#### 5.3.3 DiffExplainerService

**Sorumluluk:** Bir kod farkını insan diline çevirir, risk kategorisi atar ve eksik test senaryolarını önerir.

- LLM Provider Router üzerinden yapılandırılmış (structured output) bir prompt ile çalışır; çıktı şu JSON şemasına zorlanır:

```json
{
  "summary": "string (max 3 cümle)",
  "risk_category": "low | medium | high",
  "affected_areas": ["auth", "payment", "data-deletion", "..."],
  "missing_tests": ["string", "..."]
}
```

- Yüksek maliyetli LLM çağrısını önlemek için, önce **SecurityScannerService** ve basit sezgisel kurallarla (dosya yolu `auth/`, `payment/` gibi hassas dizinlerde mi?) bir ön risk filtresi uygulanır; yalnızca orta/yüksek riskli değişiklikler LLM'e gönderilir (maliyet optimizasyonu).

#### 5.3.4 ReviewBoardOrchestrator (Multi-Agent Review Board)

**Sorumluluk:** Yüksek riskli değişikliklerde, farklı uzmanlık "persona"larına sahip ajanları paralel çalıştırıp bir hakem ajanla sentezler.

**Mimari:**

```
                     ┌─────────────────────┐
        Diff ──────► │  ReviewBoard         │
                     │  Orchestrator         │
                     └──────────┬───────────┘
                                │  (asyncio.gather ile paralel çağrı)
        ┌───────────┬───────────┼───────────┬────────────┐
        ▼           ▼           ▼           ▼            │
   ┌─────────┐ ┌──────────┐ ┌─────────┐ ┌───────────┐    │
   │Güvenlik │ │Performans│ │ Mimari  │ │Test Yazarı│    │
   │ Ajanı   │ │  Ajanı   │ │ Ajanı   │ │  Ajanı    │    │
   └────┬────┘ └────┬─────┘ └────┬────┘ └─────┬─────┘    │
        └───────────┴────────────┴────────────┘          │
                          │  (4 görüş, JSON formatında)   │
                          ▼                                │
                  ┌───────────────┐                        │
                  │  Hakem Ajanı   │◄───────────────────────┘
                  │  (Sentezleyici)│
                  └───────┬────────┘
                          ▼
                 Konsolide Rapor
             (çelişkiler işaretlenmiş,
              öncelik sıralı öneriler)
```

- Her rol-ajanı, aynı diff'i farklı bir sistem promptuyla (ör. "Sen bir güvenlik uzmanısın, yalnızca güvenlik açıklarına odaklan") değerlendirir.
- Hakem ajanı, dört görüşü girdi olarak alır; çelişen noktaları (ör. Performans Ajanı "bu önbellek satırı verimlilik için gerekli" derken Güvenlik Ajanı "bu önbellek hassas veri sızdırabilir" diyorsa) açıkça işaretler ve nihai önceliklendirilmiş bir öneri listesi üretir.
- Maliyet/gecikme nedeniyle bu modül yalnızca **yüksek riskli** olarak ön-filtrelenen değişikliklerde tetiklenir (tüm commit'lerde değil).

#### 5.3.5 TechDebtTrackerService

**Sorumluluk:** Git geçmişini periyodik olarak analiz ederek teknik borç sinyallerini hesaplar.

**Hesaplanan Metrikler:**
- **Kod Çalkalanması (Code Churn):** Son N gün içinde bir dosyanın kaç kez değiştirildiği ve toplam eklenen/silinen satır sayısı.
- **Kod Tekrarı Oranı:** `jscpd` veya benzeri bir kopya-kod tespit aracı entegrasyonuyla hesaplanan yüzde.
- **Refactoring Oranı:** Commit mesajlarında "refactor", "cleanup", "restructure" gibi anahtar kelimelerin toplam commit sayısına oranı (basit sezgisel; gelecekte commit içeriği analiziyle geliştirilebilir).

Bu servis, bir arka plan zamanlayıcısı (`APScheduler`) ile haftalık olarak çalışır ve sonuçları SQLite'a yazar; VS Code paneli bu verileri zaman serisi grafiği olarak görselleştirir.

#### 5.3.6 PersonalMetricsService

**Sorumluluk:** Geliştiricinin AI-üretimi/insan-üretimi kod oranını ve AI önerilerini "olduğu gibi kabul etme" oranını izler.

- VS Code eklentisi, bir kod bloğunun AI tarafından mı (ör. Copilot/Claude Code'un dosyaya yazdığı bir değişiklik) yoksa kullanıcı tarafından mı (manuel klavye girdisi) oluşturulduğunu, editör olaylarından (`onDidChangeTextDocument` olayının kaynağı) ayırt ederek etiketler.
- Bu veri tamamen yerel tutulur, hiçbir sunucuya gönderilmez (bkz. Bölüm 12 Gizlilik Tasarımı).

### 5.4 Bileşenler Arası Bağımlılık Kuralı

Uygulama katmanındaki beş servis birbirinden bağımsızdır ve doğrudan birbirini çağırmaz; tüm orkestrasyon Port Katmanı'ndaki API Gateway üzerinden yapılır. Bu, her servisin izole biçimde birim test edilebilmesini sağlar ve NFR-3 (genişletilebilirlik) gereksinimini karşılar.

---

## 6. Veri Modeli

Sistem, yerel bir SQLite veritabanı kullanır. Temel şema aşağıdaki gibidir:

```sql
-- Tarama geçmişi
CREATE TABLE scan_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    file_path TEXT NOT NULL,
    commit_hash TEXT,
    risk_level TEXT CHECK(risk_level IN ('low','medium','high')),
    findings_json TEXT NOT NULL,       -- Finding listesi, JSON serileştirilmiş
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Paket kontrol geçmişi
CREATE TABLE package_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_name TEXT NOT NULL,
    ecosystem TEXT CHECK(ecosystem IN ('pypi','npm')),
    verdict TEXT CHECK(verdict IN ('safe','suspicious','not_found')),
    risk_score INTEGER,
    checked_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Review Board sonuçları
CREATE TABLE review_board_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    diff_hash TEXT NOT NULL,
    security_opinion TEXT,
    performance_opinion TEXT,
    architecture_opinion TEXT,
    test_opinion TEXT,
    arbiter_summary TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Teknik borç zaman serisi
CREATE TABLE tech_debt_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_path TEXT NOT NULL,
    snapshot_date DATE NOT NULL,
    churn_score REAL,
    duplication_pct REAL,
    refactor_ratio REAL
);

-- Kişisel metrikler
CREATE TABLE personal_metrics_daily (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    date DATE NOT NULL,
    ai_generated_lines INTEGER DEFAULT 0,
    human_written_lines INTEGER DEFAULT 0,
    ai_suggestions_accepted_unchanged INTEGER DEFAULT 0,
    ai_suggestions_total INTEGER DEFAULT 0
);
```

**Tasarım Notu:** `findings_json` gibi alanlarda JSON serileştirme tercih edilmesinin nedeni, `Finding` yapısının (kural adı, satır numarası, önem derecesi, açıklama) sık değişebilecek esnek bir şema olması ve SQLite'ın JSON1 uzantısıyla sorgulanabilir olmasıdır — bu, ayrı bir NoSQL bağımlılığı eklemeden esneklik sağlar.

---

## 7. API Tasarımı

Port Katmanı, aşağıdaki REST uç noktalarını sunar (FastAPI ile otomatik OpenAPI/Swagger dokümantasyonu üretilir):

| Metot | Endpoint | Açıklama |
|---|---|---|
| POST | `/api/v1/scan` | Bir diff'i güvenlik taramasından geçirir |
| POST | `/api/v1/packages/check` | Bir paket adının güvenilirliğini kontrol eder |
| POST | `/api/v1/diff/explain` | Bir diff'in insan-diline özetini üretir |
| POST | `/api/v1/review-board/run` | Multi-agent review board'u tetikler |
| GET | `/api/v1/tech-debt/{repo_id}` | Belirli bir reponun teknik borç zaman serisini döner |
| GET | `/api/v1/metrics/personal/{user_id}` | Kişisel AI-bağımlılık metriklerini döner |
| GET | `/api/v1/health` | Servis sağlık kontrolü (editör eklentileri Core Engine'in ayakta olup olmadığını buradan kontrol eder) |
| WS | `/api/v1/ws/scan-stream` | Gerçek zamanlı tarama sonuçları için WebSocket kanalı (büyük dosyalarda ilerleme bildirimi) |

**Örnek İstek/Yanıt (`POST /api/v1/scan`):**

```json
// İstek
{
  "repo_path": "/home/user/projects/crypto-mas",
  "file_path": "app/api/auth.py",
  "diff_content": "+ query = f\"SELECT * FROM users WHERE id={user_id}\"",
  "language": "python"
}

// Yanıt
{
  "risk_level": "high",
  "findings": [
    {
      "rule_id": "sql-string-concat",
      "severity": "critical",
      "line": 42,
      "message": "Doğrudan string birleştirme ile SQL sorgusu oluşturuluyor; parametreli sorgu kullanın.",
      "cwe": "CWE-89"
    }
  ]
}
```

---

## 8. MCP Sunucu Tasarımı

Claude Code ve Google Antigravity gibi agent-first platformlarla entegrasyon, warden'ın bir **MCP (Model Context Protocol) sunucusu** olarak dışa açılmasıyla sağlanır. Bu, editör eklentisinden farklı olarak, **ajanın kendisinin** warden araçlarını görev akışı içinde doğrudan çağırabilmesini sağlar.

### 8.1 Sunulan Araçlar (Tool Tanımları)

```json
{
  "tools": [
    {
      "name": "security_scan",
      "description": "Verilen bir kod diff'ini OWASP Top-10 tabanlı güvenlik kurallarına göre tarar.",
      "input_schema": {
        "type": "object",
        "properties": {
          "file_path": {"type": "string"},
          "diff_content": {"type": "string"},
          "language": {"type": "string", "enum": ["python", "javascript", "typescript"]}
        },
        "required": ["file_path", "diff_content", "language"]
      }
    },
    {
      "name": "check_package",
      "description": "Bir paketin kurulum öncesi güvenilirliğini (yaş, indirme sayısı, isim benzerliği) kontrol eder.",
      "input_schema": {
        "type": "object",
        "properties": {
          "package_name": {"type": "string"},
          "ecosystem": {"type": "string", "enum": ["pypi", "npm"]}
        },
        "required": ["package_name", "ecosystem"]
      }
    },
    {
      "name": "run_review_board",
      "description": "Yüksek riskli bir değişiklik için çoklu-ajan inceleme kurulunu tetikler ve konsolide rapor döner.",
      "input_schema": {
        "type": "object",
        "properties": {
          "diff_content": {"type": "string"},
          "context": {"type": "string", "description": "Değişikliğin amacı/bağlamı"}
        },
        "required": ["diff_content"]
      }
    }
  ]
}
```

### 8.2 Entegrasyon Akışı

Claude Code veya Antigravity, bir görev planı içinde (örn. bir "commit öncesi güvenlik kontrolü yap" adımında) bu araçları otomatik olarak çağırabilir. Bu, warden'ı bir "pasif eklenti"den bir "ajanın araç setinin parçası"na dönüştürür — ajan, kendi ürettiği kodu kendisi denetleyebilir hale gelir.

**Yapılandırma örneği (`.mcp.json`, Claude Code için):**

```json
{
  "mcpServers": {
    "warden": {
      "command": "warden-mcp-server",
      "args": ["--repo", "${workspaceFolder}"]
    }
  }
}
```

---

## 9. Editör ve Araç Entegrasyonları

### 9.1 VS Code Eklentisi

- **Dil:** TypeScript
- **Aktivasyon olayları:** `onDidSaveTextDocument`, `onDidChangeTextDocument` (debounce ile 800ms gecikmeli), Git commit hook tetiklemesi
- **Arayüz bileşenleri:**
  - Diagnostic Collection API üzerinden Problems panelinde bulgular
  - CodeLens ile riskli satırların üzerinde "Neden riskli?" bağlantısı
  - Webview tabanlı yan panel: teknik borç grafiği (Chart.js) ve kişisel metrik özeti
- **Antigravity uyumluluğu:** Google Antigravity, VS Code'un açık kaynak temelini (fork) kullandığından ve VS Code eklenti API'sini miras aldığından, bu eklenti ek bir derleme/paketleme değişikliği gerektirmeden Antigravity üzerinde de çalışır. Bu, mimari kararının doğrudan bir kazanımıdır.

### 9.2 IntelliJ IDEA Eklentisi (Faz 3)

- **Dil:** Kotlin, IntelliJ Platform SDK
- **Mimari:** Aynı REST API'ye HTTP istemcisi üzerinden bağlanır; UI, IntelliJ'nin `ToolWindow` ve `Annotator` API'leri ile VS Code eklentisiyle işlevsel eşdeğerlik sağlayacak şekilde ayrı olarak geliştirilir (platformlar arası UI kodu paylaşımı mümkün değildir).

### 9.3 Claude Code / Google Antigravity Entegrasyonu

Bölüm 8'de detaylandırılan MCP sunucusu aracılığıyla sağlanır. Ek olarak, Claude Code'un **hook** mekanizması (`PreToolUse`, `PostToolUse`) kullanılarak, ajan bir dosyaya yazma işlemi gerçekleştirdikten hemen sonra otomatik olarak `security_scan` aracının tetiklenmesi sağlanabilir — bu, ajanın kendisinin talep etmesini beklemeden proaktif bir güvenlik ağı oluşturur.

### 9.4 Git Hook (Evrensel Fallback Katmanı)

- `pre-commit` hook'u, `husky` (JS ekosistemi) veya doğrudan `.git/hooks/pre-commit` betiği aracılığıyla kurulur.
- Bu katman, hiçbir editör eklentisi veya MCP entegrasyonu olmasa dahi (örneğin bir CI/CD pipeline'ında veya farklı bir geliştiricinin makinesinde) temel güvenlik ve paket kontrolünün çalışmasını garanti eder.
- Bu nedenle **MVP'nin omurgası** bu katman + Core Engine olarak tanımlanmıştır (bkz. Bölüm 14).

---

## 10. Senaryo Akışları (Sıra Diyagramları)

### 10.1 Senaryo: Dosya Kaydetme Anında Güvenlik Taraması

```
Geliştirici        VS Code Eklentisi       Core Engine API        SecurityScanner
    │                      │                       │                     │
    │  Ctrl+S (kaydet)     │                       │                     │
    ├─────────────────────►│                       │                     │
    │                      │  POST /api/v1/scan    │                     │
    │                      ├──────────────────────►│                     │
    │                      │                       │  scan_diff(diff)    │
    │                      │                       ├────────────────────►│
    │                      │                       │                     │ (Semgrep çalışır)
    │                      │                       │◄────────────────────┤
    │                      │  ScanResult (JSON)    │  ScanResult         │
    │                      │◄──────────────────────┤                     │
    │  Problems panelinde  │                       │                     │
    │  uyarı gösterilir    │                       │                     │
    │◄─────────────────────┤                       │                     │
```

### 10.2 Senaryo: Claude Code Ajanının MCP Aracını Çağırması

```
Claude Code Ajanı     MCP Sunucusu (warden)     PackageIntegrityChecker    PyPI Registry
       │                        │                            │                    │
       │ (görev: "requests-     │                            │                    │
       │  turbo-fast" paketini  │                            │                    │
       │  kurmadan önce kontrol │                            │                    │
       │  et")                  │                            │                    │
       │  tool_call:            │                            │                    │
       │  check_package         │                            │                    │
       ├───────────────────────►│                            │                    │
       │                        │  check(package_name, pypi) │                    │
       │                        ├───────────────────────────►│                    │
       │                        │                             │  GET /pypi/.../json│
       │                        │                             ├───────────────────►│
       │                        │                             │◄───────────────────┤
       │                        │  PackageVerdict             │                    │
       │                        │◄────────────────────────────┤                    │
       │  {"status":"suspicious"│                            │                    │
       │   ,"risk":"high"}      │                            │                    │
       │◄───────────────────────┤                            │                    │
       │ (ajan kararını buna    │                            │                    │
       │  göre günceller)       │                            │                    │
```

### 10.3 Senaryo: Yüksek Riskli Değişiklikte Review Board Tetiklenmesi

```
Git Hook (pre-commit) → Core Engine → SecurityScanner (ön filtre: risk=HIGH tespit edildi)
                                    → ReviewBoardOrchestrator tetiklenir
                                        ├─► Güvenlik Ajanı  (paralel)
                                        ├─► Performans Ajanı (paralel)
                                        ├─► Mimari Ajanı     (paralel)
                                        └─► Test Ajanı       (paralel)
                                    → Hakem Ajanı (4 görüşü sentezler)
                                    → Konsolide rapor → commit engellenir veya
                                      kullanıcıya "onaylıyor musunuz?" sorulur
```

---

## 11. Teknoloji Yığını ve Gerekçelendirme

| Katman | Teknoloji | Gerekçe |
|---|---|---|
| Core Engine | Python 3.12, FastAPI | Ekibin (geliştiricinin) mevcut Crypto MAS/NOVA projelerindeki birikimiyle tutarlı; async destek gecikme gereksinimini (NFR-2) karşılar |
| Statik analiz motoru | Semgrep (açık kaynak) | Sıfırdan AST parser yazmak yerine olgun, çok-dilli bir motor üzerine özelleştirilmiş kural seti eklemek zaman/kalite açısından daha verimli |
| Veritabanı | SQLite | Yerel çalışma, sıfır kurulum, gizlilik gereksinimiyle (NFR-1) uyumlu |
| LLM erişimi | Provider Router + Circuit Breaker (Anthropic API birincil, Ollama yerel model yedek) | AI Caddy projesinde kanıtlanmış, dayanıklılık gereksinimini (NFR-7) karşılayan bir desen |
| VS Code Eklentisi | TypeScript, VS Code Extension API | Standart, iyi belgelenmiş; Antigravity uyumluluğunu bedava sağlar |
| IntelliJ Eklentisi | Kotlin, IntelliJ Platform SDK | JetBrains'in resmi önerdiği dil/SDK |
| MCP Sunucusu | Python MCP SDK (Anthropic resmi) | Claude Code ve Antigravity ile protokol uyumluluğu garantisi |
| Zamanlanmış görevler | APScheduler | Teknik borç analizinin periyodik (haftalık) çalıştırılması için hafif bir çözüm |
| Kopya kod tespiti | jscpd (açık kaynak) | Çok dilli kod tekrarı tespitinde yaygın kullanılan, entegrasyonu kolay bir araç |

---

## 12. Güvenlik ve Gizlilik Tasarımı

warden, ironik biçimde kendisi de bir güvenlik aracı olduğundan, kendi güvenlik/gizlilik tasarımı özellikle titiz olmalıdır:

1. **Varsayılan olarak yerel işleme:** Statik analiz (Semgrep) ve paket kontrolü (registry sorgusu) tamamen yerel makinede çalışır; kod içeriği hiçbir sunucuya gönderilmez.
2. **LLM çağrılarında açık rıza:** DiffExplainer ve ReviewBoard modülleri, kod parçacıklarını harici bir LLM API'sine gönderdiğinden, bu özellik varsayılan olarak **kapalı** gelir ve kullanıcı ilk kullanımda açıkça onay vermelidir. Tamamen yerel çalışmak isteyen kullanıcılar için Ollama tabanlı yerel model seçeneği sunulur.
3. **Hassas veri filtreleme:** LLM'e gönderilmeden önce, diff içeriğinde regex tabanlı bir ön filtre (API anahtarı, şifre, kişisel veri paternleri) çalışır ve bu alanlar maskelenir.
4. **Kişisel metrik verisinin yerelliği:** PersonalMetricsService verileri (Bölüm 5.3.6), hiçbir koşulda dışa aktarılmaz; yalnızca kullanıcının kendi SQLite veritabanında tutulur.
5. **En az yetki ilkesi:** MCP sunucusu, yalnızca okuma amaçlı (dosya diff'i okuma, paket sorgulama) araçlar sunar; hiçbir araç kod tabanında yazma/silme işlemi gerçekleştirmez.

---

## 13. Test Stratejisi

| Test Türü | Kapsam | Araç |
|---|---|---|
| Birim testleri | Her Core Engine servisi (SecurityScanner, PackageChecker vb.) izole olarak | pytest |
| Entegrasyon testleri | API Gateway üzerinden uçtan uca istek/yanıt akışı | pytest + httpx test client |
| Kural doğruluğu testleri | Bilinçli olarak güvenlik açığı içeren "kirli" test dosyaları seti üzerinde SecurityScanner'ın doğru/yanlış pozitif oranı ölçümü | Özel test veri seti (OWASP WebGoat benzeri örnekler) |
| Regresyon testleri | Slopsquatting kontrolünün bilinen gerçek/sahte paket çiftleri üzerinde doğruluğu | Statik test veri seti |
| Editör eklentisi testleri | VS Code eklentisinin komut/olay tetiklemelerinin doğruluğu | VS Code Extension Test Runner |
| MCP entegrasyon testi | Claude Code'un MCP araçlarını doğru şema ile çağırıp çağırmadığının doğrulanması | Manuel senaryo testi + MCP Inspector aracı |
| Performans testi | Kaydetme anındaki tarama gecikmesinin NFR-2 (2 saniye altı) sınırını karşıladığının ölçümü | Yerel benchmark script'i |

**Hedef Test Kapsamı:** Core Engine iş mantığı katmanı için en az %80 birim test kapsamı hedeflenmektedir (Crypto MAS projesindeki 210 birim testlik disiplinle tutarlı bir yaklaşım).

---

## 14. Faz Planı ve Yol Haritası

| Faz | Kapsam | Tahmini Süre | Çıktı |
|---|---|---|---|
| **Faz 0 — Hazırlık** | Literatür/rakip analizi, gereksinim analizi (bu belge), Semgrep kural seti tasarımı | 2 hafta | Bu rapor + kural şablonları |
| **Faz 1 — MVP (Bitirme kapsamının çekirdeği)** | Core Engine (SecurityScanner + PackageIntegrityChecker), SQLite şeması, REST API, Git pre-commit hook entegrasyonu | 5 hafta | Editörsüz de çalışan, commit anında güvenlik/paket kontrolü yapan çalışan sistem |
| **Faz 2 — Editör ve Ajan Entegrasyonu** | VS Code eklentisi (Problems panel + webview), MCP sunucusu (security_scan, check_package araçları), Claude Code ile uçtan uca test | 4 hafta | VS Code + Antigravity'de çalışan eklenti; Claude Code'un araçları çağırabildiği demo |
| **Faz 3 — Genişletilmiş Modüller (sunumda "vizyon" olarak gösterilecek)** | DiffExplainer, ReviewBoardOrchestrator, TechDebtTracker, PersonalMetricsService, IntelliJ eklentisi | Bitirme dönemi sonrası / stretch goal | Kısmi prototip veya mimari kanıt (proof of concept) |
| **Faz 4 — Değerlendirme ve Yazım** | Pilot kullanım (kendi Crypto MAS/Omni-Agent/AI Caddy projeleri üzerinde), sonuçların ölçülmesi, tez/rapor yazımı | 2 hafta | Nicel sonuçlarla desteklenmiş bitirme raporu |

**Toplam MVP + Entegrasyon Süresi:** Yaklaşık 11 hafta — standart bir akademik dönem takvimine (13-14 hafta) makul bir tampon bırakarak sığmaktadır.

---

## 15. Risk Analizi

| Risk | Olasılık | Etki | Azaltma Stratejisi |
|---|---|---|---|
| Semgrep kural setinin yanlış pozitif oranının yüksek çıkması, kullanıcı güvenini zedelemesi | Orta | Yüksek | Faz 1'de küçük, yüksek güvenilirlikli bir kural alt kümesiyle başlamak; NFR-5'teki %15 eşiğini pilot testte doğrulamak |
| MCP protokolünün Claude Code/Antigravity tarafındaki davranışının proje süresince değişmesi | Orta | Orta | Port katmanı soyutlaması (Bölüm 5.1) sayesinde adaptör kodu izole edilmiştir; protokol değişikliği yalnızca ince adaptör katmanını etkiler |
| LLM API maliyetlerinin (DiffExplainer, ReviewBoard) bütçe/rate-limit sınırlarını aşması | Düşük-Orta | Orta | Ön risk filtresi ile yalnızca yüksek riskli değişikliklerde LLM çağrısı yapılması (Bölüm 5.3.3); yerel model (Ollama) yedek seçeneği |
| Kapsamın (5 modül + 4 platform) bir dönemde tamamlanamaması | Yüksek | Yüksek | Faz 1-2'nin net MVP olarak tanımlanması, Faz 3'ün "vizyon/gelecek çalışma" olarak sunulması (Bölüm 14) |
| Gerçek/temsili "kirli" test veri setinin (bilinçli güvenlik açığı içeren kod örnekleri) yetersiz kalması | Düşük | Orta | OWASP WebGoat, Juice Shop gibi açık kaynak zafiyetli uygulama örneklerinden test seti türetilmesi |

---

## 16. Başarı Kriterleri ve Değerlendirme Metrikleri

Projenin başarısı, aşağıdaki ölçülebilir kriterlerle değerlendirilecektir:

1. **Güvenlik tarayıcısı doğruluğu:** Bilinçli olarak oluşturulmuş, bilinen güvenlik açığı içeren en az 30 test dosyasından oluşan bir sette, SecurityScannerService'in yakalama oranı (recall) ve yanlış pozitif oranı (precision) hesaplanacaktır.
2. **Slopsquatting tespiti doğruluğu:** Bilinen gerçek paketler ile kasıtlı olarak üretilmiş "sahte/hayali" paket adları içeren bir test setinde doğruluk oranı ölçülecektir.
3. **Gecikme:** NFR-2'de tanımlanan 2 saniyelik hedefin gerçek kullanım koşullarında (kendi Crypto MAS/Omni-Agent repo'ları üzerinde) karşılanıp karşılanmadığı ölçülecektir.
4. **Gerçek dünya pilot kullanımı:** Sistem, geliştiricinin kendi devam eden projelerinde (Crypto MAS, Omni-Agent, AI Caddy) en az 2 hafta boyunca fiilen kullanılacak; bu süre zarfında yakalanan gerçek bulgular (varsa) nicel olarak raporlanacaktır — bu, akademik "laboratuvar demosu" eleştirisine karşı en güçlü kanıt olacaktır.
5. **MCP entegrasyon kanıtı:** Claude Code'un, bir görev akışı sırasında warden MCP araçlarını en az bir kez kendiliğinden (insan müdahalesi olmadan) çağırdığı bir demo senaryosunun kayıt altına alınması.

### 16.1 Genel Değerlendirme Skor Kartı

Yukarıdaki metrikleri tek tek izlemenin yanında, tasarımın bütününü kategori bazında özetlemek jüri/danışman değerlendirmesi için faydalıdır. Aşağıdaki skor kartı, bu raporda tanımlanan **tasarımın mevcut olgunluk seviyesini** (henüz kod yazılmamış, yalnızca gereksinim/mimari tasarım aşaması) yansıtır; MVP tamamlandıktan sonra aynı kategoriler gerçek ölçüm verileriyle (Bölüm 16'daki kriterler) yeniden puanlanmalıdır.

| Kategori | Puan | Durum |
|---|---|---|
| 🧠 Problem Tanımı & Gerekçelendirme | 9.0/10 | 🟢 |
| 🏗️ Mimari & Tasarım (Katmanlı + Ports-and-Adapters) | 8.5/10 | 🟢 |
| 📖 Gereksinim Dokümantasyonu | 9.0/10 | 🟢 |
| 🔌 Editör/Ajan Entegrasyon Stratejisi (VS Code, IntelliJ, MCP) | 8.0/10 | 🟢 |
| 🔒 Güvenlik & Gizlilik Tasarımı | 8.0/10 | 🟢 |
| 🧪 Test Stratejisi | 7.0/10 | 🟡 |
| ⚙️ Uygulanabilirlik (1 dönem MVP kapsamı) | 6.5/10 | 🟡 |
| 💻 Somut Kod / Gerçekleştirim Kanıtı | 2.0/10 | 🔴 |
| **GENEL** | **7.3/10** | 🟢 |

**Not:** "Somut Kod / Gerçekleştirim Kanıtı" kategorisinin düşük çıkması beklenen bir durumdur — bu belge bir gereksinim/mimari tasarım raporudur, henüz bir uygulama aşaması değildir. Genel puanın yüksek çıkmasının nedeni, tasarım aşamasının (problem tanımı, mimari, gereksinim netliği) sağlam temellere oturmasıdır; ancak bu skor kartı, projenin asıl sınavının **Faz 1 MVP'nin gerçekten çalışır şekilde teslim edilmesinde** olduğunu unutturmamalıdır.

---

## 17. Sonuç ve Öneriler

Bu rapor, vibe coding paradigmasının güncel ve ölçülmüş risklerine (güvenlik açıkları, tedarik zinciri saldırıları, teknik borç birikimi, yetkinlik erozyonu) karşı, editörden ve yapay zekâ sağlayıcısından bağımsız, genişletilebilir bir mimariyle yanıt veren warden sistemini tanımlamıştır.

Mimarinin temel gücü, iş mantığını (Core Engine) sunum katmanından (editör eklentileri) tamamen ayırması ve dış dünyayla yalnızca standart portlar (REST, MCP, Git hook) üzerinden konuşmasıdır. Bu tasarım kararı sayesinde:

- Google Antigravity desteği, VS Code eklenti mimarisinin doğal bir sonucu olarak **ek maliyetsiz** elde edilir.
- Claude Code ve gelecekteki agent-first platformlarla entegrasyon, MCP protokolü sayesinde **ajanın kendi araç setinin bir parçası** haline gelir; bu, pasif bir eklentiden çok daha güçlü bir konumlandırmadır.
- Git hook katmanı, hiçbir editör bağımlılığı olmadan sistemin **her koşulda çalışmasını** garanti eder.

**Önerilen sonraki adım:** Faz 0'daki Semgrep kural setinin somut olarak yazılmasıyla başlanması ve Faz 1 (MVP) kapsamının hiçbir sapma olmadan tamamlanması — çünkü bu raporun risk analizinde de vurgulandığı gibi, projenin en büyük tehdidi teknik değil, **kapsam yönetimidir**.

---

## 18. Ekler

### Ek A: Terimler Sözlüğü

- **Vibe Coding:** Geliştiricinin kodu satır satır yazmak yerine doğal dil talimatlarıyla bir yapay zekâ ajanına ürettirdiği, üretilen kodu ayrıntılı incelemeden "işe yarıyor mu" testiyle kabul etme eğiliminde olduğu geliştirme yaklaşımı.
- **Slopsquatting:** Saldırganların, LLM'lerin sıkça halüsinasyon yoluyla önerdiği var olmayan paket isimlerini önceden kayıt ettirerek kötü amaçlı kod dağıtması.
- **Kod Çalkalanması (Code Churn):** Bir kod parçasının kısa aralıklarla tekrar tekrar değiştirilmesi; genellikle plansız/düşünülmemiş geliştirmenin bir göstergesi olarak kabul edilir.
- **MCP (Model Context Protocol):** Yapay zekâ ajanlarının harici araçları/veri kaynaklarını standart bir protokolle keşfedip çağırabilmesini sağlayan açık protokol.

### Ek B: Referans Alınan Mimari Desenler

- Ports and Adapters (Hexagonal Architecture) — Alistair Cockburn
- Circuit Breaker Deseni — dayanıklı dağıtık sistem tasarımı literatürü
- Single Responsibility Principle — SOLID prensipleri

### Ek C: Bu Raporun Dayandığı Güncel Sektör Verileri

Bu raporun 2. bölümünde sunulan istatistikler (güvenlik açığı oranları, kod çalkalanması artışı, halüsinasyon paket oranları), 2025-2026 döneminde yayınlanmış bağımsız güvenlik testleri ve kod analitiği platformlarının (CodeRabbit, GitClear ve çeşitli güvenlik araştırma firmaları) raporlarına dayanmaktadır. Bitirme projesi teslim aşamasında, bu verilerin orijinal kaynaklarına tam atıf yapılması ve mümkünse projenin kendi pilot verileriyle karşılaştırılması önerilir.
