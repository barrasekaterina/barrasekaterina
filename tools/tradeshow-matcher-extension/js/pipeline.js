// End-to-end pipeline: tradeshow file + CRM exports -> enriched result rows.
// Ported from Python matcher/pipeline.py. There is no business-card (BC)
// input or matching path anywhere in this tool.
(function (global) {
  "use strict";

  const CRM_CONTACT_URL = "https://crm.admortgage.com/crm/contact/details/{id}/";
  const CRM_LEAD_URL = "https://crm.admortgage.com/crm/lead/details/{id}/";

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
  // crmLeadsFile when both are given for the same source.
  async function runPipeline({
    tradeshowFile,
    crmContactsFile,
    crmLeadsFile,
    crmContactsRows,
    crmLeadsRows,
  }) {
    const { rows: tradeshow, detectedFields } = await Loaders.loadTradeshowFile(tradeshowFile);

    const crmContacts = crmContactsRows || (crmContactsFile ? await Loaders.loadCrmContacts(crmContactsFile) : null);
    const crmLeads = crmLeadsRows || (crmLeadsFile ? await Loaders.loadCrmLeads(crmLeadsFile) : null);

    const contactMatches = crmContacts ? Matching.matchTradeshowToCrm(tradeshow, crmContacts, detectedFields) : [];
    const leadMatches = crmLeads ? Matching.matchTradeshowToCrm(tradeshow, crmLeads, detectedFields) : [];

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
