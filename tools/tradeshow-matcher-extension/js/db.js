// Client for the local Flask backend's /api/contacts and /api/leads
// endpoints (tools/tradeshow-matcher/app.py). This exists because a
// browser extension cannot open a direct SQL Server connection itself -
// the actual pyodbc connection happens in that local backend, which must
// be running on this machine. Credentials are only ever held in memory for
// the duration of one fetch() call; nothing here writes them to disk,
// chrome.storage, or logs them.
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

  async function fetchContactsLive(backendUrl, { server, uid, pwd }) {
    return postJson(`${backendUrl.replace(/\/$/, "")}/api/contacts`, { server, uid, pwd });
  }

  async function fetchLeadsLive(backendUrl, { server }) {
    return postJson(`${backendUrl.replace(/\/$/, "")}/api/leads`, { server });
  }

  global.DbClient = { fetchContactsLive, fetchLeadsLive };
})(typeof window !== "undefined" ? window : globalThis);
