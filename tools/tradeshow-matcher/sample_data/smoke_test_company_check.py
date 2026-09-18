"""Validates the "Existing Account Company" / "Existing Lead Company"
columns, for both matched and unmatched attendees:

- Matched to a specific Contact/Lead: does their company agree (fuzzy,
  not exact) with what's on file for *that* record?
- Not matched at all (New Contact/New Lead): falls back to the broader
  "does this company exist anywhere in that pool (Contacts or Leads)"
  check, so these columns still say something useful rather than just
  being blank.
- Blank only when there's no Company Name at all to check.
"""
import io
import sys

sys.path.insert(0, "/home/user/barrasekaterina/tools/tradeshow-matcher")

from matcher.pipeline import run_pipeline  # noqa: E402

# - john smith: matches a Contact whose on-file company agrees (fuzzy) -> Yes;
#   Acme Lending isn't any Lead's company either -> Existing Lead Company No.
# - jane roe: matches a Contact whose on-file company is a different company -> No.
# - carla diaz: matches a Lead only, no Contact at all; Diaz Realty isn't any
#   Contact's company -> Existing Account Company No (checked broader pool),
#   Existing Lead Company Yes (matched Lead's own company agrees).
# - brand person: no personal match at all (New Contact), but Acme Lending
#   is a known Contact company -> Existing Account Company Yes even with no
#   specific match; not a known Lead company -> Existing Lead Company No.
tradeshow_csv = (
    "Full Name,Company Name,Phone,Email\n"
    "john smith,Acme Lending,5551234567,john@acme.com\n"
    "jane roe,Roe Mortgage,5551112222,jane@roe.com\n"
    "carla diaz,Diaz Realty,5559998888,carla@diazrealty.com\n"
    "brand person,Acme Lending,5550000000,brand@acmelending.com\n"
)
crm_contacts_csv = (
    "First Name;Last Name;Company;Status;Responsible;Work Phone;Mobile;Fax;Home Phone;"
    "Other Phone Number;Work E-mail;Home E-mail;Other E-mail;Company NMLS;MLO's NMLS;ID\n"
    "John;Smith;Acme Lending;Active;;5551234567;;;;;john@acme.com;;;;;101\n"
    "Jane;Roe;Totally Different Corp;Active;;5551112222;;;;;jane@roe.com;;;;;102\n"
)
crm_leads_csv = (
    "Lead Name;Lead Companies;Responsible;Work Phone;Mobile;Fax;Home Phone;Other Phone Number;"
    "Work E-mail;Home E-mail;Other E-mail;Company NMLS;NMLS MLOs;Stage;Additional Lead Type;"
    "Lead Type;Source;ID\n"
    "Carla Diaz;Diaz Realty;;5559998888;;;;;carla@diazrealty.com;;;;;New;;;;201\n"
)

result = run_pipeline(
    tradeshow_file=io.BytesIO(tradeshow_csv.encode()),
    tradeshow_filename="tradeshow.csv",
    crm_contacts_file=io.BytesIO(crm_contacts_csv.encode()),
    crm_leads_file=io.BytesIO(crm_leads_csv.encode()),
)
table = result.table.set_index("Full Name")
print(table[["Status", "Existing Account Company", "Existing Lead Company"]].to_string())

assert table.loc["john smith", "Existing Account Company"] == "Yes"
assert table.loc["john smith", "Existing Lead Company"] == "No"

assert table.loc["jane roe", "Existing Account Company"] == "No"

assert table.loc["carla diaz", "Existing Account Company"] == "No"
assert table.loc["carla diaz", "Existing Lead Company"] == "Yes"

assert table.loc["brand person", "Status"] == "New Contact"
assert table.loc["brand person", "Existing Account Company"] == "Yes"
assert table.loc["brand person", "Existing Lead Company"] == "No"

print("\nALL EXISTING-ACCOUNT/LEAD-COMPANY TESTS PASSED")
