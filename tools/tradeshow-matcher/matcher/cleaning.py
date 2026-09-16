"""Shared cleaning helpers for tradeshow and CRM data.

Ported from the original notebooks (convertion.ipynb, crm_data_contacts.ipynb,
crm_data_leads.ipynb). Business-card (BC) handling is intentionally not present
anywhere in this module.
"""
from __future__ import annotations

import re

import pandas as pd

_SYMBOLS_TO_REMOVE = re.compile(r"[+\-() .]")
_EXT_PATTERN = re.compile(r"(?:ext|Ext|#)([^,]*)")
_EXT_STRIP_PATTERN = re.compile(r"(ext|Ext)[^,]*")
_HASH_STRIP_PATTERN = re.compile(r"#[^,]*")
_OFFICE_STRIP_PATTERN = re.compile(r"Office:[^,]*")


def clean_phone_series(phone: pd.Series) -> pd.Series:
    """Strip extensions/symbols and a leading country '1' from a phone column."""
    phone = phone.astype(str)
    phone = phone.str.replace(_EXT_STRIP_PATTERN, "", regex=True)
    phone = phone.str.replace(_HASH_STRIP_PATTERN, "", regex=True)
    phone = phone.str.replace(_OFFICE_STRIP_PATTERN, "", regex=True)

    def _clean_one(value: str) -> str:
        if pd.isna(value) or value.lower() == "nan":
            return ""
        return ", ".join(
            _SYMBOLS_TO_REMOVE.sub("", part.strip())
            for part in value.split(", ")
            if part.strip()
        )

    phone = phone.apply(_clean_one)

    def _strip_leading_one(value: str) -> str:
        if not isinstance(value, str):
            return value
        return value[1:] if value.startswith("1") else value

    return phone.apply(_strip_leading_one)


def extract_extension(phone: pd.Series) -> pd.Series:
    ext = phone.str.extract(_EXT_PATTERN)[0]
    return ext.apply(lambda x: f"Ext{x.strip()}" if pd.notna(x) else "")


def normalize_phone_set(phone_str: str) -> set[str]:
    """Extract the last-10-digit signature of every number in a comma list."""
    if not phone_str:
        return set()
    numbers = phone_str.replace(" ", "").split(",")
    cleaned: set[str] = set()
    for num in numbers:
        digits = re.sub(r"\D", "", num)
        if len(digits) >= 10:
            cleaned.add(digits[-10:])
    return cleaned


def split_full_name(full_name: str) -> tuple[str, str]:
    parts = str(full_name).strip().split()
    if len(parts) > 1:
        return parts[0], parts[-1]
    if len(parts) == 1:
        return parts[0], ""
    return "", ""


def build_full_name(first: pd.Series, last: pd.Series) -> pd.Series:
    first = first.fillna("").astype(str).str.lower()
    last = last.fillna("").astype(str).str.lower()
    return (first + " " + last).str.strip()


def combine_non_empty(df: pd.DataFrame, columns: list[str], sep: str = ", ") -> pd.Series:
    """Concatenate several columns (e.g. Work/Home/Other e-mail) skipping blanks."""
    existing = [c for c in columns if c in df.columns]
    if not existing:
        return pd.Series([""] * len(df), index=df.index)
    return df[existing].apply(
        lambda row: sep.join(
            str(x) for x in row if pd.notna(x) and str(x).strip() not in ("0", "")
        ),
        axis=1,
    )
