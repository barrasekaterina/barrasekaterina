"""Shared HTML-parsing core for Modex Recruit "Loan Officers" result pages.

Both `parse_loan_officers.py` (single saved page) and `scrape_all_pages.py`
(every page, fetched live) import this module so the extraction logic lives
in exactly one place.
"""

import re
from dataclasses import dataclass
from typing import List, Optional
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

FIELDS = [
    "name",
    "profile_url",
    "nmls_id",
    "employer_type",
    "employer_name",
    "employer_url",
    "volume",
    "units",
    "licensed_employment_history",
    "modex_score",
]


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


def parse_page(html: str) -> List[LoanOfficer]:
    """Return every loan officer record found on one results page."""
    soup = BeautifulSoup(html, "lxml")
    cards = soup.select(
        "div.bg-white.rounded.shadow-md.border.border-gray-300.mb-4.overflow-hidden"
    )
    records = [parse_card(card) for card in cards]
    # Drop cards that yielded no name (e.g. the "no results" placeholder card).
    return [record for record in records if record.name]


def parse_result_summary(html: str) -> Optional[dict]:
    """Pull the "Showing X to Y of Z results" footer, if present.

    Returns {"from": int, "to": int, "total": int} or None if the page
    doesn't have that footer (e.g. a fetch error page).
    """
    match = re.search(
        r"Showing\s*<span[^>]*>\s*([\d,]+)\s*</span>\s*to\s*<span[^>]*>\s*([\d,]+)\s*</span>\s*of\s*<span[^>]*>\s*([\d,]+)\s*results",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not match:
        return None
    to_int = lambda s: int(s.replace(",", ""))
    return {
        "from": to_int(match.group(1)),
        "to": to_int(match.group(2)),
        "total": to_int(match.group(3)),
    }
