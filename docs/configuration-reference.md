# ⚙️ Yapılandırma Referansı (Configuration Reference)

WARDEN; yapılandırma hiyerarşisinde **12-Factor App** prensiplerine uyar. Ayarlar aşağıdaki öncelik sırasına göre yüklenir:

```
[ CLI Parametreleri ]  ──►  [ .env / Ortam Değişkenleri ]  ──►  [ warden.config.yaml ]  ──►  [ Varsayılan Ayarlar ]
   (En Yüksek Öncelik)                                                                     (En Düşük Öncelik)
```

---

## 📄 `warden.config.yaml` Tam Şablonu

Proje kök dizininde `warden.config.yaml` dosyası oluşturarak denetim kurallarını projenize göre özelleştirebilirsiniz:

```yaml
# ==============================================================================
# 🛡️ WARDEN — Merkezi Yapılandırma Dosyası
# ==============================================================================

general:
  project_name: "Warden Core"
  threshold_score: 75.0               # Kalite kapısı geçme barajı (0 - 100)
  fail_on_critical_vulns: true        # Kritik CVE veya sızıntıda skordan bağımsız fail et
  ignore_paths:                       # Taramadan hariç tutulacak ek dizinler
    - "tests/fixtures"
    - "alembic/versions"
    - "frontend/dist"
    - "legacy"

# ------------------------------------------------------------------------------
# ⚖️ Katman 1 Kategori Ağırlıkları (Toplam = 1.00 olmalıdır)
# ------------------------------------------------------------------------------
category_weights:
  security_supply_chain: 0.25         # Güvenlik ve Tedarik Zinciri
  code_health_test: 0.25              # Kod Sağlığı ve Test Kapsamı
  structural_health: 0.20             # Yapısal Sağlık & Karmaşıklık
  resilience_performance: 0.15        # Dayanıklılık & Timeout Disiplini
  dev_hygiene_devops: 0.15            # Geliştirici Hijyeni & Vibe-Coding

# ------------------------------------------------------------------------------
# 🎯 Eşik Değerleri ve Tolerans Limitleri
# ------------------------------------------------------------------------------
thresholds:
  max_complexity: 12                  # Kabul edilebilir maksimum döngüsel karmaşıklık (Cyclomatic)
  max_duplication_percent: 3.0        # İzin verilen maksimum kod tekrarı yüzdesi (%)
  min_coverage: 80.0                  # Hedeflenen minimum test satır kapsamı (%)
  max_vibe_ratio: 0.15                # Kabul edilebilir maksimum AI-slop / didaktik yorum oranı
  max_hotspot_churn_ratio: 0.05       # Karmaşık dosyalarda riskli commit değişim sıklığı eşiği

# ------------------------------------------------------------------------------
# 🧠 Katman 2: LLM ve Rubrik Ayarları
# ------------------------------------------------------------------------------
llm:
  provider: "gemini"                  # gemini | openai | anthropic | ollama
  models:                             # Yedekli fallback model listesi (sırayla denenir)
    - "gemini-2.5-pro"
    - "gemini-2.5-flash"
    - "gemini-2.0-flash"
  timeout_seconds: 45                 # LLM çağrısı zaman aşımı (sn)
  temperature: 0.1                    # Deterministik puanlama için düşük sıcaklık
  retry_count: 3                      # Rate limit (429) durumunda yeniden deneme adedi
```

---

## 🔐 Ortam Değişkenleri (`.env`)

Gizli anahtarlar, veritabanı bağlantıları ve harici servis entegrasyonları için `.env` dosyasını kullanın:

| Değişken Adı | Tip | Varsayılan Değer | Açıklama |
| :--- | :---: | :---: | :--- |
| `GEMINI_API_KEY` | String | - | Katman 2 için Google Gemini API anahtarı. |
| `OPENAI_API_KEY` | String | - | OpenAI sağlayıcısı kullanılacaksa API anahtarı. |
| `ANTHROPIC_API_KEY`| String | - | Claude modelleri için API anahtarı. |
| `WARDEN_LLM_PROVIDER` | String | `gemini` | Varsayılan LLM sağlayıcısı. |
| `DATABASE_URL` | String | `sqlite:///./warden.db`| SQLModel bağlantı URI (`postgresql://user:pass@host/db`). |
| `REDIS_URL` | String | `redis://localhost:6379/0`| Dağıtık önbellek URI (Yoksa bellek içi önbelleğe düşer). |
| `WARDEN_AUTH_ENABLED`| Boolean| `false` | API uç noktalarında JWT kimlik doğrulamasını zorunlu kılar. |
| `JWT_SECRET_KEY` | String | `dev-secret` | JWT token imzalamak için HS256 gizli anahtarı. |
| `SLACK_WEBHOOK_URL`| String | - | Denetim sonuçlarının gönderileceği Slack Incoming Webhook. |
| `DISCORD_WEBHOOK_URL`| String| - | Denetim sonuçlarının gönderileceği Discord Webhook. |
| `WARDEN_SANDBOX` | Boolean| `true` | Test koşumlarında OS kaynak limitlerini ve izolasyonu aktif eder. |
