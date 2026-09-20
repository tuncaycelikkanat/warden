from pathlib import Path

import pytest

from core.services.test_quality import TestQualityResult, TestQualityService


@pytest.mark.asyncio
async def test_indirect_helper_validation(tmp_path: Path):
    """Tests delegating verification to local helper functions containing asserts are NOT marked fake."""
    test_file = tmp_path / "test_api.py"
    test_file.write_text(
        "def assert_valid_response(resp):\n"
        "    assert resp['status'] == 200\n"
        "    assert 'id' in resp\n"
        "\n"
        "def test_create_user():\n"
        "    resp = {'status': 200, 'id': 123}\n"
        "    assert_valid_response(resp)\n"
    )

    service = TestQualityService()
    res: TestQualityResult = await service.analyze(tmp_path)

    assert res.total_tests == 1
    assert res.fake_tests == 0
    assert res.score == 100.0
    assert len(res.fake_test_locations) == 0


@pytest.mark.asyncio
async def test_async_test_functions(tmp_path: Path):
    """Async test functions (ast.AsyncFunctionDef) must be properly discovered and analyzed."""
    test_file = tmp_path / "test_async.py"
    test_file.write_text(
        "import pytest\n"
        "\n"
        "@pytest.mark.asyncio\n"
        "async def test_fetch_data():\n"
        "    data = {'result': 'ok'}\n"
        "    assert data['result'] == 'ok'\n"
        "\n"
        "async def test_async_fake():\n"
        "    pass\n"
    )

    service = TestQualityService()
    res: TestQualityResult = await service.analyze(tmp_path)

    assert res.total_tests == 2
    assert res.fake_tests == 1
    assert res.fake_test_locations[0].function_name == "test_async_fake"


@pytest.mark.asyncio
async def test_trivial_assertions_flagged_as_fake(tmp_path: Path):
    """Trivial constant assertions (assert True, assert 1) must not count as genuine validation."""
    test_file = tmp_path / "test_trivial.py"
    test_file.write_text(
        "def test_fake_bool():\n"
        "    assert True\n"
        "\n"
        "def test_fake_int():\n"
        "    assert 1\n"
        "\n"
        "def test_legit():\n"
        "    x = 10\n"
        "    assert x == 10\n"
    )

    service = TestQualityService()
    res: TestQualityResult = await service.analyze(tmp_path)

    assert res.total_tests == 3
    assert res.fake_tests == 2
    assert {loc.function_name for loc in res.fake_test_locations} == {"test_fake_bool", "test_fake_int"}


@pytest.mark.asyncio
async def test_pytest_raises_and_warns(tmp_path: Path):
    """Both pytest.raises and bare raises as well as warns context managers count as assertions."""
    test_file = tmp_path / "test_exceptions.py"
    test_file.write_text(
        "import pytest\n"
        "from pytest import raises\n"
        "\n"
        "def test_attr_raises():\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError('bad')\n"
        "\n"
        "def test_bare_raises():\n"
        "    with raises(KeyError):\n"
        "        raise KeyError('missing')\n"
        "\n"
        "def test_warns():\n"
        "    with pytest.warns(UserWarning):\n"
        "        pass\n"
    )

    service = TestQualityService()
    res: TestQualityResult = await service.analyze(tmp_path)

    assert res.total_tests == 3
    assert res.fake_tests == 0
    assert res.score == 100.0


@pytest.mark.asyncio
async def test_assertion_library_calls(tmp_path: Path):
    """Test assertion library methods like pytest.fail, mock asserts, and self.assert*."""
    test_file = tmp_path / "test_calls.py"
    test_file.write_text(
        "import pytest\n"
        "from unittest.mock import MagicMock\n"
        "\n"
        "def test_pytest_fail():\n"
        "    if False:\n"
        "        pytest.fail('unreachable')\n"
        "\n"
        "def test_mock_assert():\n"
        "    m = MagicMock()\n"
        "    m.assert_called_once()\n"
    )

    service = TestQualityService()
    res: TestQualityResult = await service.analyze(tmp_path)

    assert res.total_tests == 2
    assert res.fake_tests == 0
    assert res.score == 100.0


@pytest.mark.asyncio
async def test_score_clamping_to_zero(tmp_path: Path):
    """When fake test ratio exceeds 50%, score must clamp to 0.0 and never become negative."""
    test_file = tmp_path / "test_mostly_fake.py"
    code_lines = ["def test_real(): assert 1 == 1"]
    for i in range(9):
        code_lines.append(f"def test_fake_{i}(): pass")
    test_file.write_text("\n".join(code_lines))

    service = TestQualityService()
    res: TestQualityResult = await service.analyze(tmp_path)

    assert res.total_tests == 10
    assert res.fake_tests == 9
    assert res.score == 0.0
    assert res.fake_test_ratio == 0.9


@pytest.mark.asyncio
async def test_fake_test_location_details(tmp_path: Path):
    """Location metadata (file, function name, line) must be accurate."""
    test_file = tmp_path / "test_sample.py"
    test_file.write_text(
        "# line 1\n"
        "# line 2\n"
        "def test_empty_candidate():\n"
        "    x = 1\n"
    )

    service = TestQualityService()
    res: TestQualityResult = await service.analyze(tmp_path)

    assert len(res.fake_test_locations) == 1
    loc = res.fake_test_locations[0]
    assert loc.function_name == "test_empty_candidate"
    assert loc.line_number == 3
    assert "test_sample.py" in loc.file_path


@pytest.mark.asyncio
async def test_test_quality_self_scan():
    """Runs analyzer on WARDEN itself without error."""
    service = TestQualityService()
    res = await service.analyze(Path("."))

    assert 0.0 <= res.score <= 100.0
    assert res.total_tests > 0
    assert res.avg_assertion_density >= 0.0
