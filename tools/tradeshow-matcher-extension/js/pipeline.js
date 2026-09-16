// End-to-end pipeline: tradeshow file + CRM exports -> enriched result rows.
// Ported from Python matcher/pipeline.py. There is no business-card (BC)
// input or matching path anywhere in this tool.
(function (global) {
  "use strict";

  const CRM_CONTACT_URL = "https://crm.admortgage.com/crm/contact/details/{id}/";
  const CRM_LEAD_URL = "https://crm.admortgage.com/crm/lead/details/{id}/";

  // A synchronous matching pass over a large CRM export can take long
  // enough to block the main thread; without a yield here, the browser
  // won't repaint the progress text set just before it, so it looks frozen
  // rather than showing what it's doing.
  function yieldToUi() {
    return new Promise((resolve) => setTimeout(resolve, 0));
  }

  function aggregateBestMatchPerAttendee(matches) {
    const best = new Map();
    matches.forEach((m) => {
      const key = m.tradeshowIndex;
      const prev = best.get(key);
      if (!prev || m.totalScore > prev.totalScore) best.set(key, m);
    });
    return best;
  }

  // crmContactsRows / crmLeadsRows let a caller (e.g. the live-DB path in
  // app.js, which fetches already-standardized rows from the local Flask
  // backend) skip file parsing entirely. They win over crmContactsFile /
  // crmLeadsFile when both are given for the same source. onProgress(text)
  // is called before each stage so the UI can show what's happening.
  async function runPipeline({
    tradeshowFile,
    crmContactsFile,
    crmLeadsFile,
    crmContactsRows,
    crmLeadsRows,
    onProgress = () => {},
  }) {
    onProgress("Reading tradeshow file...");
    const { rows: tradeshow, detectedFields } = await Loaders.loadTradeshowFile(tradeshowFile);

    let crmContacts = crmContactsRows || null;
    if (!crmContacts && crmContactsFile) {
      onProgress("Reading CRM Contacts file...");
      crmContacts = await Loaders.loadCrmContacts(crmContactsFile);
    }
    let crmLeads = crmLeadsRows || null;
    if (!crmLeads && crmLeadsFile) {
      onProgress("Reading CRM Leads file...");
      crmLeads = await Loaders.loadCrmLeads(crmLeadsFile);
    }

    let contactMatches = [];
    if (crmContacts) {
      onProgress(`Matching ${tradeshow.length} attendees against ${crmContacts.length} CRM Contacts...`);
      await yieldToUi();
      contactMatches = Matching.matchTradeshowToCrm(tradeshow, crmContacts, detectedFields);
    }

    let leadMatches = [];
    if (crmLeads) {
      onProgress(`Matching ${tradeshow.length} attendees against ${crmLeads.length} CRM Leads...`);
      await yieldToUi();
      leadMatches = Matching.matchTradeshowToCrm(tradeshow, crmLeads, detectedFields);
    }

    const bestContact = aggregateBestMatchPerAttendee(contactMatches);
    const bestLead = aggregateBestMatchPerAttendee(leadMatches);

    let result = tradeshow.map((row, idx) => {
      const cm = bestContact.get(idx);
      const lm = bestLead.get(idx);
      return {
        ...row,
        isContactMatch: !!cm,
        contactFullMatch: !!cm && cm.bestMatchLabel === "Name Match",
        isLeadMatch: !!lm,
        "Contact CRM ID": cm ? cm.crm.ID || "" : "",
        "Lead CRM ID": lm ? lm.crm.ID || "" : "",
      };
    });

    onProgress("Categorizing job titles, flagging duplicates and new contacts...");
    await yieldToUi();
    const crmDomains = crmContacts ? Enrich.crmEmailDomains(crmContacts) : new Set();
    result = Enrich.enrichAndScoreStatus(result, !!crmContacts, !!crmLeads, crmDomains);

    result = result.map((row) => ({
      ...row,
      "Contact CRM Link": row["Contact CRM ID"] ? CRM_CONTACT_URL.replace("{id}", row["Contact CRM ID"]) : "",
      "Lead CRM Link": row["Lead CRM ID"] ? CRM_LEAD_URL.replace("{id}", row["Lead CRM ID"]) : "",
    }));

    const displayCols = [
      "Status", "Full Name", "Company Name", "Phone", "Email", "Job Title",
      "Job_Category", "Banks and Credit Unions", "Duplicate", "New Contact",
      "Contact CRM Link", "Lead CRM Link",
    ].filter((c) => c in (result[0] || {}));

    const summary = {
      totalAttendees: result.length,
      matchedContacts: result.filter((r) => r.isContactMatch).length,
      matchedLeads: result.filter((r) => r.isLeadMatch).length,
      duplicates: result.filter((r) => r.Duplicate === "Duplicate").length,
      newContacts: result.filter((r) => r["New Contact"] === "New Contact").length,
      personalEmails: result.filter((r) => r["New Contact"] === "personal_email").length,
    };

    return { detectedFields, table: result, displayCols, summary };
  }

  global.Pipeline = { runPipeline };
})(typeof window !== "undefined" ? window : globalThis);
