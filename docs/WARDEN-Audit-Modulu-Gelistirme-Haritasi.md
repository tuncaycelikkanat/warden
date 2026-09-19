# WARDEN Denetim ve Karne Modülü — Geliştirme Haritası

Bu belge, `WARDEN-Audit-Modulu-Mimari.md`'de tanımlanan Denetim ve Karne modülünü, ana geliştirme haritasındaki (`WARDEN-Gelistirme-Haritasi.md`) **Milestone 8** olarak, aynı küçük-adım formatında ele alır. Ön koşul: Milestone 1 (Security Scanner), Milestone 2 (Paket Kontrolü) ve mimari rapordaki TechDebtTracker'ın (Faz 3) en azından iskelet halinde tamamlanmış olması — bu modül onların üzerine inşa edilir, onları tekrar yazmaz.

**Not:** On kategoriyi eklemek, tek seferde kod yazmak anlamına gelmiyor — her kategori kendi küçük grubu, her grup kendi küçük adımları. Bir grubu bitirip çalışır görmeden diğerine geçme; bu şekilde 30'a yakın adım olsa da hiçbiri tek başına zor değil.

---

## Milestone 8 — WARDEN Denetim ve Karne Modülü

### Grup A: Full-Repo Tarama Altyapısı

**Adım 8.1 — Dosya keşif fonksiyonunu yaz**
Bir repo yolunu alıp, `.py`/`.js`/`.ts` uzantılı, `node_modules`/`.venv` gibi klasörleri hariç tutan bir dosya listesi döndüren basit bir fonksiyon yaz.
✅ *Bittiğinde göreceğin:* Kendi Crypto MAS repo'nda çalıştırdığında, gerçek kaynak dosyalarının tam listesini (gereksiz klasörler hariç) alıyorsun.

**Adım 8.2 — SecurityScanner'ı çoklu dosya üzerinde çalıştır**
Milestone 1'de yazdığın `SecurityScannerService`i, tek dosya yerine bir dosya listesi alacak şekilde küçük bir metotla genişlet (`scan_files`), `asyncio.gather` ile paralel çalıştır.
✅ *Bittiğinde göreceğin:* 20-30 dosyalık bir klasörde tarama birkaç saniyede bitiyor, her dosya için ayrı ayrı değil, tek bir toplu sonuç JSON'u dönüyor.

**Adım 8.3 — Birim testini yaz**
Bilinçli olarak 2-3 dosyada güvenlik açığı bırakılmış küçük bir test klasörü oluştur, `scan_files`in doğru sayıda bulgu döndürdüğünü doğrula.
✅ *Bittiğinde göreceğin:* `pytest` testi geçiyor, beklenen bulgu sayısı ile gerçek sayı eşleşiyor.

---

### Grup B: Bağımlılık Sağlığı (OSV.dev Entegrasyonu)

**Adım 8.4 — Manifest dosyasını parse et**
`requirements.txt` dosyasını okuyup paket adı + versiyon çiftlerine ayıran basit bir fonksiyon yaz (önce yalnızca `requirements.txt`, `pyproject.toml` sonraya bırakılabilir).
✅ *Bittiğinde göreceğin:* Kendi bir projendeki `requirements.txt`'i verdiğinde, doğru paket/versiyon listesi çıkıyor.

**Adım 8.5 — OSV.dev API'sini manuel dene**
Terminalde/Postman'de `https://api.osv.dev/v1/query` adresine bilinen zafiyetli bir paket (ör. eski bir `django` sürümü) için manuel bir POST isteği at.
✅ *Bittiğinde göreceğin:* Dönen JSON'da gerçek bir CVE kaydı görüyorsun — API'nin veri yapısına aşina oluyorsun.

**Adım 8.6 — httpx ile async OSV sorgu fonksiyonunu yaz**
Bir paket adı + versiyon alıp OSV.dev'e sorgu atan, dönen zafiyet listesini basit bir veri yapısına çeviren fonksiyonu yaz.
✅ *Bittiğinde göreceğin:* `pytest` testinde, bilinen zafiyetli bir paket için en az 1 zafiyet kaydı dönüyor; güncel bir paket için boş liste dönüyor.

**Adım 8.7 — Milestone 2'deki PackageIntegrityChecker ile birleştir**
`DependencyHealthService`i yaz: manifest'teki her paket için hem eski servisi (yaş/isim benzerliği) hem yeni OSV sorgusunu çağırıp tek bir sonuçta birleştir.
✅ *Bittiğinde göreceğin:* Bir `requirements.txt` verdiğinde, her paket için "güvenilirlik" ve "bilinen zafiyet" bilgisini yan yana gösteren bir liste alıyorsun.

**Adım 8.8 — Hata toleransını ekle**
OSV.dev erişilemezse (ağ hatası), o paket için "kontrol edilemedi" durumu dönsün, tüm işlem çökmesin.
✅ *Bittiğinde göreceğin:* İnternet bağlantını geçici kapatıp test ettiğinde, sistem çökmeden "kontrol edilemedi" uyarısıyla devam ediyor.

---

### Grup C: Kod Karmaşıklığı & Stil (radon + ruff)

**Adım 8.9 — `radon` ve `ruff`'ı manuel dene**
Terminalde `radon cc . -a` ve `ruff check .` komutlarını kendi bir projende çalıştır, çıktı formatlarına bak.
✅ *Bittiğinde göreceğin:* İki aracın da JSON çıktı modunu (`radon cc . --json`, `ruff check . --output-format=json`) nasıl vereceğini biliyorsun.

**Adım 8.10 — CodeComplexityService ve LintStyleService'i yaz**
İki ayrı, küçük servis sınıfı yaz — her biri tek bir aracı `subprocess` ile çağırıp JSON çıktısını parse ediyor (bkz. mimari dokümanın 4.3 bölümü).
✅ *Bittiğinde göreceğin:* Bir repo için "ortalama karmaşıklık: 6.3" ve "lint hatası: 12" olarak iki ayrı, bağımsız sonuç alıyorsun.

---

### Grup D: Gizli Bilgi Sızıntısı (gitleaks)

**Adım 8.11 — `gitleaks`'i manuel dene**
Kasıtlı olarak bir commit'e sahte bir API anahtarı ekleyip bir sonraki commit'te silen küçük bir test reposu oluştur; `gitleaks detect --source .` komutunu çalıştır.
✅ *Bittiğinde göreceğin:* Anahtar kod tabanında artık görünmese bile, gitleaks'in onu Git geçmişinde bulduğunu görüyorsun — bu, bu servisin neden gerekli olduğunu somut olarak kanıtlıyor.

**Adım 8.12 — SecretLeakScannerService'i yaz**
`gitleaks`'i JSON çıktı modunda (`--report-format json`) çağırıp sonucu parse eden servisi yaz.
✅ *Bittiğinde göreceğin:* Test reposu için "1 sızıntı bulundu", temiz bir repo için "0 sızıntı" dönüyor.

---

### Grup E: Test Kapsamı (coverage.py)

**Adım 8.13 — `coverage.py`'ı manuel dene**
Kendi bir projende (test dosyaları olan) `coverage run -m pytest && coverage json` komutlarını çalıştır, çıkan `coverage.json` dosyasının yapısına bak.
✅ *Bittiğinde göreceğin:* Toplam kapsam yüzdesinin JSON'da hangi alanda olduğunu biliyorsun.

**Adım 8.14 — TestCoverageAnalyzerService'i yaz**
Bu komutları çalıştırıp sonucu parse eden servisi yaz; **coverage yapılandırması hiç yoksa çökmeden `measured=False` dönmesine özellikle dikkat et** (bkz. mimari dokümanın 4.5 bölümündeki adalet notu).
✅ *Bittiğinde göreceğin:* Testi olan bir projede gerçek bir yüzde, testi hiç olmayan bir projede ise hata almadan "ölçülemedi" sonucu alıyorsun.

---

### Grup F: Dokümantasyon (interrogate + README kontrolü)

**Adım 8.15 — `interrogate`'i manuel dene**
`interrogate -v .` komutunu kendi bir projende çalıştır, docstring kapsama yüzdesinin nasıl raporlandığına bak.
✅ *Bittiğinde göreceğin:* Hangi fonksiyonların docstring'i eksik, hangilerinin tam olduğunu gösteren bir çıktı görüyorsun.

**Adım 8.16 — README kontrol fonksiyonunu yaz**
`README.md` dosyasını okuyup basitçe "Kurulum"/"Installation" ve "Kullanım"/"Usage" gibi başlıkların var olup olmadığını kontrol eden küçük bir fonksiyon yaz (regex veya basit string arama yeterli, karmaşık bir parser gerekmez).
✅ *Bittiğinde göreceğin:* Kendi projenin README'sinde bu bölümlerin olup olmadığını doğru tespit ediyor.

**Adım 8.17 — DocumentationAnalyzerService'i birleştir**
İki kontrolü tek bir serviste topla.
✅ *Bittiğinde göreceğin:* Tek bir çağrıyla hem docstring yüzdesini hem README kontrolünü alıyorsun.

---

### Grup G: Hata Yönetimi & Dayanıklılık (Kendi AST Kuralın)

**Adım 8.18 — Python `ast` modülünü küçük bir örnekle dene**
Basit bir Python dosyasını `ast.parse` ile ayrıştır, `ast.dump()` çıktısına bakarak bir `try/except` bloğunun ağaçta nasıl göründüğünü incele.
✅ *Bittiğinde göreceğin:* Bir `except:` (bare except) bloğunu koddan "elle" tanıyabiliyorsun — bir sonraki adımda bunu otomatikleştireceksin.

**Adım 8.19 — Boş except tespiti yaz**
AST üzerinde gezinip (`ast.walk`), tip belirtilmemiş (`except:`) veya yalnızca `pass` içeren except bloklarını bulan bir fonksiyon yaz.
✅ *Bittiğinde göreceğin:* Kasıtlı olarak `except: pass` içeren bir test dosyasında bu paterni doğru yakalıyor, normal bir `except ValueError:` bloğunu yanlışlıkla işaretlemiyor.

**Adım 8.20 — Eksik timeout tespiti yaz**
AST üzerinde `requests.get(...)`/`httpx.get(...)` gibi çağrıları bulup, `timeout=` argümanı olmayanları işaretleyen bir fonksiyon yaz.
✅ *Bittiğinde göreceğin:* `timeout` parametresi eksik bir çağrıyı doğru yakalıyor, `timeout=5` içeren bir çağrıyı işaretlemiyor.

**Adım 8.21 — ResilienceAnalyzerService'i birleştir**
İki kontrolü tek bir serviste topla, sonucu "deneysel" etiketiyle işaretle (bkz. mimari dokümanın 4.7 bölümündeki dürüst sınır notu).
✅ *Bittiğinde göreceğin:* Tek bir çağrıyla iki paterni de tarayan, bulguları listeleyen bir sonuç alıyorsun.

---

### Grup H: Proje Profilleyici (Dinamik Kategori Seçimi)

**Adım 8.22 — Sinyal sınıflarını yaz**
Dört basit sinyal tipini yaz: `DependencySignal` (manifest'te paket var mı), `FilePatternSignal` (glob eşleşmesi + minimum sayı), `DirectorySignal` (dizin var mı), `SourcePatternSignal` (kaynak kodda metin geçiyor mu).
✅ *Bittiğinde göreceğin:* Her sinyal tipi için bir pytest testi geçiyor — ör. `DependencySignal(["react"])` bir React projesinde `True`, bir Python projesinde `False` dönüyor.

**Adım 8.23 — Kategori kataloğunu yaz**
Mimari dokümanın 4.8 bölümündeki `CATEGORY_CATALOG` sözlüğünü oluştur (7 kategori ile başla), bir `CATALOG_VERSION` sabiti ekle.
✅ *Bittiğinde göreceğin:* Katalog bir Python sözlüğü olarak hazır; henüz çalışmıyor ama yapı net.

**Adım 8.24 — ProjectProfilerService'i yaz**
Katalogdaki her kategorinin sinyallerini kontrol edip eşleşenleri döndüren, kanıt sayısına göre sıralayıp ilk 5'i seçen servisi yaz.
✅ *Bittiğinde göreceğin:* Kendi Crypto MAS repo'nda çalıştırdığında "Kantitatif Mantık, LLM Entegrasyonu, Mimari Disiplin, DevOps" gibi beklediğin kategoriler açılıyor; basit bir CLI aracında hiçbiri açılmıyor.

**Adım 8.25 — Profil imzasını hesapla**
Seçilen kategori anahtarları + ağırlıkları üzerinden kısa bir hash (`profile_signature`) üret.
✅ *Bittiğinde göreceğin:* Aynı repo'da iki kez çalıştırınca aynı imza, repo'ya yeni bir bağımlılık ekleyince farklı imza çıkıyor.

---

### Grup I: Çapalı Rubrik Değerlendirmesi

**Adım 8.26 — Rubrik tanımlarını yaz**
Katalogdaki her kategori için 3/6/9 seviyelerinin ne anlama geldiğini somut cümlelerle tanımla (bkz. mimari dokümanın 4.9 bölümü). Bu adım kod değil, **metin yazma** işi — ama sistemin en kritik parçası, aceleye getirme.
✅ *Bittiğinde göreceğin:* Her kategori için üç seviyeyi okuduğunda, kendi projelerinden birini elle hangi seviyeye koyacağını net biliyorsun. Bilemiyorsan çapalar yeterince somut değil demektir.

**Adım 8.27 — Kanıt toplayıcıyı yaz**
Bir kategori için LLM'e gönderilecek kanıt paketini derleyen fonksiyonu yaz: ilgili dosya yolları, Katman 1'den gelen ilgili metrikler, dizin yapısı özeti. **Ham kod satırı koyma** (gizlilik kısıtı).
✅ *Bittiğinde göreceğin:* Bir kategori için üretilen kanıt paketini yazdırdığında, içinde hiç kod satırı olmadığını ama değerlendirme için yeterli bilgi olduğunu görüyorsun.

**Adım 8.28 — RubricEvaluatorService'i yaz**
Rubrik + kanıtı prompt'a çevirip LLM'den JSON (`level`, `justification`, `cited_evidence`) alan, geçersiz seviye gelirse hata fırlatan servisi yaz.
✅ *Bittiğinde göreceğin:* Bir kategori için LLM'den geçerli bir seviye ve gerekçe dönüyor; gerekçede somut dosya/metrik adı geçiyor.

**Adım 8.29 — Determinizm kontrolü yap**
Aynı kanıtla servisi 5 kez çalıştır, seçilen seviyelerin dağılımına bak.
✅ *Bittiğinde göreceğin:* Seviyeler ±1 bandında kalıyor. Daha fazla oynuyorsa, Adım 8.26'ya dönüp rubriği daha somut çapalarla yeniden yaz — bu bir başarısızlık değil, beklenen bir iterasyon.

---

### Grup J: Puanlama ve Birleştirme

**Adım 8.30 — Tek bir çekirdek kategori için puanlama fonksiyonunu yaz**
Önce yalnızca güvenlik kategorisi için: bulgu sayısına göre 100'den puan düşen basit fonksiyonu yaz (bkz. mimari dokümanın 5.4 bölümü).
✅ *Bittiğinde göreceğin:* Temiz bir klasör için 100, bilerek kirletilmiş bir klasör için düşük bir puan (ör. 55) alıyorsun.

**Adım 8.31 — Kalan dokuz çekirdek kategorinin puanlama fonksiyonlarını ekle**
Her kategori için (5.2'deki tablo sırasıyla) benzer, kategoriye özel puanlama mantıklarını yaz — hepsini aynı anda değil, birer birer, her birini kendi biriminde test ederek.
✅ *Bittiğinde göreceğin:* On çekirdek kategorinin de bağımsız 0-100 puanlar ürettiğini, her biri için ayrı bir pytest testiyle doğruluyorsun.

**Adım 8.32 — "Ölçülemedi" durumunu ve ağırlık normalizasyonunu ekle**
Bir kategori "ölçülemedi" döndüğünde (ör. coverage yapılandırması yok), o kategorinin ağırlığının genel puana dahil edilmeyip kalanlar arasında orantılı dağıtılmasını sağla.
✅ *Bittiğinde göreceğin:* Testi olmayan bir projede genel puan haksız yere çok düşük çıkmıyor, elle hesapladığın normalize değerle eşleşiyor.

**Adım 8.33 — İki katmanı birleştir**
`ScorecardAggregator`ı yaz: Katman 1 %60 sabit ağırlıklarla, Katman 2 %40'ın seçilen kategori sayısına bölünmesiyle; rubrik seviyesi ×10 ile 0-100'e ölçeklenir.
✅ *Bittiğinde göreceğin:* 4 dinamik kategorili bir projede her birinin %10 ağırlık aldığını, hiç dinamik kategori olmayan bir projede %40'ın çekirdeğe devredildiğini elle doğruluyorsun.

**Adım 8.34 — Kalibrasyon testini yap (kritik adım)**
Bilinçli olarak üç referans repo hazırla: zayıf (test yok, açıklar var, dokümantasyon yok), orta, iyi (kendi Crypto MAS'ın olabilir). Üçünde de denetim çalıştır.
✅ *Bittiğinde göreceğin:* Üç puan gerçekten ayrışıyor (ör. 45 / 68 / 85). **Üçü de 8+ alıyorsa sistem bozuk demektir** — rubriği ve ceza katsayılarını yeniden kalibre et. Bu adım, "sisteminiz hiç düşük puan verir mi?" sorusuna cevabın olacak.

**Adım 8.35 — AuditOrchestratorService ile hepsini birleştir**
Profiler → Katman 1 (paralel) → Katman 2 (paralel) → Aggregator zincirini kuran orkestratörü yaz (bkz. mimari doküman 4.1).
✅ *Bittiğinde göreceğin:* Tek bir `run_full_audit(repo_path)` çağrısıyla, profil + iki katmanın puanları + genel puan birlikte dönüyor.

---

### Grup K: Rapor Üretimi ve Kalıcılık

**Adım 8.36 — Veritabanı tablolarını oluştur**
Mimari dokümandaki (Bölüm 6) iki tabloyu (`audit_reports` + `audit_dynamic_categories`) SQLModel ile tanımla.
✅ *Bittiğinde göreceğin:* Bir denetim çalıştırdığında ana tabloda bir satır, dinamik tabloda seçilen kategori sayısı kadar satır oluşuyor.

**Adım 8.37 — Markdown rapor şablonunu yaz**
Mimari dokümandaki 8 bölümlü iskeleti (Bölüm 9) Jinja2 ile üret: başlık, iki katmanlı tablo (Kaynak sütunu dahil), proje profili, bulgular, güçlü yönler, eksikler, aksiyonlar.
✅ *Bittiğinde göreceğin:* Diske gerçek, okunabilir bir `report.md` yazılıyor — iki ayrı tablo, ⚙️/🧠 etiketleri ve "bu kategori neden açıldı" bölümü doğru görünüyor.

**Adım 8.38 — Trend sorgusunu imzaya göre filtrele**
Geçmiş denetimleri listeleyen sorguyu, yalnızca aynı `profile_signature`'a sahip kayıtları getirecek şekilde yaz.
✅ *Bittiğinde göreceğin:* İki farklı imzayla yapılmış denetimler trend grafiğinde birbirine karışmıyor.

**Adım 8.39 — (İsteğe bağlı) LLM Executive Summary'yi ekle**
Yalnızca bulgu metadatasını LLM'e gönderip bir özet paragraf üret, `--with-summary` bayrağıyla devreye gir.
✅ *Bittiğinde göreceğin:* Bayrak verildiğinde raporun sonunda bir "Yönetici Özeti" bölümü beliriyor; verilmediğinde hiç yok.

---

### Grup L: Tetikleme Noktaları

**Adım 8.40 — CLI komutunu ekle**
`click` ile `warden audit --repo <path> --output <file>` komutunu yaz.
✅ *Bittiğinde göreceğin:* Terminalden tek komutla tam bir denetim çalıştırıp rapor dosyası alabiliyorsun.

**Adım 8.41 — VS Code komutunu ekle**
"WARDEN: Generate Project Scorecard" komutunu, ilerleme çubuğuyla (`vscode.window.withProgress`) birlikte ekle.
✅ *Bittiğinde göreceğin:* Command Palette'ten komutu çalıştırdığında ilerleme çubuğu görünüyor, bitince rapor bir webview'de açılıyor.

**Adım 8.42 — `run_full_audit` MCP aracını ekle**
Milestone 5'te kurduğun MCP sunucusuna bu yeni aracı ekle.
✅ *Bittiğinde göreceğin:* MCP Inspector'dan bu aracı çağırdığında, iki katmanın puanlarıyla birlikte tam bir denetim raporu JSON olarak dönüyor.

**Adım 8.43 — Claude Code ile uçtan uca dene**
Claude Code'a "bu projede release öncesi tam bir denetim yap" gibi bir görev ver, ajanın `run_full_audit` aracını kendiliğinden çağırıp çağırmadığını gözlemle.
✅ *Bittiğinde göreceğin:* Ajan, senin doğrudan komut vermeden, görev bağlamından yola çıkarak bu aracı çağırıyor — **bu, tüm projenin "kapanış demosu" olarak sunulabilecek en güçlü an.**

---

## Özet Sıralama

| Grup | Odak | Yaklaşık Süre |
|---|---|---|
| A | Full-repo tarama altyapısı | 2 gün |
| B | Bağımlılık sağlığı (OSV.dev) | 3 gün |
| C | Kod karmaşıklığı & stil | 1-2 gün |
| D | Gizli bilgi sızıntısı (gitleaks) | 1-2 gün |
| E | Test kapsamı (coverage.py) | 1-2 gün |
| F | Dokümantasyon (interrogate + README) | 1-2 gün |
| G | Hata yönetimi & dayanıklılık (kendi AST kuralın) | 2-3 gün |
| H | Proje profilleyici (dinamik kategori seçimi) | 2-3 gün |
| I | Çapalı rubrik değerlendirmesi | 3-4 gün |
| J | Puanlama, birleştirme ve kalibrasyon | 3-4 gün |
| K | Rapor üretimi ve kalıcılık | 2-3 gün |
| L | Tetikleme noktaları (CLI/VS Code/MCP) | 2-3 gün |

**Toplam:** ~24-32 gün. Bu modül tamamen isteğe bağlıdır (bkz. ana geliştirme haritasındaki Milestone 6 notu).

**Zaman darsa daraltma sırası:** Önce Grup G (en deneysel servis), sonra D/E/F'den ikisi çıkarılabilir. **Grup H, I ve J'yi çıkarma** — dinamik kategori seçimi ve çapalı rubrik, bu modülün asıl özgün katkısıdır; onlar olmadan geriye yalnızca "hazır araçları çalıştırıp toplayan bir script" kalır. Minimum savunulabilir kapsam: A + B + C + H + I + J + L.
