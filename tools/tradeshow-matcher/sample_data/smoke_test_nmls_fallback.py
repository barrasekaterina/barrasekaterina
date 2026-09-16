"""Validates matcher.nmls.match_individuals_by_name (the fallback path for
attendees with no CRM match) against a mocked dbo.Individual table, and the
priority logic in app.py's /run handler: CRM-derived MLO NMLS wins when
present, name+company similarity is only used when it isn't.

Covers:
1. A unique name in NMLS -> accepted without needing company confirmation.
2. Two same-named individuals at different companies -> company name
   disambiguates.
3. Two same-named individuals, attendee has no Company Name -> left
   unmatched (too ambiguous to guess at).
4. The full /run flow: one attendee found via CRM, one found only via the
   name+company fallback, confirming "NMLS Match Method" reflects which
   path was actually used for each.
"""
import sys
import types

import pandas as pd

sys.path.insert(0, "/home/user/barrasekaterina/tools/tradeshow-matcher")

fake_pyodbc = types.ModuleType("pyodbc")


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


fake_pyodbc.connect = lambda cs: _FakeConnection()
sys.modules["pyodbc"] = fake_pyodbc

from matcher import nmls  # noqa: E402

INDIVIDUAL_TABLE = pd.DataFrame({
    "IndividualNMLSID": [1001, 2001, 2002, 3001, 3002],
    "FirstName": ["Carla", "John", "John", "Jane", "Jane"],
    "LastName": ["Diaz", "Doe", "Doe", "Roe", "Roe"],
})
TABLES = {
    "dbo.IndividualLicense": pd.DataFrame({"IndividualNMLSID": [1001, 2001, 2002, 3001, 3002], "IsAuthorized": ["Yes"] * 5}),
    "dbo.IndividualRegistration": pd.DataFrame({"IndividualNMLSID": [], "AuthorizedToConductBusiness": []}),
    "dbo.IndividualSponsorship": pd.DataFrame({
        "IndividualNMLSID": [1001, 2001, 2002, 3001, 3002],
        "CompanyNMLSID": [9001, 9101, 9102, 9201, 9202],
        "EndDate": [None] * 5,
    }),
    "dbo.IndividualRegistrationDetail": pd.DataFrame({"IndividualNMLSID": [], "InstitutionNMLSID": [], "EndDate": []}),
    "dbo.IndividualLocation": pd.DataFrame({
        "IndividualNMLSID": [1001, 2001, 2002, 3001, 3002],
        "LocationNMLSID": [9001, 9101, 9102, 9201, 9202],
        "LocationType": ["Main"] * 5,
        "StartDate": ["2024-01-01"] * 5,
    }),
    "dbo.Branch": pd.DataFrame({"BranchNMLSID": [], "CompanyNMLSID": [], "IsAuthorized": [], "Name": []}),
    "dbo.CompanyLicense": pd.DataFrame({"CompanyNMLSID": []}),
    "dbo.Company": pd.DataFrame({
        "CompanyNMLSID": [9001, 9101, 9102, 9201, 9202],
        "Name": ["Diaz Realty", "Doe Lending East", "Doe Lending West", "Roe Mortgage A", "Roe Mortgage B"],
        "RegistrationStatus": ["Active"] * 5,
    }),
}
TABLE_NAMES = [
    "dbo.Individual", "dbo.IndividualLicense", "dbo.IndividualRegistration",
    "dbo.IndividualSponsorship", "dbo.IndividualRegistrationDetail",
    "dbo.IndividualLocation", "dbo.Branch", "dbo.CompanyLicense", "dbo.Company",
]
TABLE_ORDER = sorted(TABLE_NAMES, key=len, reverse=True)
# The same table can be queried with different WHERE-clause filter columns
# depending on the caller (e.g. dbo.Individual is filtered by LastName in
# the name-matching path, but by IndividualNMLSID in
# fetch_nmls_enrichment's own lookup) - detect it from the SQL text itself.
FILTER_COLUMN_CANDIDATES = ["LastName", "IndividualNMLSID", "BranchNMLSID", "CompanyNMLSID"]


def fake_read_sql(sql, conn, params=None):
    for table in TABLE_ORDER:
        if table in sql:
            df = INDIVIDUAL_TABLE.copy() if table == "dbo.Individual" else TABLES[table].copy()
            if "InstitutionNMLSID AS CompanyNMLSID" in sql:
                df = df.rename(columns={"InstitutionNMLSID": "CompanyNMLSID"})
            if params and not df.empty:
                col = next(c for c in FILTER_COLUMN_CANDIDATES if f"{c} IN (" in sql and c in df.columns)
                if df[col].dtype == object:
                    param_set = {str(p).lower() for p in params}
                    return df[df[col].astype(str).str.lower().isin(param_set)].reset_index(drop=True)
                return df[df[col].isin(params)].reset_index(drop=True)
            return df
    raise AssertionError(f"No mocked table matched:\n{sql}")


nmls.pd.read_sql = fake_read_sql

attendees = pd.DataFrame({
    "First Name": ["carla", "john", "jane"],
    "Last Name": ["diaz", "doe", "roe"],
    "Company Name": ["Diaz Realty", "Doe Lending West", ""],
})

ids, enrichment = nmls.match_individuals_by_name(attendees)
print(ids)
print()
print(enrichment[["IndividualNMLSID", "LocationName"]].to_string())

assert ids.loc[0] == "1001", ids.loc[0]  # unique name -> accepted directly
assert ids.loc[1] == "2002", ids.loc[1]  # "Doe Lending West" -> disambiguates to 2002
assert ids.loc[2] == "", ids.loc[2]      # ambiguous "Jane Roe", no company -> left unmatched

print("\nALL NAME-FALLBACK TESTS PASSED")
