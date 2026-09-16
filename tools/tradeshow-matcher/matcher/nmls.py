"""Optional live enrichment: given a set of individual NMLS IDs (the
MLO_NMLS values already pulled from CRM Contacts/Leads), look up each
person's current "Authorized to Represent" location in the NMLS database
and resolve that location's name via the Company or Branch table.

This is a *scoped* rewrite of a bulk reporting script that processes the
entire dbo.Individual table (hundreds of thousands of rows) to build an
offline reference export. Running that per web request would be far too
slow, so every query here is filtered to just the IndividualNMLSIDs the
caller actually asks about via SQL "IN (...)" - typically the handful to
few hundred MLO_NMLS values that matched in one tradeshow run.

Business logic (RegulationType, LicensingStatus, "Authorized to Represent"
location resolution, active-entity gating) is ported as closely as
possible from the original script. One deliberate simplification: the
original kept every currently-represented location per individual, joined
into a comma-separated string; this version keeps only the single most
recent one; call sites here want one company/branch name per attendee,
not a compliance-report-style full history.

Connects to a different server (p-nmls-db01.admortgage.com / NMLS
database) than the CRM database, via Windows Integrated Auth same as
matcher/db.py, so it needs network access to that server plus the ODBC
Driver 17 - not available in this sandbox, so only exercised here against
a mocked shape (see sample_data/smoke_test_nmls.py), not a live database.
The Company/Branch "Name" column name is taken on faith from how this
feature was requested - if that's wrong, the SQL error will name the
missing column and it's a one-line fix.
"""
from __future__ import annotations

import os

import pandas as pd

from .cleaning import safe_str_series

# Active license statuses per the NMLS B2B Data Specification.
ACTIVE_LICENSE_STATUSES = {
    "Approved",
    "Approved-Inactive",
    "Approved-Surrender/Cancellation Requested",
    "Temporary Cease and Desist",
    "Revoked-On Appeal",
    "Suspended",
    "Suspended-On Appeal",
}

ENRICHMENT_COLUMNS = [
    "IndividualNMLSID", "RegulationType", "LicensingStatus",
    "LocationNMLSID", "LocationType", "OwningCompanyNMLSID", "LocationName",
]

_BATCH_SIZE = 500  # keeps well under SQL Server's ~2100 parameter limit


def _connection_string(server: str, database: str) -> str:
    return (
        "DRIVER={ODBC Driver 17 for SQL Server};"
        f"SERVER={server};"
        f"DATABASE={database};"
        "Trusted_Connection=yes;"
        "TrustServerCertificate=yes;"
    )


def _placeholders(n: int) -> str:
    return ",".join("?" for _ in range(n))


def _clean_ids(individual_nmls_ids) -> list[int]:
    out = set()
    for x in individual_nmls_ids:
        if x is None:
            continue
        s = str(x).strip()
        if not s or s.lower() in ("nan", "<na>", "none"):
            continue
        try:
            out.add(int(float(s)))
        except ValueError:
            continue
    return sorted(out)


def _read_scoped(conn, sql: str, id_column_position_ids: list[int]) -> pd.DataFrame:
    """Run `sql` (with one "IN ({placeholders})" already filled in) against
    every batch of ids, concatenating the results."""
    frames = []
    for start in range(0, len(id_column_position_ids), _BATCH_SIZE):
        batch = id_column_position_ids[start:start + _BATCH_SIZE]
        placeholders = _placeholders(len(batch))
        frames.append(pd.read_sql(sql.format(placeholders=placeholders), conn, params=batch))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def fetch_nmls_enrichment(
    individual_nmls_ids,
    server: str | None = None,
    database: str = "NMLS",
) -> pd.DataFrame:
    """Return one row per requested IndividualNMLSID that NMLS knows about,
    with RegulationType, LicensingStatus, and the name of the company or
    branch they're currently authorized to represent."""
    import pyodbc  # imported lazily: optional dependency, only needed for this path

    ids = _clean_ids(individual_nmls_ids)
    if not ids:
        return pd.DataFrame(columns=ENRICHMENT_COLUMNS)

    server = server or os.environ.get("NMLS_DB_SERVER", "p-nmls-db01.admortgage.com")
    conn_str = _connection_string(server, database)

    with pyodbc.connect(conn_str) as conn:
        df_individual = _read_scoped(
            conn,
            "SELECT DISTINCT IndividualNMLSID FROM dbo.Individual "
            "WHERE IsDeleted = 0 AND IndividualNMLSID IN ({placeholders})",
            ids,
        )
        if df_individual.empty:
            return pd.DataFrame(columns=ENRICHMENT_COLUMNS)
        df_individual["IndividualNMLSID"] = pd.to_numeric(
            df_individual["IndividualNMLSID"], errors="coerce"
        ).astype("Int64")
        df_individual = df_individual.dropna(subset=["IndividualNMLSID"]).drop_duplicates()
        known_ids = df_individual["IndividualNMLSID"].astype("int64").tolist()

        # -- Regulation type + licensing status -----------------------------
        df_state_all = _read_scoped(
            conn,
            "SELECT DISTINCT IndividualNMLSID FROM dbo.IndividualLicense "
            "WHERE IsDeleted = 0 AND IndividualNMLSID IN ({placeholders})",
            known_ids,
        )
        state_ids = set(pd.to_numeric(df_state_all.get("IndividualNMLSID", pd.Series(dtype="object")),
                                       errors="coerce").dropna().astype("int64"))

        df_state_active = _read_scoped(
            conn,
            "SELECT DISTINCT IndividualNMLSID FROM dbo.IndividualLicense "
            "WHERE IsDeleted = 0 AND LOWER(LTRIM(RTRIM(IsAuthorized))) = 'yes' "
            "AND IndividualNMLSID IN ({placeholders})",
            known_ids,
        )
        active_state_ids = set(pd.to_numeric(
            df_state_active.get("IndividualNMLSID", pd.Series(dtype="object")),
            errors="coerce").dropna().astype("int64"))

        df_federal_all = _read_scoped(
            conn,
            "SELECT DISTINCT IndividualNMLSID FROM dbo.IndividualRegistration "
            "WHERE IsDeleted = 0 AND IndividualNMLSID IN ({placeholders})",
            known_ids,
        )
        federal_ids = set(pd.to_numeric(
            df_federal_all.get("IndividualNMLSID", pd.Series(dtype="object")),
            errors="coerce").dropna().astype("int64"))

        df_federal_active = _read_scoped(
            conn,
            "SELECT DISTINCT IndividualNMLSID FROM dbo.IndividualRegistration "
            "WHERE IsDeleted = 0 AND LOWER(LTRIM(RTRIM(AuthorizedToConductBusiness))) = 'yes' "
            "AND IndividualNMLSID IN ({placeholders})",
            known_ids,
        )
        active_federal_ids = set(pd.to_numeric(
            df_federal_active.get("IndividualNMLSID", pd.Series(dtype="object")),
            errors="coerce").dropna().astype("int64"))

        def regulation_type(nmls_id: int) -> str:
            in_state, in_federal = nmls_id in state_ids, nmls_id in federal_ids
            if in_state and in_federal:
                return "Dual"
            if in_state:
                return "State-Licensed"
            if in_federal:
                return "Federally Registered"
            return "None"

        def licensing_status(nmls_id: int) -> str:
            return "Active" if (nmls_id in active_state_ids or nmls_id in active_federal_ids) else "Inactive"

        df_individual["RegulationType"] = df_individual["IndividualNMLSID"].astype("int64").apply(regulation_type)
        df_individual["LicensingStatus"] = df_individual["IndividualNMLSID"].astype("int64").apply(licensing_status)

        # -- Authorized-to-Represent (current sponsorship / registration) --
        df_rep_state = _read_scoped(
            conn,
            "SELECT DISTINCT IndividualNMLSID, CompanyNMLSID FROM dbo.IndividualSponsorship "
            "WHERE IsDeleted = 0 AND (EndDate IS NULL OR EndDate = '19000101') "
            "AND IndividualNMLSID IN ({placeholders})",
            known_ids,
        )
        df_rep_fed = _read_scoped(
            conn,
            "SELECT DISTINCT IndividualNMLSID, InstitutionNMLSID AS CompanyNMLSID "
            "FROM dbo.IndividualRegistrationDetail "
            "WHERE IsDeleted = 0 AND (EndDate IS NULL OR EndDate = '19000101') "
            "AND IndividualNMLSID IN ({placeholders})",
            known_ids,
        )
        df_rep = pd.concat([df_rep_state, df_rep_fed], ignore_index=True)
        if not df_rep.empty:
            df_rep["IndividualNMLSID"] = pd.to_numeric(df_rep["IndividualNMLSID"], errors="coerce").astype("Int64")
            df_rep["CompanyNMLSID"] = pd.to_numeric(df_rep["CompanyNMLSID"], errors="coerce").astype("Int64")
            df_rep = df_rep.dropna(subset=["IndividualNMLSID", "CompanyNMLSID"]).drop_duplicates()

        # -- Individual locations (Main / Branch / Work) --------------------
        df_loc = _read_scoped(
            conn,
            "SELECT IndividualNMLSID, LocationNMLSID, LocationType, StartDate "
            "FROM dbo.IndividualLocation "
            "WHERE IsDeleted = 0 AND LocationType IN ('Main', 'Branch', 'Work') "
            "AND IndividualNMLSID IN ({placeholders})",
            known_ids,
        )
        if df_loc.empty or df_rep.empty:
            return _finalize(df_individual, pd.DataFrame(), {}, {})

        df_loc["IndividualNMLSID"] = pd.to_numeric(df_loc["IndividualNMLSID"], errors="coerce").astype("Int64")
        df_loc["LocationNMLSID"] = pd.to_numeric(df_loc["LocationNMLSID"], errors="coerce").astype("Int64")
        df_loc = df_loc.dropna(subset=["IndividualNMLSID", "LocationNMLSID"])
        df_loc = (
            df_loc.sort_values("StartDate", ascending=False)
            .drop_duplicates(subset=["IndividualNMLSID", "LocationNMLSID", "LocationType"], keep="first")
        )

        # -- Branch -> parent company, and branch names ----------------------
        branch_location_ids = df_loc.loc[df_loc["LocationType"] == "Branch", "LocationNMLSID"].astype("int64").unique().tolist()
        df_branch_tbl = _read_scoped(
            conn,
            "SELECT BranchNMLSID, CompanyNMLSID, IsAuthorized, Name "
            "FROM dbo.Branch WHERE IsDeleted = 0 AND BranchNMLSID IN ({placeholders})",
            branch_location_ids,
        ) if branch_location_ids else pd.DataFrame(columns=["BranchNMLSID", "CompanyNMLSID", "IsAuthorized", "Name"])

        branch_parent: dict[int, int] = {}
        branch_name: dict[int, str] = {}
        active_branch_ids: set[int] = set()
        if not df_branch_tbl.empty:
            df_branch_tbl["BranchNMLSID"] = pd.to_numeric(df_branch_tbl["BranchNMLSID"], errors="coerce").astype("Int64")
            df_branch_tbl["CompanyNMLSID"] = pd.to_numeric(df_branch_tbl["CompanyNMLSID"], errors="coerce").astype("Int64")
            df_branch_tbl = df_branch_tbl.dropna(subset=["BranchNMLSID", "CompanyNMLSID"])
            branch_parent = dict(zip(df_branch_tbl["BranchNMLSID"].astype("int64"),
                                      df_branch_tbl["CompanyNMLSID"].astype("int64")))
            branch_name = dict(zip(df_branch_tbl["BranchNMLSID"].astype("int64"),
                                    safe_str_series(df_branch_tbl["Name"])))
            active_branch_ids = set(
                df_branch_tbl.loc[
                    df_branch_tbl["IsAuthorized"].astype(str).str.strip().str.lower().eq("yes"),
                    "BranchNMLSID",
                ].astype("int64")
            )

        # -- Owning company per location --------------------------------------
        is_branch = df_loc["LocationType"].eq("Branch")
        df_loc["OwningCompany"] = df_loc["LocationNMLSID"]
        df_loc.loc[is_branch, "OwningCompany"] = (
            df_loc.loc[is_branch, "LocationNMLSID"].astype("int64").map(branch_parent)
        )
        df_loc["OwningCompany"] = pd.to_numeric(df_loc["OwningCompany"], errors="coerce").astype("Int64")
        df_loc = df_loc.dropna(subset=["OwningCompany"])

        # -- Active companies + names (scoped to owning companies we found) --
        owning_company_ids = df_loc["OwningCompany"].astype("int64").unique().tolist()
        company_name: dict[int, str] = {}
        active_company_ids: set[int] = set()
        all_company_ids: set[int] = set()
        if owning_company_ids:
            df_company_license = _read_scoped(
                conn,
                "SELECT DISTINCT CompanyNMLSID FROM dbo.CompanyLicense "
                "WHERE LOWER(LTRIM(RTRIM(IsAuthorized))) = 'yes' AND CompanyNMLSID IN ({placeholders})",
                owning_company_ids,
            )
            df_company = _read_scoped(
                conn,
                "SELECT CompanyNMLSID, Name, RegistrationStatus FROM dbo.Company "
                "WHERE IsDeleted = 0 AND CompanyNMLSID IN ({placeholders})",
                owning_company_ids,
            )
            if not df_company.empty:
                df_company["CompanyNMLSID"] = pd.to_numeric(df_company["CompanyNMLSID"], errors="coerce").astype("Int64")
                df_company = df_company.dropna(subset=["CompanyNMLSID"])
                company_name = dict(zip(df_company["CompanyNMLSID"].astype("int64"),
                                         safe_str_series(df_company["Name"])))
                all_company_ids = set(df_company["CompanyNMLSID"].astype("int64"))
                active_company_ids |= set(
                    df_company.loc[
                        df_company["RegistrationStatus"].astype(str).str.strip().str.lower().eq("active"),
                        "CompanyNMLSID",
                    ].astype("int64")
                )
            if not df_company_license.empty:
                active_company_ids |= set(
                    pd.to_numeric(df_company_license["CompanyNMLSID"], errors="coerce").dropna().astype("int64")
                )

        def entity_active(row) -> bool:
            location_id = int(row["LocationNMLSID"])
            if row["LocationType"] == "Branch":
                return location_id in active_branch_ids
            if location_id not in all_company_ids:
                # We have no activity signal for this company/institution at
                # all (a documented NMLS B2B caveat); the df_rep inner join
                # below is the real activity gate for these.
                return True
            return location_id in active_company_ids

        df_loc = df_loc[df_loc.apply(entity_active, axis=1)].copy()

        # -- Keep only "Authorized to Represent" locations --------------------
        df_loc = df_loc.merge(
            df_rep.rename(columns={"CompanyNMLSID": "OwningCompany"}),
            on=["IndividualNMLSID", "OwningCompany"], how="inner",
        )

        # One row per individual: the single most recent authorized location.
        df_loc = (
            df_loc.sort_values("StartDate", ascending=False)
            .drop_duplicates(subset=["IndividualNMLSID"], keep="first")
        )

        return _finalize(df_individual, df_loc, branch_name, company_name)


def _finalize(df_individual, df_loc, branch_name, company_name) -> pd.DataFrame:
    if df_loc.empty:
        result = df_individual.copy()
        for col in ("LocationNMLSID", "LocationType", "OwningCompanyNMLSID", "LocationName"):
            result[col] = ""
        return result[ENRICHMENT_COLUMNS]

    df_loc = df_loc.rename(columns={"OwningCompany": "OwningCompanyNMLSID"})

    def resolve_name(row) -> str:
        loc_id = int(row["LocationNMLSID"])
        if row["LocationType"] == "Branch":
            return branch_name.get(loc_id, "")
        return company_name.get(loc_id, "")

    df_loc["LocationName"] = df_loc.apply(resolve_name, axis=1)

    result = df_individual.merge(
        df_loc[["IndividualNMLSID", "LocationNMLSID", "LocationType", "OwningCompanyNMLSID", "LocationName"]],
        on="IndividualNMLSID", how="left",
    )
    for col in ("LocationNMLSID", "LocationType", "OwningCompanyNMLSID", "LocationName"):
        result[col] = safe_str_series(result[col])
    return result[ENRICHMENT_COLUMNS]


def merge_nmls_enrichment(table: pd.DataFrame, enrichment: pd.DataFrame, mlo_nmls_col: str = "MLO NMLS") -> pd.DataFrame:
    """Left-join NMLS enrichment columns onto the matcher's result table by
    the MLO NMLS id. Rows with no MLO NMLS value, or no NMLS match, get
    blank enrichment columns rather than being dropped."""
    if mlo_nmls_col not in table.columns or enrichment.empty:
        out = table.copy()
        for col in ("RegulationType", "LicensingStatus", "LocationNMLSID", "LocationName"):
            out[f"NMLS {col}"] = ""
        return out

    lookup = enrichment.set_index(enrichment["IndividualNMLSID"].astype(str))
    ids = safe_str_series(table[mlo_nmls_col])

    out = table.copy()
    out["NMLS RegulationType"] = ids.map(lookup["RegulationType"]).fillna("") if "RegulationType" in lookup else ""
    out["NMLS LicensingStatus"] = ids.map(lookup["LicensingStatus"]).fillna("") if "LicensingStatus" in lookup else ""
    out["NMLS LocationNMLSID"] = ids.map(lookup["LocationNMLSID"]).fillna("") if "LocationNMLSID" in lookup else ""
    out["NMLS LocationName"] = ids.map(lookup["LocationName"]).fillna("") if "LocationName" in lookup else ""
    return out
