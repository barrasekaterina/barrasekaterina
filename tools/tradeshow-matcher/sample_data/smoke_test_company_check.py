"""Validates the "Existing Account Company" / "Existing Lead Company"
columns: for an attendee matched to a specific CRM Contact/Lead, do they
actually agree on the company? Fuzzy, not exact - and blank rather than
"No" when there's nothing to compare (no match at all, or either side has
no company on file)."""
import io
import sys

sys.path.insert(0, "/home/user/barrasekaterina/tools/tradeshow-matcher")

from matcher.pipeline import run_pipeline  # noqa: E402

# - john smith: matches a Contact whose on-file company agrees (fuzzy) -> Yes
# - jane roe: matches a Contact whose on-file company is a different company -> No
# - carla diaz: matches a Lead only, no Contact at all -> Existing Account Company blank
tradeshow_csv = (
    "Full Name,Company Name,Phone,Email\n"
    "john smith,Acme Lending,5551234567,john@acme.com\n"
    "jane roe,Roe Mortgage,5551112222,jane@roe.com\n"
    "carla diaz,Diaz Realty,5559998888,carla@diazrealty.com\n"
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
print(table[["Existing Account Company", "Existing Lead Company"]].to_string())

assert table.loc["john smith", "Existing Account Company"] == "Yes"
assert table.loc["jane roe", "Existing Account Company"] == "No"
assert table.loc["carla diaz", "Existing Account Company"] == ""
assert table.loc["carla diaz", "Existing Lead Company"] == "Yes"

print("\nALL EXISTING-ACCOUNT/LEAD-COMPANY TESTS PASSED")
