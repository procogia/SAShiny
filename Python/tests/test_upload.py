"""Tests for dataset upload conversion (spec §7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from sashiny.upload import UploadError, UploadFile, read_upload, resolve_upload, sanitize_names

pd = pytest.importorskip("pandas")

SPEC = {
    "type": "dataset",
    "target": "work.adsl",
    "columns": [
        {"name": "usubjid", "type": "character"},
        {"name": "age", "type": "numeric"},
        {"name": "trtsdt", "type": "date"},
    ],
}


def _csv(tmp_path: Path, text: str, name: str = "adsl.csv") -> UploadFile:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return UploadFile(path=path, name=name)


def test_resolve_upload(tmp_path: Path) -> None:
    assert resolve_upload(None, SPEC, tmp_path) is None
    with pytest.raises(UploadError, match="no sample"):
        resolve_upload(True, SPEC, tmp_path)
    sample = resolve_upload(True, {**SPEC, "sample": "data/x.csv"}, tmp_path)
    assert sample == UploadFile(path=tmp_path / "data" / "x.csv", name="x.csv")
    assert resolve_upload(tmp_path / "y.CSV", SPEC, tmp_path).extension == "csv"
    upload = UploadFile(path=tmp_path / "tmp123", name="real.xlsx")
    assert resolve_upload(upload, SPEC, tmp_path) is upload


def test_sanitize_names() -> None:
    assert sanitize_names(["a b", "1x", "A_B", "é"]) == ["a_b", "_1x", "A_B_2", "_"]
    long = "x" * 40
    assert sanitize_names([long, long]) == ["x" * 32, "x" * 30 + "_2"]


def test_read_csv_converts_declared_and_inferred_columns(tmp_path: Path) -> None:
    upload = _csv(
        tmp_path,
        "USUBJID,AGE,TRTSDT,extra num,note\nS1,45,2024-01-02,1.5,hi\nS2,,,2,\n",
    )
    df, datetimes = read_upload(upload, SPEC)
    assert list(df.columns) == ["USUBJID", "AGE", "TRTSDT", "extra_num", "note"]
    assert datetimes == {"TRTSDT": "date"}
    assert df["AGE"].tolist()[0] == 45
    assert pd.isna(df["AGE"].tolist()[1])
    assert pd.api.types.is_datetime64_any_dtype(df["TRTSDT"])
    assert pd.api.types.is_numeric_dtype(df["extra_num"])
    assert df["note"].tolist() == ["hi", ""]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("USUBJID,AGE\nS1,40\n", "no column trtsdt"),
        ("USUBJID,AGE,TRTSDT\nS1,old,2024-01-01\n", "not numbers"),
        ("USUBJID,AGE,TRTSDT\nS1,4,01/02/2024\n", "YYYY-MM-DD"),
    ],
)
def test_read_csv_rejects_bad_values(tmp_path: Path, text: str, message: str) -> None:
    with pytest.raises(UploadError, match=message):
        read_upload(_csv(tmp_path, text), SPEC)


def test_read_upload_checks_extension_size_and_existence(tmp_path: Path) -> None:
    with pytest.raises(UploadError, match="not accepted"):
        read_upload(_csv(tmp_path, "a\n1\n"), {**SPEC, "accept": ["xlsx"]})
    with pytest.raises(UploadError, match="file not found"):
        read_upload(UploadFile(path=tmp_path / "nope.csv", name="nope.csv"), SPEC)
    big = _csv(tmp_path, "a\n" + "1\n" * 1000)
    with pytest.raises(UploadError, match="MB"):
        read_upload(big, {**SPEC, "columns": [], "max_size_mb": 0.0001})


def test_read_xlsx(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    path = tmp_path / "adsl.xlsx"
    pd.DataFrame({"USUBJID": ["S1"], "AGE": [50], "TRTSDT": [pd.Timestamp("2024-03-01")]}).to_excel(
        path, index=False
    )
    df, datetimes = read_upload(UploadFile(path=path, name="adsl.xlsx"), SPEC)
    assert datetimes == {"TRTSDT": "date"}
    assert df["AGE"].tolist() == [50]


def test_read_csv_rejects_literal_na_in_date(tmp_path: Path) -> None:
    # Spec §7 step 3: only empty/whitespace is missing; the literal text "NA"
    # is unparseable and reported as V014 (parity with R).
    upload = _csv(tmp_path, "USUBJID,AGE,TRTSDT\nS1,45,NA\n")
    with pytest.raises(UploadError, match="YYYY-MM-DD"):
        read_upload(upload, SPEC)


def test_read_xlsx_character_column_drops_float_dot_zero(tmp_path: Path) -> None:
    # Spec §7 step 3: character columns convert numbers like R's as.character,
    # so an integer-valued float 1.0 becomes "1", not "1.0".
    pytest.importorskip("openpyxl")
    spec = {
        "type": "dataset",
        "target": "work.adsl",
        "columns": [{"name": "code", "type": "character"}],
    }
    path = tmp_path / "adsl.xlsx"
    pd.DataFrame({"code": [1.0, 1.5]}).to_excel(path, index=False)
    df, _ = read_upload(UploadFile(path=path, name="adsl.xlsx"), spec)
    assert df["code"].tolist() == ["1", "1.5"]


def test_read_xlsx_numeric_whitespace_is_missing(tmp_path: Path) -> None:
    # Spec §7 step 3: "empty = missing"; a whitespace-only cell in a non-CSV
    # numeric column is empty (parity with R).
    pytest.importorskip("openpyxl")
    path = tmp_path / "adsl.xlsx"
    frame = pd.DataFrame(
        {"USUBJID": ["S1", "S2"], "AGE": [50, " "], "TRTSDT": ["2024-01-01", "2024-01-02"]}
    )
    frame.to_excel(path, index=False)
    df, _ = read_upload(UploadFile(path=path, name="adsl.xlsx"), SPEC)
    assert df["AGE"].tolist()[0] == 50
    assert pd.isna(df["AGE"].tolist()[1])


def test_read_unreadable_file(tmp_path: Path) -> None:
    path = tmp_path / "bad.xlsx"
    path.write_bytes(b"not a workbook")
    with pytest.raises(UploadError, match="could not read"):
        read_upload(UploadFile(path=path, name="bad.xlsx"), SPEC)


def test_read_xlsx_preserves_literal_na_and_leading_zeros(tmp_path: Path) -> None:
    # Spec §7 step 3: only empty/whitespace is missing; the literal text "NA"
    # is data for a character column, and leading zeros are preserved.
    pytest.importorskip("openpyxl")
    spec = {
        "type": "dataset",
        "target": "work.adsl",
        "columns": [{"name": "code", "type": "character"}],
    }
    path = tmp_path / "adsl.xlsx"
    pd.DataFrame({"code": ["001", "NA"]}).to_excel(path, index=False)
    df, _ = read_upload(UploadFile(path=path, name="adsl.xlsx"), spec)
    assert df["code"].tolist() == ["001", "NA"]


def test_read_xlsx_rejects_literal_na_in_numeric(tmp_path: Path) -> None:
    # Spec §7 step 3: the literal text "NA" in a numeric column is unparseable
    # (V014), not missing.
    pytest.importorskip("openpyxl")
    path = tmp_path / "adsl.xlsx"
    pd.DataFrame({"USUBJID": ["S1"], "AGE": ["NA"], "TRTSDT": ["2024-01-01"]}).to_excel(
        path, index=False
    )
    with pytest.raises(UploadError, match="not numbers"):
        read_upload(UploadFile(path=path, name="adsl.xlsx"), SPEC)


def test_read_csv_preserves_duplicate_headers(tmp_path: Path) -> None:
    # Spec §7 step 2: duplicate headers resolve to x, x_2 (not pandas' x, x.1).
    upload = _csv(tmp_path, "x,x\n1,2\n")
    df, _ = read_upload(upload, {"type": "dataset", "target": "work.test"})
    assert list(df.columns) == ["x", "x_2"]


def test_read_csv_rejects_unpadded_date(tmp_path: Path) -> None:
    # Spec §7 step 3: dates must be exactly YYYY-MM-DD; "2026-1-2" is unparseable.
    upload = _csv(tmp_path, "USUBJID,AGE,TRTSDT\nS1,45,2026-1-2\n")
    with pytest.raises(UploadError, match="YYYY-MM-DD"):
        read_upload(upload, SPEC)
