# 🏛️ Mimari ve Skorlama Metodolojisi

WARDEN, geleneksel statik kod analiz araçlarının (linter, SAST) yetersiz kaldığı modern yapay zeka çağında, **deterministik mekanik ölçümler** ile **LLM destekli anlamsal (semantik) muhakemeyi** birleştiren iki katmanlı hibrit bir değerlendirme modeli kullanır.

```
Toplam Skor = (Katman 1 Skoru × 0.60) + (Katman 2 Skoru × 0.40)
```

*(Eğer Katman 2 devre dışıysa veya LLM API erişimi yoksa: Katman 1 Ağırlığı = %100)*

---

## 🏗️ 1. İki Katmanlı Mimari (Dual-Layer Model)

```
                            ┌─────────────────────────────────────────┐
                            │               WARDEN                    │
                            │      Otonom Yönetişim Motoru            │
                            └────────────────────┬────────────────────┘
                                                 │
                        ┌────────────────────────┴────────────────────────┐
                        ▼                                                 ▼
        ┌───────────────────────────────┐                 ┌───────────────────────────────┐
        │           KATMAN 1            │                 │           KATMAN 2            │
        │    Mekanik Analiz (%60)       │                 │   Semantik LLM Rubriği (%40)  │
        └───────────────┬───────────────┘                 └───────────────┬───────────────┘
                        │                                                 │
        ┌───────────────┴───────────────┐                 ┌───────────────┴───────────────┐
        ▼                               ▼                 ▼                               ▼
 16 Deterministik               5 Ana Boyut       7 Dinamik Kanıt                 0-3-6-9 Çapalı
  Ölçüm Motoru                   (Core Groups)      Toplayıcı Modül                 Somut Rubrikler
```

---

## 📊 2. Beş Ana Grup ve Katman 1 Üyeleri

Katman 1, kod tabanını 5 ana başlık altında toplanan **16 otonom üye** ile denetler:

### 🛡️ Grup 1: Güvenlik ve Tedarik Zinciri (Ağırlık: %25)
Yazılımın doğrudan dış dünyaya maruz kalan zafiyetlerini ve bağımlılık risklerini denetler.

| Üye Adı | Metrik / Araç | Açıklama ve Ceza Kriteri |
| :--- | :---: | :--- |
| `security_semgrep` | Semgrep SAST | OWASP Top 10, SQLi, RCE, güvensiz deserialization ve XSS açıkları. |
| `secret_leak_gitleaks` | Gitleaks Engine | Git geçmişinde unutulan token, API anahtarı, private key ve parola sızıntıları. |
| `dependency_osv` | Google OSV API | Proje bağımlılıklarındaki bilinen CVE güvenlik açıkları (CRITICAL / HIGH). |
| `license_compliance` | Pip-Licenses & AST | Açık kaynak lisans uyumluluğu (AGPL/GPL ticari çakışmaları, tescilli kod riskleri). |

### 🧪 Grup 2: Kod Sağlığı ve Test (Ağırlık: %25)
Kodun test edilebilirliğini, doğruluğunu ve tip güvenliğini inceler.

| Üye Adı | Metrik / Araç | Açıklama ve Ceza Kriteri |
| :--- | :---: | :--- |
| `test_coverage` | Coverage.py (İzole) | Satır ve dal (branch) test kapsamı. Sandbox ortamında güvenle koşturulur. |
| `test_quality` | AST Assertion Audit | Sadece satır sayısını şişiren boş testleri eler; assertion yoğunluğunu ve çeşitliliğini ölçer. |
| `type_safety` | Mypy / Pyright | Statik tip doğrulaması, `: any` kaçışları ve tip hata yoğunluğu (hata/KLOC). |
| `documentation` | Interrogate & Regex | Fonksiyon/sınıf docstring oranı, README kurulum ve kullanım bölümlerinin varlığı. |

### 📐 Grup 3: Yapısal Sağlık ve Karmaşıklık (Ağırlık: %20)
Kodun mimari temizliğini ve bakım maliyetini analiz eder.

| Üye Adı | Metrik / Araç | Açıklama ve Ceza Kriteri |
| :--- | :---: | :--- |
| `cyclomatic_complexity` | Radon (McCabe) | Fonksiyon başına dallanma sayısı. A-F baremi ile B üstü karmaşık bloklar cezalandırılır. |
| `duplication_jscpd` | JSCPD Tokenizer | Diller arası kod kopyalama (DRY prensibi). %3 üzeri tekrar cezalandırılır. |
| `maintainability_index` | Halstead Metrikleri | Kodun uzun vadeli okunabilirliği ve bakım indeksi. |

### ⚡ Grup 4: Dayanıklılık ve Performans (Ağırlık: %15)
Çalışma zamanında sistemin çökmesini veya asılı kalmasını önleyecek defansif mekanizmaları arar.

| Üye Adı | Metrik / Araç | Açıklama ve Ceza Kriteri |
| :--- | :---: | :--- |
| `resilience_ast` | AST Defect Scanner | Zaman aşımı (timeout) olmayan HTTP/DB istekleri, bare except blokları (`except:`). |
| `docker_readiness` | Dockerfile Linter | Multi-stage build varlığı, non-root user kullanımı, HEALTHCHECK direktifi. |

### 🤖 Grup 5: Geliştirici Hijyeni ve Vibe-Coding (Ağırlık: %15)
Yapay zeka araçlarının kontrolsüz kullanımını ve repo hijyenini ölçer.

| Üye Adı | Metrik / Araç | Açıklama ve Ceza Kriteri |
| :--- | :---: | :--- |
| `vibe_coding_detector` | Heuristic NLP/Regex | Didaktik AI yorumları, LLM prompt kalıntıları, Markdown artıkları ve silinmemiş şablonlar. |
| `commit_hygiene` | Git Conventional | Commit mesajlarının açıklığı, spam/anlamsız mesajlar (`asdf`, `fix`) ve bot commit ayrımı. |
| `tech_debt_hotspots` | Git Churn × Karmaşıklık | Çok sık değişen ama döngüsel karmaşıklığı yüksek olan "patlamaya hazır" dosyalar. |

---

## 🧠 3. Katman 2: LLM Destekli Dinamik Semantik Rubrik

Katman 2, kod tabanını yüzeysel bir prompt ile değil; **7 bağımsız kanıt toplayıcı modül** aracılığıyla toplanan somut kod parçacıkları ve yapısal kanıtlarla besler:

1. **`api` Toplayıcısı:** FastAPI, Flask, Django veya Express endpoint rotaları, şema doğrulaması ve HTTP durum kodları.
2. **`architecture` Toplayıcısı:** Katmanlı mimari sınırları, soyutlama katmanları ve döngüsel bağımlılıklar.
3. **`concurrency` Toplayıcısı:** Async/await, thread pool, mutex, lock ve race-condition savunmaları.
4. **`devops` Toplayıcısı:** CI/CD iş akışları, Docker yapıları ve altyapı kodları (IaC).
5. **`frontend` Toplayıcısı:** Durum yönetimi (Redux/Zustand), erişilebilirlik (ARIA) ve bileşen mimarisi.
6. **`llm` Toplayıcısı:** Prompt enjeksiyon korumaları, structured output (JSON mode) ve fallback sağlayıcıları.
7. **`quantitative` Toplayıcısı:** Katman 1'in ürettiği sayısal özetleri LLM'in bağlamsal yorumlaması için hazırlar.

### ⚓ 0-3-6-9 Çapa Puanlama Sistemi

LLM, serbest metin yerine her kategori için kesin kanıt çapalarına göre seviye belirler:
- **Seviye 0-2 (Kritik / İlkel):** Standartlar tamamen yok sayılmış; sistem güvenliği veya mimarisi tehlikede.
- **Seviye 3-5 (Geliştirilmeli):** Temel fonksiyonlar çalışıyor ancak hata yakalama, sınır durumlar veya dokümantasyon eksik.
- **Seviye 6-8 (Başarılı / Yetkin):** Sektör standartlarında temiz tasarım, tip güvenliği ve defansif kodlama.
- **Seviye 9-10 (Mükemmel / Örnek):** Kapsamlı soyutlama, yüksek test dayanıklılığı, sıfır sızıntı ve üretim kalitesinde mimari.

---

## 🎓 4. Başarı Notu Baremi (Grade System)

Denetim tamamlandığında nihai 100 puan üzerinden harf notu hesaplanır:

| Skor Aralığı | Harf Notu | Durum | Kalite Kapısı (Default Baraj: 75) |
| :---: | :---: | :--- | :---: |
| **95 - 100** | **A+** | 🟢 Olağanüstü Kalite & Güvenlik | ✅ GEÇTİ |
| **90 - 94** | **A** | 🟢 Üretim Standardında Başarılı | ✅ GEÇTİ |
| **80 - 89** | **B** | 🟢 Sağlam & Güvenilir | ✅ GEÇTİ |
| **70 - 79** | **C** | 🟡 Kabul Edilebilir (Eksikler Var) | ⚠️ Sınırdan Geçti / Kaldı |
| **60 - 69** | **D** | 🔴 Riskli (Ciddi İyileştirme Gerekir) | ❌ KALDI |
| **0 - 59** | **F** | 🔴 Başarısız (Üretim İçin Tehlikeli) | ❌ KALDI |
