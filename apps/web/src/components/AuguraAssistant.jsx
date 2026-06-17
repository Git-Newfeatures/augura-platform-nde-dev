import { useState } from "react";
import { MessageSquare, X } from "lucide-react";
import InlineChatbot from "@/components/InlineChatbot";

// Global, always-mounted Augura assistant — a floating launcher (bottom-right)
// that opens a panel wrapping the existing InlineChatbot, so it talks to the
// real /api/anthropic backend with no new wiring.
//
// Two rules keep this safe as a *global* assistant (it renders on every page,
// across every study):
//   1. It owns its own message history (single owner) and starts empty.
//   2. It passes a GENERIC system prompt — no study-specific or sensitive data
//      is injected — so navigating between studies/pages never leaks context
//      into the conversation. InlineChatbot only ever sends `system` + the
//      messages held here.
//
// Mounted in AppShell (behind the auth gate), so it persists across navigation
// and never appears on the login / reset-password screens.

const SYSTEM = `You are the Augura Assistant, a helpful guide to the Augura evidence-intelligence platform.

Augura runs causal-inference studies through a workflow: Data input, Profiling, Causal question, Causal model, Variable & data verification, Study design, Simulation, Results, Sensitivity, and Report. Help users understand these steps, causal-inference concepts (estimands, confounding, identification, sensitivity analysis), and how to navigate the product.

You are a general assistant available on every page. You do NOT have access to the user's specific study, dataset, or results, so do not claim to. Answer generally and, when helpful, point users to the relevant part of the workflow. Keep answers concise.`;

const SUGGESTIONS = [
  "What can the Augura Assistant help with?",
  "Explain the study workflow steps",
  "How is a causal question built?",
];

export default function AuguraAssistant() {
  const [open, setOpen] = useState(false);
  // Single owner of conversation history (InlineChatbot is controlled).
  const [history, setHistory] = useState([]);

  return (
    <>
      {open && (
        <div
          role="dialog"
          aria-label="Augura Assistant"
          className="fixed bottom-[84px] right-6 z-[90] w-[min(380px,calc(100vw-2rem))]"
        >
          <InlineChatbot
            history={history}
            onHistory={setHistory}
            system={SYSTEM}
            suggestions={SUGGESTIONS}
          />
        </div>
      )}

      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close Augura Assistant" : "Open Augura Assistant"}
        className="fixed bottom-6 right-6 z-[90] flex h-[52px] w-[52px] items-center justify-center rounded-full bg-primary text-white shadow-lg transition hover:brightness-110 focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
      >
        {open ? <X size={20} /> : <MessageSquare size={20} />}
      </button>
    </>
  );
}
