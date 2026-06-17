import { ArrowLeft, Radio } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import InlineChatbot from "../components/InlineChatbot";

// ─────────────────────────────────────────────────────────────────────────────
// VIEW 11: POST-STUDY MONITORING DASHBOARD
//
// The entire dashboard was previously rendered from fabricated mock data
// (MOCK_SNAPSHOTS / MOCK_SIGNALS) with no live source. There is no backend
// /monitoring endpoint wired (snapshots + signals scoped to a tenant), so the
// data-rendering body has been removed in favour of an honest empty state.
// Re-introduce the KPI row, charts, subgroup forest and signal log once a real
// /monitoring data source is available.
// ─────────────────────────────────────────────────────────────────────────────

export default function MonitoringView({ onBack, partnerLabel = 'Partner', chatProps = {} }) {
  return (
    <div className="mx-auto max-w-[1060px]">
      {/* Header */}
      <div className="mb-5 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="mb-1.5 text-[13px] font-semibold text-primary">
            Post-study monitoring
          </div>
          <div className="mb-1 text-[15px] font-semibold tracking-[-0.01em] text-foreground">
            Post-study monitoring dashboard
          </div>
          <div className="text-[12.5px] text-muted-foreground">
            Longitudinal real-world evidence · {partnerLabel} platform
          </div>
        </div>
      </div>

      {/* Empty state */}
      <Card className="flex flex-col items-center justify-center gap-3 rounded-xl px-6 py-16 text-center">
        <div className="flex h-11 w-11 items-center justify-center rounded-full bg-muted/60">
          <Radio size={20} className="text-muted-foreground" />
        </div>
        <div className="text-[14px] font-semibold text-foreground">
          Live monitoring not available yet
        </div>
        <div className="max-w-[440px] text-[12.5px] leading-relaxed text-muted-foreground">
          No /monitoring data source is wired. Snapshots and drift signals will
          appear here once the backend exposes a tenant-scoped monitoring feed.
        </div>
      </Card>

      {/* Chatbot */}
      <InlineChatbot {...chatProps} />

      {/* Navigation */}
      <div className="mt-6 flex justify-between">
        <Button variant="outline" onClick={onBack}>
          <ArrowLeft size={15} /> Back to Report
        </Button>
      </div>
    </div>
  );
}
