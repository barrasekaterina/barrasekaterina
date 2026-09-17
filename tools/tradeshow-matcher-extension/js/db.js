// Client for the local Flask backend's /api/contacts, /api/leads, and
// /api/nmls endpoints (tools/tradeshow-matcher/app.py). This exists because
// a browser extension cannot open a direct SQL Server connection itself -
// the actual pyodbc connection happens in that local backend, which must
// be running on this machine. All three endpoints authenticate via
// Windows Integrated Auth server-side, so no credentials are collected or
// sent from here at all.
(function (global) {
  "use strict";

  async function postJson(url, body) {
    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
    } catch (err) {
      throw new Error(
        `Could not reach ${url} - is the local matcher backend running? ` +
          `(cd tools/tradeshow-matcher && python app.py) Details: ${err.message || err}`
      );
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.error) {
      throw new Error(data.error || `Request to ${url} failed (HTTP ${response.status}).`);
    }
    return data.rows || [];
  }

  async function fetchContactsLive(backendUrl) {
    return postJson(`${backendUrl.replace(/\/$/, "")}/api/contacts`, {});
  }

  async function fetchLeadsLive(backendUrl) {
    return postJson(`${backendUrl.replace(/\/$/, "")}/api/leads`, {});
  }

  async function fetchNmlsEnrichmentLive(backendUrl, { ids }) {
    return postJson(`${backendUrl.replace(/\/$/, "")}/api/nmls`, { ids });
  }

  // Counterpart to /api/nmls for attendees with no CRM match at all (so no
  // MLO NMLS id to look up directly): fuzzy-matches Name+Company against
  // NMLS itself. Returns {ids, enrichment} instead of just rows, since
  // postJson's `rows || []` unwrapping doesn't fit this endpoint's shape.
  async function fetchNmlsFallbackLive(backendUrl, { attendees }) {
    const url = `${backendUrl.replace(/\/$/, "")}/api/nmls-fallback`;
    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ attendees }),
      });
    } catch (err) {
      throw new Error(
        `Could not reach ${url} - is the local matcher backend running? ` +
          `(cd tools/tradeshow-matcher && python app.py) Details: ${err.message || err}`
      );
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.error) {
      throw new Error(data.error || `Request to ${url} failed (HTTP ${response.status}).`);
    }
    return { ids: data.ids || [], enrichment: data.enrichment || [] };
  }

  global.DbClient = { fetchContactsLive, fetchLeadsLive, fetchNmlsEnrichmentLive, fetchNmlsFallbackLive };
})(typeof window !== "undefined" ? window : globalThis);
