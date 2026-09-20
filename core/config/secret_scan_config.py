"""Configuration constants for secret leak scanning and mock fixture detection."""

# High-confidence mock tokens: unlikely to appear by chance in a real secret.
HIGH_CONFIDENCE_MOCK_TOKENS = {
    "mock",
    "fake",
    "dummy",
    "placeholder",
    "example",
    "testkey",
}


# Low-confidence mock tokens: NOT sufficient on their own to ignore a finding.
# Must be accompanied by a high-confidence token or mock variable/context indicator.
LOW_CONFIDENCE_MOCK_TOKENS = {
    "test",
    "sample",
    "123456",
    "deadbeef",
    "xxxx",
    "000000",
}

# Universal placeholders: obvious template values anywhere in the codebase.
UNIVERSAL_PLACEHOLDERS = {
    "your_api_key_here",
    "your_api_key",
    "your-api-key",
    "change_me",
    "replace_me",
    "insert_key_here",
    "insert_here",
    "my_secret_key",
    "placeholder",
    "dummy_key",
    "dummy_secret",
    "dummy_token",
    "fake_secret",
    "fake_key",
    "sk_test_",
    "pk_test_",
    "sk-test-",
    "pk-test-",
}

# Live/production key prefixes that must NEVER be treated as false positives even in test files.
LIVE_KEY_PREFIXES = (
    "sk_live_",
    "pk_live_",
    "ak_live_",
    "AKIA",
    "-----BEGIN",
)

# Test directories and file patterns
TEST_DOC_DIRS = {
    "test",
    "tests",
    "testing",
    "fixtures",
    "fixture",
    "mocks",
    "mock",
    "__tests__",
    "spec",
    "specs",
    "sample",
    "samples",
    "example",
    "examples",
}

TEST_FILE_EXTENSIONS = (
    "_test.py",
    ".test.ts",
    ".test.js",
    ".spec.ts",
    ".spec.js",
    ".test.jsx",
    ".test.tsx",
    ".spec.jsx",
    ".spec.tsx",
)

TEST_FILE_NAMES = {
    "conftest.py",
    "mock.py",
    "fixture.py",
    "fixtures.py",
    "test.py",
    "tests.py",
}

DEFAULT_SINCE_MONTHS = 6
