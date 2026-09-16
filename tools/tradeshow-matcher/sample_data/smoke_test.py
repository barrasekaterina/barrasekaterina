import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from matcher.pipeline import run_pipeline, write_excel

HERE = os.path.dirname(__file__)

variants = [
    "tradeshow_name_email.xlsx",
    "tradeshow_name_company_phone.xlsx",
    "tradeshow_name_company_email.xlsx",
    "tradeshow_name_company_phone_email.xlsx",
]

for variant in variants:
    print(f"\n=== {variant} ===")
    with open(os.path.join(HERE, variant), "rb") as ts, \
         open(os.path.join(HERE, "crm_contacts_sample.csv"), "rb") as cc, \
         open(os.path.join(HERE, "crm_leads_sample.csv"), "rb") as cl:
        result = run_pipeline(ts, variant, cc, cl)
    print("detected fields:", result.detected_fields)
    print("summary:", result.summary)
    print(result.table[["Status", "Full Name", "Contact CRM Link", "Lead CRM Link"]].to_string())
    out_path = os.path.join(HERE, f"out_{variant}.xlsx")
    write_excel(result.table, out_path)
    print("wrote", out_path)

print("\nALL VARIANTS RAN OK")
