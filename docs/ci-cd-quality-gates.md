# 🚦 CI/CD Kalite Kapıları (Quality Gates) ve Entegrasyon

WARDEN, CI/CD pipeline'larında bir **Kalite Kapısı (Quality Gate)** olarak çalışarak standartların altına düşen Pull Request'lerin veya commit'lerin ana dala (main/master) birleştirilmesini engeller.

---

## 🛑 Çıkış Kodları (Exit Codes)

Otomasyon araçlarının ve CI runner'ların WARDEN durumunu anlaması için aşağıdaki standart çıkış kodları kullanılır:

| Çıkış Kodu | Anlamı | CI Pipeline Davranışı |
| :---: | :--- | :--- |
| **`0`** | **Başarılı:** Kalite kapısı barajı aşıldı, kritik açık yok. | ✅ Pipeline Başarılı (Passed) |
| **`1`** | **Baraj Altı:** Toplam skor `--min-score` eşiğinin altında kaldı. | ❌ Pipeline Başarısız (Blocked) |
| **`2`** | **Kritik Güvenlik Açığı:** Puan yeterli olsa bile kritik CVE veya gizli anahtar sızıntısı bulundu (`--fail-on-critical`). | ❌ Pipeline Başarısız (Security Fail) |
| **`3`** | **Yürütme Hatası:** Geçersiz hedef dizin, eksik bağımlılık veya sistem hatası. | ⚠️ Pipeline Hatası (Error) |

---

## 🐙 1. GitHub Actions Entegrasyonu

Aşağıdaki iş akışı, her Pull Request açıldığında:
1. WARDEN denetimini yalnızca değişen dosyalar üzerinde (`--incremental`) koşturur.
2. PR özetini ve skor kartını otomatik olarak PR yorumu olarak ekler.
3. Skor 75'in altındaysa PR merge işlemini kilitler.

`.github/workflows/warden-pr.yml`:

```yaml
name: WARDEN Quality Gate

on:
  pull_request:
    branches: [ main, master ]

permissions:
  contents: read
  pull-requests: write

jobs:
  warden-audit:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout Code
        uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Git geçmişi ve diff analizi için zorunlu

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv & Dependencies
        run: |
          curl -LsSf https://astral.sh/uv/install.sh | sh
          uv venv
          uv pip install -r requirements.txt

      - name: Install System Scanners (Gitleaks & jscpd)
        run: |
          sudo apt-get update && sudo apt-get install -y npm
          sudo npm install -g jscpd
          # Gitleaks kurulumu
          wget https://github.com/gitleaks/gitleaks/releases/download/v8.21.0/gitleaks_8.21.0_linux_x64.tar.gz
          tar -xzf gitleaks_8.21.0_linux_x64.tar.gz
          sudo mv gitleaks /usr/local/bin/

      - name: Run WARDEN Audit
        id: warden
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          source .venv/bin/activate
          # Kalite kapısı: minimum skor 75, kritik açıkta direkt fail
          python core/main.py audit \
            --path . \
            --incremental \
            --since-commit origin/${{ github.base_ref }} \
            --min-score 75 \
            --fail-on-critical

      - name: Comment PR with WARDEN Report
        if: always() && steps.warden.outcome != 'skipped'
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const reportPath = 'WARDEN_EXECUTIVE_REPORT.md';
            if (fs.existsSync(reportPath)) {
              const reportContent = fs.readFileSync(reportPath, 'utf8');
              github.rest.issues.createComment({
                issue_number: context.issue.number,
                owner: context.repo.owner,
                repo: context.repo.repo,
                body: `## 🛡️ WARDEN Kalite Güvence Raporu\n\n` + reportContent
              });
            }
```

---

## 🦊 2. GitLab CI / CD Entegrasyonu

`.gitlab-ci.yml`:

```yaml
stages:
  - test
  - quality-gate

warden_governance:
  stage: quality-gate
  image: python:3.12-slim
  variables:
    GIT_DEPTH: "0"
  before_script:
    - apt-get update && apt-get install -y git curl npm
    - npm install -g jscpd
    - pip install uv && uv pip install --system -r requirements.txt
  script:
    - python core/main.py audit --path . --min-score 80 --fail-on-critical
  artifacts:
    when: always
    paths:
      - WARDEN_EXECUTIVE_REPORT.md
      - warden_reports/
    expire_in: 30 days
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
```

---

## 🪝 3. Git Pre-Commit Kancası (Local Hook)

Geliştiricilerin bozuk veya düşük puanlı kodu repoya göndermesini yerel ortamda engellemek için:

`.git/hooks/pre-commit`:

```bash
#!/usr/bin/env bash
set -e

echo "🔍 WARDEN yerel artımlı denetimi çalıştırıyor..."

# Yalnızca stage edilmiş değişiklikleri hızlıca denetle
uv run python core/main.py audit --path . --incremental --min-score 70

if [ $? -ne 0 ]; then
    echo "❌ WARDEN: Kod kalite barajının altında kaldı! Commit iptal edildi."
    exit 1
fi

echo "✅ WARDEN kalite kapısı geçildi."
```

Dosyayı çalıştırılabilir yapın:
```bash
chmod +x .git/hooks/pre-commit
```
