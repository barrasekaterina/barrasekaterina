// Shared cleaning helpers - ported from the Python matcher/cleaning.py.
// No business-card (BC) logic exists here, same as the Python version.
(function (global) {
  "use strict";

  const EXT_PATTERN = /(?:ext|Ext|#)([^,]*)/;
  const EXT_STRIP_PATTERN = /(ext|Ext)[^,]*/g;
  const HASH_STRIP_PATTERN = /#[^,]*/g;
  const OFFICE_STRIP_PATTERN = /Office:[^,]*/g;
  const SYMBOLS_TO_REMOVE = /[+\-() .]/g;

  function cleanPhone(value) {
    if (value == null) return "";
    let s = String(value);
    s = s.replace(EXT_STRIP_PATTERN, "").replace(HASH_STRIP_PATTERN, "").replace(OFFICE_STRIP_PATTERN, "");
    if (!s.trim() || s.toLowerCase() === "nan") return "";
    const cleaned = s
      .split(", ")
      .map((part) => part.trim())
      .filter(Boolean)
      .map((part) => part.replace(SYMBOLS_TO_REMOVE, ""));
    let result = cleaned.join(", ");
    if (result.startsWith("1")) result = result.slice(1);
    return result;
  }

  function extractExtension(value) {
    if (value == null) return "";
    const match = EXT_PATTERN.exec(String(value));
    return match ? `Ext${match[1].trim()}` : "";
  }

  function normalizePhoneSet(phoneStr) {
    const out = new Set();
    if (!phoneStr) return out;
    String(phoneStr)
      .replace(/\s+/g, "")
      .split(",")
      .forEach((num) => {
        const digits = num.replace(/\D/g, "");
        if (digits.length >= 10) out.add(digits.slice(-10));
      });
    return out;
  }

  function splitFullName(fullName) {
    const parts = String(fullName || "").trim().split(/\s+/).filter(Boolean);
    if (parts.length > 1) return [parts[0], parts[parts.length - 1]];
    if (parts.length === 1) return [parts[0], ""];
    return ["", ""];
  }

  function buildFullName(first, last) {
    const f = (first || "").toString().toLowerCase();
    const l = (last || "").toString().toLowerCase();
    return `${f} ${l}`.trim();
  }

  function combineNonEmpty(row, columns, sep = ", ") {
    const parts = columns
      .map((c) => row[c])
      .filter((v) => v != null && String(v).trim() !== "" && String(v).trim() !== "0");
    return parts.join(sep);
  }

  global.Cleaning = {
    cleanPhone,
    extractExtension,
    normalizePhoneSet,
    splitFullName,
    buildFullName,
    combineNonEmpty,
  };
})(typeof window !== "undefined" ? window : globalThis);
