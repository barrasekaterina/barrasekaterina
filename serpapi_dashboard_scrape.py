#!/usr/bin/env python3
"""Scrape your SerpApi dashboard's "Search History" pages (serpapi.com/searches?page=N)
into a single pandas DataFrame, using your browser session cookie for auth.

This exists because SerpApi has no API that lists your whole account history -- only
the dashboard's own paginated HTML pages show it, and those require a logged-in
session (not an api_key). This is unofficial/fragile: if SerpApi changes the page
layout, the table parsing below may need adjusting.

SECURITY: the cookie below is your live login -- treat it like a password.
    - Set it via the SERPAPI_COOKIE environment variable, never hardcode it in a file
      you might commit or share.
    - After you're done exporting, sign out of all sessions / change your SerpApi
      password to invalidate it (especially since "remember_user_token" cookies are
      long-lived).

Usage:
    # PowerShell:
    $env:SERPAPI_COOKIE = "paste the full Cookie header value here"
    python serpapi_dashboard_scrape.py -o search_history.csv

Notebook usage:
    from serpapi_dashboard_scrape import scrape_search_history

    df = scrape_search_history(cookie="paste the full Cookie header value here")
    df.to_csv("search_history.csv", index=False)
"""

import argparse
import os
import re
import sys

import pandas as pd
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://serpapi.com/searches"
SEARCH_ID_RE = re.compile(r"/searches/([a-f0-9]{24})")


def parse_page(html):
    """Extract table rows from one dashboard page's HTML."""
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table")
    if not tables:
        return []

    table = max(tables, key=lambda t: len(t.find_all("tr")))
    headers = [th.get_text(strip=True) for th in table.find_all("th")]

    rows = []
    for tr in table.find_all("tr"):
        cells = tr.find_all("td")
        if not cells:
            continue

        if headers and len(headers) == len(cells):
            row = {headers[i]: cells[i].get_text(strip=True) for i in range(len(cells))}
        else:
            row = {f"col_{i}": c.get_text(strip=True) for i, c in enumerate(cells)}

        # Recover the real search_id from a row link even if not shown as plain text.
        link = tr.find("a", href=SEARCH_ID_RE)
        if link:
            row["search_id"] = SEARCH_ID_RE.search(link["href"]).group(1)

        rows.append(row)

    return rows


def scrape_search_history(cookie=None, max_pages=500):
    """Walk every ?page=N of the dashboard's search history and return one DataFrame."""
    cookie = cookie or os.getenv("SERPAPI_COOKIE")
    if not cookie:
        raise ValueError("No cookie provided. Pass cookie= or set SERPAPI_COOKIE.")

    headers = {
        "Cookie": cookie,
        "User-Agent": "Mozilla/5.0",
    }

    all_rows = []
    with requests.Session() as session:
        for page in range(max_pages):
            response = session.get(BASE_URL, params={"page": page}, headers=headers, timeout=30)

            if "sign_in" in response.url or "login" in response.url:
                raise RuntimeError(
                    "Redirected to a login page -- the cookie is invalid or expired. "
                    "Grab a fresh Cookie header from your browser and try again."
                )

            rows = parse_page(response.text)
            if not rows:
                break

            all_rows.extend(rows)
            print(f"page {page}: {len(rows)} rows (total so far: {len(all_rows)})")

    return pd.DataFrame(all_rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cookie", default=os.getenv("SERPAPI_COOKIE"), help="Cookie header value (default: $SERPAPI_COOKIE)")
    parser.add_argument("-o", "--output", default="search_history.csv", help="Output CSV path")
    args, _unknown = parser.parse_known_args()

    if not args.cookie:
        sys.exit("No cookie provided. Set SERPAPI_COOKIE or pass --cookie.")

    df = scrape_search_history(cookie=args.cookie)
    df.to_csv(args.output, index=False)
    print(f"Exported {len(df)} rows to {args.output}")


if __name__ == "__main__":
    main()
