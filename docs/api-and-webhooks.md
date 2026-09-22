# 🌐 REST API ve Webhook Entegrasyon Kılavuzu

WARDEN; hem bir CLI aracı hem de mikroservis mimarileri ve harici panellerle entegre olabilen zengin bir **FastAPI tabanlı RESTful API** sunar.

---

## 📌 REST API Uç Noktaları

API sunucusunu başlatmak için:
```bash
uv run uvicorn core.main:app --host 0.0.0.0 --port 8000
```

Etkileşimli Swagger dokümantasyonuna `http://localhost:8000/docs` adresinden erişebilirsiniz.

### 1. Kimlik Doğrulama & Sağlık
| Metod | Uç Nokta | Yetki | Açıklama |
| :---: | :--- | :---: | :--- |
| `POST` | `/api/v1/auth/token` | Public | Kullanıcı adı ve şifre ile JWT erişim token'ı üretir. |
| `GET` | `/health` | Public | Servis canlılık kontrolü (liveness probe). |
| `GET` | `/api/v1/metrics` | Public / Ops | CPU, bellek, disk, önbellek ve denetim istatistikleri. |

### 2. Denetim & Paket İnceleme
| Metod | Uç Nokta | Yetki | Açıklama |
| :---: | :--- | :---: | :--- |
| `POST` | `/api/v1/scan` | Auditor | Yeni bir repo denetimi başlatır (`{"repo_path": "/path/to/repo"}`). |
| `GET` | `/api/v1/package/{pkg_name}` | Viewer | PyPI/npm paketi için typosquatting ve güvenlik risk skoru döndürür. |

### 3. Dashboard & Raporlama
| Metod | Uç Nokta | Yetki | Açıklama |
| :---: | :--- | :---: | :--- |
| `GET` | `/api/v1/dashboard/summary` | Viewer | Genel istatistikler, son denetim skoru ve aktif repo sayısı. |
| `GET` | `/api/v1/dashboard/repos` | Viewer | Veritabanında kayıtlı benzersiz repo yollarını listeler. |
| `GET` | `/api/v1/dashboard/trend` | Viewer | Belirli bir depo için tarihsel skor gelişim eğrisi. |
| `GET` | `/api/v1/dashboard/report/{id}`| Viewer | Raporun tüm Katman 1 ve Katman 2 detay karnesini döndürür. |
| `GET` | `/api/v1/dashboard/compare` | Viewer | İki denetim raporu (A vs B) arasındaki regresyon ve delta farkını hesaplar. |
| `POST` | `/api/v1/dashboard/milestone`| Admin | Bir raporu kilometre taşı (baseline) olarak işaretler veya kaldırır. |

---

## 📢 Webhook Entegrasyonları (Slack & Discord)

Denetim tamamlandığında WARDEN; Slack ve Discord kanallarına zengin biçimlendirilmiş özet kartları gönderebilir.

### `.env` Yapılandırması
```ini
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/T00/B00/XXXX"
DISCORD_WEBHOOK_URL="https://discord.com/api/webhooks/0000/XXXX"
```

### Bildirim Tetikleyicileri
1. **Denetim Tamamlandı:** Toplam skor, harf notu, Katman 1/2 dağılımı ve detay linki gönderilir.
2. **⚠️ Regresyon Alarmı (Regression Warning):** Eğer projenin skoru önceki denetime göre **5 puan veya daha fazla düşmüşse**, bildirim kırmızı renkte ve dikkat çekici bir uyarı başlığıyla iletilir.
3. **🚨 Kritik Güvenlik Uyarısı:** Kod tabanında gizli anahtar (secret leak) veya CRITICAL düzeyde CVE açığı tespit edildiğinde anında acil durum bildirimi tetiklenir.

---

## 💻 Python İstemci Örneği (cURL / Requests)

```python
import httpx

# 1. Token Alma (Eğer auth aktifse)
auth_resp = httpx.post("http://localhost:8000/api/v1/auth/token", json={
    "username": "admin",
    "password": "secure_password"
})
token = auth_resp.json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

# 2. Denetim Özeti Çekme
summary = httpx.get("http://localhost:8000/api/v1/dashboard/summary", headers=headers).json()
print(f"Sistem Skoru: {summary['average_score']}/100 | Toplam Denetim: {summary['total_audits']}")
```
