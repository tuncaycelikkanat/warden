# WARDEN — Otonom Kod Denetimi ve Karne Sistemi

WARDEN, yapay zeka destekli modern yazılım geliştirme ("vibe coding") çağında güvenlik açıklarını, tedarik zinciri zafiyetlerini, kod kokularını ve mimari disiplini güvence altına alan çok katmanlı bir denetim ve kalite güvence (QA) sistemidir.

---

## Özellikler

- **Katman 1 (Mekanik & Deterministik, %60):**
  - 🛡️ **Güvenlik & Tedarik Zinciri:** Semgrep SAST, Gitleaks geçmiş taraması, OSV.dev CVE taraması, Lisans uyumluluğu (`pip-licenses`).
  - 🧪 **Kod Sağlığı & Test:** Test kapsamı (`coverage.py`), Test kalitesi (AST assertion kontrolü), Lint & Stil (`ruff`), Tip güvenliği (`mypy`).
  - 🏗️ **Yapısal Sağlık:** Radon döngüsel karmaşıklık, JSCPD kod tekrarı, Git churn teknik borç analizi.
  - ⚙️ **Dayanıklılık & Performans:** AST ile bare `except:` ve eksik `timeout` tespiti.
  - 🔧 **DevOps & Geliştirici Hijyeni:** Dokümantasyon (`interrogate`), CI/CD boru hattı, Docker hazırlığı, Git commit hijyeni.
- **Katman 2 (Dinamik Semantik, %40):**
  - Proje profiline göre açılan dinamik kategoriler (`LLM_INTEGRATION`, `QUANTITATIVE_LOGIC`, `API_DISCIPLINE`, vb.).
  - Gemini destekli 0/3/6/9 çapalı rubrik değerlendirmesi ve kanıt paketi doğrulaması.

---

## Kurulum (Setup)

Projeyi yerel ortamınızda çalıştırmak için aşağıdaki adımları izleyin:

```bash
# 1. Depoyu klonlayın
git clone https://github.com/tuncaycelikkanat/warden.git
cd warden

# 2. Sanal ortamı oluşturun ve bağımlılıkları kurun (uv önerilir)
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 3. Çevre değişkenlerini yapılandırın
cp .env.example .env
# .env dosyasına geçerli GEMINI_API_KEY anahtarınızı girin
```

---

## Kullanım (Usage)

### 1. Tam Denetim (Full Audit) CLI Komutu

Herhangi bir depoyu veya geçerli dizini denetlemek için:

```bash
# Geçerli repo üzerinde denetim koşturma
PYTHONPATH=. uv run python core/main.py audit --path .

# Farklı bir proje dizinini denetleme
PYTHONPATH=. uv run python core/main.py audit --path /path/to/project
```

Denetim tamamlandığında:
- Konsolda özet puan ve harf notu gösterilir.
- Sonuçlar SQLite veritabanına (`warden.db`) kaydedilir.
- Proje kök dizinine görsel bir yönetici özeti (`WARDEN_EXECUTIVE_REPORT.md`) üretilir.

### 2. API Sunucusunu Başlatma

```bash
uvicorn core.main:app --host 0.0.0.0 --port 8000 --reload
```

Sağlık kontrolü:
```bash
curl http://localhost:8000/api/v1/health
```

### 3. Testleri Çalıştırma

```bash
PYTHONPATH=. uv run pytest tests/ -q --ignore=tests/fixtures
```

---

## Lisans

Bu proje MIT Lisansı ile lisanslanmıştır. Detaylar için [LICENSE](LICENSE) dosyasına bakınız.
