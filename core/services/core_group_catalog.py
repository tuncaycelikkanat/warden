"""Core group and member catalog definitions for Layer 1 hierarchical scorecard."""

from dataclasses import dataclass, field

CATALOG_VERSION = "1.0.0"


@dataclass
class CoreMember:
    """Represents a member analyzer inside a Layer 1 group."""
    key: str
    label: str
    weight: float  # intra-group weight (sums to 1.0 per group)


@dataclass
class CoreGroup:
    """Represents a thematic group of analyzers inside Layer 1."""
    key: str
    label: str
    emoji: str
    weight: float  # group weight inside Layer 1
    members: list[CoreMember] = field(default_factory=list)

CORE_GROUPS = [
    CoreGroup(
        key='security_supply_chain',
        label='Güvenlik & Tedarik Zinciri',
        emoji='🛡️',
        weight=0.16 / 0.60,
        members=[
            CoreMember('security_semgrep',    'Semgrep SAST',              7/16),
            CoreMember('secret_leak_gitleaks','Gizli Anahtar Taraması',    4/16),
            CoreMember('dependency_osv',      'Bağımlılık CVE Taraması',   4/16),
            CoreMember('license_compliance',  'Lisans Uyumluluğu',         1/16),
        ]
    ),
    CoreGroup(
        key='code_health_test',
        label='Kod Sağlığı & Test Disiplini',
        emoji='🧪',
        weight=0.18 / 0.60,
        members=[
            CoreMember('test_coverage',    'Test Kapsamı',         7/18),
            CoreMember('test_quality',     'Test Kalitesi',        4/18),
            CoreMember('lint_style_ruff',  'Lint & Stil',          4/18),
            CoreMember('type_safety',      'Tip Güvenliği',        3/18),
        ]
    ),
    CoreGroup(
        key='structural_health',
        label='Yapısal Sağlık',
        emoji='🏗️',
        weight=0.10 / 0.60,
        members=[
            CoreMember('complexity_radon',  'Kod Karmaşıklığı',    4/10),
            CoreMember('duplication_jscpd', 'Kod Tekrarı',         3/10),
            CoreMember('tech_debt_churn',   'Teknik Borç',         3/10),
        ]
    ),
    CoreGroup(
        key='resilience_performance',
        label='Dayanıklılık & Performans',
        emoji='⚙️',
        weight=0.04 / 0.60,
        members=[
            CoreMember('resilience_ast', 'Dayanıklılık Kontrolü', 1.0),
        ]
    ),
    CoreGroup(
        key='dev_hygiene_devops',
        label='Geliştirici Hijyeni & DevOps',
        emoji='🔧',
        weight=0.07 / 0.60,
        members=[
            CoreMember('documentation',    'Dokümantasyon',       3/7),
            CoreMember('cicd_presence',    'CI/CD Varlığı',       2/7),
            CoreMember('docker_readiness', 'Docker Hazırlığı',    1/7),
            CoreMember('commit_hygiene',   'Commit Kalitesi',     1/7),
        ]
    ),
]

GROUP_BY_KEY = {g.key: g for g in CORE_GROUPS}
MEMBER_TO_GROUP = {m.key: g for g in CORE_GROUPS for m in g.members}
