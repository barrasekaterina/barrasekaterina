"""Post-match enrichment: job title category, bank/credit-union tag,
duplicate flag, new/personal-email domain check, and the final Status column.

Ported from merged_entirely.ipynb. The original notebook also had an
(already-disabled, "raw") business-card cross-check and a "BC" status tag -
neither exists here; this tool has no business-card input at all.
"""
from __future__ import annotations

import re

import pandas as pd

from .cleaning import safe_str_series

JOB_TITLE_CATEGORIES: dict[str, list[str]] = {
    "Owner/ CEO/ President": [
        "owner", "ceo", "president", "co-founder", "cofounder",
        "managing partner", "founder",
    ],
    "Managing Broker": ["broker"],
    "Top Manager": [
        "coo", "director", "vp", "evp", "avp", "svp", "vice",
        "managing member", "team leader", "cfo",
    ],
    "Branch Manager": ["branch manager", "regional manager", "branch mgr"],
    "Processor": ["processor"],
    "Account Executive": [
        "business development manager", "business development regional mgr",
        "business development representative", "account executive", "ae",
        "acct exec",
    ],
    "Loan Officer": [
        "lo", "mlo", "loan advisor", "loan originator", "loan consultant",
        "senior mlo", "senior loan officer", "rmlo", "mortgage originator",
        "mortgage consultant", "originator", "mortgage planner",
        "mortgage advisor", "senior mortgage advisor",
    ],
    "Real Estate Agent": ["real estate agent", "realtor", "agent"],
    "Non-Relevant": [
        "event", "marketing", "sales rep", "assistant", "principal",
        "unknown", "recruiter", "project manager", "sales manager", "admin",
        "office manager", "escrow officer", "sales leader", "representative",
    ],
}

PERSONAL_EMAIL_DOMAINS = [
    "gmail", "yahoo", "outlook", "hotmail", "aol", "icloud", "live", "mail",
    "msn", "yandex", "protonmail", "zoho", "gmx", "comcast", "verizon",
    "btinternet", "me.com", "mac", "mail.ru", "inbox", "rocketmail", "ymail",
    "fastmail", "tutanota", "hushmail", "seznam", "rambler", "libero",
    "alice", "sfr", "att", "bellsouth", "earthlink", "netzero", "juno",
]


def categorize_job_title(title: str) -> str:
    """Require a word boundary before each keyword (not a raw substring
    check) - a plain "in" check lets short keywords like "lo" match inside
    unrelated words ("Unemployed", "Head of Business Development" both
    contain "lo" mid-word, e.g. deve-LO-pment) and misclassify them. No
    boundary is required *after* the keyword, so intentional prefix
    matches keep working ("event" still matches "Events", "lo" still
    matches "Loan Officer" since that "lo" starts a word)."""
    title = str(title).lower()
    for category, keywords in JOB_TITLE_CATEGORIES.items():
        for keyword in keywords:
            if re.search(rf"\b{re.escape(keyword)}", title):
                return category
    return "Other"


def label_bank_credit_union(organization: str) -> str | None:
    org = str(organization or "").lower()
    if "credit union" in org or " uc " in org:
        return "Bank/CU"
    if "bank" in org and "credit union" not in org and " uc " not in org:
        return "Bank/CU"
    return None


def assign_domain_flag(email_domain: str, crm_domains: set[str]) -> str:
    if not isinstance(email_domain, str) or not email_domain:
        return ""
    if any(personal in email_domain for personal in PERSONAL_EMAIL_DOMAINS):
        return "personal_email"
    if email_domain in crm_domains:
        return "Existing Domain"
    return ""


def crm_email_domains(crm_df: pd.DataFrame) -> set[str]:
    emails = safe_str_series(crm_df["Email"]).str.lower()
    domains = emails.str.extract(r"@([^.]+)")[0]
    return set(domains.dropna())


def enrich_and_score_status(
    merged: pd.DataFrame,
    crm_contacts_domains: set[str],
    company_known: pd.Series,
) -> pd.DataFrame:
    """Attach Job_Category, Banks and Credit Unions, Duplicate, Existing
    Domain / personal_email, and the composite Status column.

    `company_known` is a boolean Series (aligned to `merged`.index) saying
    whether an attendee's Company Name was found among every company seen
    in CRM Contacts + Leads combined (matcher.matching.find_known_companies)
    - only meaningful for attendees with no CRM Contact/Lead match at all;
    it's what tells New Contact (known company, new person) apart from
    New Lead (company not in CRM either)."""
    df = merged.copy()

    if "Job Title" in df.columns:
        df["Job_Category"] = safe_str_series(df["Job Title"]).apply(categorize_job_title)
    else:
        df["Job_Category"] = ""

    if "Company Name" in df.columns:
        df["Banks and Credit Unions"] = df["Company Name"].apply(label_bank_credit_union)
    else:
        df["Banks and Credit Unions"] = None

    df["Duplicate"] = df.duplicated("Full Name", keep=False).map(
        lambda dup: "Duplicate" if dup else None
    )

    if "Email" in df.columns:
        df["domain_tradeshow"] = safe_str_series(df["Email"]).str.lower().str.extract(r"@([^.]+)")[0]
        df["Existing Domain"] = df["domain_tradeshow"].apply(
            lambda d: assign_domain_flag(d, crm_contacts_domains)
        )
    else:
        df["Existing Domain"] = ""

    df["_company_known"] = company_known.reindex(df.index, fill_value=False)

    def base_status(row) -> str:
        if row.get("is_contact_match"):
            return "Existing Contact"
        if row.get("is_lead_match"):
            return "Existing Lead"
        return "New Contact" if row.get("_company_known") else "New Lead"

    df["Status"] = df.apply(base_status, axis=1)

    def append_tag(row, condition, tag):
        if condition(row):
            return f"{row['Status']}; {tag}" if row["Status"] else tag
        return row["Status"]

    # Existing Contact wins the base status even when the same attendee
    # also matched a Lead - flag that overlap rather than silently
    # dropping the Lead match info (Found in Leads/Found in CRM still
    # show it too, but this keeps it visible on Status at a glance).
    df["Status"] = df.apply(
        lambda r: append_tag(r, lambda row: row.get("is_contact_match") and row.get("is_lead_match"),
                              "Also a Lead"),
        axis=1,
    )
    df["Status"] = df.apply(
        lambda r: append_tag(r, lambda row: row.get("Job_Category") == "Non-Relevant", "Position"), axis=1
    )
    df["Status"] = df.apply(
        lambda r: append_tag(r, lambda row: row.get("Job_Category") == "Account Executive", "Position"), axis=1
    )
    df["Status"] = df.apply(
        lambda r: append_tag(r, lambda row: row.get("Banks and Credit Unions") == "Bank/CU", "Bank/CU"), axis=1
    )
    df["Status"] = df.apply(
        lambda r: append_tag(r, lambda row: row.get("Existing Domain") == "Existing Domain", "Existing Domain"),
        axis=1,
    )
    df["Status"] = df.apply(
        lambda r: append_tag(r, lambda row: row.get("Existing Domain") == "personal_email", "personal_email"),
        axis=1,
    )
    df["Status"] = df.apply(
        lambda r: append_tag(r, lambda row: row.get("Duplicate") == "Duplicate", "Duplicate"), axis=1
    )

    df = df.drop(columns=["_company_known"])
    return df
