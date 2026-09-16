// File parsing + standardization - ported from Python matcher/loaders.py.
// Only two source kinds: a tradeshow attendee list, and CRM exports
// (contacts / leads). No business-card (BC) input path exists here.
(function (global) {
  "use strict";

  const TRADESHOW_ALIASES = {
    "full name": "Full Name",
    name: "Full Name",
    "attendee name": "Full Name",
    "contact name": "Full Name",
    "company name": "Company Name",
    company: "Company Name",
    organization: "Company Name",
    employer: "Company Name",
    phone: "Phone",
    "phone number": "Phone",
    mobile: "Phone",
    "mobile phone": "Phone",
    cell: "Phone",
    telephone: "Phone",
    email: "Email",
    "e-mail": "Email",
    "email address": "Email",
    "job title": "Job Title",
    title: "Job Title",
    position: "Job Title",
  };

  const OPTIONAL_MATCH_FIELDS = ["Company Name", "Phone", "Email"];

  function readWorkbookRows(workbook) {
    const sheetName = workbook.SheetNames[0];
    const sheet = workbook.Sheets[sheetName];
    return XLSX.utils.sheet_to_json(sheet, { defval: "", raw: false });
  }

  async function parseSpreadsheetFile(file, { delimiter } = {}) {
    const name = file.name.toLowerCase();
    if (name.endsWith(".csv")) {
      const text = await file.text();
      const wb = XLSX.read(text, { type: "string", FS: delimiter || "," });
      return readWorkbookRows(wb);
    }
    if (name.endsWith(".xlsx") || name.endsWith(".xls")) {
      const buf = await file.arrayBuffer();
      const wb = XLSX.read(buf, { type: "array" });
      return readWorkbookRows(wb);
    }
    throw new Error(`Unsupported file type: ${file.name}`);
  }

  function renameWithAliases(rows, aliasMap) {
    return rows.map((row) => {
      const out = {};
      for (const [key, value] of Object.entries(row)) {
        const canonical = aliasMap[String(key).trim().toLowerCase()];
        out[canonical || key] = value;
      }
      return out;
    });
  }

  async function loadTradeshowFile(file) {
    const raw = await parseSpreadsheetFile(file);
    const rows = renameWithAliases(raw, TRADESHOW_ALIASES);

    if (!rows.length || !("Full Name" in rows[0])) {
      throw new Error(
        `Could not find a "Full Name" column in the tradeshow file. Columns found: ${
          raw.length ? Object.keys(raw[0]).join(", ") : "(no rows)"
        }`
      );
    }

    const detected = new Set();
    rows.forEach((row) => {
      OPTIONAL_MATCH_FIELDS.forEach((f) => {
        if (String(row[f] ?? "").trim() !== "") detected.add(f);
      });
    });

    const standardized = rows.map((row) => {
      const fullNameRaw = String(row["Full Name"] || "").trim();
      const [first, last] = Cleaning.splitFullName(fullNameRaw);
      const out = {
        "Full Name": Cleaning.buildFullName(first, last),
        "First Name": first.toLowerCase(),
        "Last Name": last.toLowerCase(),
        "Company Name": detected.has("Company Name") ? String(row["Company Name"] || "").trim() : "",
        Phone: "",
        Extension: "",
        Email: detected.has("Email") ? String(row["Email"] || "").trim().toLowerCase() : "",
        "Job Title": String(row["Job Title"] || ""),
      };
      if (detected.has("Phone")) {
        const rawPhone = String(row["Phone"] || "");
        out.Extension = Cleaning.extractExtension(rawPhone);
        out.Phone = Cleaning.cleanPhone(rawPhone);
      }
      return out;
    });

    return { rows: standardized, detectedFields: Array.from(detected) };
  }

  const CONTACT_EMAIL_COLS = ["Work E-mail", "Home E-mail", "Other E-mail"];
  const CONTACT_PHONE_COLS = ["Work Phone", "Mobile", "Fax", "Home Phone", "Other Phone Number"];

  async function loadCrmContacts(file) {
    const raw = await parseSpreadsheetFile(file, { delimiter: ";" });
    return raw.map((row) => {
      const email = Cleaning.combineNonEmpty(row, CONTACT_EMAIL_COLS).toLowerCase();
      const rawPhone = Cleaning.combineNonEmpty(row, CONTACT_PHONE_COLS);
      const first = String(row["First Name"] || "").split(" ")[0] || "";
      const lastParts = String(row["Last Name"] || "").split(" ");
      const last = lastParts[lastParts.length - 1] || "";
      return {
        "First Name": first.toLowerCase(),
        "Last Name": last.toLowerCase(),
        "Full Name": Cleaning.buildFullName(first, last),
        Status: row["Status"] || "",
        "Company Name": row["Company"] || "",
        Responsible: row["Responsible"] || "",
        Extension: Cleaning.extractExtension(rawPhone),
        Phone: Cleaning.cleanPhone(rawPhone),
        Email: email,
        Company_NMLS: row["Company NMLS"] || "",
        MLO_NMLS: row["MLO’s NMLS"] || row["MLO's NMLS"] || "",
        ID: row["ID"] || "",
      };
    });
  }

  const LEAD_EMAIL_COLS = ["Work E-mail", "Home E-mail", "Other E-mail"];
  const LEAD_PHONE_COLS = ["Work Phone", "Mobile", "Fax", "Home Phone", "Other Phone Number"];

  async function loadCrmLeads(file) {
    const raw = await parseSpreadsheetFile(file, { delimiter: ";" });
    return raw.map((row) => {
      const email = Cleaning.combineNonEmpty(row, LEAD_EMAIL_COLS).toLowerCase();
      const rawPhone = Cleaning.combineNonEmpty(row, LEAD_PHONE_COLS);
      const [first, last] = Cleaning.splitFullName(row["Lead Name"] || "");
      return {
        "First Name": first.toLowerCase(),
        "Last Name": last.toLowerCase(),
        "Full Name": Cleaning.buildFullName(first, last),
        "Company Name": row["Lead Companies"] || "",
        Responsible: row["Responsible"] || "",
        Extension: Cleaning.extractExtension(rawPhone),
        Phone: Cleaning.cleanPhone(rawPhone),
        Email: email,
        Company_NMLS: row["Company NMLS"] || "",
        MLO_NMLS: row["NMLS MLOs"] || "",
        Stage: row["Stage"] || "",
        "Additional Lead Type": row["Additional Lead Type"] || "",
        "Lead Type": row["Lead Type"] || "",
        Source: row["Source"] || "",
        ID: row["ID"] || "",
      };
    });
  }

  global.Loaders = { loadTradeshowFile, loadCrmContacts, loadCrmLeads, OPTIONAL_MATCH_FIELDS };
})(typeof window !== "undefined" ? window : globalThis);
