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
        "MLO NMLS": (cm && cm.crm.MLO_NMLS) || (lm && lm.crm.MLO_NMLS) || "",
        "Matched Fields": (cm && cm.matchedFields) || (lm && lm.matchedFields) || "",
      };
    });

    // Attendees with no CRM Contact/Lead match at all still might work
    // for an already-known company (a known account, just a new person
    // there) rather than being a wholly new prospect - check their
    // Company Name against every company seen across CRM Contacts +
    // Leads combined.
    const knownCompanyNames = [
      ...(crmContacts || []).map((r) => r["Company Name"]),
      ...(crmLeads || []).map((r) => r["Company Name"]),
    ].filter(Boolean);
    const unmatchedIdxs = [];
    result.forEach((row, idx) => {
      if (!row.isContactMatch && !row.isLeadMatch) unmatchedIdxs.push(idx);
    });
    const companyKnown = Matching.findKnownCompanies(
      unmatchedIdxs.map((idx) => result[idx]),
      knownCompanyNames
    );
    // findKnownCompanies returns positions into the array we gave it
    // (0..unmatchedIdxs.length-1), not the original result indices -
    // translate back so Enrich can look rows up by their real index.
    const companyKnownByResultIdx = new Set([...companyKnown].map((pos) => unmatchedIdxs[pos]));

    onProgress("Categorizing job titles, flagging duplicates and new contacts...");
    await yieldToUi();
    const crmDomains = crmContacts ? Enrich.crmEmailDomains(crmContacts) : new Set();
    result = Enrich.enrichAndScoreStatus(result, crmDomains, companyKnownByResultIdx);

    result = result.map((row) => ({
      ...row,
      "Contact CRM Link": row["Contact CRM ID"] ? CRM_CONTACT_URL.replace("{id}", row["Contact CRM ID"]) : "",
      "Lead CRM Link": row["Lead CRM ID"] ? CRM_LEAD_URL.replace("{id}", row["Lead CRM ID"]) : "",
      "Found in Contacts": row.isContactMatch ? "Yes" : "No",
      "Found in Leads": row.isLeadMatch ? "Yes" : "No",
      "Found in CRM": row.isContactMatch || row.isLeadMatch ? "Yes" : "No",
    }));

    // Match Confidence grades *what kind* of evidence backs the Status
    // conclusion, using one rule for every category: High when an
    // exact/near-exact identifier (Phone or Email) confirmed or ruled it
    // out, Medium when only fuzzy text (Name/Company) did, Low when
    // there was no usable data to compare at all.
    result = result.map((row) => {
      const base = row.Status.split(";")[0].trim();
      let confidence = "";
      let matchedBy = "";
      if (base === "Existing Contact" || base === "Existing Lead") {
        const fields = row["Matched Fields"];
        confidence = fields.includes("Phone") || fields.includes("Email") ? "High" : "Medium";
        matchedBy = fields;
      } else if (base === "New Contact") {
        confidence = "Medium";
        matchedBy = "Company (fuzzy)";
      } else {
        // New Lead: High if we had a Company Name to actually check
        // against CRM and it genuinely didn't match anything; Low if
        // there was no Company Name at all, so "New Lead" here just
        // means "unverifiable".
        confidence = String(row["Company Name"] || "").trim() ? "High" : "Low";
      }
      return { ...row, "Match Confidence": confidence, "Matched By": matchedBy };
    });

    const displayCols = [
      "Status", "Match Confidence", "Matched By",
      "Found in CRM", "Found in Contacts", "Found in Leads",
      "Full Name", "Company Name", "Phone", "Email", "Job Title",
      "Job_Category", "Banks and Credit Unions", "Duplicate", "Existing Domain",
      "Contact CRM Link", "Lead CRM Link", "MLO NMLS",
      "NMLS FullName", "NMLS RegulationType", "NMLS LicensingStatus", "NMLS LocationNMLSID", "NMLS LocationName",
    ].filter((c) => c in (result[0] || {}));

    const summary = {
      totalAttendees: result.length,
      matchedContacts: result.filter((r) => r.isContactMatch).length,
      matchedLeads: result.filter((r) => r.isLeadMatch).length,
      duplicates: result.filter((r) => r.Duplicate === "Duplicate").length,
      newContacts: result.filter((r) => r.Status.split(";")[0].trim() === "New Contact").length,
      newLeads: result.filter((r) => r.Status.split(";")[0].trim() === "New Lead").length,
      existingDomainMatches: result.filter((r) => r["Existing Domain"] === "Existing Domain").length,
      personalEmails: result.filter((r) => r["Existing Domain"] === "personal_email").length,
    };

    return { detectedFields, table: result, displayCols, summary };
  }

  // Left-join NMLS enrichment rows (from DbClient.fetchNmlsEnrichmentLive)
  // onto a pipeline result by the given id column - "MLO NMLS" (the direct
  // CRM-derived id) by default, or "NMLS ID Used" once the caller has also
  // resolved some rows through the name+company fallback. Mirrors
  // matcher.nmls.merge_nmls_enrichment's Python equivalent. Returns an
  // updated {table, displayCols}.
  function mergeNmlsEnrichment(pipelineResult, enrichmentRows, idKey = "MLO NMLS") {
    const byId = new Map(enrichmentRows.map((r) => [String(r.IndividualNMLSID), r]));
    const table = pipelineResult.table.map((row) => {
      const match = byId.get(String(row[idKey] || ""));
      return {
        ...row,
        "NMLS FullName": match ? match.FullName || "" : "",
        "NMLS RegulationType": match ? match.RegulationType || "" : "",
        "NMLS LicensingStatus": match ? match.LicensingStatus || "" : "",
        "NMLS LocationNMLSID": match ? match.LocationNMLSID || "" : "",
        "NMLS LocationName": match ? match.LocationName || "" : "",
      };
    });
    const displayCols = [...pipelineResult.displayCols];
    ["NMLS Match Method", "NMLS FullName", "NMLS RegulationType", "NMLS LicensingStatus", "NMLS LocationNMLSID", "NMLS LocationName"].forEach((c) => {
      if (!displayCols.includes(c) && c in (table[0] || {})) displayCols.push(c);
    });
    return { ...pipelineResult, table, displayCols };
  }

  global.Pipeline = { runPipeline, mergeNmlsEnrichment };
})(typeof window !== "undefined" ? window : globalThis);
