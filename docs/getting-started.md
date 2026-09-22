# 🚀 Hızlı Başlangıç Kılavuzu (Getting Started)

WARDEN, yapay zeka destekli kodlama çağında yazılım projelerinin güvenlik, mimari tutarlılık ve kod kalitesini otonom olarak denetleyen iki katmanlı bir platformdur.

Bu kılavuz, WARDEN'i 5 dakika içinde sisteminize kurup ilk denetiminizi (audit) gerçekleştirmeniz için hazırlanmıştır.

---

## 📋 Ön Gereksinimler

WARDEN'in tüm yeteneklerinden (özellikle Katman 1 mekanik analizörleri) tam verim alabilmek için aşağıdaki araçların sisteminizde bulunması önerilir:

| Araç | Minimum Sürüm | Amaç | Zorunlu mu? |
| :--- | :---: | :--- | :---: |
| **Python** | 3.11+ | Temel çalışma ortamı | **Evet** |
| **uv** | 0.4+ | Hızlı sanal ortam & bağımlılık yöneticisi | Önerilir |
| **Gitleaks** | 8.21+ | Git geçmişinde gizli anahtar/token sızıntısı taraması | Önerilir (Yoksa atlanır) |
| **Node.js & npm** | 18+ | `jscpd` ile diller arası kod tekrarı (DRY) tespiti | Önerilir (Yoksa fallback) |
| **Semgrep** | 1.60+ | AST tabanlı SAST güvenlik açığı taraması | Pip ile otomatik kurulur |

---

## ⚡ 1. Otomatik Kurulum (Linux & macOS)

En hızlı yöntem, sistem bağımlılıklarını otomatik kontrol eden `install.sh` betiğidir:

```bash
git clone https://github.com/tuncaycelikkanat/warden.git
cd warden
chmod +x install.sh
./install.sh
```

Bu script şunları otomatik yapar:
1. Python sürümünü doğrular.
2. `uv` aracını kullanarak izole bir `.venv` sanal ortamı kurar.
3. `requirements.txt` içerisindeki tüm kütüphaneleri yükler.
4. `gitleaks` ve `jscpd` gibi sistem araçlarını denetler, eksikse kurulum önerisi sunar.
5. `.env.example` dosyasından `.env` oluşturur.

---

## 🛠️ 2. Manuel Kurulum (`uv` ile)

```bash
# 1. Depoyu klonlayın
git clone https://github.com/tuncaycelikkanat/warden.git
cd warden

# 2. Sanal ortam oluşturup aktif edin
uv venv
source .venv/bin/activate  # Windows için: .venv\Scripts\activate

# 3. Bağımlılıkları yükleyin
uv pip install -r requirements.txt

# 4. Ortam dosyasını oluşturun
cp .env.example .env
```

---

## 🔑 3. Ortam Değişkenleri Yapılandırması (`.env`)

WARDEN'in **Katman 2 (LLM Semantik Değerlendirme)** katmanını kullanabilmesi için bir API anahtarına ihtiyacı vardır. 

`.env` dosyanızı açın ve Gemini API anahtarınızı tanımlayın:

```ini
# Katman 2 Semantik Rubrik Değerlendirmesi için Zorunlu:
GEMINI_API_KEY="AIzaSyYourGeminiApiKeyHere..."

# Opsiyonel: Veritabanı ve Önbellek
DATABASE_URL="sqlite:///./warden.db"
REDIS_URL="redis://localhost:6379/0"

# Opsiyonel: Güvenlik ve Webhook Bildirimleri
WARDEN_AUTH_ENABLED=false
JWT_SECRET_KEY="super-secret-jwt-key"
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/..."
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/..."
```

> [!NOTE]
> `GEMINI_API_KEY` tanımlanmamış olsa bile WARDEN çalışmayı durdurmaz. Otomatik olarak **Zarafetle Derece Düşürme (Graceful Degradation)** moduna geçer; Katman 2'nin %40'lık ağırlığını doğrudan Katman 1'in 16 mekanik analizörüne aktarır ve denetimi %100 mekanik olarak tamamlar.

---

## 🏃 4. İlk Denetiminizi Gerçekleştirin

### Kendi Projenizde Denetim Koşturma
Bulunduğunuz dizini veya hedef bir projeyi denetlemek için:

```bash
uv run python core/main.py audit --path .
```

### Örnek Terminal Çıktısı

```text
================================================================================
🛡️  WARDEN — Otonom Kod Denetimi ve Yönetişim Motoru
================================================================================
📂 Hedef Depo: /home/tuncay/PycharmProjects/warden
⏱️  Başlangıç: 2026-09-22 21:55:00
🔍 16 Katman-1 Analizörü ve Dinamik Kanıt Toplayıcılar Başlatılıyor...

[✓] Güvenlik & SAST (Semgrep) ................... 100.0/100 (0 açık)
[✓] Gizli Bilgi Sızıntısı (Gitleaks) ............ 100.0/100 (0 sızıntı)
[✓] Bağımlılık Güvenliği (OSV) .................. 100.0/100 (0 CVE)
[✓] Lisans Uyumluluğu ........................... 100.0/100 (MIT uyumlu)
[✓] Tip Güvenliği & Tutarlılık (Mypy) .......... 100.0/100 (0 tip hatası)
[✓] Döngüsel Karmaşıklık (Radon) ................ 94.2/100 (Ortalama CC: 2.1)
[✓] Kod Tekrarı & DRY (JSCPD) ................... 96.5/100 (Tekrar: %1.2)
[✓] Test Kapsamı & Kalitesi ..................... 96.0/100 (472 test, %96 cov)
[✓] AI Slop & Vibe-Coding Tespiti ............... 95.0/100 (Temiz kod tabanı)
...
🧠 Katman 2: LLM Dinamik Rubrik Değerlendirmesi ... Tamamlandı (Puan: 92/100)

================================================================================
🏆 WARDEN DENETİM KARNESİ: 94/100 (A - Başarılı)
================================================================================
• Katman 1 (Mekanik): 95/100 (%60 Ağırlık)
• Katman 2 (Semantik): 92/100 (%40 Ağırlık)
• Durum: ✅ KALİTE KAPISI GEÇİLDİ (Baraj: 75.0)
• Kaydedilen Rapor ID: #45
• Detaylı Rapor: /home/tuncay/PycharmProjects/warden/warden_reports/warden_report_20260922.md
================================================================================
```

---

## 🌐 5. Web Dashboard'u Başlatın

WARDEN'in karanlık temalı modern web kontrol panelini ve REST API'sini başlatmak için:

```bash
uv run uvicorn core.main:app --host 0.0.0.0 --port 8000 --reload
```

Tarayıcınızdan şu adresleri ziyaret edebilirsiniz:
- 📊 **Web Dashboard:** `http://localhost:8000/dashboard/`
- 📖 **Swagger API Belgeleri:** `http://localhost:8000/docs`
- 💓 **Sağlık & Metrikler:** `http://localhost:8000/api/v1/metrics`

---

## 🎯 Sıradaki Adımlar

- [Mimari ve Skorlama Modeli](architecture-and-scoring.md): WARDEN'in 5 boyutu ve puanlama formülleri.
- [Vibe-Coding Yönetişimi](vibe-coding-governance.md): AI tarafından üretilen kod riskleri ve tespit modelleri.
- [CI/CD Kalite Kapısı Kurulumu](ci-cd-quality-gates.md): GitHub Actions ve GitLab CI entegrasyonları.
- [Yapılandırma Kılavuzu](configuration-reference.md): `warden.config.yaml` dosyasının tüm parametreleri.
