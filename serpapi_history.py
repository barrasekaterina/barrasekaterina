#!/usr/bin/env python3
"""Fetch multiple archived SerpApi searches (by search_id) and export them as a pandas DataFrame.

SerpApi has no endpoint that lists your entire account's search history in one call --
only the Search Archive API (https://serpapi.com/search-archive-api), which retrieves
ONE past search per call by its search_id (found at result['search_metadata']['id']
when the search was originally run). This script fetches a list of search_ids you
already have and combines them into a single DataFrame.

If you don't have your search_ids saved anywhere, they aren't retrievable after the
fact -- check your SerpApi dashboard at https://serpapi.com/searches for a manual
export option instead.

Notebook usage:
    from serpapi_history import get_archived_searches

    df = get_archived_searches(["5b50d58a304bda2fca30bac9", "..."], api_key="YOUR_KEY")
    df.to_csv("search_history.csv", index=False)

CLI usage:
    export SERPAPI_KEY=your_api_key
    python serpapi_history.py --search-ids id1 id2 id3 -o search_history.csv
    # or: python serpapi_history.py --ids-file ids.txt -o search_history.csv
"""

import argparse
import os
import sys

import pandas as pd
import serpapi


def get_archived_searches(search_ids, api_key=None):
    """Fetch each archived search by ID and return them combined as a DataFrame."""
    api_key = api_key or os.getenv("SERPAPI_KEY")
    if not api_key:
        raise ValueError("No API key provided. Pass api_key= or set SERPAPI_KEY.")

    client = serpapi.Client(api_key=api_key)
    rows = []
    for search_id in search_ids:
        try:
            result = client.search_archive(search_id=search_id)
            row = dict(result.get("search_metadata", {}))
            row["search_id"] = search_id
            row["status"] = row.get("status")
            rows.append(row)
        except serpapi.HTTPError as exc:
            rows.append({"search_id": search_id, "status": "error", "error": str(exc)})

    return pd.DataFrame(rows)


def load_search_ids(args):
    search_ids = list(args.search_ids or [])
    if args.ids_file:
        with open(args.ids_file, "r", encoding="utf-8") as f:
            search_ids.extend(line.strip() for line in f if line.strip())
    if not search_ids:
        sys.exit("No search_ids provided. Use --search-ids and/or --ids-file.")
    return search_ids


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--search-ids", nargs="+", help="One or more search_id values")
    parser.add_argument("--ids-file", help="Path to a text file with one search_id per line")
    parser.add_argument("--api-key", default=os.getenv("SERPAPI_KEY"), help="SerpApi API key (default: $SERPAPI_KEY)")
    parser.add_argument("-o", "--output", default="search_history.csv", help="Output CSV path")
    args, _unknown = parser.parse_known_args()

    if not args.api_key:
        sys.exit("No API key provided. Set SERPAPI_KEY or pass --api-key.")

    search_ids = load_search_ids(args)
    df = get_archived_searches(search_ids, api_key=args.api_key)
    df.to_csv(args.output, index=False)
    print(f"Exported {len(df)} archived searches to {args.output}")


if __name__ == "__main__":
    main()
