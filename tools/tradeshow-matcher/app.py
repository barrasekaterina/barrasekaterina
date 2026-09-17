"""Tradeshow-vs-CRM matcher: one adaptive web tool.

Replaces four near-duplicate notebook pipelines (one per combination of
Full Name + Company Name + Phone + Email that a tradeshow list might carry)
with a single tool that detects which fields are present and matches
accordingly. There is no business-card (BC) input or matching path.
"""
from __future__ import annotations

import io
import os
import tempfile
import uuid

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file

from matcher import db, loaders, nmls
from matcher.cleaning import safe_str_frame
from matcher.pipeline import run_pipeline, write_excel

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-not-secret")

RESULTS_DIR = os.path.join(tempfile.gettempdir(), "tradeshow_matcher_results")
os.makedirs(RESULTS_DIR, exist_ok=True)

# The /api/* routes below exist so the browser-extension version of this
# tool (which cannot open a direct SQL Server connection itself) can reach
# the CRM database through this locally-running backend instead. CORS is
# deliberately restricted to chrome-extension:// origins, never "*" - an
# open CORS policy here would let ANY website you happen to have open
# silently call these endpoints (one of which needs no credentials at all)
# and read your CRM data for as long as this server is running.
ALLOWED_ORIGIN_PREFIX = "chrome-extension://"


@app.after_request
def add_extension_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if origin.startswith(ALLOWED_ORIGIN_PREFIX):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/run", methods=["POST"])
def run():
    tradeshow = request.files.get("tradeshow_file")
    if not tradeshow or not tradeshow.filename:
        return render_template("index.html", error="Please choose a tradeshow file.")

    crm_contacts_file = None
    crm_contacts_df = None
    crm_leads_file = None
    crm_leads_df = None

    try:
        if request.form.get("crm_contacts_source") == "live":
            print("[matcher] Fetching CRM Contacts live...", flush=True)
            raw = db.fetch_contacts()
            print(f"[matcher] Got {len(raw)} contact rows, standardizing...", flush=True)
            crm_contacts_df = loaders.standardize_db_contacts(raw)
        else:
            uploaded = request.files.get("crm_contacts_file")
            if uploaded and uploaded.filename:
                crm_contacts_file = io.BytesIO(uploaded.read())

        if request.form.get("crm_leads_source") == "live":
            print("[matcher] Fetching CRM Leads live...", flush=True)
            raw = db.fetch_leads()
            print(f"[matcher] Got {len(raw)} lead rows, standardizing...", flush=True)
            crm_leads_df = loaders.standardize_db_leads(raw)
        else:
            uploaded = request.files.get("crm_leads_file")
            if uploaded and uploaded.filename:
                crm_leads_file = io.BytesIO(uploaded.read())
    except Exception as exc:  # noqa: BLE001 - surface any DB/driver error to the user
        print(f"[matcher] CRM database pull failed: {exc}", flush=True)
        return render_template("index.html", error=f"CRM database pull failed: {exc}")

    print("[matcher] Running the match against the tradeshow file...", flush=True)
    try:
        result = run_pipeline(
            tradeshow_file=io.BytesIO(tradeshow.read()),
            tradeshow_filename=tradeshow.filename,
            crm_contacts_file=crm_contacts_file,
            crm_leads_file=crm_leads_file,
            crm_contacts_df=crm_contacts_df,
            crm_leads_df=crm_leads_df,
        )
    except ValueError as exc:
        print(f"[matcher] Failed: {exc}", flush=True)
        return render_template("index.html", error=str(exc))

    print(
        f"[matcher] Done: {result.summary['total_attendees']} attendees, "
        f"{result.summary['matched_contacts']} matched contacts, "
        f"{result.summary['matched_leads']} matched leads.",
        flush=True,
    )

    if request.form.get("enrich_nmls") == "on":
        # Priority: if an attendee matched a CRM Contact/Lead, use that
        # record's MLO NMLS id directly - it's a known, unambiguous id.
        # Only for attendees with no CRM match at all do we fall back to
        # fuzzy name+company matching against NMLS itself.
        result.table["NMLS ID Used"] = result.table.get("MLO NMLS", "")
        result.table["NMLS Match Method"] = result.table["NMLS ID Used"].apply(lambda v: "CRM" if v else "")
        try:
            crm_ids = [i for i in result.table["NMLS ID Used"] if i]
            print(f"[matcher] Enriching {len(crm_ids)} MLO NMLS id(s) from CRM matches...", flush=True)
            enrichment = nmls.fetch_nmls_enrichment(crm_ids)
            print(f"[matcher] NMLS returned {len(enrichment)} matched individual(s) via CRM.", flush=True)

            needs_fallback = result.table.loc[
                result.table["NMLS ID Used"] == "", ["First Name", "Last Name", "Company Name"]
            ]
            if not needs_fallback.empty:
                print(f"[matcher] Looking up {len(needs_fallback)} attendee(s) with no CRM match "
                      f"by name+company similarity...", flush=True)
                fallback_ids, fallback_enrichment = nmls.match_individuals_by_name(needs_fallback)
                matched_count = int((fallback_ids != "").sum())
                print(f"[matcher] Found {matched_count} of them by name+company.", flush=True)
                result.table.loc[fallback_ids.index, "NMLS ID Used"] = fallback_ids
                result.table.loc[fallback_ids[fallback_ids != ""].index, "NMLS Match Method"] = "Name+Company"
                enrichment = pd.concat([enrichment, fallback_enrichment], ignore_index=True)
                enrichment = enrichment.drop_duplicates(subset=["IndividualNMLSID"])

            result.table = nmls.merge_nmls_enrichment(result.table, enrichment, mlo_nmls_col="NMLS ID Used")
        except Exception as exc:  # noqa: BLE001 - surface driver/connection errors, don't fail the whole run
            print(f"[matcher] NMLS enrichment failed: {exc}", flush=True)
            result.table["NMLS FullName"] = ""
            result.table["NMLS RegulationType"] = ""
            result.table["NMLS LicensingStatus"] = ""
            result.table["NMLS LocationNMLSID"] = ""
            result.table["NMLS LocationName"] = ""

    print("[matcher] Writing Excel...", flush=True)
    token = uuid.uuid4().hex
    out_path = os.path.join(RESULTS_DIR, f"{token}.xlsx")
    write_excel(result.table, out_path)
    print(f"[matcher] Ready: {out_path}", flush=True)

    nmls_cols = [c for c in ("NMLS Match Method", "NMLS FullName", "NMLS RegulationType", "NMLS LicensingStatus",
                              "NMLS LocationNMLSID", "NMLS LocationName")
                 if c in result.table.columns]
    preview_cols = list(result.table.columns[:10]) + [c for c in nmls_cols if c not in result.table.columns[:10]]
    preview_rows = safe_str_frame(result.table[preview_cols].head(200)).values.tolist()

    return render_template(
        "results.html",
        detected_fields=result.detected_fields,
        summary=result.summary,
        preview_cols=preview_cols,
        preview_rows=preview_rows,
        download_token=token,
    )


@app.route("/api/contacts", methods=["POST", "OPTIONS"])
def api_contacts():
    if request.method == "OPTIONS":
        return "", 204

    print("[matcher] (extension) Fetching CRM Contacts live...", flush=True)
    try:
        raw = db.fetch_contacts()
        print(f"[matcher] (extension) Got {len(raw)} contact rows.", flush=True)
        standardized = loaders.standardize_db_contacts(raw)
    except Exception as exc:  # noqa: BLE001 - surface driver/connection errors to the caller
        print(f"[matcher] (extension) Contacts fetch failed: {exc}", flush=True)
        return jsonify(error=str(exc)), 500
    return jsonify(rows=safe_str_frame(standardized).to_dict(orient="records"))


@app.route("/api/leads", methods=["POST", "OPTIONS"])
def api_leads():
    if request.method == "OPTIONS":
        return "", 204

    print("[matcher] (extension) Fetching CRM Leads live...", flush=True)
    try:
        raw = db.fetch_leads()
        print(f"[matcher] (extension) Got {len(raw)} lead rows.", flush=True)
        standardized = loaders.standardize_db_leads(raw)
    except Exception as exc:  # noqa: BLE001 - surface driver/connection errors to the caller
        print(f"[matcher] (extension) Leads fetch failed: {exc}", flush=True)
        return jsonify(error=str(exc)), 500
    return jsonify(rows=safe_str_frame(standardized).to_dict(orient="records"))


@app.route("/api/nmls", methods=["POST", "OPTIONS"])
def api_nmls():
    if request.method == "OPTIONS":
        return "", 204

    payload = request.get_json(silent=True) or {}
    ids = payload.get("ids") or []
    print(f"[matcher] (extension) Enriching {len(ids)} MLO NMLS id(s)...", flush=True)
    try:
        enrichment = nmls.fetch_nmls_enrichment(ids)
        print(f"[matcher] (extension) NMLS returned {len(enrichment)} matched individual(s).", flush=True)
    except Exception as exc:  # noqa: BLE001 - surface driver/connection errors to the caller
        print(f"[matcher] (extension) NMLS enrichment failed: {exc}", flush=True)
        return jsonify(error=str(exc)), 500
    return jsonify(rows=safe_str_frame(enrichment).to_dict(orient="records"))


@app.route("/download/<token>")
def download(token: str):
    safe_token = "".join(c for c in token if c.isalnum())
    path = os.path.join(RESULTS_DIR, f"{safe_token}.xlsx")
    if not os.path.isfile(path):
        return "Result not found or expired.", 404
    return send_file(path, as_attachment=True, download_name="tradeshow_vs_crm_matches.xlsx")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
