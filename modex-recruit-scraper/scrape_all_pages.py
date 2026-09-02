#!/usr/bin/env python3
"""Fetch and parse EVERY page of a Modex Recruit results listing.

This walks the paginated listing (Loan Officers, Branches, Companies, ...)
page by page using your own logged-in session, and writes every parsed
record to a JSON-Lines file as it goes -- so you can stop and resume
without losing progress, and without holding 1M+ records in memory.

Auth
----
You must be logged into modex.com in your browser. Copy the request's
`Cookie` header (DevTools -> Network tab -> reload the page -> click the
request -> Headers -> Request Headers -> "cookie") and pass it with
--cookie, or save it to a text file and pass --cookie-file.

Pagination
----------
By default this requests:
    {url}?page={page}&per_page={per_page}
adjusted by --page-param / --per-page-param if the site uses different
query-string names. Click "Next" once in your browser with DevTools' Network
tab open and check the resulting URL/query-string to confirm the real
parameter names, then pass them here if they differ.

Examples
--------
    python scrape_all_pages.py \\
        --url "https://modex.com/recruit/loan-officers" \\
        --cookie-file cookie.txt \\
        --per-page 100 \\
        --output loan_officers.jsonl

    # Resume an interrupted run (same --output): it will pick up from the
    # last completed page automatically via the .checkpoint file.
"""

import argparse
import dataclasses
import json
import sys
import time
from pathlib import Path
from typing import Optional

import requests

from modex_parser import parse_page, parse_result_summary


def build_session(cookie: Optional[str], cookie_file: Optional[str], user_agent: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "text/html"})

    raw_cookie = cookie
    if cookie_file:
        raw_cookie = Path(cookie_file).read_text(encoding="utf-8").strip()
    if not raw_cookie:
        raise SystemExit("Provide --cookie or --cookie-file with your logged-in session cookie.")

    session.headers["Cookie"] = raw_cookie
    return session


def fetch_page(session: requests.Session, url: str, params: dict, retries: int, backoff: float) -> str:
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            response = session.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as exc:
            last_exc = exc
            wait = backoff * attempt
            print(f"  request failed ({exc}); retrying in {wait:.0f}s "
                  f"[{attempt}/{retries}]", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Giving up on {url} params={params}: {last_exc}")


def load_checkpoint(path: Path) -> int:
    if path.exists():
        return int(path.read_text(encoding="utf-8").strip() or 0)
    return 0


def save_checkpoint(path: Path, page: int) -> None:
    path.write_text(str(page), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", required=True, help="Listing URL, e.g. https://modex.com/recruit/loan-officers")
    parser.add_argument("--cookie", help="Raw 'Cookie' header value from your logged-in browser session")
    parser.add_argument("--cookie-file", help="Path to a text file containing the Cookie header value")
    parser.add_argument("--output", required=True, help="Output JSON-Lines file (one record per line)")
    parser.add_argument("--per-page", type=int, default=100, help="Results per page to request (default: 100)")
    parser.add_argument("--page-param", default="page", help="Query-string name for the page number")
    parser.add_argument("--per-page-param", default="per_page", help="Query-string name for page size")
    parser.add_argument("--extra-query", default="", help="Extra raw query string to append, e.g. 'sort=units'")
    parser.add_argument("--start-page", type=int, default=None, help="Override the resume point")
    parser.add_argument("--max-pages", type=int, default=None, help="Stop after this many pages (for testing)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds to sleep between requests (be polite)")
    parser.add_argument("--retries", type=int, default=4, help="Retries per page on network error")
    parser.add_argument("--backoff", type=float, default=5.0, help="Base seconds for retry backoff")
    parser.add_argument(
        "--user-agent",
        default="Mozilla/5.0 (compatible; internal-recruit-export/1.0)",
        help="User-Agent header to send",
    )
    args = parser.parse_args()

    session = build_session(args.cookie, args.cookie_file, args.user_agent)

    output_path = Path(args.output)
    checkpoint_path = output_path.with_suffix(output_path.suffix + ".checkpoint")
    start_page = args.start_page if args.start_page is not None else load_checkpoint(checkpoint_path) + 1
    if start_page > 1:
        print(f"Resuming from page {start_page} (checkpoint: {checkpoint_path})", file=sys.stderr)

    extra_query = dict(
        pair.split("=", 1) for pair in args.extra_query.split("&") if "=" in pair
    ) if args.extra_query else {}

    mode = "a" if start_page > 1 and output_path.exists() else "w"
    total_written = 0
    expected_total = None
    page = start_page

    with output_path.open(mode, encoding="utf-8") as out:
        while True:
            if args.max_pages is not None and (page - start_page) >= args.max_pages:
                print(f"Reached --max-pages limit ({args.max_pages}); stopping.", file=sys.stderr)
                break

            params = {args.page_param: page, args.per_page_param: args.per_page, **extra_query}
            html = fetch_page(session, args.url, params, args.retries, args.backoff)

            summary = parse_result_summary(html)
            if summary and expected_total is None:
                expected_total = summary["total"]
                print(f"Site reports {expected_total:,} total results.", file=sys.stderr)

            records = parse_page(html)
            if not records:
                print(f"Page {page} had no records; assuming end of results.", file=sys.stderr)
                break

            for record in records:
                out.write(json.dumps(dataclasses.asdict(record), ensure_ascii=False) + "\n")
            out.flush()
            total_written += len(records)
            save_checkpoint(checkpoint_path, page)

            progress = f" / {expected_total:,}" if expected_total else ""
            print(f"page {page}: +{len(records)} records (total written: {total_written:,}{progress})",
                  file=sys.stderr)

            if summary and summary["to"] >= summary["total"]:
                print("Reached the last page per the site's own count.", file=sys.stderr)
                break

            page += 1
            time.sleep(args.delay)

    print(f"Done. Wrote {total_written:,} records to {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
