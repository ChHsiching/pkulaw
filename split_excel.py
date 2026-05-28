"""Split a large Excel/JSON file into smaller files with identical headers."""
import json
import re
import argparse
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font

_ILLEGAL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")


def split_json(input_path: Path, output_dir: Path, chunk_size: int) -> None:
    cases = json.loads(input_path.read_text())
    output_dir.mkdir(parents=True, exist_ok=True)

    for i in range(0, len(cases), chunk_size):
        chunk = cases[i:i + chunk_size]
        idx = i // chunk_size + 1
        total = (len(cases) + chunk_size - 1) // chunk_size
        out_path = output_dir / f"pkulaw_cases_{idx:03d}_of_{total}.json"
        out_path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {out_path.name}: {len(chunk)} cases")

    print(f"Split {len(cases)} cases into {total} files")


def split_excel(input_path: Path, output_dir: Path, chunk_size: int) -> None:
    cases = json.loads(input_path.with_suffix(".json").read_text())
    output_dir.mkdir(parents=True, exist_ok=True)

    all_keys = set()
    for case in cases:
        all_keys.update(case.keys())

    skip = {"search_year", "summaries"}
    columns = sorted(all_keys - skip)

    for i in range(0, len(cases), chunk_size):
        chunk = cases[i:i + chunk_size]
        idx = i // chunk_size + 1
        total = (len(cases) + chunk_size - 1) // chunk_size
        out_path = output_dir / f"pkulaw_cases_{idx:03d}_of_{total}.xlsx"

        wb = Workbook()
        ws = wb.active
        ws.title = "司法案例"

        for col_idx, col_name in enumerate(columns, 1):
            cell = ws.cell(row=1, column=col_idx, value=col_name)
            cell.font = Font(bold=True)

        for row_idx, case in enumerate(chunk, 2):
            for col_idx, col_name in enumerate(columns, 1):
                val = case.get(col_name, "")
                if isinstance(val, str):
                    val = _ILLEGAL_RE.sub("", val)
                ws.cell(row=row_idx, column=col_idx, value=val)

        wb.save(str(out_path))
        print(f"  {out_path.name}: {len(chunk)} cases, {len(columns)} columns")

    print(f"Split {len(cases)} cases into {total} Excel files ({len(columns)} columns each)")


def main():
    parser = argparse.ArgumentParser(description="Split large case data into smaller files")
    parser.add_argument("--input", default="output/pkulaw_cases.json", help="Input JSON path")
    parser.add_argument("--output-dir", default="output/split", help="Output directory")
    parser.add_argument("--chunk-size", type=int, default=10000, help="Cases per file")
    parser.add_argument("--format", choices=["json", "excel", "both"], default="both")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)

    cases = json.loads(input_path.read_text())
    print(f"Loaded {len(cases)} cases from {input_path}")

    if args.format in ("json", "both"):
        print(f"\nSplitting JSON ({args.chunk_size} per file):")
        split_json(input_path, output_dir, args.chunk_size)

    if args.format in ("excel", "both"):
        print(f"\nSplitting Excel ({args.chunk_size} per file):")
        split_excel(input_path, output_dir, args.chunk_size)


if __name__ == "__main__":
    main()
