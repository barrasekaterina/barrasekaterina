#!/usr/bin/env python3
"""Extract loan officer records from ONE saved Modex Recruit results page.

Usage:
    python parse_loan_officers.py page.html --format csv > loan_officers.csv
    python parse_loan_officers.py page.html --format json > loan_officers.json

For scraping every page of results (not just one saved page), use
`scrape_all_pages.py` instead.
"""

import argparse
import csv
import json
import sys
from dataclasses import asdict

from modex_parser import FIELDS, parse_page


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html_file", help="Path to the saved Modex Recruit HTML page")
    parser.add_argument("--format", choices=["json", "csv"], default="json")
    args = parser.parse_args()

    with open(args.html_file, "r", encoding="utf-8") as fh:
        html = fh.read()

    records = parse_page(html)

    if args.format == "json":
        json.dump([asdict(r) for r in records], sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        writer = csv.DictWriter(sys.stdout, fieldnames=FIELDS)
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))

    print(f"Parsed {len(records)} loan officer record(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
