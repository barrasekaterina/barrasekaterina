"""Validates matcher.enrich.categorize_job_title against real-world titles
that surfaced a substring-matching bug: the bare "lo" keyword (meant to
catch the abbreviation "LO") matched anywhere inside a word, so titles
like "Unemployed" and "Head of Business Development" - both of which
happen to contain "lo" mid-word (unemp-LO-yed, deve-LO-pment) - were
wrongly classified as "Loan Officer". Also checks that fixing that
doesn't regress prefix/abbreviation matches that were previously relying
on the same loose substring behavior ("Loan Officer" itself via "lo",
"Events" via "event", "EVP"/"AVP" via "vp").
"""
import sys

sys.path.insert(0, "/home/user/barrasekaterina/tools/tradeshow-matcher")

from matcher.enrich import categorize_job_title  # noqa: E402

CASES = {
    "Unemployed": "Other",
    "Head of Business Development": "Other",
    "Loan Officer": "Loan Officer",
    "MLO": "Loan Officer",
    "LOAN PROCESSOR": "Processor",
    "AE": "Account Executive",
    "Account Executive": "Account Executive",
    "Events": "Non-Relevant",
    "Events Producer": "Non-Relevant",
    "EVP, National Sales": "Top Manager",
    "AVP, Community Lending Officer": "Top Manager",
    "VP, Regional Manager": "Top Manager",
    "Head of Broker Relations": "Managing Broker",
}

for title, expected in CASES.items():
    actual = categorize_job_title(title)
    assert actual == expected, f"{title!r}: expected {expected!r}, got {actual!r}"

print("ALL JOB-TITLE CATEGORY TESTS PASSED")
