#!/usr/bin/env python3
"""Extract loan officer records from a saved Modex Recruit results page.

Usage:
    python parse_loan_officers.py page.html --format csv > loan_officers.csv
    python parse_loan_officers.py page.html --format json > loan_officers.json

The input is the raw HTML of a Modex Recruit "Loan Officers" search results
page (e.g. saved from the browser after applying filters). Each result card
is parsed into a flat record with the profile name/link, NMLS ID, employer
(company or branch), and the four stat tiles shown on the card.
"""

import argparse
import csv
import json
import re
import sys
from dataclasses import asdict, dataclass
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

BASE_URL = "https://modex.com"

# Card stat tiles are matched by their visible label, not position, since a
# missing stat (e.g. no Modex Score yet) shifts the remaining tiles left.
STAT_LABELS = {
    "Volume (1 Year)": "volume",
    "Units (1 Year)": "units",
    "Licensed Employment History": "licensed_employment_history",
    "Modex Score": "modex_score",
}


@dataclass
class LoanOfficer:
    name: Optional[str]
    profile_url: Optional[str]
    nmls_id: Optional[str]
    employer_type: Optional[str]  # "company" or "branch"
    employer_name: Optional[str]
    employer_url: Optional[str]
    volume: Optional[str]
    units: Optional[str]
    licensed_employment_history: Optional[str]
    modex_score: Optional[str]


def _text(node) -> Optional[str]:
    if node is None:
        return None
    text = node.get_text(strip=True)
    return text or None


def parse_card(card) -> LoanOfficer:
    name_link = card.select_one('a[href*="/recruit/loan-officers/"]')
    name = _text(name_link)
    profile_url = urljoin(BASE_URL, name_link["href"]) if name_link and name_link.get("href") else None

    nmls_span = card.find("span", string=re.compile(r"NMLS ID:"))
    nmls_id = None
    if nmls_span:
        match = re.search(r"NMLS ID:\s*(\S+)", nmls_span.get_text(strip=True))
        nmls_id = match.group(1) if match else None

    employer_link = card.select_one('a[href*="/recruit/companies/"], a[href*="/recruit/branches/"]')
    employer_type = None
    employer_name = None
    employer_url = None
    if employer_link and employer_link.get("href"):
        employer_type = "company" if "/companies/" in employer_link["href"] else "branch"
        employer_name = _text(employer_link)
        employer_url = urljoin(BASE_URL, employer_link["href"])

    stats = {value: None for value in STAT_LABELS.values()}
    for label, key in STAT_LABELS.items():
        label_node = card.find(string=re.compile(rf"^\s*{re.escape(label)}\s*$"))
        if label_node is None:
            continue
        label_div = label_node.find_parent("div")
        if label_div is None:
            continue
        value_div = label_div.find_previous_sibling("div")
        stats[key] = _text(value_div)

    return LoanOfficer(
        name=name,
        profile_url=profile_url,
        nmls_id=nmls_id,
        employer_type=employer_type,
        employer_name=employer_name,
        employer_url=employer_url,
        **stats,
    )


def parse_page(html: str) -> list:
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(
        "div.bg-white.rounded.shadow-md.border.border-gray-300.mb-4.overflow-hidden"
    )
    records = [parse_card(card) for card in cards]
    # Drop cards that yielded no name (e.g. the "no results" placeholder card).
    return [record for record in records if record.name]


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
        writer = csv.DictWriter(sys.stdout, fieldnames=list(asdict(LoanOfficer(*[None] * 10)).keys()))
        writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))

    print(f"Parsed {len(records)} loan officer record(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
