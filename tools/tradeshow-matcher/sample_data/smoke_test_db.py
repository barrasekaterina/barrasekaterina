"""Validate the DB-adapter path (matcher.db output -> standardized schema ->
matching) using a mocked DataFrame shaped like the real SQL query output.

This does NOT open a real database connection - there is no network access
to the internal admortgage BI server nor the ODBC driver in this sandbox.
It only proves loaders.standardize_db_contacts/leads correctly feed the
existing matching engine, the same one already exercised against the CSV
path in smoke_test.py.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pandas as pd

from matcher import loaders, matching

# Shaped like matcher.db.fetch_contacts() output (post NMLS cast/drop).
mock_contacts_raw = pd.DataFrame({
    "iBitrix_Contact_ID": [101, 102],
    "First_Name": ["John", "Maria"],
    "Last_Name": ["Smith", "Garcia"],
    "ContactStatus": ["Active", "Active"],
    "NMLS_Status": ["Active", "Active"],
    "Employment": ["Current", "Current"],
    "ContactCategory": ["", ""],
    "ID_Comp": [1, 2],
    "sEmail": ["john.smith@acmelending.com", "maria.garcia@bestmortgage.com"],
    "sPhone": ["305-555-0100", "305-555-0199"],
    "AE_First_Name": ["Rep", "Rep"],
    "AE_Last_Name": ["One", "Two"],
    "Observers_name": ["", ""],
    "CompanyName": ["Acme Lending", "Best Mortgage"],
    "iCompany_NMLS": [1111, 2222],
    "iBitrix_Contact_NMLS": [5555, 6666],
})

# Shaped like matcher.db.fetch_leads() output.
mock_leads_raw = pd.DataFrame({
    "TITLE": ["Carla Diaz", "Tom Nolan"],
    "AE": ["Rep Two", "Rep One"],
    "COMPANY_TITLE": ["Diaz Realty", "Nolan Brokerage"],
    "LC_ID": [1, 2],
    "MLO_NMLS": ["", ""],
    "COMPANY_NMLS": ["9999", "1010"],
    "NMLS_STATUS": [None, None],
    "EMPLOYMENT_STATUS": [None, None],
    "Email": ["carla.diaz@diazrealty.com", "tom.nolan@yahoo.com"],
    "Phone": ["954-555-0300", "954-555-0399"],
    "Additional Phones": ["", ""],
    "Additional Emails": ["", ""],
    "LEAD_ID": [201, 202],
    "STAGE_ID": ["NEW", "UC_STARTED"],
    "STAGE": ["New", "Started"],
})

contacts = loaders.standardize_db_contacts(mock_contacts_raw)
leads = loaders.standardize_db_leads(mock_leads_raw)

print("standardized contacts:")
print(contacts[["Full Name", "Company Name", "Phone", "Email", "MLO_NMLS", "ID"]])
print("\nstandardized leads:")
print(leads[["Full Name", "Company Name", "Phone", "Email", "Stage", "ID"]])

tradeshow = pd.DataFrame({
    # Full Name is lowercase here because loaders.load_tradeshow_file()
    # always lowercases it via cleaning.build_full_name() - matching this
    # by hand since this fixture skips that loader.
    "Full Name": ["john smith", "carla diaz"],
    "First Name": ["john", "carla"],
    "Last Name": ["smith", "diaz"],
    "Company Name": ["Acme Lending", "Diaz Realty"],
    "Phone": ["3055550100", "9545550300"],
    "Email": ["john.smith@acmelending.com", "carla.diaz@diazrealty.com"],
})

fields = ["Company Name", "Phone", "Email"]
matched_contacts = matching.aggregate_matches(
    matching.match_tradeshow_to_crm(tradeshow, contacts, fields), fields
)
matched_leads = matching.aggregate_matches(
    matching.match_tradeshow_to_crm(tradeshow, leads, fields), fields
)

print("\nmatched against DB-sourced contacts:")
print(matched_contacts[["Full Name_tradeshow", "Full Name_crm", "total_score"]] if not matched_contacts.empty else "EMPTY")
print("\nmatched against DB-sourced leads:")
print(matched_leads[["Full Name_tradeshow", "Full Name_crm", "total_score"]] if not matched_leads.empty else "EMPTY")

assert not matched_contacts.empty, "expected John Smith to match DB contacts"
assert not matched_leads.empty, "expected Carla Diaz to match DB leads"
print("\nDB ADAPTER SMOKE TEST OK")
