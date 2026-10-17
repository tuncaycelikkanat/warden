"""Curated benchmark dataset for WARDEN static detectors.

Contains labeled positive (vulnerable/defective) and negative (clean/safe) code samples
for evaluating Precision, Recall, and F1-score across:
1. missing_timeout: HTTP requests missing explicit network timeout parameters.
2. bare_except: Catch-all except clauses without exception specification.
3. silent_swallow: Broad exception handlers that swallow errors without logging or re-raising.
4. secret_entropy: High-entropy credentials and API keys vs. safe identifiers and placeholders.
5. ai_slop: Conversational, didactic, and boilerplate AI-generated comments vs. genuine code comments.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BenchmarkSample:
    """A labeled source code snippet for detector benchmarking."""

    id: str
    category: str
    code: str
    is_positive: bool  # True if defect/vulnerability is present; False if clean.
    description: str


def load_benchmark_dataset() -> list[BenchmarkSample]:
    """Returns the complete set of ground-truth benchmark samples."""
    samples: list[BenchmarkSample] = []

    # -------------------------------------------------------------------------
    # 1. Missing Timeout Benchmark Samples
    # -------------------------------------------------------------------------
    samples.extend([
        BenchmarkSample(
            id="to_pos_01",
            category="missing_timeout",
            code="import requests\n\ndef fetch_data():\n    return requests.get('https://api.example.com/items').json()\n",
            is_positive=True,
            description="requests.get without timeout",
        ),
        BenchmarkSample(
            id="to_pos_02",
            category="missing_timeout",
            code="import httpx\n\ndef post_payload(payload):\n    return httpx.post('https://api.example.com/v1', json=payload)\n",
            is_positive=True,
            description="httpx.post without timeout",
        ),
        BenchmarkSample(
            id="to_pos_03",
            category="missing_timeout",
            code="import requests\n\ndef check_status():\n    return requests.head('https://health.example.com', timeout=None)\n",
            is_positive=True,
            description="requests.head with explicit timeout=None",
        ),
        BenchmarkSample(
            id="to_pos_04",
            category="missing_timeout",
            code="import requests\n\nsession = requests.Session()\ndef send(data):\n    return session.put('https://api.example.com', data=data)\n",
            is_positive=True,
            description="session.put without timeout parameter",
        ),
        BenchmarkSample(
            id="to_neg_01",
            category="missing_timeout",
            code="import requests\n\ndef fetch_data():\n    return requests.get('https://api.example.com/items', timeout=5.0).json()\n",
            is_positive=False,
            description="requests.get with explicit float timeout",
        ),
        BenchmarkSample(
            id="to_neg_02",
            category="missing_timeout",
            code="import httpx\n\ndef post_payload(payload):\n    return httpx.post('https://api.example.com/v1', json=payload, timeout=httpx.Timeout(10.0))\n",
            is_positive=False,
            description="httpx.post with httpx.Timeout object",
        ),
        BenchmarkSample(
            id="to_neg_03",
            category="missing_timeout",
            code="def compute_sum(a, b):\n    # Pure calculation without network IO\n    return a + b\n",
            is_positive=False,
            description="Non-HTTP code",
        ),
    ])

    # -------------------------------------------------------------------------
    # 2. Bare Except Benchmark Samples
    # -------------------------------------------------------------------------
    samples.extend([
        BenchmarkSample(
            id="bare_pos_01",
            category="bare_except",
            code="def run_step():\n    try:\n        do_something()\n    except:\n        print('failed')\n",
            is_positive=True,
            description="Classic bare except statement",
        ),
        BenchmarkSample(
            id="bare_pos_02",
            category="bare_except",
            code="def connect():\n    try:\n        socket.connect()\n    except:\n        pass\n",
            is_positive=True,
            description="Bare except with pass",
        ),
        BenchmarkSample(
            id="bare_neg_01",
            category="bare_except",
            code="def parse_int(s):\n    try:\n        return int(s)\n    except ValueError:\n        return None\n",
            is_positive=False,
            description="Specific ValueError handler",
        ),
        BenchmarkSample(
            id="bare_neg_02",
            category="bare_except",
            code="def fetch():\n    try:\n        req()\n    except (ConnectionError, TimeoutError) as exc:\n        logger.warning(exc)\n",
            is_positive=False,
            description="Tuple of specific network exceptions",
        ),
        BenchmarkSample(
            id="bare_neg_03",
            category="bare_except",
            code="def save():\n    try:\n        db.commit()\n    except Exception as exc:\n        logger.error('Commit failed', exc_info=True)\n        raise\n",
            is_positive=False,
            description="Typed Exception with re-raise",
        ),
    ])

    # -------------------------------------------------------------------------
    # 3. Silent Exception Swallow Benchmark Samples
    # -------------------------------------------------------------------------
    samples.extend([
        BenchmarkSample(
            id="swallow_pos_01",
            category="silent_swallow",
            code="def cleanup(path):\n    try:\n        os.remove(path)\n    except Exception:\n        pass\n",
            is_positive=True,
            description="except Exception: pass without logging",
        ),
        BenchmarkSample(
            id="swallow_pos_02",
            category="silent_swallow",
            code="def ping():\n    try:\n        check_liveness()\n    except BaseException:\n        ...\n",
            is_positive=True,
            description="except BaseException: ... (ellipsis no-op)",
        ),
        BenchmarkSample(
            id="swallow_pos_03",
            category="silent_swallow",
            code="def sync():\n    try:\n        sync_data()\n    except Exception:\n        \"\"\"ignored error\"\"\"\n",
            is_positive=True,
            description="except Exception with docstring only",
        ),
        BenchmarkSample(
            id="swallow_neg_01",
            category="silent_swallow",
            code="def cleanup(path):\n    try:\n        os.remove(path)\n    except FileNotFoundError:\n        pass  # Expected when file does not exist\n",
            is_positive=False,
            description="Expected specific FileNotFoundError swallowed intentionally",
        ),
        BenchmarkSample(
            id="swallow_neg_02",
            category="silent_swallow",
            code="def fetch_record():\n    try:\n        return query()\n    except Exception as exc:\n        logger.exception('Query failed')\n        return None\n",
            is_positive=False,
            description="except Exception with full structured logging",
        ),
        BenchmarkSample(
            id="swallow_neg_03",
            category="silent_swallow",
            code="def process():\n    try:\n        run()\n    except Exception as err:\n        metrics.increment('failures')\n        raise CustomError(str(err))\n",
            is_positive=False,
            description="except Exception that wraps and re-raises",
        ),
    ])

    # -------------------------------------------------------------------------
    # 4. Secret Entropy Benchmark Samples
    # -------------------------------------------------------------------------
    samples.extend([
        BenchmarkSample(
            id="secret_pos_01",
            category="secret_entropy",
            code="api_secret = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYz89472619A'\n",
            is_positive=True,
            description="High entropy 40-char AWS-style secret key",
        ),
        BenchmarkSample(
            id="secret_pos_02",
            category="secret_entropy",
            code="private_key_hex = 'a8f7c9e2b1d4068593a2e7c41b80f934df6a81c0'\n",
            is_positive=True,
            description="Hexadecimal private key assignment",
        ),
        BenchmarkSample(
            id="secret_pos_03",
            category="secret_entropy",
            code="webhook_token = '" + "xoxb" + "-987654321098-876543210987-aB3dE5fG7hI9jK1lM3nO5pQ'\n",
            is_positive=True,
            description="Slack-style bot token",
        ),
        BenchmarkSample(
            id="secret_neg_01",
            category="secret_entropy",
            code="api_key = 'YOUR_API_KEY_HERE'\n",
            is_positive=False,
            description="Placeholder text with low entropy and keyword placeholder",
        ),
        BenchmarkSample(
            id="secret_neg_02",
            category="secret_entropy",
            code="request_id = '123e4567-e89b-12d3-a456-426614174000'\n",
            is_positive=False,
            description="Standard non-sensitive UUID string",
        ),
        BenchmarkSample(
            id="secret_neg_03",
            category="secret_entropy",
            code="welcome_banner = 'Welcome to the WARDEN audit platform!'\n",
            is_positive=False,
            description="Natural language sentence",
        ),
        BenchmarkSample(
            id="secret_neg_04",
            category="secret_entropy",
            code="dummy_token = 'mock_sample_test_token_123456'\n",
            is_positive=False,
            description="Mock / sample token with explicit test markers",
        ),
    ])

    # -------------------------------------------------------------------------
    # 5. AI Slop Comment Benchmark Samples
    # -------------------------------------------------------------------------
    samples.extend([
        BenchmarkSample(
            id="slop_pos_01",
            category="ai_slop",
            code="# Import all necessary libraries and modules\nimport os\nimport sys\n",
            is_positive=True,
            description="Didactic import commentary",
        ),
        BenchmarkSample(
            id="slop_pos_02",
            category="ai_slop",
            code="# Step 1: Initialize the variables for calculation\nx = 10\ny = 20\n",
            is_positive=True,
            description="Procedural step-by-step tutorial commentary",
        ),
        BenchmarkSample(
            id="slop_pos_03",
            category="ai_slop",
            code="# In production, you should replace this with a secure API key\nKEY = 'demo'\n",
            is_positive=True,
            description="AI production boilerplate disclaimer",
        ),
        BenchmarkSample(
            id="slop_pos_04",
            category="ai_slop",
            code="# Here is the complete implementation as requested:\ndef process():\n    pass\n",
            is_positive=True,
            description="Conversational LLM response opening inside code",
        ),
        BenchmarkSample(
            id="slop_neg_01",
            category="ai_slop",
            code="# Workaround for upstream issue #412: flush buffer before socket shutdown\nstream.flush()\n",
            is_positive=False,
            description="Engineered rationale explaining non-obvious workaround",
        ),
        BenchmarkSample(
            id="slop_neg_02",
            category="ai_slop",
            code="# KaTeX math parsing requires double backslashes for literal dollar signs\nformula = r'\\$100'\n",
            is_positive=False,
            description="Technical constraint explanation",
        ),
        BenchmarkSample(
            id="slop_neg_03",
            category="ai_slop",
            code="# Invariant: array is pre-sorted in ascending order by timestamp\nassert items == sorted(items)\n",
            is_positive=False,
            description="Formal algorithmic invariant specification",
        ),
    ])

    return samples
