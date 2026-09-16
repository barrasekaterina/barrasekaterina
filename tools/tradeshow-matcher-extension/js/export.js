// Turn the result table into a downloadable file.
//
// Note: the free/community build of SheetJS (vendored in lib/) can write
// hyperlinks but not cell fill colors - so unlike the Python tool's Excel
// export, the Status column here is not color-coded. CSV export has no
// styling either way. This is a known, documented gap versus the Python
// version; a paid SheetJS Pro build could restore the coloring if needed.
(function (global) {
  "use strict";

  function allColumns(table) {
    if (!table.length) return [];
    const cols = new Set();
    table.forEach((row) => Object.keys(row).forEach((k) => cols.add(k)));
    // Drop internal bookkeeping fields not meant for export.
    ["isContactMatch", "contactFullMatch", "isLeadMatch", "Contact CRM ID", "Lead CRM ID"].forEach((k) =>
      cols.delete(k)
    );
    return Array.from(cols);
  }

  function orderedColumns(displayCols, table) {
    const rest = allColumns(table).filter((c) => !displayCols.includes(c));
    return [...displayCols, ...rest];
  }

  function toCsvBlob(table, displayCols) {
    const cols = orderedColumns(displayCols, table);
    const rows = table.map((row) => cols.map((c) => row[c] ?? ""));
    const ws = XLSX.utils.aoa_to_sheet([cols, ...rows]);
    const csv = XLSX.utils.sheet_to_csv(ws);
    return new Blob([csv], { type: "text/csv;charset=utf-8;" });
  }

  function toXlsxBlob(table, displayCols) {
    const cols = orderedColumns(displayCols, table);
    const rows = table.map((row) => cols.map((c) => row[c] ?? ""));
    const ws = XLSX.utils.aoa_to_sheet([cols, ...rows]);

    ["Contact CRM Link", "Lead CRM Link"].forEach((linkCol) => {
      const colIdx = cols.indexOf(linkCol);
      if (colIdx === -1) return;
      table.forEach((row, rowIdx) => {
        const url = row[linkCol];
        if (!url) return;
        const cellRef = XLSX.utils.encode_cell({ r: rowIdx + 1, c: colIdx });
        if (ws[cellRef]) ws[cellRef].l = { Target: url };
      });
    });

    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, ws, "Sheet1");
    const out = XLSX.write(wb, { bookType: "xlsx", type: "array" });
    return new Blob([out], { type: "application/octet-stream" });
  }

  function downloadBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  global.Export = { toCsvBlob, toXlsxBlob, downloadBlob, orderedColumns };
})(typeof window !== "undefined" ? window : globalThis);
