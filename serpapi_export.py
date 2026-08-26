#!/usr/bin/env python3
"""Run one or more SerpApi searches and export the combined organic results as a pandas DataFrame/CSV.

CLI usage:
    export SERPAPI_KEY=your_api_key
    python serpapi_export.py -q "coffee" -q "tea" -o searches.csv

    # or read queries from a file (one query per line)
    python serpapi_export.py --queries-file queries.txt -o searches.csv

Notebook / Jupyter usage:
    from serpapi_export import export_searches

    df = export_searches(["coffee", "tea"], api_key="your_api_key")
    df.to_csv("searches.csv", index=False)
"""

import argparse
import os
import sys

import pandas as pd
import serpapi


def fetch_searches(client, queries, engine):
    rows = []
    for query in queries:
        results = client.search({"engine": engine, "q": query})
        for result in results.get("organic_results", []):
            rows.append({"query": query, **result})
    return rows


def export_searches(queries, api_key=None, engine="google"):
    """Run `queries` through SerpApi and return the combined organic results as a DataFrame."""
    api_key = api_key or os.getenv("SERPAPI_KEY")
    if not api_key:
        raise ValueError("No API key provided. Pass api_key= or set SERPAPI_KEY.")

    client = serpapi.Client(api_key=api_key)
    rows = fetch_searches(client, queries, engine)
    return pd.DataFrame(rows)


def load_queries(args):
    queries = list(args.query or [])
    if args.queries_file:
        with open(args.queries_file, "r", encoding="utf-8") as f:
            queries.extend(line.strip() for line in f if line.strip())
    if not queries:
        sys.exit("No queries provided. Use -q/--query and/or --queries-file.")
    return queries


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-q", "--query", action="append", help="A search query (repeatable)")
    parser.add_argument("--queries-file", help="Path to a text file with one query per line")
    parser.add_argument("--engine", default="google", help="SerpApi engine (default: google)")
    parser.add_argument("--api-key", default=os.getenv("SERPAPI_KEY"), help="SerpApi API key (default: $SERPAPI_KEY)")
    parser.add_argument("-o", "--output", default="searches.csv", help="Output CSV path (default: searches.csv)")
    # parse_known_args ignores extra args (e.g. Jupyter's "-f kernel.json") so this
    # also works when run inside a notebook via %run instead of the command line.
    args, _unknown = parser.parse_known_args()

    if not args.api_key:
        sys.exit("No API key provided. Set SERPAPI_KEY or pass --api-key.")

    queries = load_queries(args)
    df = export_searches(queries, api_key=args.api_key, engine=args.engine)
    df.to_csv(args.output, index=False)
    print(f"Exported {len(df)} results from {len(queries)} search(es) to {args.output}")


if __name__ == "__main__":
    main()
