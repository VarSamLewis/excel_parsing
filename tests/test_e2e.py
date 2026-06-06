import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e

CLI = [sys.executable, str(Path(__file__).resolve().parent.parent / "cli" / "excel_ingest_cli.py")]
PROJECT = Path(__file__).resolve().parent.parent
EXCELS = Path(__file__).parent / "excels"
SCHEMAS = Path(__file__).parent / "schemas"
ARTIFACTS = PROJECT / "artifacts"


def _run(*args, timeout=120):
    result = subprocess.run(
        [*CLI, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result


def _latest(stem_glob):
    files = sorted(ARTIFACTS.glob(stem_glob))
    assert files, f"No artifacts found for {stem_glob}"
    return files[-1]


def _assert_extracted(stem, schema_path):
    schema = json.loads(schema_path.read_text())
    fields = {f["name"]: f["field_type"] for f in schema["fields"]}
    data = json.loads(_latest(f"extracted_data_{stem}_*.json").read_text())
    assert len(data) == 3
    for row in data:
        assert all(k in row for k in fields)
        assert all(v is not None for v in row.values())
        for name, ftype in fields.items():
            if ftype == "number":
                assert isinstance(row[name], (int, float))
            elif ftype == "boolean":
                assert isinstance(row[name], bool)
            elif ftype == "date":
                assert re.match(r"\d{4}-\d{2}-\d{2}", row[name])
            elif ftype == "string":
                assert isinstance(row[name], str)


def _assert_report(stem, schema_path):
    schema = json.loads(schema_path.read_text())
    field_names = {f["name"] for f in schema["fields"]}
    report = json.loads(_latest(f"ingestion_report_{stem}_*.json").read_text())
    assert report["success"] is True
    assert report["row_count"] == 3
    assert report["sheet_names"]
    assert report["schema_version"] >= 1
    mapped = {m["target_field"] for m in report["sheets"][0]["mapping"]["mappings"]}
    assert field_names.issubset(mapped)


def _assert_code(stem):
    code = _latest(f"extraction_code_{stem}_*.py").read_text()
    assert "from openpyxl import" in code
    assert "import json" in code
    assert "def main()" in code
    assert 'if __name__ == "__main__":' in code
    assert "convert_to_" in code
    compile(code, "<replay>", "exec")


def _assert_verify(stem):
    verify = _latest(f"verify_report_{stem}_*.md").read_text()
    assert "Rows produced: 3" in verify
    assert "Deterministic status: PASS" in verify
    assert "Numeric Diagnostics" in verify


def test_cli_health():
    result = _run("health")
    assert result.returncode == 0
    data = json.loads(result.stdout.strip())
    assert data == {"status": "ok"}


def test_cli_ingest_people():
    result = _run(
        "ingest",
        "--schema-file",
        str(SCHEMAS / "people_sample.schema.json"),
        "--excel-file",
        str(EXCELS / "people_sample.xlsx"),
        "--out-dir",
        str(ARTIFACTS),
        timeout=300,
    )
    assert result.returncode == 0
    _assert_extracted("people_sample", SCHEMAS / "people_sample.schema.json")
    _assert_report("people_sample", SCHEMAS / "people_sample.schema.json")
    _assert_code("people_sample")
    _assert_verify("people_sample")


def test_cli_ingest_sales():
    result = _run(
        "ingest",
        "--schema-file",
        str(SCHEMAS / "sales_sample.schema.json"),
        "--excel-file",
        str(EXCELS / "sales_sample.xlsx"),
        "--out-dir",
        str(ARTIFACTS),
        timeout=300,
    )
    assert result.returncode == 0
    _assert_extracted("sales_sample", SCHEMAS / "sales_sample.schema.json")
    _assert_report("sales_sample", SCHEMAS / "sales_sample.schema.json")
    _assert_code("sales_sample")
    _assert_verify("sales_sample")


def test_cli_ingest_with_llm_verify():
    result = _run(
        "ingest",
        "--schema-file",
        str(SCHEMAS / "people_sample.schema.json"),
        "--excel-file",
        str(EXCELS / "people_sample.xlsx"),
        "--out-dir",
        str(ARTIFACTS),
        "--llm-verify",
        timeout=300,
    )
    assert result.returncode == 0
    _assert_extracted("people_sample", SCHEMAS / "people_sample.schema.json")
    _assert_report("people_sample", SCHEMAS / "people_sample.schema.json")
    _assert_code("people_sample")
    _assert_verify("people_sample")


def test_cli_ingest_dir():
    result = _run(
        "ingest-dir",
        "--schema-file",
        str(SCHEMAS / "sales_sample.schema.json"),
        "--excel-dir",
        str(EXCELS),
        "--out-dir",
        str(ARTIFACTS),
        timeout=600,
    )
    assert result.returncode == 0
    assert list(ARTIFACTS.glob("extraction_code_people_sample_*.py"))
    assert list(ARTIFACTS.glob("extraction_code_sales_sample_*.py"))
