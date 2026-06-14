import { useState, useEffect, useRef } from "react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

// ── Inline markdown + source badge renderer ───────────────────────────────────
// NOTE: the markdown output is injected via dangerouslySetInnerHTML, so its styles
// must remain inline HTML-string styles — Tailwind does not scan dynamically
// injected markup at build time.

const SOURCE_BADGES = [
  { re: /\[Augura corpus\]/g, label: "Augura corpus", bg: "#E1F5EE", fg: "#085041" },
  { re: /\[FDA Guidance\]/g,  label: "FDA Guidance",  bg: "#FEF3C7", fg: "#92400E" },
  { re: /\[ClinicalTrials\]/g,label: "ClinicalTrials",bg: "#E0F2FE", fg: "#075985" },
  { re: /\[PubMed\]/g,        label: "PubMed",        bg: "#FCE7F3", fg: "#831843" },
  { re: /\[MAUDE\]/g,         label: "MAUDE",         bg: "#FAEEDA", fg: "#633806" },
];

function mkBadge(label, bg, fg) {
  return `<span style="font-size:9px;padding:1px 6px;border-radius:10px;font-weight:600;background:${bg};color:${fg};display:inline-block;margin:0 1px;vertical-align:middle">${label}</span>`;
}

function applyInline(line) {
  // Code spans first — prevents bold inside code
  line = line.replace(/`([^`]+)`/g, (_, c) =>
    `<code style="font-family:'Geist Mono Variable', 'Geist Mono',monospace;font-size:0.9em;background:#e8e6df;padding:1px 5px;border-radius:3px">${c}</code>`
  );
  // Bold
  line = line.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic
  line = line.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");
  // Source badges (longest label first to avoid partial matches)
  SOURCE_BADGES.forEach(({ re, label, bg, fg }) => {
    line = line.replace(re, mkBadge(label, bg, fg));
  });
  return line;
}

function renderMarkdown(raw) {
  if (!raw) return "";
  // Escape HTML, then apply inline formatting
  const esc = s => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = raw.split("\n");
  const out = [];
  let inUl = false, inOl = false;

  for (const rawLine of lines) {
    const line    = esc(rawLine);
    const h2Match = line.match(/^##\s+(.+)/);
    const h3Match = line.match(/^###\s+(.+)/);
    const ulMatch = line.match(/^(?:–|-)\s+(.+)/);
    const olMatch = line.match(/^\d+\.\s+(.+)/);

    if (h3Match) {
      if (inUl) { out.push("</ul>"); inUl = false; }
      if (inOl) { out.push("</ol>"); inOl = false; }
      out.push(`<h4 style="font-size:12px;font-weight:600;color:#4B5563;margin:8px 0 4px">${applyInline(h3Match[1])}</h4>`);
    } else if (h2Match) {
      if (inUl) { out.push("</ul>"); inUl = false; }
      if (inOl) { out.push("</ol>"); inOl = false; }
      out.push(`<h3 style="font-size:13px;font-weight:600;color:#111827;margin:12px 0 6px">${applyInline(h2Match[1])}</h3>`);
    } else if (ulMatch) {
      if (inOl) { out.push("</ol>"); inOl = false; }
      if (!inUl) { out.push('<ul style="margin:4px 0 4px 16px;padding:0;list-style:disc">'); inUl = true; }
      out.push(`<li style="margin:2px 0">${applyInline(ulMatch[1])}</li>`);
    } else if (olMatch) {
      if (inUl) { out.push("</ul>"); inUl = false; }
      if (!inOl) { out.push('<ol style="margin:4px 0 4px 16px;padding:0">'); inOl = true; }
      out.push(`<li style="margin:2px 0">${applyInline(olMatch[1])}</li>`);
    } else {
      if (inUl) { out.push("</ul>"); inUl = false; }
      if (inOl) { out.push("</ol>"); inOl = false; }
      if (!line.trim()) {
        if (out.length > 0 && out[out.length - 1] !== "<br/>") out.push("<br/>");
      } else {
        out.push(applyInline(line));
      }
    }
  }
  if (inUl) out.push("</ul>");
  if (inOl) out.push("</ol>");
  return out.join("");
}

// ── Copy icon SVG ─────────────────────────────────────────────────────────────

function CopyIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2"/>
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
    </svg>
  );
}

// ── Assistant bubble with hover copy button ───────────────────────────────────

function AssistantBubble({ text }) {
  const [hovered, setHovered] = useState(false);
  const [copied,  setCopied]  = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }

  return (
    <div
      className="relative max-w-[88%] self-start"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <div
        className="rounded-[3px_10px_10px_10px] bg-muted px-[11px] py-2 text-[12px] leading-[1.55] text-foreground/80"
        dangerouslySetInnerHTML={{ __html: renderMarkdown(text) }}
      />
      {hovered && (
        <button
          onClick={handleCopy}
          title={copied ? "Copied!" : "Copy response"}
          className="absolute top-1 right-1 flex items-center justify-center rounded-[3px] border-none bg-white/85 p-0.5 cursor-pointer"
          style={{ color: copied ? "var(--primary)" : undefined }}
        >
          {copied
            ? <span className="text-[10px] font-semibold">✓</span>
            : <span className="text-muted-foreground/60"><CopyIcon /></span>}
        </button>
      )}
    </div>
  );
}

// ── Main InlineChatbot ────────────────────────────────────────────────────────

const WELCOME = "I'm the Augura assistant. Ask me anything about this view — profile scores, data sources, regulatory context, or next steps.";

export default function InlineChatbot({
  history     = [],
  onHistory,
  system      = "",
  suggestions = [],
}) {
  const [input,    setInput]    = useState("");
  const [loading,  setLoading]  = useState(false);
  const [clearMsg, setClearMsg] = useState(null);
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [history, loading, clearMsg]);

  // Show welcome when no conversation yet
  const displayMsgs = history.length === 0
    ? [{ role: "assistant", text: WELCOME }]
    : history;

  async function send() {
    const q = input.trim();
    if (!q || loading) return;
    setInput("");

    const userMsg    = { role: "user", text: q };
    const newHistory = [...history, userMsg];
    onHistory?.(newHistory);
    setLoading(true);

    // Full conversation history sent on every turn (multi-turn)
    const messages = newHistory.map(m => ({ role: m.role, content: m.text }));

    try {
      const res = await fetch("/api/anthropic", {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          model:      "claude-sonnet-4-20250514",
          max_tokens: 600,
          system,
          messages,
        }),
      });
      const data = await res.json();
      const text = data.content?.filter(b => b.type === "text").map(b => b.text).join("") || "Engine unavailable.";
      onHistory?.([...newHistory, { role: "assistant", text }]);
    } catch {
      onHistory?.([...newHistory, { role: "assistant", text: "Engine unavailable — check connection." }]);
    }
    setLoading(false);
  }

  function handleClear() {
    onHistory?.([]);
    setClearMsg("Conversation cleared");
    setTimeout(() => setClearMsg(null), 2000);
  }

  return (
    <Card className="flex flex-col gap-0 p-4 px-5" style={{ minHeight: 380 }}>
      <style>{`@keyframes dotPulse{0%,100%{opacity:.2}50%{opacity:1}}`}</style>

      {/* Header */}
      <div className="mb-0.5 flex items-center gap-2">
        <div
          className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-md text-[11px] font-bold text-white"
          style={{ background: "linear-gradient(135deg,#0EA5E9,#8B5CF6)" }}
        >A</div>

        <span className="flex-1 text-[13px] font-semibold text-foreground">
          Augura Assistant
        </span>

        {/* Clear button */}
        <button
          onClick={handleClear}
          className="cursor-pointer border-none bg-transparent px-1 py-0.5 text-[10px] text-muted-foreground/60"
        >Clear</button>
      </div>

      <div className="mb-2.5 text-[11px] text-muted-foreground">
        Ask the engine anything about this view — powered by the project profile and evidence corpus.
      </div>

      {/* Suggestion pills */}
      {suggestions.length > 0 && (
        <div className="mb-2.5 flex flex-wrap gap-[5px]">
          {suggestions.map(s => (
            <button
              key={s}
              onClick={() => setInput(s)}
              className="cursor-pointer rounded-[20px] border-[0.5px] border-border bg-muted px-[9px] py-[3px] text-[10.5px] text-muted-foreground"
            >{s}</button>
          ))}
        </div>
      )}

      {/* Message list */}
      <div
        ref={ref}
        className="mb-2.5 flex flex-1 flex-col gap-2 overflow-y-auto pr-0.5"
        style={{ minHeight: 160, maxHeight: 520 }}
      >
        {displayMsgs.map((m, i) =>
          m.role === "user" ? (
            <div
              key={i}
              className="max-w-[88%] self-end rounded-[10px_3px_10px_10px] bg-secondary px-[11px] py-2 text-[12px] leading-[1.55] text-[#085041]"
            >{m.text}</div>
          ) : (
            <AssistantBubble key={i} text={m.text} />
          )
        )}

        {/* Animated typing indicator */}
        {loading && (
          <div className="flex items-center gap-[5px] self-start rounded-[3px_10px_10px_10px] bg-muted px-3.5 py-2.5">
            {[0, 1, 2].map(i => (
              <span
                key={i}
                className="inline-block h-1.5 w-1.5 rounded-full bg-muted-foreground/60"
                style={{ animation: `dotPulse 1.2s ease-in-out ${i * 0.3}s infinite` }}
              />
            ))}
          </div>
        )}

        {/* "Conversation cleared" flash */}
        {clearMsg && (
          <div className="self-center rounded-lg border-[0.5px] border-[#5DCAA5] bg-secondary px-[11px] py-[5px] text-[10.5px] text-primary">
            {clearMsg}
          </div>
        )}
      </div>

      {/* Input row */}
      <div className="flex gap-1.5">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === "Enter" && send()}
          placeholder="Ask about this view…"
          className="flex-1 rounded-lg border-[0.5px] border-border bg-muted/40 px-[11px] py-2 text-[12px] text-foreground outline-none focus:ring-2 focus:ring-primary/15"
        />
        <Button onClick={send} className="text-xs font-medium">Send</Button>
      </div>
    </Card>
  );
}
