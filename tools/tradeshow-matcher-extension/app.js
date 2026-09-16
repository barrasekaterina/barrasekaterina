(function () {
  "use strict";

  const form = document.getElementById("match-form");
  const errorBox = document.getElementById("error");
  const uploadCard = document.querySelector("main.card:not(.wide)");
  const resultsCard = document.getElementById("results");
  let lastResult = null;

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function clearError() {
    errorBox.hidden = true;
    errorBox.textContent = "";
  }

  function renderSummary(summary) {
    const items = [
      ["Attendees", summary.totalAttendees],
      ["Matched Contacts", summary.matchedContacts],
      ["Matched Leads", summary.matchedLeads],
      ["Duplicates", summary.duplicates],
      ["New Contacts", summary.newContacts],
      ["Personal Emails", summary.personalEmails],
    ];
    const el = document.getElementById("summary");
    el.innerHTML = items.map(([label, value]) => `<div><span>${value}</span>${label}</div>`).join("");
  }

  function renderPreview(table, displayCols) {
    const cols = Export.orderedColumns(displayCols, table).slice(0, 10);
    const head = document.getElementById("preview-head");
    head.innerHTML = cols.map((c) => `<th>${escapeHtml(c)}</th>`).join("");

    const body = document.getElementById("preview-body");
    const rows = table.slice(0, 200);
    body.innerHTML = rows
      .map((row) => `<tr>${cols.map((c) => `<td>${escapeHtml(row[c] ?? "")}</td>`).join("")}</tr>`)
      .join("");
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  const progressBox = document.getElementById("progress");
  function showProgress(text) {
    progressBox.innerHTML = `<span class="spinner"></span><span>${escapeHtml(text)}</span>`;
    progressBox.hidden = false;
  }
  function hideProgress() {
    progressBox.hidden = true;
    progressBox.innerHTML = "";
  }

  const dbFieldsBox = document.getElementById("db-fields");
  function anyLiveSourceSelected() {
    return (
      document.querySelector('input[name="crm_contacts_source"]:checked').value === "live" ||
      document.querySelector('input[name="crm_leads_source"]:checked').value === "live"
    );
  }
  function refreshSourceVisibility() {
    document.getElementById("contacts-upload").hidden =
      document.querySelector('input[name="crm_contacts_source"]:checked').value === "live";
    document.getElementById("leads-upload").hidden =
      document.querySelector('input[name="crm_leads_source"]:checked').value === "live";
    dbFieldsBox.hidden = !anyLiveSourceSelected();
  }
  document.querySelectorAll('input[name="crm_contacts_source"], input[name="crm_leads_source"]').forEach((el) => {
    el.addEventListener("change", refreshSourceVisibility);
  });
  refreshSourceVisibility();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearError();

    const tradeshowFile = document.getElementById("tradeshow_file").files[0];
    if (!tradeshowFile) {
      showError("Please choose a tradeshow file.");
      return;
    }

    const contactsSource = document.querySelector('input[name="crm_contacts_source"]:checked').value;
    const leadsSource = document.querySelector('input[name="crm_leads_source"]:checked').value;
    const backendUrl = document.getElementById("db_backend_url").value.trim();
    const dbServer = document.getElementById("db_server").value.trim() || undefined;

    const runBtn = document.getElementById("run-btn");
    runBtn.disabled = true;
    runBtn.textContent = "Running...";

    try {
      let crmContactsFile = null;
      let crmContactsRows = null;
      let crmLeadsFile = null;
      let crmLeadsRows = null;

      if (contactsSource === "live") {
        showProgress("Fetching CRM Contacts from the local backend...");
        crmContactsRows = await DbClient.fetchContactsLive(backendUrl, { server: dbServer });
      } else {
        crmContactsFile = document.getElementById("crm_contacts_file").files[0] || null;
      }

      if (leadsSource === "live") {
        showProgress("Fetching CRM Leads from the local backend...");
        crmLeadsRows = await DbClient.fetchLeadsLive(backendUrl, { server: dbServer });
      } else {
        crmLeadsFile = document.getElementById("crm_leads_file").files[0] || null;
      }

      const result = await Pipeline.runPipeline({
        tradeshowFile,
        crmContactsFile,
        crmLeadsFile,
        crmContactsRows,
        crmLeadsRows,
        onProgress: showProgress,
      });
      lastResult = result;

      document.getElementById("detected-fields").textContent = result.detectedFields.length
        ? ", " + result.detectedFields.map((f) => f).join(", ")
        : "";
      renderSummary(result.summary);
      renderPreview(result.table, result.displayCols);

      uploadCard.hidden = true;
      resultsCard.hidden = false;
    } catch (err) {
      showError(err.message || String(err));
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = "Run matching";
      hideProgress();
    }
  });

  document.getElementById("download-csv").addEventListener("click", () => {
    if (!lastResult) return;
    const blob = Export.toCsvBlob(lastResult.table, lastResult.displayCols);
    Export.downloadBlob(blob, "tradeshow_vs_crm_matches.csv");
  });

  document.getElementById("download-xlsx").addEventListener("click", () => {
    if (!lastResult) return;
    const blob = Export.toXlsxBlob(lastResult.table, lastResult.displayCols);
    Export.downloadBlob(blob, "tradeshow_vs_crm_matches.xlsx");
  });

  document.getElementById("run-another").addEventListener("click", () => {
    form.reset();
    lastResult = null;
    resultsCard.hidden = true;
    uploadCard.hidden = false;
    refreshSourceVisibility();
  });
})();
