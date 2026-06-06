#!/usr/bin/env python3

"""Generate sample Excel files for local CLI/backend testing."""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet


def _write_sales_workbook(path: Path) -> None:
    """Create sales workbook; args: path (Path); returns: None."""
    wb: Workbook = Workbook()
    ws_candidate: Worksheet | None = wb.active
    if ws_candidate is None:
        raise RuntimeError("Workbook has no active worksheet")
    ws: Worksheet = ws_candidate
    ws.title = "Sales"
    ws.append(["company_name", "invoice_date", "amount", "paid"])
    ws.append(["Acme Ltd", date(2026, 1, 10), 1200.50, True])
    ws.append(["Globex", date(2026, 1, 14), 980.00, False])
    ws.append(["Initech", date(2026, 2, 2), 1550.75, True])
    wb.save(path)


def _write_people_workbook(path: Path) -> None:
    """Create people workbook; args: path (Path); returns: None."""
    wb: Workbook = Workbook()
    ws_candidate: Worksheet | None = wb.active
    if ws_candidate is None:
        raise RuntimeError("Workbook has no active worksheet")
    ws: Worksheet = ws_candidate
    ws.title = "Employees"
    ws.append(["name", "department", "start_date", "salary"])
    ws.append(["Alice Brown", "Operations", "2024-04-01", "55000"])
    ws.append(["Sam Carter", "Finance", "2023-09-15", "62000"])
    ws.append(["Ravi Patel", "Engineering", "2025-01-20", "78000"])
    wb.save(path)


def main() -> int:
    """Generate sample Excel set; args: none; returns: int."""
    parser: argparse.ArgumentParser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", default="tests/excels", help="Output directory")
    args: argparse.Namespace = parser.parse_args()
    out_dir: Path = Path(str(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)

    sales_path: Path = out_dir / "sales_sample.xlsx"
    people_path: Path = out_dir / "people_sample.xlsx"

    _write_sales_workbook(sales_path)
    _write_people_workbook(people_path)

    print(f"Wrote {sales_path}")
    print(f"Wrote {people_path}")
    return 0


if __name__ == "__main__":
    main()
