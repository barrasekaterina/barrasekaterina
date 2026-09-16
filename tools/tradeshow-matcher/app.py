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

from flask import Flask, jsonify, render_template, request, send_file

from matcher import db, loaders
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
            server = request.form.get("db_server") or None
            print(f"[matcher] Fetching CRM Contacts live from {server or 'default server'}...", flush=True)
            raw = db.fetch_contacts(server=server)
            print(f"[matcher] Got {len(raw)} contact rows, standardizing...", flush=True)
            crm_contacts_df = loaders.standardize_db_contacts(raw)
        else:
            uploaded = request.files.get("crm_contacts_file")
            if uploaded and uploaded.filename:
                crm_contacts_file = io.BytesIO(uploaded.read())

        if request.form.get("crm_leads_source") == "live":
            server = request.form.get("db_server") or None
            print(f"[matcher] Fetching CRM Leads live from {server or 'default server'}...", flush=True)
            raw = db.fetch_leads(server=server)
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
        f"{result.summary['matched_leads']} matched leads. Writing Excel...",
        flush=True,
    )
    token = uuid.uuid4().hex
    out_path = os.path.join(RESULTS_DIR, f"{token}.xlsx")
    write_excel(result.table, out_path)
    print(f"[matcher] Ready: {out_path}", flush=True)

    preview_cols = list(result.table.columns[:10])
    preview_rows = result.table[preview_cols].head(200).fillna("").astype(str).values.tolist()

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

    payload = request.get_json(silent=True) or {}
    server = payload.get("server") or None
    print(f"[matcher] (extension) Fetching CRM Contacts live from {server or 'default server'}...", flush=True)
    try:
        raw = db.fetch_contacts(server=server)
        print(f"[matcher] (extension) Got {len(raw)} contact rows.", flush=True)
        standardized = loaders.standardize_db_contacts(raw)
    except Exception as exc:  # noqa: BLE001 - surface driver/connection errors to the caller
        print(f"[matcher] (extension) Contacts fetch failed: {exc}", flush=True)
        return jsonify(error=str(exc)), 500
    return jsonify(rows=standardized.fillna("").to_dict(orient="records"))


@app.route("/api/leads", methods=["POST", "OPTIONS"])
def api_leads():
    if request.method == "OPTIONS":
        return "", 204

    payload = request.get_json(silent=True) or {}
    server = payload.get("server") or None
    print(f"[matcher] (extension) Fetching CRM Leads live from {server or 'default server'}...", flush=True)
    try:
        raw = db.fetch_leads(server=server)
        print(f"[matcher] (extension) Got {len(raw)} lead rows.", flush=True)
        standardized = loaders.standardize_db_leads(raw)
    except Exception as exc:  # noqa: BLE001 - surface driver/connection errors to the caller
        print(f"[matcher] (extension) Leads fetch failed: {exc}", flush=True)
        return jsonify(error=str(exc)), 500
    return jsonify(rows=standardized.fillna("").to_dict(orient="records"))


@app.route("/download/<token>")
def download(token: str):
    safe_token = "".join(c for c in token if c.isalnum())
    path = os.path.join(RESULTS_DIR, f"{safe_token}.xlsx")
    if not os.path.isfile(path):
        return "Result not found or expired.", 404
    return send_file(path, as_attachment=True, download_name="tradeshow_vs_crm_matches.xlsx")


if __name__ == "__main__":
    app.run(debug=True, port=5050)
