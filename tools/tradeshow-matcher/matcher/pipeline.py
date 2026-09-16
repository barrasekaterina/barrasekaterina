"""End-to-end pipeline: tradeshow file + CRM exports -> enriched result table.

This is the single adaptive replacement for the notebook sequence
(convertion -> crm_data_contacts/leads -> tradeshow_matching ->
ml_matching_contacts/leads -> tradeshow_original_*_merge -> merged_entirely)
that used to be duplicated four times, once per field combination, with a
fifth notebook (tradeshow_bc_matching.ipynb) for business cards. That fifth
notebook and every BC merge step has no equivalent here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import enrich, loaders, matching

STATUS_COLORS = {
    "Duplicate": "8A2BE2",
    "Lead - Existing": "006400",
    "Contact - Unchecked": "FFA500",
    "Contact": "FFA500",
    "Bank/CU": "FFC0CB",
    "Position": "FFFF00",
    "New Contact": "87CEFA",
}

CRM_CONTACT_URL = "https://crm.admortgage.com/crm/contact/details/{id}/"
CRM_LEAD_URL = "https://crm.admortgage.com/crm/lead/details/{id}/"


@dataclass
class PipelineResult:
    detected_fields: list[str]
    table: pd.DataFrame
    summary: dict = field(default_factory=dict)


def _match_against(tradeshow: pd.DataFrame, crm: pd.DataFrame | None, fields: list[str], label: str):
    if crm is None or crm.empty:
        return None, None
    matched = matching.match_tradeshow_to_crm(tradeshow, crm, fields)
    aggregated = matching.aggregate_matches(matched, fields)
    return matched, aggregated


def run_pipeline(
    tradeshow_file,
    tradeshow_filename: str,
    crm_contacts_file=None,
    crm_leads_file=None,
    crm_contacts_df: pd.DataFrame | None = None,
    crm_leads_df: pd.DataFrame | None = None,
) -> PipelineResult:
    """Run the matcher. CRM contacts/leads can come from an uploaded CSV
    (crm_contacts_file / crm_leads_file) or from an already-standardized
    DataFrame (crm_contacts_df / crm_leads_df, e.g. from matcher.db plus
    loaders.standardize_db_contacts/leads) - the *_df arguments win if both
    are given for the same source.
    """
    tradeshow, detected_fields = loaders.load_tradeshow_file(tradeshow_file, tradeshow_filename)

    if crm_contacts_df is not None:
        crm_contacts = crm_contacts_df
    elif crm_contacts_file:
        crm_contacts = loaders.load_crm_contacts(crm_contacts_file)
    else:
        crm_contacts = None

    if crm_leads_df is not None:
        crm_leads = crm_leads_df
    elif crm_leads_file:
        crm_leads = loaders.load_crm_leads(crm_leads_file)
    else:
        crm_leads = None

    _, agg_contacts = _match_against(tradeshow, crm_contacts, detected_fields, "contacts")
    _, agg_leads = _match_against(tradeshow, crm_leads, detected_fields, "leads")

    result = tradeshow.copy()
    result["is_contact_match"] = False
    result["contact_full_match"] = False
    result["is_lead_match"] = False
    result["Contact CRM ID"] = ""
    result["Lead CRM ID"] = ""

    if agg_contacts is not None and not agg_contacts.empty:
        key = "Full Name_tradeshow"
        matched_names = set(agg_contacts[key])
        result["is_contact_match"] = result["Full Name"].isin(matched_names)
        full_match_names = set(
            agg_contacts.loc[agg_contacts["best_match_label"].str.contains("Name", na=False), key]
        )
        result["contact_full_match"] = result["Full Name"].isin(full_match_names)
        if "ID" in agg_contacts.columns:
            id_map = dict(zip(agg_contacts[key], agg_contacts["ID"]))
            result["Contact CRM ID"] = result["Full Name"].map(id_map).fillna("")

    if agg_leads is not None and not agg_leads.empty:
        key = "Full Name_tradeshow"
        matched_names = set(agg_leads[key])
        result["is_lead_match"] = result["Full Name"].isin(matched_names)
        if "ID" in agg_leads.columns:
            id_map = dict(zip(agg_leads[key], agg_leads["ID"]))
            result["Lead CRM ID"] = result["Full Name"].map(id_map).fillna("")

    crm_domains = enrich.crm_email_domains(crm_contacts) if crm_contacts is not None else set()
    result = enrich.enrich_and_score_status(
        result,
        has_contacts=crm_contacts is not None,
        has_leads=crm_leads is not None,
        crm_contacts_domains=crm_domains,
    )

    result["Contact CRM Link"] = result["Contact CRM ID"].apply(
        lambda i: CRM_CONTACT_URL.format(id=i) if i else ""
    )
    result["Lead CRM Link"] = result["Lead CRM ID"].apply(
        lambda i: CRM_LEAD_URL.format(id=i) if i else ""
    )

    display_cols = [
        "Status", "Full Name", "Company Name", "Phone", "Email", "Job Title",
        "Job_Category", "Banks and Credit Unions", "Duplicate", "New Contact",
        "Contact CRM Link", "Lead CRM Link",
    ]
    display_cols = [c for c in display_cols if c in result.columns]
    other_cols = [c for c in result.columns if c not in display_cols]
    result = result[display_cols + other_cols]

    summary = {
        "total_attendees": len(result),
        "matched_contacts": int(result["is_contact_match"].sum()),
        "matched_leads": int(result["is_lead_match"].sum()),
        "duplicates": int((result["Duplicate"] == "Duplicate").sum()),
        "new_contacts": int((result["New Contact"] == "New Contact").sum()),
        "personal_emails": int((result["New Contact"] == "personal_email").sum()),
    }

    return PipelineResult(detected_fields=detected_fields, table=result, summary=summary)


def write_excel(result: pd.DataFrame, out_path: str) -> None:
    from openpyxl.styles import PatternFill
    from openpyxl.worksheet.table import Table, TableStyleInfo

    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        result.to_excel(writer, index=False, sheet_name="Sheet1")
        sheet = writer.book["Sheet1"]

        for idx, row in result.reset_index(drop=True).iterrows():
            excel_row = idx + 2
            if row.get("Contact CRM Link"):
                col = result.columns.get_loc("Contact CRM Link") + 1
                sheet.cell(row=excel_row, column=col).hyperlink = row["Contact CRM Link"]
            if row.get("Lead CRM Link"):
                col = result.columns.get_loc("Lead CRM Link") + 1
                sheet.cell(row=excel_row, column=col).hyperlink = row["Lead CRM Link"]

        if "Status" in result.columns and len(result) > 0:
            status_col_idx = result.columns.get_loc("Status")
            for row in sheet.iter_rows(min_row=2, max_row=sheet.max_row):
                status_value = str(row[status_col_idx].value or "")
                tags = [t.strip() for t in status_value.split(";")]
                for tag, color in STATUS_COLORS.items():
                    if tag in tags or status_value == tag:
                        row[status_col_idx].fill = PatternFill(
                            start_color=color, end_color=color, fill_type="solid"
                        )
                        break

        table = Table(displayName="TradeshowMatches", ref=sheet.dimensions)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium9", showFirstColumn=False, showLastColumn=False,
            showRowStripes=True, showColumnStripes=True,
        )
        sheet.add_table(table)
