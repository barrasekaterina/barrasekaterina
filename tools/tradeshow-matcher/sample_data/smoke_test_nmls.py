"""Validate matcher/nmls.py's business logic against a fully mocked NMLS
schema (no real pyodbc/network connection - not available in this sandbox).
Covers both a Main-location (company-level) individual and a
Branch-location individual, plus one individual with no active
represented location at all.
"""
import sys
import types

import pandas as pd

sys.path.insert(0, "/home/user/barrasekaterina/tools/tradeshow-matcher")

# --- Build a fake `pyodbc` module so nmls.py's lazy `import pyodbc` picks
# it up, without needing the real driver installed. ------------------------
fake_pyodbc = types.ModuleType("pyodbc")


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _fake_connect(conn_str):
    return _FakeConnection()


fake_pyodbc.connect = _fake_connect
sys.modules["pyodbc"] = fake_pyodbc

from matcher import nmls  # noqa: E402  (must come after the pyodbc stub)

# --- Canned table contents --------------------------------------------------
TABLES = {
    "dbo.Individual": pd.DataFrame({"IndividualNMLSID": [5555, 9999, 7777]}),
    "dbo.IndividualLicense": pd.DataFrame({
        "IndividualNMLSID": [5555],
        "IsAuthorized": ["Yes"],
    }),
    "dbo.IndividualRegistration": pd.DataFrame({
        "IndividualNMLSID": [9999],
        "AuthorizedToConductBusiness": ["Yes"],
    }),
    "dbo.IndividualSponsorship": pd.DataFrame({
        "IndividualNMLSID": [5555],
        "CompanyNMLSID": [1111],
        "EndDate": [None],
    }),
    "dbo.IndividualRegistrationDetail": pd.DataFrame({
        "IndividualNMLSID": [9999],
        "InstitutionNMLSID": [3333],
        "EndDate": [None],
    }),
    "dbo.IndividualLocation": pd.DataFrame({
        "IndividualNMLSID": [5555, 9999],
        "LocationNMLSID": [1111, 2222],
        "LocationType": ["Main", "Branch"],
        "StartDate": ["2024-01-01", "2024-02-01"],
    }),
    "dbo.Branch": pd.DataFrame({
        "BranchNMLSID": [2222],
        "CompanyNMLSID": [3333],
        "IsAuthorized": ["Yes"],
        "Name": ["Downtown Branch"],
    }),
    "dbo.CompanyLicense": pd.DataFrame({"CompanyNMLSID": []}),
    "dbo.Company": pd.DataFrame({
        "CompanyNMLSID": [1111, 3333],
        "Name": ["Acme Lending", "Diaz Mortgage Corp"],
        "RegistrationStatus": ["Active", "Active"],
    }),
}

# Longest/most-specific table names first, so "IndividualRegistrationDetail"
# is checked before "IndividualRegistration" is checked before "Individual".
TABLE_ORDER = sorted(TABLES, key=len, reverse=True)

# Which column each query's "IN (...)" clause actually filters by - matches
# the WHERE clause nmls.py writes for that table, not a heuristic guess
# (a generic "ends with NMLSID" heuristic breaks for dbo.Company, where the
# *only* NMLSID-suffixed column is also the one you'd want to exclude for
# the aliased Detail-table case).
FILTER_COLUMN = {
    "dbo.Individual": "IndividualNMLSID",
    "dbo.IndividualLicense": "IndividualNMLSID",
    "dbo.IndividualRegistration": "IndividualNMLSID",
    "dbo.IndividualSponsorship": "IndividualNMLSID",
    "dbo.IndividualRegistrationDetail": "IndividualNMLSID",
    "dbo.IndividualLocation": "IndividualNMLSID",
    "dbo.Branch": "BranchNMLSID",
    "dbo.CompanyLicense": "CompanyNMLSID",
    "dbo.Company": "CompanyNMLSID",
}


def fake_read_sql(sql, conn, params=None):
    for table in TABLE_ORDER:
        if table in sql:
            df = TABLES[table].copy()
            # Simulate SQL "AS" column aliasing, since the real driver would
            # rename the column in its result set - a naive canned-table
            # mock that skips this masks real column-name mismatches.
            if "InstitutionNMLSID AS CompanyNMLSID" in sql:
                df = df.rename(columns={"InstitutionNMLSID": "CompanyNMLSID"})
            if params and not df.empty:
                return df[df[FILTER_COLUMN[table]].isin(params)].reset_index(drop=True)
            return df
    raise AssertionError(f"No mocked table matched this query:\n{sql}")


nmls.pd.read_sql = fake_read_sql

# --- Run it ------------------------------------------------------------------
result = nmls.fetch_nmls_enrichment([5555, 9999, 7777, "not-a-number", None])
print(result.to_string())

assert set(result["IndividualNMLSID"]) == {5555, 9999, 7777}

row_5555 = result[result["IndividualNMLSID"] == 5555].iloc[0]
assert row_5555["RegulationType"] == "State-Licensed", row_5555["RegulationType"]
assert row_5555["LicensingStatus"] == "Active"
assert row_5555["LocationName"] == "Acme Lending", row_5555["LocationName"]

row_9999 = result[result["IndividualNMLSID"] == 9999].iloc[0]
assert row_9999["RegulationType"] == "Federally Registered", row_9999["RegulationType"]
assert row_9999["LicensingStatus"] == "Active"
assert row_9999["LocationName"] == "Downtown Branch", row_9999["LocationName"]

row_7777 = result[result["IndividualNMLSID"] == 7777].iloc[0]
assert row_7777["RegulationType"] == "None"
assert row_7777["LicensingStatus"] == "Inactive"
assert row_7777["LocationName"] == ""

# --- Merge into a matcher-shaped result table -------------------------------
table = pd.DataFrame({
    "Full Name": ["john smith", "carla diaz", "no one"],
    "MLO NMLS": ["5555", "9999", ""],
})
merged = nmls.merge_nmls_enrichment(table, result)
print("\n", merged.to_string())
assert merged.loc[0, "NMLS LocationName"] == "Acme Lending"
assert merged.loc[1, "NMLS LocationName"] == "Downtown Branch"
assert merged.loc[2, "NMLS LocationName"] == ""
assert merged.loc[0, "NMLS LocationNMLSID"] == "1111"
assert merged.loc[1, "NMLS LocationNMLSID"] == "2222"
assert merged.loc[2, "NMLS LocationNMLSID"] == ""

print("\nALL NMLS TESTS PASSED")
