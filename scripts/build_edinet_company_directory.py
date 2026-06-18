from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.edinet_client import EdinetClient  # noqa: E402
from src.edinet_company_directory import (  # noqa: E402
    DEFAULT_EDINET_DIRECTORY_PATH,
    build_company_directory_from_filings,
)
from src.edinet_lookup import fetch_document_rows_in_period  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a lightweight EDINET company lookup directory.")
    parser.add_argument("--days", type=int, default=730, help="Lookback days from the end date.")
    parser.add_argument("--end-date", default=None, help="End date in YYYY-MM-DD. Defaults to yesterday.")
    parser.add_argument("--output", type=Path, default=DEFAULT_EDINET_DIRECTORY_PATH)
    parser.add_argument("--doc-type", type=int, default=2)
    parser.add_argument("--csv-only", action="store_true", help="Keep only rows with CSV flag.")
    parser.add_argument("--annual-only", action="store_true", help="Keep only annual securities reports.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    end_date = date.fromisoformat(args.end_date) if args.end_date else date.today() - timedelta(days=1)
    client = EdinetClient(timeout_seconds=30)
    if not client.has_api_key:
        print("EDINET_API_KEY is not set.", file=sys.stderr)
        return 2

    rows = fetch_document_rows_in_period(
        client,
        end_date=end_date,
        lookback_days=args.days,
        doc_type=args.doc_type,
        annual_only=args.annual_only,
        csv_only=args.csv_only,
    )
    directory = build_company_directory_from_filings(pd.DataFrame(rows))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    directory.to_csv(args.output, index=False, encoding="utf-8")
    print(
        {
            "output": str(args.output),
            "end_date": end_date.isoformat(),
            "days": args.days,
            "filing_rows": len(rows),
            "company_rows": len(directory),
        }
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
