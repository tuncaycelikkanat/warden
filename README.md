<div align="center">

```text
 ██╗    ██╗ █████╗ ██████╗ ██████╗ ███████╗███╗   ██╗
 ██║    ██║██╔══██╗██╔══██╗██╔══██╗██╔════╝████╗  ██║
 ██║ █╗ ██║███████║██████╔╝██║  ██║█████╗  ██╔██╗ ██║
 ██║███╗██║██╔══██║██╔══██╗██║  ██║██╔══╝  ██║╚██╗██║
 ╚███╔███╔╝██║  ██║██║  ██║██████╔╝███████╗██║ ╚████║
  ╚══╝╚══╝ ╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝ ╚══════╝╚═╝  ╚═══╝
```

### 🛡️ Otonom Kod Denetimi, Mimari Kalite ve Vibe-Coding Yönetişim Motoru

[![CI/CD Tests](https://img.shields.io/badge/Tests-472%20Passed%20(100%25)-success?style=for-the-badge&logo=pytest&logoColor=white)](.github/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/Coverage-96%25-brightgreen?style=for-the-badge&logo=codecov&logoColor=white)](tests/)
[![Python](https://img.shields.io/badge/Python-3.11%20|%203.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](Dockerfile)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

[Hızlı Başlangıç](docs/getting-started.md) • [Mimari & Skorlama](docs/architecture-and-scoring.md) • [Vibe-Coding Rehberi](docs/vibe-coding-governance.md) • [CI/CD Kalite Kapısı](docs/ci-cd-quality-gates.md) • [REST API](docs/api-and-webhooks.md)

</div>

---

## 💡 Neden WARDEN?

Yapay zeka kod asistanlarının (**Cursor**, **GitHub Copilot**, **ChatGPT**, **Claude**) yazılım geliştirme dünyasını hızlandırdığı bu yeni çağda, geliştiriciler mimari detaylardan uzaklaşarak **"Vibe Coding"** tarzına yönelmektedir. Bu hız muazzam bir üretkenlik sağlasa da arkasında şu tehlikeleri bırakır:

- ❌ **Yutulan Hatalar (Swallowed Exceptions):** Kodun çalışıyor gibi görünmesi için eklenen ve sessizce hataları yutan `except Exception: pass` blokları.
- ❌ **Didaktik AI Yorum Kirliliği (AI Slop):** Bariz işlemleri anlatan uzun eğitici yorumlar ve dosyalarda unutulan chat/markdown artıkları (` ```python `).
- ❌ **Zaman Aşımı (Timeout) Eksikliği:** Ağ veya veritabanı kilitlendiğinde tüm sunucuyu asılı bırakan parametresiz istekler.
- ❌ **Pini Çözülmüş / Zehirli Bağımlılıklar:** Belirsiz sürüm numaraları veya typosquatting tuzaklarına düşen sahte paketler.
- ❌ **Gizli Anahtar Sızıntıları:** Git geçmişine veya test dosyalarına dikkatsizce gömülen gerçek API anahtarları ve token'lar.

**WARDEN**, bu yeni nesil yazılım risklerini ortadan kaldırmak için geliştirilmiş, **deterministik mekanik ölçümler ile LLM tabanlı semantik muhakemeyi birleştiren iki katmanlı otonom bir kalite güvence (QA) ve denetim motorudur.**

---

## 🏛️ İki Katmanlı Mimari (Dual-Layer Governance)

WARDEN, yalnızca statik analiz kurallarıyla sınırlı kalmaz; yapay zekanın ürettiği mimari kararları da somut kanıtlarla doğrular:

```text
                                [ WARDEN CLI / API / CI ]
                                            │
                             ┌──────────────┴──────────────┐
                             ▼                             ▼
                  ┌─────────────────────┐       ┌─────────────────────┐
                  │      KATMAN 1       │       │      KATMAN 2       │
                  │ Mekanik Analiz (%60)│       │ Semantik Rubrik(%40)│
                  └──────────┬──────────┘       └──────────┬──────────┘
                             │                             │
    ┌────────────────────────┼────────────────────┐        │
    ▼                        ▼                    ▼        ▼
┌──────────────┐      ┌──────────────┐     ┌─────────────┐ ┌─────────────────────┐
│  Güvenlik &  │      │   Sağlık &   │     │ Vibe-Coding │ │  7 Dinamik Kanıt    │
│  Tedarik (%25)│      │  Karmaşıklık │     │  Hijyeni    │ │  Toplayıcı Modül  │
├──────────────┤      ├──────────────┤     ├─────────────┤ ├─────────────────────┤
│• Semgrep SAST│      │• Radon (CC)  │     │• AI Yorumlar│ │• API & Rotalar      │
│• Gitleaks    │      │• JSCPD (DRY) │     │• Bare Except│ │• Concurrency & Lock │
│• Google OSV  │      │• Coverage.py │     │• Prompt Leak│ │• DevOps & Docker   │
│• Pip-Licenses│      │• Mypy / Tip  │     │• Churn×Risk │ │• Frontend & State   │
└──────────────┘      └──────────────┘     └─────────────┘ └──────────┬──────────┘
                                                                      ▼
                                                           ┌─────────────────────┐
                                                           │ LLM Sağlayıcı Havuzu│
                                                           │ (Gemini / OpenAI /  │
                                                           │  Claude / Ollama)   │
                                                           └─────────────────────┘
                                            │
                             ┌──────────────┴──────────────┐
                             ▼                             ▼
                  ┌─────────────────────┐       ┌─────────────────────┐
                  │    Önbellek & DB    │       │     Raporlama       │
                  │ (Redis / PostgreSQL)│       │ (Dashboard/PR/Slack)│
                  └─────────────────────┘       └─────────────────────┘
```

> [!TIP]
> **Zarafetle Derece Düşürme (Graceful Degradation):** Eğer `GEMINI_API_KEY` veya harici bir LLM anahtarı tanımlanmamışsa, sistem çalışmayı kesmez. Katman 2'nin %40'lık ağırlığı doğrudan Katman 1'e devredilir (%60 → %100) ve denetim sıfır dış bağımlılıkla kusursuz tamamlanır.

---

## 📊 Terminal Çıktısı (Canlı Denetim Örneği)

`uv run python core/main.py audit --path . --min-score 75` komutu çalıştırıldığında WARDEN'in ürettiği terminal karnesi:

```text
================================================================================
🛡️  WARDEN — Otonom Kod Denetimi ve Kalite Güvence Karnesi
================================================================================
📂 Hedef: /home/tuncay/PycharmProjects/warden  |  ⏱️  Süre: 14.2s
🔍 16 Katman-1 Analizörü ve Dinamik Kanıt Toplayıcılar Tamamlandı

┌───────────────────────────────────────┬──────────┬─────────────┬──────────────┐
│ Denetim Grubu                         │ Ağırlık  │ Puan (/100) │ Durum        │
├───────────────────────────────────────┼──────────┼─────────────┼──────────────┤
│ 🛡️ Güvenlik & Tedarik Zinciri          │   %25    │    100.0    │ 🟢 Mükemmel  │
│ 🧪 Kod Sağlığı & Test Kapsamı         │   %25    │     97.5    │ 🟢 Mükemmel  │
│ 📐 Yapısal Sağlık & Karmaşıklık       │   %20    │     94.8    │ 🟢 Başarılı  │
│ ⚡ Dayanıklılık & Performans          │   %15    │     96.2    │ 🟢 Mükemmel  │
│ 🤖 Geliştirici Hijyeni & Vibe-Coding  │   %15    │     95.0    │ 🟢 Başarılı  │
├───────────────────────────────────────┼──────────┼─────────────┼──────────────┤
│ Katman 1 (Mekanik Analiz Skoru)       │   %60    │     96.8    │ 🟢 Başarılı  │
│ Katman 2 (LLM Semantik Rubrik)        │   %40    │     93.0    │ 🟢 Başarılı  │
└───────────────────────────────────────┴──────────┴─────────────┴──────────────┘

🏆 GENEL WARDEN SKORU: 95/100 (A+ — Olağanüstü Başarı)
• Kalite Kapısı: ✅ GEÇTİ (Baraj Eşiği: 75.0)
• Veritabanı Rapor ID: #46 (Milestone olarak kaydedildi)
• Markdown Rapor: WARDEN_EXECUTIVE_REPORT.md
================================================================================
```

---

## 🚀 Hızlı Başlangıç

### 1. Kurulum (Tek Komutla)
```bash
git clone https://github.com/tuncaycelikkanat/warden.git
cd warden
chmod +x install.sh
./install.sh
```

### 2. Ortam Değişkeni Tanımlama
`.env` dosyanızı oluşturup LLM anahtarınızı ekleyin (Katman 2 için):
```bash
cp .env.example .env
echo 'GEMINI_API_KEY="AIzaSyYourKeyHere"' >> .env
```

### 3. Denetim Koşturma
```bash
# Geçerli repoyu denetle
uv run python core/main.py audit --path .

# Minimum puan barajı koyarak denetle (Kalite Kapısı)
uv run python core/main.py audit --path . --min-score 80 --fail-on-critical
```

---

## 💻 CLI Kullanım Kılavuzu

WARDEN güçlü ve zengin parametreli bir CLI arayüzüne sahiptir:

```bash
# 1. Tam Denetim (Full Audit) ve Kilometre Taşı Olarak İşaretleme
uv run python core/main.py audit --path . --milestone "v1.0.0-rc1"

# 2. Hızlı / Artımlı Denetim (Sadece değişen dosyaları 3 saniyede denetle)
uv run python core/main.py audit --path . --incremental

# 3. Belirli bir commit/branch'ten bu yana yapılan değişiklikleri denetle
uv run python core/main.py audit --path . --incremental --since-commit origin/main

# 4. JSON Formatında Çıktı Alma (CI/CD araçları için)
uv run python core/main.py audit --path . --json > audit_result.json

# 5. İki Denetim Raporu Arasındaki Delta ve Regresyonları Kıyaslama
uv run python core/main.py compare 42 46

# 6. Güvenli Olmayan veya Typosquatting Riski Taşıyan Paket Taraması
uv run python core/main.py scan requests-security-patch
```

---

## 🌐 Modern Web Kontrol Paneli (Dashboard UI)

FastAPI tabanlı web sunucusu çalıştırıldığında karanlık temalı modern Single-Page Application (SPA) arayüzü anında devreye girer:

```bash
uv run uvicorn core.main:app --host 0.0.0.0 --port 8000 --reload
```

- 📊 **Web Dashboard:** [http://localhost:8000/dashboard/](http://localhost:8000/dashboard/)
- 📖 **Swagger API Belgeleri:** [http://localhost:8000/docs](http://localhost:8000/docs)
- 📈 **Prometheus / Sağlık Metrikleri:** [http://localhost:8000/api/v1/metrics](http://localhost:8000/api/v1/metrics)

### Dashboard Yetenekleri:
- 🎯 **KPI Kartları:** Son denetim skoru, harf notu, bulunan açıklar ve test kapsamı.
- 🕸️ **5 Boyutlu Radar Analizi:** Güvenlik, Test, Yapısal Sağlık, DevOps ve Vibe-Coding dengesi.
- 📈 **Zaman Serisi Skor Eğrisi:** Commit bazında projenin kalite trendi ve regresyon uyarıları.
- ⚖️ **A/B Karşılaştırma Paneli:** İki denetim arasındaki puan artış/azalışlarını yan yana inceleme.
- 🏷️ **Kilometre Taşı (Milestone) Yönetimi:** Önemli sürümleri etiketleme ve taban çizgisi (baseline) belirleme.

---

## ⚙️ Yapılandırma (`warden.config.yaml`)

Projenizin kurallarını `warden.config.yaml` dosyası üzerinden ince ayar yapabilirsiniz:

```yaml
general:
  project_name: "Warden Core"
  threshold_score: 75.0               # Kalite kapısı geçme barajı (0-100)
  fail_on_critical_vulns: true        # Kritik güvenlik açığında doğrudan fail et
  ignore_paths:
    - "tests/fixtures"
    - "migrations"

category_weights:
  security_supply_chain: 0.25         # Güvenlik ve Tedarik Zinciri
  code_health_test: 0.25              # Kod Sağlığı ve Test
  structural_health: 0.20             # Yapısal Sağlık & Karmaşıklık
  resilience_performance: 0.15        # Dayanıklılık & Timeout Disiplini
  dev_hygiene_devops: 0.15            # Geliştirici Hijyeni & Vibe-Coding

thresholds:
  max_complexity: 12                  # Kabul edilebilir döngüsel karmaşıklık
  max_duplication_percent: 3.0        # İzin verilen maksimum kod tekrarı (%)
  min_coverage: 80.0                  # Minimum test kapsamı (%)
```

Detaylı parametre listesi için [Yapılandırma Kılavuzu](docs/configuration-reference.md) sayfasına bakın.

---

## 🐙 CI/CD Kalite Kapısı (GitHub Actions & GitLab)

Her Pull Request açıldığında WARDEN'i çalıştırıp PR'ı otomatik yorumlayan ve skoru düşükse merge edilmesini engelleyen GitHub Actions iş akışı:

`.github/workflows/warden-pr.yml`:
```yaml
name: WARDEN Quality Gate

on:
  pull_request:
    branches: [ main ]

jobs:
  warden:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install WARDEN
        run: |
          pip install uv && uv pip install --system -r requirements.txt
      - name: Audit & Quality Gate
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          python core/main.py audit \
            --path . \
            --incremental \
            --since-commit origin/${{ github.base_ref }} \
            --min-score 75 \
            --fail-on-critical
```

Detaylı CI/CD entegrasyon şablonları için [CI/CD Rehberi](docs/ci-cd-quality-gates.md) sayfasına bakın.

---

## 🐳 Production Dağıtımı (Docker & Terraform)

### Docker Compose
```bash
docker-compose up -d --build
```
- Multi-stage build ile hafif ve güvenli imaj.
- Non-root `warden` kullanıcısı ile çalışır.
- Otomatik PostgreSQL & Redis bağlantı havuzu.

### AWS ECS Fargate & Terraform
```bash
cd terraform
terraform init
terraform apply -var="subnet_ids=[\"subnet-a\", \"subnet-b\"]"
```

---

## 🔬 Test Gücü ve Dayanıklılık

WARDEN kod tabanı strictly yüksek test disipliniyle korunmaktadır:
- **472 Birim & Entegrasyon Testi** (Tümü %100 Başarılı)
- **%96 Genel Kod Kapsamı (Coverage)**
- Ağ çağrılarından ve flaky gecikmelerden arındırılmış, deterministik ve air-gapped test yürütme (<80 saniye).

```bash
# Testleri koşturmak için:
uv run pytest tests/ -q --ignore=tests/fixtures

# Kapsam raporu almak için:
uv run coverage run -m pytest tests/ -q --ignore=tests/fixtures
uv run coverage report --include="core/*"
```

---

## 📚 Dokümantasyon Rehberleri

- 🚀 [Hızlı Başlangıç Kılavuzu](docs/getting-started.md)
- 🏛️ [Mimari ve 25+ Metrik Skorlama Modeli](docs/architecture-and-scoring.md)
- 🤖 [Vibe-Coding ve AI Slop Yönetişimi](docs/vibe-coding-governance.md)
- 🚦 [CI/CD Kalite Kapıları ve Otomasyon](docs/ci-cd-quality-gates.md)
- ⚙️ [Merkezi Yapılandırma Referansı](docs/configuration-reference.md)
- 🌐 [REST API ve Webhook Entegrasyonları](docs/api-and-webhooks.md)

---

## 📄 Lisans

Bu proje **MIT Lisansı** altında lisanslanmıştır. Detaylı bilgi için [LICENSE](LICENSE) dosyasına göz atabilirsiniz.
