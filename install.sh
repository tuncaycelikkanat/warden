#!/usr/bin/env bash
# WARDEN kurulum scripti — sistem bağımlılıkları dahil
set -euo pipefail

echo "🛡️  WARDEN kurulumu başlatılıyor..."
echo ""

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64)  ARCH="amd64" ;;
    aarch64) ARCH="arm64" ;;
    arm64)   ARCH="arm64" ;;
    *)       echo "Desteklenmeyen mimari: $ARCH" ; exit 1 ;;
esac

GITLEAKS_VERSION="8.21.2"
JSCPD_VERSION="3.5.10"

# ─────────────────────────────────────────────
# 1. Python bağımlılıkları (uv)
# ─────────────────────────────────────────────
echo "📦 Python bağımlılıkları kuruluyor (uv)..."
if ! command -v uv &>/dev/null; then
    echo "  → uv bulunamadı, kuruluyor..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi
uv sync
echo "  ✓ Python bağımlılıkları kuruldu"

# ─────────────────────────────────────────────
# 2. Gitleaks (secret tarama için zorunlu)
# ─────────────────────────────────────────────
echo ""
echo "🔍 Gitleaks kontrolü..."
if command -v gitleaks &>/dev/null; then
    CURRENT_VER="$(gitleaks version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo 'unknown')"
    echo "  ✓ Gitleaks zaten kurulu (v${CURRENT_VER})"
else
    echo "  → Gitleaks bulunamadı, kuruluyor v${GITLEAKS_VERSION}..."
    GITLEAKS_URL="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_${OS}_${ARCH}.tar.gz"
    TMPDIR="$(mktemp -d)"
    curl -sSfL "$GITLEAKS_URL" | tar -xz -C "$TMPDIR" gitleaks
    if [ -w /usr/local/bin ]; then
        mv "$TMPDIR/gitleaks" /usr/local/bin/gitleaks
    else
        echo "  → /usr/local/bin yazma izni yok, $HOME/.local/bin kullanılıyor..."
        mkdir -p "$HOME/.local/bin"
        mv "$TMPDIR/gitleaks" "$HOME/.local/bin/gitleaks"
        echo "  ⚠️  PATH'e \$HOME/.local/bin ekleyin: export PATH=\"\$HOME/.local/bin:\$PATH\""
    fi
    rm -rf "$TMPDIR"
    echo "  ✓ Gitleaks v${GITLEAKS_VERSION} kuruldu"
fi

# ─────────────────────────────────────────────
# 3. jscpd (kod tekrarı analizi için zorunlu)
# ─────────────────────────────────────────────
echo ""
echo "🔁 jscpd kontrolü..."
if command -v jscpd &>/dev/null; then
    echo "  ✓ jscpd zaten kurulu"
else
    if command -v npm &>/dev/null; then
        echo "  → jscpd kuruluyor (npm ile)..."
        npm install -g "jscpd@${JSCPD_VERSION}" --silent
        echo "  ✓ jscpd v${JSCPD_VERSION} kuruldu"
    else
        echo "  ⚠️  npm bulunamadı. jscpd (kod tekrarı tarayıcısı) kurulamadı."
        echo "     Node.js kurulumundan sonra: npm install -g jscpd"
        echo "     jscpd olmadan kod tekrarı analizi atlanacak."
    fi
fi

# ─────────────────────────────────────────────
# 4. Pre-commit hook (opsiyonel)
# ─────────────────────────────────────────────
echo ""
if [ -d ".git" ] && [ -f "git-hooks/pre-commit" ]; then
    echo "🔗 Pre-commit hook kuruluyor..."
    cp git-hooks/pre-commit .git/hooks/pre-commit
    chmod +x .git/hooks/pre-commit
    echo "  ✓ Her commit'te WARDEN otomatik çalışacak"
fi

# ─────────────────────────────────────────────
# 5. Ortam değişkeni hatırlatması
# ─────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ WARDEN kurulumu tamamlandı!"
echo ""
echo "📋 Kullanım:"
echo "   warden audit .                    # Mevcut repoyu denetle"
echo "   warden audit /path/to/repo        # Belirli bir repo"
echo "   warden milestone <id> --label v1  # Baseline işaretle"
echo "   warden serve                      # REST API sunucusu"
echo ""
if [ -z "${GEMINI_API_KEY:-}" ]; then
    echo "⚠️  Layer 2 (LLM rubric) için GEMINI_API_KEY ortam değişkeni gerekli:"
    echo "   export GEMINI_API_KEY='your-key-here'"
    echo "   Layer 2 olmadan sadece Layer 1 (mekanik) testler çalışır."
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
