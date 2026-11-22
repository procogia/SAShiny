"""Data frames as dataset inputs (spec CONTRACT.md 6.10 and 7.1)."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

import sashiny
from engines_helper import MockEngine
from sashiny import modules
from sashiny.upload import FrameUpload, UploadError, frame_csv, resolve_upload

pd = pytest.importorskip("pandas")

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / "spec" / "fixtures"


def _cases() -> list[dict[str, Any]]:
    return json.loads((FIX / "frames" / "cases.json").read_text(encoding="utf-8"))["cases"]


def _series(col: dict[str, Any]) -> Any:  # noqa: PLR0911 - one return per column type
    """A pandas column from a case's column spec (frames/cases.json)."""
    v = col["values"]
    kind = col["type"]
    if kind == "character":
        return pd.Series(v, dtype=object)
    if kind == "factor":
        return pd.Series(pd.Categorical(v))
    if kind == "integer":
        return pd.Series(pd.array(v, dtype="Int64"))
    if kind == "double":
        return pd.Series([float("nan") if x is None else float(x) for x in v], dtype="float64")
    if kind == "logical":
        return pd.Series(pd.array(v, dtype="boolean"))
    if kind == "date":
        return pd.Series([None if x is None else dt.date.fromisoformat(x) for x in v], dtype=object)
    if kind == "datetime":
        return pd.Series(pd.to_datetime(v, utc=True, format="ISO8601"))
    raise AssertionError(kind)


def _frame(columns: list[dict[str, Any]]) -> Any:
    data = {col["name"]: _series(col) for col in columns}
    return pd.DataFrame(data, columns=[col["name"] for col in columns])


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["name"])
def test_frame_cases_write_the_expected_bytes(case: dict[str, Any]) -> None:
    assert frame_csv(_frame(case["columns"])) == case["csv"].encode("utf-8")


def test_object_columns_are_written_value_by_value() -> None:
    frame = pd.DataFrame(
        {"mix": pd.Series(["a", 1, 2.5, True, None, dt.date(2025, 1, 2)], dtype=object)}
    )
    assert frame_csv(frame) == b"mix\na\n1\n2.5\n1\n\n2025-01-02\n"


def test_naive_datetimes_count_as_utc() -> None:
    naive = pd.DataFrame({"ts": pd.to_datetime(["2025-03-01 08:00:00.25"])})
    aware = pd.DataFrame({"ts": pd.to_datetime(["2025-03-01T09:00:00.25+01:00"], utc=True)})
    assert frame_csv(naive) == frame_csv(aware) == b"ts\n2025-03-01T08:00:00.25Z\n"


def test_frames_that_cannot_be_written_are_upload_errors() -> None:
    with pytest.raises(UploadError, match="infinite"):
        frame_csv(pd.DataFrame({"x": [1.0, float("inf")]}))
    with pytest.raises(UploadError, match="column 'items'"):
        frame_csv(pd.DataFrame({"items": pd.Series([[1], {"a": 2}], dtype=object)}))
    with pytest.raises(UploadError, match="column 'd'"):
        frame_csv(pd.DataFrame({"d": pd.to_timedelta(["1 day"])}))
    with pytest.raises(UploadError, match="no columns"):
        frame_csv(pd.DataFrame())
    with pytest.raises(UploadError, match="must be a data frame"):
        frame_csv("adsl.csv")


def _dataset_contract() -> sashiny.Contract:
    return sashiny.load(FIX / "contracts" / "valid" / "dataset" / "contract.sashiny.yml")


def _adsl() -> Any:
    return pd.DataFrame(
        {
            "USUBJID": ["S-001", "S-002"],
            "AGE": [54.0, 61.0],
            "TRTSDT": [dt.date(2026, 1, 15), dt.date(2026, 2, 1)],
        }
    )


def test_resolve_upload_writes_frames_as_id_csv(tmp_path: Path) -> None:
    contract = _dataset_contract()
    spec = contract.data["inputs"]["adsl"]
    by_frame = resolve_upload(_adsl(), spec, tmp_path, "adsl")
    wrapped = resolve_upload(FrameUpload(frame=_adsl(), input_id="adsl"), spec, tmp_path)
    assert by_frame is not None
    assert wrapped is not None
    assert by_frame.name == wrapped.name == "adsl.csv"
    assert by_frame.path.read_bytes() == wrapped.path.read_bytes() == frame_csv(_adsl())


def test_same_frame_same_upload_hash_as_its_csv_file(tmp_path: Path) -> None:
    # The upload SHA-256 is part of the cache and recording keys (spec 6.11, 8.3).
    path = tmp_path / "adsl.csv"
    path.write_bytes(frame_csv(_adsl()))
    spec = _dataset_contract().data["inputs"]["adsl"]
    upload = resolve_upload(_adsl(), spec, tmp_path, "adsl")
    assert upload is not None
    assert (
        hashlib.sha256(upload.path.read_bytes()).hexdigest()
        == hashlib.sha256(path.read_bytes()).hexdigest()
    )


def test_run_accepts_a_frame_for_a_dataset_input() -> None:
    result = MockEngine().run(_dataset_contract(), {}, uploads={"adsl": _adsl()})
    assert result.status == "success"
    assert not result.metadata.get("issues")


def test_a_frame_missing_a_declared_column_is_v014() -> None:
    result = MockEngine().run(
        _dataset_contract(), {}, uploads={"adsl": pd.DataFrame({"USUBJID": ["S-001"]})}
    )
    assert result.status == "error"
    assert "V014" in {i["code"] for i in result.metadata["issues"]}


def test_snapshot_takes_dataset_values_from_values() -> None:
    contract = _dataset_contract()
    read = {}.get
    snap = modules._snapshot_inputs(contract, read, {"adsl": _adsl()})
    assert not isinstance(snap, sashiny.Result)
    assert isinstance(snap[1]["adsl"], FrameUpload)
    assert MockEngine().run(contract, snap[0], uploads=snap[1]).status == "success"

    # None removes it: the required dataset is missing (V001).
    snap = modules._snapshot_inputs(contract, read, {"adsl": None})
    assert not isinstance(snap, sashiny.Result)
    missing = MockEngine().run(contract, snap[0], uploads=snap[1])
    assert "V001" in {i["code"] for i in missing.metadata["issues"]}

    # Anything else for a dataset id is V014.
    snap = modules._snapshot_inputs(contract, read, {"adsl": "adsl.csv"})
    assert not isinstance(snap, sashiny.Result)
    other = MockEngine().run(contract, snap[0], uploads=snap[1])
    assert "V014" in {i["code"] for i in other.metadata["issues"]}


def test_merge_uploads_without_values_keeps_the_ui_uploads() -> None:
    contract = _dataset_contract()
    assert modules.merge_uploads(contract, {"adsl": True}, None) == {"adsl": True}
    assert modules.merge_uploads(contract, {"adsl": True}, {"other": 1}) == {"adsl": True}
