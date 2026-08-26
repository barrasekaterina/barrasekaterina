#!/usr/bin/env python3
"""Run one or more SerpApi searches and export the combined organic results as a pandas DataFrame/CSV.

Usage:
    export SERPAPI_KEY=your_api_key
    python serpapi_export.py -q "coffee" -q "tea" -o searches.csv

    # or read queries from a file (one query per line)
    python serpapi_export.py --queries-file queries.txt -o searches.csv
"""

import argparse
import os
import sys

import pandas as pd
import serpapi


def load_queries(args):
    queries = list(args.query or [])
    if args.queries_file:
        with open(args.queries_file, "r", encoding="utf-8") as f:
            queries.extend(line.strip() for line in f if line.strip())
    if not queries:
        sys.exit("No queries provided. Use -q/--query and/or --queries-file.")
    return queries


def fetch_searches(client, queries, engine):
    rows = []
    for query in queries:
        results = client.search({"engine": engine, "q": query})
        for result in results.get("organic_results", []):
            rows.append({"query": query, **result})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("-q", "--query", action="append", help="A search query (repeatable)")
    parser.add_argument("--queries-file", help="Path to a text file with one query per line")
    parser.add_argument("--engine", default="google", help="SerpApi engine (default: google)")
    parser.add_argument("--api-key", default=os.getenv("SERPAPI_KEY"), help="SerpApi API key (default: $SERPAPI_KEY)")
    parser.add_argument("-o", "--output", default="searches.csv", help="Output CSV path (default: searches.csv)")
    args = parser.parse_args()

    if not args.api_key:
        sys.exit("No API key provided. Set SERPAPI_KEY or pass --api-key.")

    queries = load_queries(args)
    client = serpapi.Client(api_key=args.api_key)
    rows = fetch_searches(client, queries, args.engine)

    df = pd.DataFrame(rows)
    df.to_csv(args.output, index=False)
    print(f"Exported {len(df)} results from {len(queries)} search(es) to {args.output}")


if __name__ == "__main__":
    main()
