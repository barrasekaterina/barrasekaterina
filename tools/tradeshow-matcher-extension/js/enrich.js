// Post-match enrichment - ported from Python matcher/enrich.py.
// No "BC" business-card status tag exists here, same as the Python version.
(function (global) {
  "use strict";

  const JOB_TITLE_CATEGORIES = {
    "Owner/ CEO/ President": ["owner", "ceo", "president", "co-founder", "cofounder", "managing partner", "founder"],
    "Managing Broker": ["broker"],
    "Top Manager": ["coo", "director", "vp", "evp", "avp", "svp", "vice", "managing member", "team leader", "cfo"],
    "Branch Manager": ["branch manager", "regional manager", "branch mgr"],
    Processor: ["processor"],
    "Account Executive": [
      "business development manager",
      "business development regional mgr",
      "business development representative",
      "account executive",
      "ae",
      "acct exec",
    ],
    "Loan Officer": [
      "lo", "mlo", "loan advisor", "loan originator", "loan consultant", "senior mlo",
      "senior loan officer", "rmlo", "mortgage originator", "mortgage consultant",
      "originator", "mortgage planner", "mortgage advisor", "senior mortgage advisor",
    ],
    "Real Estate Agent": ["real estate agent", "realtor", "agent"],
    "Non-Relevant": [
      "event", "marketing", "sales rep", "assistant", "principal", "unknown", "recruiter",
      "project manager", "sales manager", "admin", "office manager", "escrow officer",
      "sales leader", "representative",
    ],
  };

  const PERSONAL_EMAIL_DOMAINS = [
    "gmail", "yahoo", "outlook", "hotmail", "aol", "icloud", "live", "mail", "msn",
    "yandex", "protonmail", "zoho", "gmx", "comcast", "verizon", "btinternet", "me.com",
    "mac", "mail.ru", "inbox", "rocketmail", "ymail", "fastmail", "tutanota", "hushmail",
    "seznam", "rambler", "libero", "alice", "sfr", "att", "bellsouth", "earthlink",
    "netzero", "juno",
  ];

  function escapeRegExp(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  // Requires a word boundary before each keyword, not a raw substring
  // check - a plain .includes() lets short keywords like "lo" match
  // inside unrelated words ("Unemployed", "Head of Business Development"
  // both contain "lo" mid-word, e.g. deve-LO-pment) and misclassify them.
  // No boundary is required *after* the keyword, so intentional prefix
  // matches keep working ("event" still matches "Events", "lo" still
  // matches "Loan Officer" since that "lo" starts a word).
  function categorizeJobTitle(title) {
    const t = (title || "").toLowerCase();
    for (const [category, keywords] of Object.entries(JOB_TITLE_CATEGORIES)) {
      if (keywords.some((kw) => new RegExp(`\\b${escapeRegExp(kw)}`).test(t))) return category;
    }
    return "Other";
  }

  function labelBankCreditUnion(organization) {
    const org = (organization || "").toLowerCase();
    if (org.includes("credit union") || org.includes(" uc ")) return "Bank/CU";
    if (org.includes("bank") && !org.includes("credit union") && !org.includes(" uc ")) return "Bank/CU";
    return null;
  }

  function crmEmailDomains(crmRows) {
    const domains = new Set();
    crmRows.forEach((row) => {
      const email = (row.Email || "").toLowerCase();
      const m = /@([^.]+)/.exec(email);
      if (m) domains.add(m[1]);
    });
    return domains;
  }

  function assignDomainFlag(domain, crmDomains) {
    if (!domain) return "";
    if (PERSONAL_EMAIL_DOMAINS.some((p) => domain.includes(p))) return "personal_email";
    if (crmDomains.has(domain)) return "New Contact";
    return "";
  }

  function appendTag(status, tag) {
    return status ? `${status}; ${tag}` : tag;
  }

  // rows: array of standardized tradeshow rows, already annotated with
  // isContactMatch / contactFullMatch / isLeadMatch by pipeline.js.
  function enrichAndScoreStatus(rows, hasContacts, hasLeads, crmContactsDomains) {
    const nameCounts = new Map();
    rows.forEach((r) => {
      const key = r["Full Name"];
      nameCounts.set(key, (nameCounts.get(key) || 0) + 1);
    });

    return rows.map((row) => {
      const out = { ...row };
      out.Job_Category = out["Job Title"] ? categorizeJobTitle(out["Job Title"]) : "";
      out["Banks and Credit Unions"] = out["Company Name"] ? labelBankCreditUnion(out["Company Name"]) : null;
      out.Duplicate = nameCounts.get(out["Full Name"]) > 1 ? "Duplicate" : null;

      const domain = out.Email ? (/@([^.]+)/.exec(out.Email.toLowerCase()) || [])[1] : null;
      out["New Contact"] = domain ? assignDomainFlag(domain, crmContactsDomains) : "";

      let status = "";
      if (hasContacts && out.isContactMatch) {
        status = out.contactFullMatch ? "Contact" : "Contact - Unchecked";
      } else if (hasLeads && out.isLeadMatch) {
        status = "Lead - Existing";
      }

      if (out.Job_Category === "Non-Relevant") status = appendTag(status, "Position");
      if (out.Job_Category === "Account Executive") status = appendTag(status, "Position");
      if (out["Banks and Credit Unions"] === "Bank/CU") status = appendTag(status, "Bank/CU");
      if (out["New Contact"] === "New Contact") status = appendTag(status, "New Contact");
      if (out["New Contact"] === "personal_email") status = appendTag(status, "personal_email");
      if (out.Duplicate === "Duplicate") status = appendTag(status, "Duplicate");

      out.Status = status;
      return out;
    });
  }

  global.Enrich = { categorizeJobTitle, labelBankCreditUnion, crmEmailDomains, assignDomainFlag, enrichAndScoreStatus };
})(typeof window !== "undefined" ? window : globalThis);
