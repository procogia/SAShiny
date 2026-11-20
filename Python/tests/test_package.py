import re

import sashiny


def test_info_reports_versions() -> None:
    info = sashiny.info()
    assert info.version == sashiny.__version__
    assert re.fullmatch(r"1\.\d+", info.spec)
    assert info.contract == 1
    assert str(info) == f"sashiny {info.version} (spec {info.spec}, contract sashiny: 1)"


def test_spec_release_matches_contract_md() -> None:
    from _repo import repo_root  # noqa: PLC0415

    text = (repo_root() / "spec" / "CONTRACT.md").read_text(encoding="utf-8")
    m = re.search(r"Spec release: \*\*([0-9.]+)\*\*", text)
    assert m is not None
    assert m.group(1) == sashiny.info().spec


def test_version_is_pep440() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+(\.dev\d+|a\d+|b\d+|rc\d+)?", sashiny.__version__)
