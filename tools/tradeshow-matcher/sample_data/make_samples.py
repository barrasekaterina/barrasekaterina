"""Generate small synthetic fixtures to smoke-test the matcher.

Not part of the app; run manually with `python sample_data/make_samples.py`.
"""
import os

import pandas as pd

HERE = os.path.dirname(__file__)

crm_contacts = pd.DataFrame({
    "First Name": ["John", "Maria", "Bob", "Alice"],
    "Middle Name": ["", "", "", ""],
    "Last Name": ["Smith", "Garcia", "Lee", "Nguyen"],
    "Status": ["Active", "Active", "Active", "Active"],
    "Company": ["Acme Lending", "Best Mortgage", "Lee Capital", "Nguyen Realty"],
    "Responsible": ["rep1", "rep2", "rep1", "rep3"],
    "Work Phone": ["+1 (305) 555-0100", "", "", ""],
    "Mobile": ["", "305-555-0199", "", "786-555-0200"],
    "Fax": ["", "", "", ""],
    "Home Phone": ["", "", "", ""],
    "Other Phone Number": ["", "", "", ""],
    "Work E-mail": ["john.smith@acmelending.com", "", "bob.lee@leecapital.com", ""],
    "Home E-mail": ["", "maria.garcia@bestmortgage.com", "", "alice.nguyen@gmail.com"],
    "Other E-mail": ["", "", "", ""],
    "Company NMLS": ["1111", "2222", "3333", "4444"],
    "MLO’s NMLS": ["5555", "6666", "7777", "8888"],
    "ID": ["101", "102", "103", "104"],
})
crm_contacts.to_csv(os.path.join(HERE, "crm_contacts_sample.csv"), sep=";", index=False)

crm_leads = pd.DataFrame({
    "Lead Name": ["Carla Diaz", "Tom Nolan"],
    "Responsible": ["rep2", "rep1"],
    "Work Phone": ["954-555-0300", ""],
    "Mobile": ["", "954-555-0399"],
    "Fax": ["", ""],
    "Home Phone": ["", ""],
    "Other Phone Number": ["", ""],
    "Work E-mail": ["carla.diaz@diazrealty.com", ""],
    "Home E-mail": ["", "tom.nolan@yahoo.com"],
    "Other E-mail": ["", ""],
    "Company NMLS": ["9999", "1010"],
    "Stage": ["New", "Contacted"],
    "Additional Lead Type": ["", ""],
    "Lead Type": ["Realtor", "Broker"],
    "Source": ["Tradeshow", "Tradeshow"],
    "Lead Companies": ["Diaz Realty", "Nolan Brokerage"],
    "NMLS MLOs": ["", ""],
    "ID": ["201", "202"],
})
crm_leads.to_csv(os.path.join(HERE, "crm_leads_sample.csv"), sep=";", index=False)

# Variant 1: Full Name + Email only
pd.DataFrame({
    "Full Name": ["John Smith", "Maria Garcia", "New Person"],
    "Email": ["john.smith@acmelending.com", "maria.garcia@bestmortgage.com", "new.person@somecorp.com"],
}).to_excel(os.path.join(HERE, "tradeshow_name_email.xlsx"), index=False)

# Variant 2: Full Name + Company Name + Phone
pd.DataFrame({
    "Full Name": ["Bob Lee", "Alice Nguyen", "Someone Else"],
    "Company Name": ["Lee Capital", "Nguyen Realty", "Other Co"],
    "Phone": ["(786) 555-0200", "305-555-0199", "111-222-3333"],
}).to_excel(os.path.join(HERE, "tradeshow_name_company_phone.xlsx"), index=False)

# Variant 3: Full Name + Company Name + Email
pd.DataFrame({
    "Full Name": ["Tom Nolan", "Carla Diaz", "Nobody Here"],
    "Company Name": ["Nolan Brokerage", "Diaz Realty", "Nowhere Inc"],
    "Email": ["tom.nolan@yahoo.com", "carla.diaz@diazrealty.com", "nobody@nowhere.com"],
    "Job Title": ["Broker", "Realtor", "Marketing Coordinator"],
}).to_excel(os.path.join(HERE, "tradeshow_name_company_email.xlsx"), index=False)

# Variant 4: Full Name + Company Name + Phone + Email
pd.DataFrame({
    "Full Name": ["John Smith", "Carla Diaz", "Random Attendee"],
    "Company Name": ["Acme Lending", "Diaz Realty", "Random LLC"],
    "Phone": ["305-555-0100", "954-555-0300", "000-000-0000"],
    "Email": ["john.smith@acmelending.com", "carla.diaz@diazrealty.com", "random@randomllc.com"],
}).to_excel(os.path.join(HERE, "tradeshow_name_company_phone_email.xlsx"), index=False)

print("Sample files written to", HERE)
