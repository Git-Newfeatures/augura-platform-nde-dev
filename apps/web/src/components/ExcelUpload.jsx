import { useState, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

// Light per-column DQ stats — computed on the FULL data (not the 50-row sample).
// These feed the variable-check agent so its confidence reflects data reality,
// not just header heuristics.
function computeColumnStats(headers, rows) {
  if (!headers?.length || !rows?.length) return [];

  return headers.map((h, ci) => {
    const colName = String(h ?? "").trim();
    let nNonNull = 0;
    let nNumeric = 0;
    let nBool = 0;
    let nDate = 0;
    let nString = 0;
    let min = Infinity, max = -Infinity;
    const distinct = new Set();

    for (let i = 0; i < rows.length; i++) {
      const v = rows[i]?.[ci];
      if (v === "" || v === null || v === undefined) continue;
      nNonNull++;
      const s = String(v).trim();
      if (s === "") continue;

      // Distinct (cap memory for high-cardinality cols)
      if (distinct.size < 1000) distinct.add(s);

      // Type inference per cell
      const num = Number(s);
      const isNum = !isNaN(num) && /^-?\d+(\.\d+)?(e-?\d+)?$/i.test(s);
      const isBool = /^(true|false|yes|no|0|1)$/i.test(s);
      const isDate = !isNum && !isNaN(Date.parse(s)) && /\d{4}|\d{2}[-/]\d{2}/.test(s);

      if (isNum) {
        nNumeric++;
        if (num < min) min = num;
        if (num > max) max = num;
      } else if (isBool) {
        nBool++;
      } else if (isDate) {
        nDate++;
      } else {
        nString++;
      }
    }

    const nTotal = rows.length;
    const nullPct = nTotal > 0 ? (nTotal - nNonNull) / nTotal : 0;

    // Pick dominant type (>= 80% of non-null values)
    let valueKind = "mixed";
    const dom = Math.max(nNumeric, nBool, nDate, nString);
    if (nNonNull > 0 && dom / nNonNull >= 0.8) {
      if (dom === nNumeric) valueKind = "numeric";
      else if (dom === nBool) valueKind = "boolean";
      else if (dom === nDate) valueKind = "date";
      else valueKind = "string";
    } else if (nNonNull === 0) {
      valueKind = "empty";
    }

    const nDistinct = distinct.size;
    const top3 = valueKind === "string" || valueKind === "boolean"
      ? [...distinct].slice(0, 3)
      : null;

    return {
      column: colName,
      n_total: nTotal,
      n_non_null: nNonNull,
      null_pct: Number(nullPct.toFixed(4)),
      value_kind: valueKind,
      n_distinct: nDistinct,
      // For numeric only; otherwise null
      min: valueKind === "numeric" && nNumeric > 0 ? min : null,
      max: valueKind === "numeric" && nNumeric > 0 ? max : null,
      // For categorical/boolean — sample of distinct values
      top_values: top3,
    };
  });
}

export default function ExcelUpload({ onData, uploadedData }) {
  const [parsing, setParsing] = useState(false);
  const [error, setError]     = useState(null);
  const fileRef = useRef(null);

  async function loadXLSX() {
    if (window.XLSX) return window.XLSX;
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = "https://cdnjs.cloudflare.com/ajax/libs/xlsx/0.18.5/xlsx.full.min.js";
      s.onload = () => resolve(window.XLSX);
      s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  async function handleFile(file) {
    if (!file) return;
    const ext = file.name.split(".").pop().toLowerCase();
    if (!["xlsx","xls","csv"].includes(ext)) {
      setError("Unsupported format — use .xlsx, .xls, or .csv");
      return;
    }
    setParsing(true); setError(null);
    try {
      const XLSX = await loadXLSX();
      const buf  = await file.arrayBuffer();
      const wb   = XLSX.read(buf, { type:"array" });

      const sheets = wb.SheetNames.map(name => {
        const ws   = wb.Sheets[name];
        const rows = XLSX.utils.sheet_to_json(ws, { header:1, defval:"" });
        const isHeaderRow = r => r.filter(c => c !== "" && isNaN(c)).length >= Math.max(2, r.filter(c=>c!=="").length * 0.5);
        const headerIdx = rows.findIndex(r => isHeaderRow(r));
        const headers = headerIdx >= 0 ? rows[headerIdx] : (rows[0] || []);
        const fullData = (headerIdx >= 0 ? rows.slice(headerIdx + 1) : rows.slice(1))
          .filter(r => r.some(c => c !== ""));
        // Per-column stats computed on FULL data before truncation.
        const column_stats = computeColumnStats(headers, fullData);
        // totalRowCount = true row count BEFORE the 50-row cap. Sample (data) is
        // kept tiny so it can flow into agent prompts.
        return {
          name,
          headers,
          data: fullData.slice(0, 50),
          totalRowCount: fullData.length,
          column_stats,
        };
      });

      const summary = sheets.map(s => {
        const colList = s.headers.join(" | ");
        const preview = s.data.slice(0, 5).map(r => r.join(" | ")).join("\n");
        return `Sheet: ${s.name}\nColumns: ${colList}\nSample rows (up to 5):\n${preview}`;
      }).join("\n\n");

      onData({ filename: file.name, sheets, summary });
    } catch(e) {
      setError(`Parse error: ${e.message}`);
    }
    setParsing(false);
  }

  function onDrop(e) {
    e.preventDefault();
    handleFile(e.dataTransfer.files[0]);
  }

  function onInputChange(e) { handleFile(e.target.files[0]); }

  if (uploadedData) {
    const { filename, sheets } = uploadedData;
    return (
      <div className="flex flex-col gap-2">
        <Card className="flex flex-row items-center gap-2 border-primary/40 bg-secondary px-2.5 py-2">
          <span className="text-base">📊</span>
          <div className="flex-1">
            <div className="text-[11px] font-semibold text-primary">{filename}</div>
            <div className="text-[10px] text-muted-foreground">
              {sheets.length} sheet{sheets.length!==1?"s":""} · {sheets.reduce((a,s)=>a+s.data.length,0)} rows loaded
            </div>
          </div>
          <Button
            variant="outline"
            onClick={()=>{ onData(null); if(fileRef.current) fileRef.current.value=""; }}
            className="h-auto rounded-md px-2 py-[3px] text-[10px] text-muted-foreground"
          >
            Remove
          </Button>
        </Card>
        <div className="font-mono text-[10px] text-muted-foreground/70">
          ✓ {sheets.length} sheet{sheets.length !== 1 ? "s" : ""} ({sheets.map(s => s.name).join(", ")}) included in E1 agent context
        </div>
      </div>
    );
  }

  return (
    <div
      onDrop={onDrop}
      onDragOver={e=>e.preventDefault()}
      onClick={()=>fileRef.current?.click()}
      className="cursor-pointer rounded-lg border-2 border-dashed border-border bg-muted/30 px-4 py-5 text-center transition-colors hover:bg-muted/60"
    >
      <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv"
        onChange={onInputChange} className="hidden" />
      {parsing ? (
        <div className="text-[11px] italic text-muted-foreground">Parsing file…</div>
      ) : (
        <>
          <div className="mb-1.5 text-xl">📊</div>
          <div className="text-[11px] text-muted-foreground">
            Click or drag to upload · <strong>.xlsx · .xls · .csv</strong>
          </div>
          <div className="mt-1 text-[10px] text-muted-foreground/70">
            Optional — cohort data, biomarker export, characteristics table
          </div>
        </>
      )}
      {error && (
        <div className="mt-1.5 text-[10px] text-[#C0392B]">{error}</div>
      )}
    </div>
  );
}
