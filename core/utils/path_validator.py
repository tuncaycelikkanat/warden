"""Path validation utilities for WARDEN audit targets."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Denetlenmesi yasak sistem dizinleri
FORBIDDEN_PATH_PREFIXES = (
    "/etc",
    "/root",
    "/proc",
    "/sys",
    "/dev",
    "/run",
    "/boot",
    "/lib",
    "/lib64",
    "/sbin",
    "/bin",
    "/usr",
    "/var",
)


def validate_audit_path(raw_path: str) -> Path:
    """Resolves and validates the target path for a WARDEN audit.

    Raises ValueError for forbidden system paths, non-existent directories,
    and paths that exceed a reasonable depth.

    Returns:
        Resolved absolute Path object ready for audit.
    """
    raw_str = str(Path(raw_path))
    path = Path(raw_path).resolve()
    path_str = str(path)

    # 1. Yasak sistem dizinleri (ham yol veya çözümlenmiş yol üzerinden)
    for forbidden in FORBIDDEN_PATH_PREFIXES:
        if (
            path_str == forbidden
            or path_str.startswith(forbidden + "/")
            or raw_str == forbidden
            or raw_str.startswith(forbidden + "/")
        ):
            raise ValueError(
                f"Güvenlik: '{path}' denetim için yasaklı bir sistem dizinidir. "
                f"Lütfen kendi proje dizinlerinizi kullanın."
            )

    # 2. Dizin var mı?
    if not path.exists():
        raise ValueError(f"Audit hedef dizini bulunamadı: {path}")
    if not path.is_dir():
        raise ValueError(f"Audit hedefi bir dizin olmalıdır, dosya verildi: {path}")

    # 3. Git deposu kontrolü (uyarı, hata değil)
    if not (path / ".git").exists():
        logger.warning(
            f"Uyarı: '{path}' bir Git deposu değil. "
            "Gitleaks ve git churn analizleri atlanabilir."
        )

    return path
