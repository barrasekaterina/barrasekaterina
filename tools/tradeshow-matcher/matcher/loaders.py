"""Load and standardize the tradeshow list and the two CRM exports.

Only two source kinds are recognized: a tradeshow attendee list, and the CRM
exports (contacts / leads). There is no business-card (BC) input path here —
that source has been dropped entirely.
"""
from __future__ import annotations

import io

import pandas as pd

from . import cleaning

# Column-name aliases -> canonical name, checked case-insensitively.
TRADESHOW_ALIASES = {
    "full name": "Full Name",
    "name": "Full Name",
    "attendee name": "Full Name",
    "contact name": "Full Name",
    "company name": "Company Name",
    "company": "Company Name",
    "organization": "Company Name",
    "employer": "Company Name",
    "phone": "Phone",
    "phone number": "Phone",
    "mobile": "Phone",
    "mobile phone": "Phone",
    "cell": "Phone",
    "telephone": "Phone",
    "email": "Email",
    "e-mail": "Email",
    "email address": "Email",
    "job title": "Job Title",
    "title": "Job Title",
    "position": "Job Title",
}

# The optional fields a tradeshow file may carry alongside the required Full Name.
OPTIONAL_MATCH_FIELDS = ["Company Name", "Phone", "Email"]


def _read_any(file_obj, filename: str) -> pd.DataFrame:
    lowered = filename.lower()
    if lowered.endswith(".csv"):
        return pd.read_csv(file_obj, dtype=str, low_memory=False)
    if lowered.endswith((".xlsx", ".xls")):
        return pd.read_excel(file_obj, dtype=str)
    raise ValueError(f"Unsupported file type: {filename}")


def _rename_with_aliases(df: pd.DataFrame, aliases: dict[str, str]) -> pd.DataFrame:
    rename_map = {}
    for col in df.columns:
        canonical = aliases.get(str(col).strip().lower())
        if canonical:
            rename_map[col] = canonical
    return df.rename(columns=rename_map)


def load_tradeshow_file(file_obj, filename: str) -> tuple[pd.DataFrame, list[str]]:
    """Load a tradeshow attendee list and return (cleaned_df, detected_optional_fields).

    Detection is purely based on which optional columns (Company Name, Phone,
    Email) are present and contain at least one non-empty value - this is
    what lets a single tool auto-recognize any of the four combinations the
    original notebooks each hard-coded (name+email, name+company+phone,
    name+company+email, name+company+phone+email).
    """
    raw = _read_any(file_obj, filename)
    df = _rename_with_aliases(raw, TRADESHOW_ALIASES)

    if "Full Name" not in df.columns:
        raise ValueError(
            "Could not find a 'Full Name' column in the tradeshow file. "
            f"Columns found: {list(raw.columns)}"
        )

    df["Full Name"] = df["Full Name"].astype(str).str.strip()
    first, last = zip(*df["Full Name"].apply(cleaning.split_full_name))
    df["First Name"] = [f.lower() for f in first]
    df["Last Name"] = [l.lower() for l in last]
    df["Full Name"] = cleaning.build_full_name(pd.Series(first), pd.Series(last))

    detected = []
    for field in OPTIONAL_MATCH_FIELDS:
        if field in df.columns and df[field].fillna("").astype(str).str.strip().ne("").any():
            detected.append(field)
        elif field not in df.columns:
            df[field] = ""

    if "Email" in detected:
        df["Email"] = df["Email"].astype(str).str.strip().str.lower()
    if "Phone" in detected:
        df["Extension"] = cleaning.extract_extension(df["Phone"].astype(str))
        df["Phone"] = cleaning.clean_phone_series(df["Phone"])
    else:
        df["Extension"] = ""
    if "Company Name" in detected:
        df["Company Name"] = df["Company Name"].astype(str).str.strip()

    if "Job Title" not in df.columns:
        df["Job Title"] = ""

    return df, detected


_CONTACT_EMAIL_COLS = ["Work E-mail", "Home E-mail", "Other E-mail"]
_CONTACT_PHONE_COLS = ["Work Phone", "Mobile", "Fax", "Home Phone", "Other Phone Number"]


def load_crm_contacts(file_obj) -> pd.DataFrame:
    raw = pd.read_csv(file_obj, sep=";", dtype=str, low_memory=False)
    df = raw.copy()

    for col in _CONTACT_EMAIL_COLS:
        if col in df.columns:
            df[col] = df[col].str.lower()

    df["Email"] = cleaning.combine_non_empty(df, _CONTACT_EMAIL_COLS)
    df["Phone"] = cleaning.combine_non_empty(df, _CONTACT_PHONE_COLS)

    first = df.get("First Name", pd.Series([""] * len(df))).fillna("")
    last = df.get("Last Name", pd.Series([""] * len(df))).fillna("")
    df["First Name"] = first.str.split(" ").str[0].str.lower()
    df["Last Name"] = last.str.split(" ").str[-1].str.lower()
    df["Full Name"] = cleaning.build_full_name(df["First Name"], df["Last Name"])

    df["Extension"] = cleaning.extract_extension(df["Phone"])
    df["Phone"] = cleaning.clean_phone_series(df["Phone"])

    df = df.rename(
        columns={
            "Company": "Company Name",
            "Company NMLS": "Company_NMLS",
            "MLO’s NMLS": "MLO_NMLS",
            "MLO's NMLS": "MLO_NMLS",
        }
    )
    if "Company Name" not in df.columns:
        df["Company Name"] = ""
    if "MLO_NMLS" not in df.columns:
        df["MLO_NMLS"] = ""
    if "Responsible" not in df.columns:
        df["Responsible"] = ""
    if "Status" not in df.columns:
        df["Status"] = ""

    keep = [
        "First Name", "Last Name", "Full Name", "Status", "Company Name",
        "Responsible", "Phone", "Email", "Extension", "Company_NMLS",
        "MLO_NMLS", "ID",
    ]
    keep = [c for c in keep if c in df.columns]
    return df[keep]


_LEAD_EMAIL_COLS = ["Work E-mail", "Home E-mail", "Other E-mail"]
_LEAD_PHONE_COLS = ["Work Phone", "Mobile", "Fax", "Home Phone", "Other Phone Number"]


def load_crm_leads(file_obj) -> pd.DataFrame:
    raw = pd.read_csv(file_obj, sep=";", dtype=str, low_memory=False)
    df = raw.copy()

    for col in _LEAD_EMAIL_COLS:
        if col in df.columns:
            df[col] = df[col].str.lower()

    df["Email"] = cleaning.combine_non_empty(df, _LEAD_EMAIL_COLS)
    df["Phone"] = cleaning.combine_non_empty(df, _LEAD_PHONE_COLS)

    lead_name = df.get("Lead Name", pd.Series([""] * len(df))).fillna("")
    first = lead_name.str.split().str[0].fillna("").astype(str)
    last = lead_name.str.split().str[-1].fillna("").astype(str)
    df["Full Name"] = cleaning.build_full_name(first, last)
    df["First Name"] = first.str.lower()
    df["Last Name"] = last.str.lower()

    df["Extension"] = cleaning.extract_extension(df["Phone"])
    df["Phone"] = cleaning.clean_phone_series(df["Phone"])

    df = df.rename(
        columns={
            "Lead Companies": "Company Name",
            "Company NMLS": "Company_NMLS",
            "NMLS MLOs": "MLO_NMLS",
        }
    )
    for col in ("Company Name", "MLO_NMLS", "Responsible", "Stage",
                "Additional Lead Type", "Lead Type", "Source"):
        if col not in df.columns:
            df[col] = ""

    keep = [
        "First Name", "Last Name", "Full Name", "Company Name", "Responsible",
        "Phone", "Email", "Extension", "Company_NMLS", "MLO_NMLS", "Stage",
        "Additional Lead Type", "Lead Type", "Source", "ID",
    ]
    keep = [c for c in keep if c in df.columns]
    return df[keep]


def _col(df: pd.DataFrame, name: str) -> pd.Series:
    """Fetch a column as a string Series, or an all-empty Series if absent."""
    if name in df.columns:
        return df[name].fillna("").astype(str)
    return pd.Series([""] * len(df), index=df.index)


def standardize_db_contacts(df: pd.DataFrame) -> pd.DataFrame:
    """Map matcher.db.fetch_contacts() output onto the standard contacts schema."""
    df = df.copy()
    df["Email"] = _col(df, "sEmail").str.lower()
    df["Phone"] = _col(df, "sPhone")
    df["Extension"] = cleaning.extract_extension(df["Phone"].astype(str))
    df["Phone"] = cleaning.clean_phone_series(df["Phone"])

    first = _col(df, "First_Name")
    last = _col(df, "Last_Name")
    df["Full Name"] = cleaning.build_full_name(first, last)
    df["First Name"] = first.str.split(" ").str[0].str.lower()
    df["Last Name"] = last.str.split(" ").str[-1].str.lower()

    df["Company Name"] = _col(df, "CompanyName")
    df["Company_NMLS"] = _col(df, "iCompany_NMLS")
    df["MLO_NMLS"] = _col(df, "iBitrix_Contact_NMLS")
    df["Status"] = _col(df, "ContactStatus")
    df["Responsible"] = (_col(df, "AE_First_Name") + " " + _col(df, "AE_Last_Name")).str.strip()
    df["ID"] = _col(df, "iBitrix_Contact_ID")

    keep = [
        "First Name", "Last Name", "Full Name", "Status", "Company Name",
        "Responsible", "Phone", "Email", "Extension", "Company_NMLS",
        "MLO_NMLS", "ID",
    ]
    return df[keep]


def standardize_db_leads(df: pd.DataFrame) -> pd.DataFrame:
    """Map matcher.db.fetch_leads() output onto the standard leads schema."""
    df = df.copy()
    df["Email"] = _col(df, "Email").str.lower()
    df["Phone"] = _col(df, "Phone")
    df["Extension"] = cleaning.extract_extension(df["Phone"].astype(str))
    df["Phone"] = cleaning.clean_phone_series(df["Phone"])

    lead_name = _col(df, "TITLE")
    first = lead_name.str.split().str[0].fillna("").astype(str)
    last = lead_name.str.split().str[-1].fillna("").astype(str)
    df["Full Name"] = cleaning.build_full_name(first, last)
    df["First Name"] = first.str.lower()
    df["Last Name"] = last.str.lower()

    df["Company Name"] = _col(df, "COMPANY_TITLE")
    df["Company_NMLS"] = _col(df, "COMPANY_NMLS")
    df["MLO_NMLS"] = _col(df, "MLO_NMLS")
    df["Responsible"] = _col(df, "AE")
    df["Stage"] = _col(df, "STAGE")
    df["ID"] = _col(df, "LEAD_ID")
    for col in ("Additional Lead Type", "Lead Type", "Source"):
        df[col] = ""

    keep = [
        "First Name", "Last Name", "Full Name", "Company Name", "Responsible",
        "Phone", "Email", "Extension", "Company_NMLS", "MLO_NMLS", "Stage",
        "Additional Lead Type", "Lead Type", "Source", "ID",
    ]
    return df[keep]
