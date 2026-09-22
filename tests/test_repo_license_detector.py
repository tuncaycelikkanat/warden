"""Unit tests for RepoLicenseDetector."""

from pathlib import Path
from core.services.repo_license_detector import RepoLicenseDetector, LICENSE_CATEGORY_MAP


def test_match_text_to_spdx():
    detector = RepoLicenseDetector()

    assert detector._match_text_to_spdx("This program is free software: Affero General Public License") == "AGPL-3.0-only"
    assert detector._match_text_to_spdx("GNU Lesser General Public License version 3") == "LGPL-3.0-only"
    assert detector._match_text_to_spdx("GNU Lesser General Public License") == "LGPL-2.1-only"
    assert detector._match_text_to_spdx("GNU General Public License version 3") == "GPL-3.0-only"
    assert detector._match_text_to_spdx("GNU General Public License version 2") == "GPL-2.0-only"
    assert detector._match_text_to_spdx("Apache License Version 2.0") == "Apache-2.0"
    assert detector._match_text_to_spdx("MIT License Permission is hereby granted, free of charge") == "MIT"
    assert detector._match_text_to_spdx("Mozilla Public License 2.0") == "MPL-2.0"
    assert detector._match_text_to_spdx("Redistribution and use in source and binary forms neither the name of clause") == "BSD-3-Clause"
    assert detector._match_text_to_spdx("Redistribution and use in source and binary forms") == "BSD-2-Clause"
    assert detector._match_text_to_spdx("Permission to use, copy, modify, and/or distribute this software") == "ISC"
    assert detector._match_text_to_spdx("This is free and unencumbered software released into the public domain") == "Unlicense"
    assert detector._match_text_to_spdx("Completely random proprietary text") is None


def test_extract_from_pyproject_variations(tmp_path: Path):
    detector = RepoLicenseDetector()

    # 1. Invalid TOML
    p_invalid = tmp_path / "pyproject_invalid.toml"
    p_invalid.write_text("invalid = [toml", encoding="utf-8")
    assert detector._extract_from_pyproject(p_invalid) is None

    # 2. String license field
    p_str = tmp_path / "pyproject_str.toml"
    p_str.write_text('[project]\nlicense = "MIT"\n', encoding="utf-8")
    assert detector._extract_from_pyproject(p_str) == "MIT"

    # 3. Dict license field
    p_dict = tmp_path / "pyproject_dict.toml"
    p_dict.write_text('[project.license]\ntext = "Apache-2.0"\n', encoding="utf-8")
    assert detector._extract_from_pyproject(p_dict) == "Apache-2.0"

    # 4. Classifiers
    p_class = tmp_path / "pyproject_class.toml"
    p_class.write_text("""[project]
classifiers = [
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "License :: OSI Approved :: MIT License",
]
""", encoding="utf-8")
    assert detector._extract_from_pyproject(p_class) == "GPL-3.0-only"

    # 5. Other classifiers
    for classifier, expected in [
        ("License :: OSI Approved :: Apache Software License", "Apache-2.0"),
        ("License :: OSI Approved :: GNU General Public License v2 (GPLv2)", "GPL-2.0-only"),
        ("License :: OSI Approved :: BSD License", "BSD-3-Clause"),
        ("License :: OSI Approved :: Mozilla Public License 2.0 (MPL 2.0)", "MPL-2.0"),
    ]:
        p = tmp_path / "pyproject_temp.toml"
        p.write_text(f'[project]\nclassifiers = ["{classifier}"]\n', encoding="utf-8")
        assert detector._extract_from_pyproject(p) == expected


def test_detect_candidate_files_and_fallbacks(tmp_path: Path):
    detector = RepoLicenseDetector()

    # Empty repo -> all_rights_reserved_by_default
    empty_res = detector.detect(tmp_path)
    assert empty_res.confidence == "none"
    assert empty_res.category == "all_rights_reserved_by_default"
    assert empty_res.spdx_id is None

    # Repo with LICENSE file
    lic_file = tmp_path / "LICENSE"
    lic_file.write_text("MIT License\nPermission is hereby granted, free of charge...", encoding="utf-8")
    res = detector.detect(tmp_path)
    assert res.confidence == "high"
    assert res.spdx_id == "MIT"
    assert res.category == "permissive"
    assert res.source == "LICENSE"

    # Remove LICENSE and add pyproject
    lic_file.unlink()
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project]\nlicense = "Apache-2.0"\n', encoding="utf-8")
    res_py = detector.detect(tmp_path)
    assert res_py.confidence == "medium"
    assert res_py.spdx_id == "Apache-2.0"
    assert res_py.category == "permissive"


def test_repo_license_detector_extra_branches(tmp_path: Path):
    detector = RepoLicenseDetector()

    # Generic GNU GPL
    assert detector._match_text_to_spdx("GNU General Public License strictly") == "GPL-3.0-only"

    # pyproject license string with matched spdx
    p1 = tmp_path / "p1.toml"
    p1.write_text('[project]\nlicense = "MIT License"\n', encoding="utf-8")
    assert detector._extract_from_pyproject(p1) == "MIT"

    # pyproject license dict with matched spdx
    p2 = tmp_path / "p2.toml"
    p2.write_text('[project.license]\ntext = "MIT License"\n', encoding="utf-8")
    assert detector._extract_from_pyproject(p2) == "MIT"

    # pyproject classifier MIT
    p3 = tmp_path / "p3.toml"
    p3.write_text('[project]\nclassifiers = ["License :: OSI Approved :: MIT License"]\n', encoding="utf-8")
    assert detector._extract_from_pyproject(p3) == "MIT"

    # Unreadable file exception handling
    bad_lic = tmp_path / "LICENSE"
    bad_lic.mkdir()  # is a directory, read_text will fail
    info = detector.detect(tmp_path)
    assert info.category == "all_rights_reserved_by_default"

