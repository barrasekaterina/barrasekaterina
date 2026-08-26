#!/usr/bin/env python3
"""Fetch your SerpApi account's search history (all past requests) as a pandas DataFrame.

IMPORTANT: SerpApi does not officially document a single endpoint that lists every past
search for an account -- the documented API only offers per-search lookup by ID
(https://serpapi.com/search-archive-api) and account usage stats
(https://serpapi.com/account-api). This script calls the same JSON endpoint their
dashboard's "Search History" page (https://serpapi.com/searches) uses, authenticated
with your api_key query param instead of a browser session. This is UNDOCUMENTED and
may change or stop working without notice -- if it fails, log into the dashboard at
https://serpapi.com/searches and look for a manual export/download option instead.

Notebook usage:
    from serpapi_history import get_search_history

    df = get_search_history(api_key="YOUR_SERPAPI_KEY")
    df.to_csv("search_history.csv", index=False)

CLI usage:
    export SERPAPI_KEY=your_api_key
    python serpapi_history.py -o search_history.csv
"""

import argparse
import os
import sys

import pandas as pd
import requests

HISTORY_URL = "https://serpapi.com/searches.json"


def get_search_history(api_key=None, max_pages=1000):
    """Page through the account's search history and return it as a DataFrame."""
    api_key = api_key or os.getenv("SERPAPI_KEY")
    if not api_key:
        raise ValueError("No API key provided. Pass api_key= or set SERPAPI_KEY.")

    rows = []
    page = 1
    while page <= max_pages:
        response = requests.get(HISTORY_URL, params={"api_key": api_key, "page": page}, timeout=30)
        response.raise_for_status()
        payload = response.json()

        # The exact response shape is unconfirmed since this endpoint is undocumented;
        # handle the two most likely shapes (a top-level list, or {"searches": [...]}).
        batch = payload if isinstance(payload, list) else payload.get("searches", [])
        if not batch:
            break

        rows.extend(batch)
        page += 1

    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-key", default=os.getenv("SERPAPI_KEY"), help="SerpApi API key (default: $SERPAPI_KEY)")
    parser.add_argument("-o", "--output", default="search_history.csv", help="Output CSV path")
    args, _unknown = parser.parse_known_args()

    if not args.api_key:
        sys.exit("No API key provided. Set SERPAPI_KEY or pass --api-key.")

    df = get_search_history(api_key=args.api_key)
    df.to_csv(args.output, index=False)
    print(f"Exported {len(df)} past searches to {args.output}")


if __name__ == "__main__":
    main()
