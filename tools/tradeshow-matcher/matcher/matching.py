"""Adaptive fuzzy matching of a tradeshow list against a CRM export.

This replaces the four separate ml_matching_*.ipynb notebooks (one per field
combination: name+email, name+company+phone, name+company+email,
name+company+phone+email). Instead of picking a notebook by hand, the field
combination present on the uploaded tradeshow file is detected once
(matcher.loaders.load_tradeshow_file) and used here to build the right
recordlinkage comparison on the fly. No business-card (BC) matching exists
in this path.
"""
from __future__ import annotations

import pandas as pd
import recordlinkage

# Thresholds mirror the values used across the original notebooks.
FIRST_NAME_THRESHOLD = 0.80
LAST_NAME_THRESHOLD = 0.85
COMPANY_THRESHOLD = 0.85
EMAIL_THRESHOLD = 0.95

# Stricter than COMPANY_THRESHOLD above: that threshold corroborates a
# specific person's identity (name already matched; company just adds
# confidence), where a same-ish-sounding company is an acceptable risk.
# This one instead answers "does this company already exist in CRM at
# all" with no person-match backing it up - at the scale of a full CRM
# export (thousands of unique companies), a looser threshold risks
# false positives between genuinely different companies ("First Choice
# Lending" vs "First Choice Mortgage"), wrongly implying an existing
# relationship where none exists.
NEW_CONTACT_COMPANY_THRESHOLD = 0.92

FIELD_LABELS = {
    "first_last_name_score": "Name",
    "company_score": "Company",
    "phone_score": "Phone",
    "email_score": "Email",
}


def match_tradeshow_to_crm(tradeshow: pd.DataFrame, crm: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    """Return one row per matched (tradeshow, crm) pair with score columns.

    `fields` is the subset of {"Company Name", "Phone", "Email"} that was
    detected on the tradeshow file. Name matching always participates.
    """
    tradeshow = tradeshow.copy()
    crm = crm.copy()

    from .cleaning import normalize_phone_set, safe_str_series

    for col in ["Full Name", "First Name", "Last Name", "Company Name", "Email"]:
        tradeshow[col] = safe_str_series(tradeshow[col])
        crm[col] = safe_str_series(crm[col])

    if "Phone" in fields:
        tradeshow["_phone_set"] = safe_str_series(tradeshow["Phone"]).apply(normalize_phone_set)
        crm["_phone_set"] = safe_str_series(crm["Phone"]).apply(normalize_phone_set)

    indexer = recordlinkage.Index()
    indexer.sortedneighbourhood("Full Name")
    candidate_links = indexer.index(tradeshow, crm)

    compare_cl = recordlinkage.Compare()
    compare_cl.string("First Name", "First Name", method="jarowinkler",
                       threshold=FIRST_NAME_THRESHOLD, label="first_name")
    compare_cl.string("Last Name", "Last Name", method="jarowinkler",
                       threshold=LAST_NAME_THRESHOLD, label="last_name")
    if "Company Name" in fields:
        compare_cl.string("Company Name", "Company Name", method="jarowinkler",
                           threshold=COMPANY_THRESHOLD, label="company_name")
    if "Email" in fields:
        compare_cl.string("Email", "Email", method="jarowinkler",
                           threshold=EMAIL_THRESHOLD, label="email")

    features = compare_cl.compute(candidate_links, tradeshow, crm)

    # Number of participating "slots": name always counts as one.
    slots = 1 + len(fields)
    weight = 1.0 / slots

    features["first_last_name_score"] = (
        features["first_name"] * (weight / 2) + features["last_name"] * (weight / 2)
    )

    if "Company Name" in fields:
        features["company_score"] = features["company_name"] * weight
    if "Phone" in fields:
        ts_idx = features.index.get_level_values(0)
        crm_idx = features.index.get_level_values(1)
        phone_hits = [
            1 if (tradeshow.loc[t, "_phone_set"] & crm.loc[c, "_phone_set"]) else 0
            for t, c in zip(ts_idx, crm_idx)
        ]
        features["phone_score"] = pd.Series(phone_hits, index=features.index) * weight
    if "Email" in fields:
        ts_idx = features.index.get_level_values(0)
        crm_idx = features.index.get_level_values(1)
        email_hits = [
            1 if tradeshow.loc[t, "Email"].lower() == crm.loc[c, "Email"].lower() and tradeshow.loc[t, "Email"]
            else 0
            for t, c in zip(ts_idx, crm_idx)
        ]
        features["email_score"] = pd.Series(email_hits, index=features.index) * weight

    score_cols = ["first_last_name_score"] + [
        f"{f.lower().replace(' name', '').strip()}_score" for f in fields
    ]
    features["total_score"] = features[score_cols].sum(axis=1)
    features = features[features["total_score"] > 0]

    # Keep only matches where the full name matched AND at least one other
    # supporting field also hit its max score - mirrors the filter condition
    # used in every ml_matching_*.ipynb variant.
    name_hit = features["first_last_name_score"].round(6) == round(weight, 6)
    other_cols = [c for c in score_cols if c != "first_last_name_score"]
    other_hit = pd.Series(False, index=features.index)
    for col in other_cols:
        other_hit = other_hit | (features[col].round(6) == round(weight, 6))
    features = features[name_hit & (other_hit if other_cols else True)]

    features["match_percentage"] = features["total_score"] * 100
    features["best_match"] = features[score_cols].idxmax(axis=1)
    labels = {
        "first_last_name_score": "Name Match",
        "company_score": "Company Match",
        "phone_score": "Phone Match",
        "email_score": "Email Match",
    }
    features["best_match_label"] = features["best_match"].map(labels)

    # Every field that actually hit its max score, not just the single
    # best one - e.g. "Name, Phone" - so callers can grade match
    # confidence by which *kind* of evidence backed a match (an exact
    # identifier like Phone/Email vs. fuzzy text like Name/Company alone).
    def matched_fields_str(row) -> str:
        hits = [FIELD_LABELS[c] for c in score_cols if round(row[c], 6) == round(weight, 6)]
        return ", ".join(hits)

    features["matched_fields"] = features.apply(matched_fields_str, axis=1)

    features = features.reset_index()
    features = features.rename(columns={"level_0": "tradeshow_index", "level_1": "crm_index"})

    matched = features.merge(tradeshow.drop(columns=["_phone_set"], errors="ignore"),
                              left_on="tradeshow_index", right_index=True)
    matched = matched.merge(crm.drop(columns=["_phone_set"], errors="ignore"),
                             left_on="crm_index", right_index=True, suffixes=("_tradeshow", "_crm"))
    matched = matched.sort_values(by=["tradeshow_index", "total_score"], ascending=[True, False])
    return matched


def find_known_companies(unmatched: pd.DataFrame, known_companies: pd.DataFrame) -> pd.Series:
    """For attendees with no CRM Contact/Lead match at all, check whether
    their Company Name already exists among every unique company seen in
    CRM Contacts + Leads combined - i.e. is this a *known account*, even
    though this particular person isn't in CRM yet?

    `unmatched` needs a "Company Name" column (blank is fine - those rows
    just can't be checked and come back False). `known_companies` needs a
    "Company Name" column of every unique company name from CRM Contacts
    and CRM Leads. Uses the same sortedneighbourhood blocking as the main
    name-matching above rather than a full cross-product, since a real CRM
    export can carry thousands of unique company names - comparing every
    unmatched attendee against every one of them individually would be
    far slower than blocking first.

    Returns a boolean Series aligned to unmatched.index.
    """
    from .cleaning import safe_str_series

    result = pd.Series(False, index=unmatched.index)
    if known_companies.empty:
        return result

    unmatched = unmatched.copy()
    known_companies = known_companies.copy()
    unmatched["Company Name"] = safe_str_series(unmatched["Company Name"]).str.lower().str.strip()
    known_companies["Company Name"] = safe_str_series(known_companies["Company Name"]).str.lower().str.strip()

    has_company = unmatched["Company Name"] != ""
    if not has_company.any():
        return result
    checkable = unmatched[has_company]

    indexer = recordlinkage.Index()
    indexer.sortedneighbourhood("Company Name")
    candidate_links = indexer.index(checkable, known_companies)
    if len(candidate_links) == 0:
        return result

    compare_cl = recordlinkage.Compare()
    compare_cl.string("Company Name", "Company Name", method="jarowinkler",
                       threshold=NEW_CONTACT_COMPANY_THRESHOLD, label="company")
    features = compare_cl.compute(candidate_links, checkable, known_companies)
    matched_idx = features[features["company"] > 0].index.get_level_values(0).unique()
    result.loc[matched_idx] = True
    return result


def aggregate_matches(matched: pd.DataFrame, fields: list[str]) -> pd.DataFrame:
    """Collapse duplicate matches per tradeshow attendee (groupby + join with '; ')."""
    if matched.empty:
        return matched

    group_cols = ["Full Name_tradeshow"]
    if "Company Name" in fields:
        group_cols.append("Company Name_tradeshow")
    if "Phone" in fields:
        group_cols.append("Phone_tradeshow")
    if "Email" in fields:
        group_cols.append("Email_tradeshow")

    return (
        matched.groupby(group_cols)
        .agg(lambda x: "; ".join(x.astype(str).unique()))
        .reset_index()
    )
