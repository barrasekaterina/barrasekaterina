"""Validates the redesigned Status/Match Confidence/Matched By logic:

Status is exactly one of Existing Contact / Existing Lead / New Contact /
New Lead, with "Existing Contact" winning even when the same attendee also
matched a Lead (flagged via an "Also a Lead" tag rather than silently
dropped). New Contact vs New Lead is decided by matcher.matching.
find_known_companies: does this unmatched attendee's Company Name already
exist anywhere among CRM Contacts + Leads combined?

Match Confidence applies one rule identically across every category: High
when an exact/near-exact identifier (Phone/Email) backed the conclusion,
Medium when only fuzzy text (Name/Company) did, Low when there was no
usable data to check at all.
"""
import io
import sys

sys.path.insert(0, "/home/user/barrasekaterina/tools/tradeshow-matcher")

from matcher.pipeline import run_pipeline  # noqa: E402

# Attendees:
# - john smith @ Acme Lending  -> matches a CRM Contact via Phone (High)
# - carla diaz @ Diaz Realty   -> matches CRM Contact AND a Lead -> "Also a Lead"
# - brand person @ Acme Lending -> no personal match, but Acme Lending is a
#   known company (via john smith's contact record) -> New Contact (Medium)
# - nobody here @ Totally New Co -> no personal match, company unknown -> New Lead (High, we checked)
# - no company at all -> no personal match, no Company Name -> New Lead (Low, unverifiable)
tradeshow_csv = (
    "Full Name,Company Name,Phone,Email\n"
    "john smith,Acme Lending,5551234567,john@acme.com\n"
    "carla diaz,Diaz Realty,5559998888,carla@diazrealty.com\n"
    "brand person,Acme Lending,5550000000,brand@acmelending.com\n"
    "nobody here,Totally New Co,5551112222,nobody@totallynewco.com\n"
    "no company,,5553334444,nocompany@example.com\n"
)
crm_contacts_csv = (
    "First Name;Last Name;Company;Status;Responsible;Work Phone;Mobile;Fax;Home Phone;"
    "Other Phone Number;Work E-mail;Home E-mail;Other E-mail;Company NMLS;MLO's NMLS;ID\n"
    "John;Smith;Acme Lending;Active;;5551234567;;;;;john@acme.com;;;1111;5555;101\n"
    "Carla;Diaz;Diaz Realty;Active;;5559998888;;;;;carla@diazrealty.com;;;;;102\n"
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
print(table[["Status", "Match Confidence", "Matched By"]].to_string())

assert table.loc["john smith", "Status"] == "Existing Contact; Existing Domain"
assert table.loc["john smith", "Match Confidence"] == "High"
assert "Phone" in table.loc["john smith", "Matched By"]

assert table.loc["carla diaz", "Status"] == "Existing Contact; Also a Lead; Existing Domain"
assert table.loc["carla diaz", "Match Confidence"] == "High"

assert table.loc["brand person", "Status"] == "New Contact"
assert table.loc["brand person", "Match Confidence"] == "Medium"
assert table.loc["brand person", "Matched By"] == "Company (fuzzy)"

assert table.loc["nobody here", "Status"] == "New Lead"
assert table.loc["nobody here", "Match Confidence"] == "High"

assert table.loc["no company", "Status"] == "New Lead"
assert table.loc["no company", "Match Confidence"] == "Low"

print("\nALL STATUS/CONFIDENCE TESTS PASSED")
