# 🤖 Vibe-Coding ve AI Slop Yönetişimi

Son yıllarda LLM tabanlı kod asistanlarının (Cursor, GitHub Copilot, Claude, ChatGPT vb.) yaygınlaşmasıyla birlikte **"Vibe Coding"** terimi hayatımıza girdi: Geliştiricinin detaylara ve mimari disipline odaklanmak yerine doğrudan yapay zekanın ürettiği kod bloklarını projeye kabul etmesi.

Yapay zeka muazzam bir hız katsayısı sunsa da, arkasında **"AI Slop" (Yapay Zeka Kirliliği)** ve sinsi mimari çürümeler bırakır. WARDEN, bu yeni nesil yazılım risklerini tespit etmek ve yönetmek üzere tasarlanmış ilk otonom denetim motorudur.

---

## ⚠️ Yapay Zeka Kaynaklı 5 Temel Risk

```
                  ┌─────────────────────────────────────────┐
                  │          Vibe-Coding Riskleri           │
                  └────────────────────┬────────────────────┘
                                       │
     ┌──────────────────┬──────────────┴─────┬──────────────────┐
     ▼                  ▼                    ▼                  ▼
┌───────────────┐ ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│ Didaktik Yorum│ │   Yutulan     │  │   Zaman Aşımı │  │   Prompt      │
│  & MD Artıkları│ │  Hatalar     │  │   Eksikliği   │  │   Sızıntısı   │
│ (AI Slop)     │ │ (except pass) │  │  (Hang Riski) │  │   & Enjeksiyon│
└───────────────┘ └───────────────┘  └───────────────┘  └───────────────┘
```

### 1. Didaktik Yorum Kirliliği ve Markdown Artıkları
Yapay zeka asistanları, genellikle insan geliştiricilere açıklama yapmak amacıyla kodun içine aşırı verbose, eğitici (didaktik) ve bariz şeyleri tekrarlayan yorum satırları ekler:
```python
# ❌ Vibe-Coding Örneği:
# This function calculates the sum of two integers
# It takes parameter a which is an integer
# and parameter b which is an integer
# and then returns the sum of a and b using the plus operator.
def add(a: int, b: int) -> int:
    return a + b
```
Ayrıca, chat penceresinden kopyalanırken kod dosyasına sızan ` ```python ` veya `Here is the implementation:` gibi markdown artıkları WARDEN tarafından anında yakalanır.

### 2. Yutulan İstisnalar (Silent Failure & Swallowed Exceptions)
Yapay zeka asistanları, kodun hata vermeden "çalışıyor gibi görünmesi" için sık sık `try-except` blokları ekleyip hataları sessizce yutar:
```python
# ❌ Vibe-Coding Örneği:
try:
    process_payment(order)
except Exception:
    pass  # Hata susturuldu, işlem başarısız oldu ama kimsenin haberi yok!
```
WARDEN'in AST tabanlı `resilience_ast` analizörü, istisnası yutulmuş tüm blokları tespit eder ve güvenlik/dayanıklılık puanını düşürür.

### 3. Zaman Aşımı (Timeout) Tanımlanmamış Dış Çağrılar
LLM'ler tarafından üretilen `requests.get()`, `httpx.post()` veya veritabanı bağlantılarında neredeyse her zaman `timeout` parametresi unutulur:
```python
# ❌ Tehlikeli: Ağda bir gecikme olursa thread sonsuza dek kilitlenir
response = requests.get("https://api.external.com/data")

# ✅ WARDEN Standardı:
response = requests.get("https://api.external.com/data", timeout=10.0)
```

### 4. Pini Çözülmüş Bağımlılıklar (Unpinned Dependencies)
Yapay zeka, `requirements.txt` veya `package.json` önerirken genellikle sürüm numaralarını ya yazmaz ya da `latest` kullanır. Bu durum projenin yarın sabah bozulmasına veya tedarik zinciri saldırılarına (supply-chain attack) açık hale gelmesine yol açar.

### 5. Yüksek Churn × Yüksek Karmaşıklık (Hallucination Drift)
Geliştirici bir bug'ı çözmek için LLM'e sürekli aynı dosyayı yeniden yazdırdığında, o dosyanın commit sıklığı (churn) tavan yapar ancak fonksiyonlar gitgide daha karmaşık hale gelir. WARDEN, Git geçmişi ile Radon döngüsel karmaşıklığını birleştirerek bu "saatli bombaları" (**Hotspots**) haritalandırır.

---

## 🔍 WARDEN Nasıl Tespit Eder?

WARDEN, vibe-coding ve AI kirliliğini tespit etmek için çok katmanlı bir mekanizma işletir:

1. **Heuristic Regex & NLP Analizi:** AI tarafından sıkça kullanılan kalıp cümleler ("sure, here is...", "as requested", "note that we need to", "let's implement...") ve gereksiz eğitici kalıplar taranır.
2. **Semgrep Vibe-Coding Kural Paketi (`core/rules/`):**
   - Prompt Injection zafiyetleri (doğrudan kullanıcı girdisinin system prompt'a yapıştırılması).
   - `eval()`, `exec()`, `os.system()` gibi güvensiz dinamik çalıştırma kalıpları.
   - Kontrolsüz CORS politikaları (`allow_origins=["*"]`).
3. **AST Hiyerarşik Denetimi:** Python AST'si üzerinden `except:` blokları, `timeout` parametresi eksik olan fonksiyon çağrıları ve eksik tip tanımları taranır.
4. **JavaScript / TypeScript Özel Kuralları:** `any` tipi bağımlılığı, kontrolsüz `innerHTML` kullanımı ve debug logları (`console.log`) tespit edilir.

---

## 💡 Yapay Zeka ile Güvenli Geliştirme İçin En İyi Pratikler

1. **WARDEN'i CI Pipeline'ına Kalite Kapısı (Quality Gate) Olarak Ekleyin:** Kod tabanına giren her Pull Request, en az 75 (veya 80) puan almak zorunda olsun.
2. **Artımlı Denetim (Incremental Audit) Kullanın:** Commit atmadan önce `warden audit --incremental` çalıştırarak yalnızca yazdığınız yeni satırları 3 saniyede denetleyin.
3. **Docstring ve Tip İpuçlarını Zorunlu Tutun:** Yapay zekaya kod yazdırırken `mypy` ve `interrogate` kurallarından taviz vermeyin.
4. **Yapay Zeka Yorumlarını Temizleyin:** Kodu kabul etmeden önce bariz şeyleri anlatan didaktik yorumları silin, yalnızca "neden" yapıldığını açıklayan mimari kararları koruyun.
