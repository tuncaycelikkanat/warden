#!/bin/bash
echo "WARDEN kurulumu başlatılıyor..."

if [ ! -d ".git" ]; then
    echo "Hata: Bu klasör bir Git deposu değil. Lütfen proje dizininde çalıştırın."
    exit 1
fi

echo "Pre-commit hook kopyalanıyor..."
cp git-hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

echo "✅ Kurulum tamamlandı! Artık her commit'te WARDEN kodunuzu denetleyecek."
