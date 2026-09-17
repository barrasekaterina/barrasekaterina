"""Validates matcher.nmls.compare_company_match: flags whether the company
on file matches what NMLS currently shows for that MLO, prioritizing an
exact Company NMLS id comparison and falling back to a *fuzzy* Company
Name comparison - never an exact string check - when an id isn't
available on both sides. Covers all attendees regardless of whether they
matched via CRM (has a Company NMLS id) or the name+company fallback
(no CRM record, so no Company NMLS id - only their own typed Company
Name to fuzzy-compare)."""
import sys

import pandas as pd

sys.path.insert(0, "/home/user/barrasekaterina/tools/tradeshow-matcher")

from matcher import nmls  # noqa: E402

table = pd.DataFrame({
    "Company Name": ["Acme Lending", "Best Mortgage", "Roe Mortgage B", "Totally Different Co", "No One"],
    "Company NMLS": ["1111", "2222", "", "", ""],
    "NMLS OwningCompanyNMLSID": ["1111", "3333", "", "", ""],
    "NMLS LocationName": ["Acme Lending", "Diaz Mortgage Corp", "Roe Mortgage B", "Doe Lending East", ""],
})
result = nmls.compare_company_match(table)
print(result[["Company Name", "Company NMLS", "NMLS OwningCompanyNMLSID", "NMLS LocationName", "Company Match"]]
      .to_string())

assert result.loc[0, "Company Match"] == "Yes", "matching Company NMLS ids should compare Yes"
assert result.loc[1, "Company Match"] == "No", "mismatched Company NMLS ids should compare No, not fall back to name"
assert result.loc[2, "Company Match"] == "Yes", "no CRM id at all - fuzzy Company Name match should still say Yes"
assert result.loc[3, "Company Match"] == "No", "fuzzy Company Name mismatch should say No"
assert result.loc[4, "Company Match"] == "", "no NMLS data at all - should be blank, not Yes/No"

# No NMLS enrichment ran at all for this run - every row should be blank.
no_enrichment = pd.DataFrame({"Company Name": ["Acme Lending"], "Company NMLS": ["1111"]})
result2 = nmls.compare_company_match(no_enrichment)
assert result2.loc[0, "Company Match"] == ""

print("\nALL COMPANY-MATCH TESTS PASSED")
