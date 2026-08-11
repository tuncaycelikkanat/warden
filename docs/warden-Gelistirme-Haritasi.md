# warden — Geliştirme Haritası (Küçük Adımlarla İlerleme Planı)

Bu belge, mimari tasarım raporunda tanımlanan Faz 1 (MVP) ve Faz 2 (Editör/Ajan Entegrasyonu) kapsamını, her biri **1-3 gün içinde bitirebileceğin, net bir "bu bittiğinde şunu göreceksin" kriteri olan** küçük adımlara böler. Adım sayısı fazla olsa da, her adım tek başına küçük ve anlaşılırdır — sırayla ilerledikçe sistem parça parça hayata geçer.

---

## 0. Önce: Dil ve Teknoloji Seçimi (Gerekçeli)

### Ana Programlama Dili: **Python**

warden'ın Core Engine'i için en performanslı seçim aslında Python'dur — bu ilk bakışta şaşırtıcı gelebilir ("Python yavaş değil mi?") ama şu nedenlerle doğru tercih:

- **İş yükü CPU-ağır değil, I/O-ağır:** Sistem çoğunlukla dosya okuma, harici API'lere (PyPI/npm, LLM sağlayıcı) ağ isteği atma ve dış süreç (Semgrep) çalıştırma işleri yapıyor. Bu tür işlerde Python'un `asyncio` ile yazılmış async kodu, Go/Rust gibi dillerle neredeyse aynı gerçek dünya performansını verir — çünkü darboğaz CPU değil, ağ gecikmesidir.
- **Ekosistem uyumu:** Semgrep (Python), Anthropic'in resmi MCP SDK'sı (Python), GitPython — hepsi Python'da olgun ve iyi belgelenmiş. Rust/Go seçseydin bu araçların çoğunu ya yeniden yazman ya da süreç dışı (subprocess) çağırman gerekirdi.
- **Senin mevcut deneyimin:** Crypto MAS, Omni-Agent, NOVA — hepsi Python/FastAPI. Yeni bir dil öğrenmeye zaman harcamak yerine, doğrudan üretime geçebilirsin.

**Nerede Python "yeterince hızlı değil" olabilir?** Git hook'un her commit'te açılıp kapanması senaryosunda, Python yorumlayıcısının başlangıç (interpreter startup) gecikmesi (~100-300ms) can sıkıcı olabilir. Bunu şöyle çözüyoruz: **Core Engine sürekli çalışan bir arka plan servisi (`uvicorn` ile ayakta) olacak; Git hook yalnızca ona `curl` ile istek atan birkaç satırlık bir kabuk (shell) betiği olacak.** Böylece Python'un başlatma maliyeti bir kere (bilgisayar açılışında) ödenir, her commit'te değil.

### Kütüphane/Araç Listesi

| Amaç | Araç/Kütüphane | Neden |
|---|---|---|
| Web/API çatısı | **FastAPI** + **uvicorn** | Async destek, otomatik OpenAPI dokümantasyonu, zaten bildiğin araç |
| Veri doğrulama | **Pydantic** | FastAPI ile birebir entegre, tip güvenliği |
| Veritabanı erişimi | **SQLModel** (SQLAlchemy + Pydantic birleşimi) | SQLite ile kolay, tip güvenli sorgular |
| Statik analiz motoru | **Semgrep** (Python paketi olarak) | Hazır, olgun, kural yazımı kolay (YAML) |
| Git geçmişi erişimi | **GitPython** | Commit geçmişi, diff çıkarma |
| HTTP istemcisi (registry sorguları için) | **httpx** (async) | PyPI/npm sorgularını asyncio ile paralel atabilmek için |
| Zamanlanmış görevler | **APScheduler** | Haftalık teknik borç taraması için |
| Test | **pytest** + **pytest-asyncio** + **httpx.AsyncClient** | Birim ve entegrasyon testleri |
| MCP sunucusu | **mcp** (Anthropic'in resmi Python SDK'sı) | Claude Code/Antigravity uyumluluğu garantisi |
| VS Code eklentisi | **TypeScript** + VS Code Extension API | Zorunlu — VS Code eklentileri başka dilde yazılamaz |
| Paket yönetimi (Python) | **uv** (pip yerine) | Çok daha hızlı bağımlılık kurulumu, modern standart |
| Kod formatlama/lint | **ruff** | Hem formatter hem linter, tek araçla ikisini de hallediyor, hızlı |

### Proje İskeleti Önerisi

```
warden/
├── core/                    # Core Engine (Python)
│   ├── api/                 # FastAPI route'ları
│   ├── services/            # SecurityScanner, PackageChecker, vb.
│   ├── models/              # Pydantic/SQLModel modelleri
│   ├── infra/               # DB, Git erişimi, LLM router
│   └── rules/vibe_coding/   # Semgrep YAML kuralları
├── mcp_server/              # MCP sunucu wrapper'ı
├── vscode-extension/        # TypeScript VS Code eklentisi
├── git-hooks/               # Shell betikleri (pre-commit)
└── tests/
```

---

## 1. Milestone 0 — Ortam ve İskelet (Hedef: "Merhaba Dünya" seviyesi çalışan bir şey)

**Adım 0.1 — Geliştirme ortamı kurulumu**
`uv` kur, Python 3.12 sanal ortamı oluştur, boş bir Git deposu aç.
✅ *Bittiğinde göreceğin:* `uv run python --version` komutu 3.12 döndürüyor.

**Adım 0.2 — Proje iskeletini oluştur**
Yukarıdaki klasör yapısını oluştur, boş `__init__.py` dosyalarını ekle.
✅ *Bittiğinde göreceğin:* Klasör yapısı hazır, henüz kod yok ama proje "var".

**Adım 0.3 — FastAPI "merhaba dünya" endpoint'i**
Tek bir `/api/v1/health` endpoint'i yaz, `{"status": "ok"}` dönsün.
✅ *Bittiğinde göreceğin:* `uv run uvicorn core.main:app --reload` çalıştırıp tarayıcıda `localhost:8000/api/v1/health` açtığında JSON cevabı görüyorsun.

**Adım 0.4 — SQLite bağlantısını kur**
SQLModel ile boş bir `scan_results` tablosu tanımla, uygulama açılışında tabloyu otomatik oluştur.
✅ *Bittiğinde göreceğin:* Proje klasöründe bir `.db` dosyası oluşuyor, içinde boş tablo var (DB Browser for SQLite ile açıp bakabilirsin).

**Adım 0.5 — İlk testini yaz**
`/api/v1/health` endpoint'i için tek bir pytest testi yaz.
✅ *Bittiğinde göreceğin:* `uv run pytest` komutu "1 passed" yazıyor.

---

## 2. Milestone 1 — Security Scanner (İlk Gerçek Özellik)

**Adım 1.1 — Semgrep'i tek başına dener misin?**
Kod yazmadan önce, terminalde `semgrep --config=p/security-audit senin_bir_test_dosyan.py` komutunu manuel çalıştır, çıktısını incele.
✅ *Bittiğinde göreceğin:* Semgrep'in ürettiği ham JSON/terminal çıktısına aşina oluyorsun — bir sonraki adımda bunu kod ile parse edeceksin.

**Adım 1.2 — İlk özel kuralını yaz**
`rules/vibe_coding/hardcoded-secret.yaml` dosyasını oluştur, tek bir basit kural yaz (örn. `api_key = "..."` paternini yakalasın).
✅ *Bittiğinde göreceğin:* Kasıtlı olarak hardcoded key içeren bir test dosyasında Semgrep bu kuralı tetikliyor.

**Adım 1.3 — SecurityScannerService iskeletini yaz**
Semgrep'i Python'dan `subprocess` ile çağıran, JSON çıktısını parse eden basit bir servis sınıfı yaz (henüz API'ye bağlama).
✅ *Bittiğinde göreceğin:* `pytest` ile bu servisi doğrudan çağıran bir birim testi geçiyor.

**Adım 1.4 — İkinci ve üçüncü kuralı ekle**
`sql-string-concat.yaml` ve `missing-input-validation.yaml` kurallarını yaz.
✅ *Bittiğinde göreceğin:* Üç farklı "kirli" test dosyasında üç farklı kural doğru tetikleniyor.

**Adım 1.5 — Servisi API'ye bağla**
`POST /api/v1/scan` endpoint'ini yaz; gelen dosya yolunu SecurityScannerService'e ver, sonucu JSON olarak dön.
✅ *Bittiğinde göreceğin:* `curl` ile bir dosya yolu gönderdiğinde gerçek tarama sonucu JSON olarak dönüyor.

**Adım 1.6 — Sonucu veritabanına kaydet**
Her tarama sonucunu `scan_results` tablosuna yaz.
✅ *Bittiğinde göreceğin:* Birkaç tarama yaptıktan sonra DB Browser'da geçmiş taramaları görebiliyorsun.

**Adım 1.7 — Risk seviyesi hesaplama mantığını ekle**
Bulunan kuralların önem derecesine göre `low/medium/high` risk seviyesi hesapla.
✅ *Bittiğinde göreceğin:* Kritik bir açık içeren dosya "high", temiz bir dosya "low" dönüyor.

---

## 3. Milestone 2 — Paket Güvenilirlik Kontrolü

**Adım 2.1 — PyPI API'sini manuel dene**
Tarayıcıda `https://pypi.org/pypi/requests/json` adresini aç, dönen JSON'un yapısına bak.
✅ *Bittiğinde göreceğin:* Paketin yayın tarihi, açıklaması gibi alanların JSON'daki yerini biliyorsun.

**Adım 2.2 — httpx ile async registry istemcisi yaz**
Verilen bir paket adı için PyPI'dan metadata çeken basit bir fonksiyon yaz.
✅ *Bittiğinde göreceğin:* `pytest` testinde gerçek bir paket adı (`requests`) için metadata dönüyor, olmayan bir isim (`asdkjaskdj123`) için `None` dönüyor.

**Adım 2.3 — Risk puanlama mantığını ekle**
Yayın tarihi + indirme sayısı üzerinden basit bir puanlama fonksiyonu yaz (npm/PyPI indirme sayısı için ayrı bir API gerekebilir — PyPI için `pypistats.org` API'sini kullanabilirsin).
✅ *Bittiğinde göreceğin:* Yeni/az bilinen bir pakette yüksek risk puanı, `requests` gibi popüler bir pakette düşük risk puanı çıkıyor.

**Adım 2.4 — İsim benzerliği (typosquatting) kontrolünü ekle**
En popüler 1000 PyPI paketinin bir listesini indir, yerel bir dosyada tut; `python-Levenshtein` kütüphanesiyle isim benzerliği hesapla.
✅ *Bittiğinde göreceğin:* `reqeusts` (yazım hatalı) gibi bir isim verdiğinde, sistem "`requests`'e çok benziyor, dikkat et" diyor.

**Adım 2.5 — Endpoint'e bağla**
`POST /api/v1/packages/check` endpoint'ini yaz.
✅ *Bittiğinde göreceğin:* `curl` ile paket adı gönderdiğinde risk değerlendirmesi JSON olarak dönüyor.

---

## 4. Milestone 3 — Git Hook Entegrasyonu (İlk Uçtan Uca Kullanım!)

**Adım 3.1 — Basit bir shell betiği yaz**
`git-hooks/pre-commit` dosyasını oluştur; şimdilik yalnızca "warden çalışıyor" yazdırsın.
✅ *Bittiğinde göreceğin:* Bir test commit attığında terminalde bu mesajı görüyorsun.

**Adım 3.2 — Değişen dosyaları tespit et**
Betik içinde `git diff --cached --name-only` ile commit'e giren dosyaları listele.
✅ *Bittiğinde göreceğin:* Betik, commit ettiğin dosyaların isimlerini terminalde listeliyor.

**Adım 3.3 — Core Engine'e istek at**
Her değişen `.py` dosyası için `curl` ile `/api/v1/scan` endpoint'ine istek at.
✅ *Bittiğinde göreceğin:* Bilerek güvenlik açığı olan bir dosyayı commit etmeye çalıştığında, terminalde uyarı çıkıyor.

**Adım 3.4 — Kritik bulguda commit'i engelle**
Eğer `risk_level == "high"` dönerse, betik `exit 1` ile commit'i durdursun.
✅ *Bittiğinde göreceğin:* Güvenlik açığı olan kodu commit edemiyorsun; düzelttiğinde commit geçiyor.

**Adım 3.5 — Kurulum betiği yaz**
`.git/hooks/pre-commit` içine bu betiği otomatik kopyalayan bir `install.sh` yaz.
✅ *Bittiğinde göreceğin:* Tek bir komutla (`./install.sh`) hook kuruluyor — **artık MVP'nin en kritik parçası eninde sonunda çalışıyor.** 🎉

---

## 5. Milestone 4 — VS Code Eklentisi (Görsel Geri Bildirim)

**Adım 4.1 — Boş bir VS Code eklentisi iskeleti oluştur**
`yo code` (Yeoman generator) ile TypeScript eklenti şablonu oluştur.
✅ *Bittiğinde göreceğin:* F5'e basınca yeni bir VS Code penceresi açılıyor, eklentin "yüklü" görünüyor.

**Adım 4.2 — Basit bir komut ekle**
Command Palette'ten çağrılabilen, sadece bir bildirim (notification) gösteren bir komut yaz.
✅ *Bittiğinde göreceğin:* `Ctrl+Shift+P` → komutunu bul → çalıştır → bildirim çıkıyor.

**Adım 4.3 — Core Engine'e HTTP isteği at**
Eklenti içinden `fetch` ile `/api/v1/health` endpoint'ine istek at, sonucu bildirim olarak göster.
✅ *Bittiğinde göreceğin:* Eklenti, arka planda çalışan Python servisiyle "konuşuyor".

**Adım 4.4 — Dosya kaydetme olayını yakala**
`onDidSaveTextDocument` olayına bağlan, kaydedilen dosyanın yolunu konsola yazdır.
✅ *Bittiğinde göreceğin:* Herhangi bir dosyayı kaydettiğinde Debug Console'da dosya yolu görünüyor.

**Adım 4.5 — Kaydetmede taramayı tetikle**
Kaydedilen dosyayı `/api/v1/scan`'e gönder, sonucu al.
✅ *Bittiğinde göreceğin:* Dosya kaydettiğinde arka planda gerçek bir tarama çalışıyor (henüz görsel çıktı yok, konsolda görüyorsun).

**Adım 4.6 — Diagnostic (Problems paneli) entegrasyonu**
`vscode.languages.createDiagnosticCollection` kullanarak bulguları Problems paneline yaz.
✅ *Bittiğinde göreceğin:* Güvenlik açığı olan bir satırın altında **kırmızı dalgalı çizgi** görüyorsun, Problems panelinde açıklama okuyabiliyorsun — bu, projenin en tatmin edici anlarından biri olacak.

---

## 6. Milestone 5 — MCP Sunucusu (Claude Code/Antigravity Entegrasyonu)

**Adım 5.1 — MCP SDK'sını kur, en basit örnek sunucuyu çalıştır**
Anthropic'in resmi Python MCP SDK dokümantasyonundaki "merhaba dünya" sunucu örneğini birebir çalıştır.
✅ *Bittiğinde göreceğin:* MCP Inspector aracıyla bu sunucuya bağlanıp örnek aracı çağırabiliyorsun.

**Adım 5.2 — `check_package` aracını MCP'ye ekle**
Milestone 2'de yazdığın paket kontrol servisini bir MCP tool olarak sar.
✅ *Bittiğinde göreceğin:* MCP Inspector'dan bu aracı çağırdığında gerçek paket kontrolü sonucu dönüyor.

**Adım 5.3 — `security_scan` aracını ekle**
Aynı şekilde Milestone 1'deki servisi MCP tool'u yap.
✅ *Bittiğinde göreceğin:* İki araç da Inspector'dan çalışıyor.

**Adım 5.4 — Claude Code ile bağla**
Projende bir `.mcp.json` dosyası oluştur, Claude Code'u bu sunucuyla yapılandır.
✅ *Bittiğinde göreceğin:* Claude Code'a "şu paketi kur" dediğinde, ajanın kendiliğinden `check_package` aracını çağırdığını (Claude Code'un tool-call loglarında) görüyorsun — **bu, projenin en etkileyici demo anı olacak.**

---

## 7. Milestone 6 — Cilalama ve Bitirme Hazırlığı

**Adım 6.1 — Test kapsamını artır**
Her serviste eksik kalan birim testlerini tamamla, `pytest --cov` ile kapsamı ölç.
✅ *Bittiğinde göreceğin:* Kapsam raporu %70+ gösteriyor.

**Adım 6.2 — Gerçek projelerinde pilot kullanım**
warden'ı kendi Crypto MAS / Omni-Agent / AI Caddy repo'larına kur, birkaç gün gerçek kullanım yap.
✅ *Bittiğinde göreceğin:* Gerçek, kendi kod tabanından yakalanmış en az birkaç bulgu — bunlar tez/rapor için en güçlü kanıtın olacak.

**Adım 6.3 — README ve kurulum dokümantasyonu yaz**
Projeyi sıfırdan kuracak biri için adım adım kurulum talimatı yaz.
✅ *Bittiğinde göreceğin:* Belgeyi takip ederek projeyi temiz bir ortamda sıfırdan kurabiliyorsun.

**Adım 6.4 — Demo senaryosu prova et**
Sunum için: (1) açık bir SQL injection'ı yakalama, (2) hayali bir paketi engelleme, (3) Claude Code'un aracı kendiliğinden çağırması — üç senaryoyu birkaç kez prova et.
✅ *Bittiğinde göreceğin:* Sunumda hiç aksama olmadan üç senaryoyu art arda gösterebiliyorsun.

---

## Özet Sıralama

| Milestone | Odak | Yaklaşık Süre |
|---|---|---|
| 0 | Ortam + iskelet | 2-3 gün |
| 1 | Security Scanner | 5-6 gün |
| 2 | Paket Kontrolü | 4-5 gün |
| 3 | Git Hook (ilk uçtan uca demo!) | 3-4 gün |
| 4 | VS Code Eklentisi | 5-6 gün |
| 5 | MCP Sunucusu | 4-5 gün |
| 6 | Cilalama + Demo Provası | 5-6 gün |

Milestone 3'ün sonunda elinde zaten **çalışan, uçtan uca bir sistem** olacak (editörsüz, sadece Git hook ile) — bu senin için hem motive edici bir kilometre taşı hem de "en kötü ihtimalle bu bile yeterli bir bitirme projesi" güvencesi.
