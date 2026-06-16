import { useState, useEffect } from "react";
import { X } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { supabase } from "./supabase";

function timeAgo(ts) {
  const diff = (Date.now() - new Date(ts)) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

function shortEmail(email) {
  if (!email) return "—";
  const [local, domain] = email.split("@");
  return `${local.slice(0, 12)}${local.length > 12 ? "…" : ""}@${domain}`;
}

const EVENT_ICONS = { login: "→", agent_run: "◈", query: "⌕", export: "↗" };

// fadeUp keyframe is the one bit of motion Tailwind can't express with a
// per-element stagger delay, so it stays in a tiny <style> block and the
// delay is applied inline (preserves the original entrance behaviour).
const fadeUp = (delay) => ({ animation: "admFadeUp 0.4s ease both", animationDelay: `${delay}ms` });

function StatCard({ label, value, sub, delay }) {
  return (
    <Card className="gap-0 p-4" style={fadeUp(delay)}>
      <div className="text-[26px] font-light leading-none tracking-[-0.02em] text-primary">{value}</div>
      <div className="mt-1.5 font-mono text-[9px] uppercase tracking-[0.12em] text-muted-foreground/70">{label}</div>
      {sub && <div className="mt-1 text-[11px] text-muted-foreground/60">{sub}</div>}
    </Card>
  );
}

function ActivityRow({ event, index }) {
  const icon = EVENT_ICONS[event.event_type] || "·";
  return (
    <div
      className="flex items-center gap-3 border-b border-border/40 px-4 py-[9px] transition-colors last:border-b-0 hover:bg-muted/50"
      style={fadeUp(index * 40)}
    >
      <span className="w-3.5 flex-shrink-0 text-center text-[11px] text-primary">{icon}</span>
      <span className="w-[160px] flex-shrink-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[10px] text-muted-foreground">
        {shortEmail(event.user_email)}
      </span>
      <span className="flex-1 font-mono text-[10px] tracking-[0.04em] text-muted-foreground/70">{event.event_type}</span>
      {event.metadata?.tokens_used && (
        <span className="flex-shrink-0 font-mono text-[9px] text-muted-foreground/60">{event.metadata.tokens_used.toLocaleString()} tok</span>
      )}
      <span className="w-14 flex-shrink-0 text-right font-mono text-[9px] text-muted-foreground/60">{timeAgo(event.created_at)}</span>
    </div>
  );
}

function MiniBar({ data }) {
  const max = Math.max(...data.map(d => d.count), 1);
  return (
    <div className="flex h-[60px] items-end gap-1.5">
      {data.map((d, i) => (
        <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-1">
          <div
            className="min-h-[2px] w-full rounded-t-sm bg-primary opacity-60 transition-[height] duration-500"
            style={{ height: `${(d.count / max) * 100}%` }}
          />
          <div className="font-mono text-[8px] tracking-[0.04em] text-muted-foreground/60">{d.label}</div>
        </div>
      ))}
    </div>
  );
}

function LoginBarChart({ data }) {
  const max = Math.max(...data.map(d => d.count), 1);
  if (data.length === 0) return (
    <div className="py-3 text-center font-mono text-[10px] tracking-[0.1em] text-muted-foreground/60">NO LOGINS YET</div>
  );
  return (
    <div className="flex flex-col gap-2.5">
      {data.map((d, i) => (
        <div key={i} className="flex items-center gap-2.5">
          <span className="w-[160px] flex-shrink-0 overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[10px] text-muted-foreground">
            {d.email}
          </span>
          <div className="h-2 flex-1 overflow-hidden rounded bg-muted">
            <div
              className="h-full rounded bg-primary opacity-75 transition-[width] duration-500"
              style={{ width: `${(d.count / max) * 100}%` }}
            />
          </div>
          <span className="w-6 flex-shrink-0 text-right font-mono text-[10px] text-primary">{d.count}</span>
        </div>
      ))}
    </div>
  );
}

function UserRow({ user, index }) {
  const fullName = user.full_name || user.user_metadata?.full_name || user.user_metadata?.name || null;
  const org = user.email?.endsWith('@augura.health') ? (user.user_metadata?.org || 'Augura') : 'External';
  const loginCount = user.login_count ?? 0;
  return (
    <Card
      className="gap-0 flex flex-row items-center gap-3.5 p-[14px_16px] transition-colors hover:border-primary/40"
      style={fadeUp(index * 50)}
    >
      <div className="flex-1">
        {fullName && <div className="mb-px text-[13px] font-normal text-foreground">{fullName}</div>}
        <div className={fullName ? "mb-[3px] text-[11px] text-muted-foreground/70" : "mb-[3px] text-[13px] font-light text-foreground"}>
          {user.email}
        </div>
        <div className="flex items-center gap-1.5 font-mono text-[9px] tracking-[0.08em] text-muted-foreground/70">
          <span>{org}</span>
        </div>
      </div>
      <div className="text-right">
        <div className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground/60">last active</div>
        <div className="font-mono text-[11px] text-muted-foreground">{user.last_sign_in_at ? timeAgo(user.last_sign_in_at) : "never"}</div>
      </div>
      <div className="min-w-[40px] text-right">
        <div className="text-[16px] font-light" style={{ color: loginCount > 0 ? "var(--color-primary)" : "var(--color-muted-foreground)" }}>
          {loginCount}
        </div>
        <div className="font-mono text-[8px] uppercase tracking-[0.1em] text-muted-foreground/60">logins</div>
      </div>
    </Card>
  );
}

export default function AuguraAdminDashboard({ onClose }) {
  const [events, setEvents] = useState([]);
  const [users, setUsers] = useState([]);
  const [stats, setStats] = useState({});
  const [dailyActivity, setDailyActivity] = useState([]);
  const [loginsByUser, setLoginsByUser] = useState([]);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState("users");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    fetchData();
    setTimeout(() => setMounted(true), 50);
  }, []);

  async function fetchData() {
    setLoading(true);
    try {
      const { data: { session } } = await supabase.auth.getSession();
      const res = await fetch("/api/admin-stats", {
        headers: { Authorization: `Bearer ${session?.access_token}` },
      });
      if (!res.ok) { setLoading(false); return; }
      const data = await res.json();

      const eventsData = data.recentEvents || [];

      // Daily activity (last 7 days) from recent events
      const days = Array.from({ length: 7 }, (_, i) => {
        const d = new Date(Date.now() - (6 - i) * 86400000);
        return { label: d.toLocaleDateString("en", { weekday: "short" }).slice(0, 2), date: d.toISOString().slice(0, 10), count: 0 };
      });
      eventsData.forEach(e => {
        const day = days.find(d => d.date === e.created_at?.slice(0, 10));
        if (day) day.count++;
      });

      const totalTokens = eventsData.reduce((sum, e) => sum + (e.metadata?.tokens_used || 0), 0);

      setEvents(eventsData);
      setDailyActivity(days);
      setLoginsByUser(data.loginsByUser || []);
      setStats({ ...data.stats, totalTokens });
      setUsers(data.users || []);
    } catch (err) {
      console.error("[admin-stats]", err);
    }
    setLoading(false);
  }

  return (
    <>
      <style>{`@keyframes admFadeUp { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }`}</style>

      <div
        className={`fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-[3px] transition-opacity duration-300 ${mounted ? "opacity-100" : "opacity-0"}`}
      >
        <Card
          className={`flex w-[min(900px,96vw)] max-h-[88vh] flex-col gap-0 overflow-hidden p-0 shadow-2xl transition-transform duration-300 ${mounted ? "translate-y-0" : "translate-y-5"}`}
        >
          {/* Topbar */}
          <div className="flex flex-shrink-0 items-center justify-between border-b border-border bg-muted px-5 py-3.5">
            <div className="flex items-center gap-2.5">
              <Badge variant="secondary" className="rounded-[3px] px-2 py-[3px] font-mono text-[9px] uppercase tracking-[0.14em] text-primary">
                Admin
              </Badge>
              <span className="text-[13px] font-normal text-muted-foreground">Usage Dashboard · Augura</span>
            </div>
            <Button
              variant="outline"
              size="icon-sm"
              onClick={onClose}
              className="text-muted-foreground/70 hover:border-destructive/50 hover:text-destructive"
            >
              <X size={14} />
            </Button>
          </div>

          {/* Tabs */}
          <div className="flex flex-shrink-0 border-b border-border bg-muted px-5">
            {["users", "overview", "activity"].map(t => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`border-b-2 px-3.5 py-[11px] font-mono text-[10px] uppercase tracking-[0.1em] transition-colors ${
                  tab === t ? "border-primary text-primary" : "border-transparent text-muted-foreground/70 hover:text-muted-foreground"
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          {/* Body */}
          <div className="flex-1 overflow-y-auto bg-muted p-5">
            {loading ? (
              <div className="flex items-center justify-center gap-2.5 p-16 font-mono text-[10px] tracking-[0.1em] text-muted-foreground/70">
                <div className="h-3.5 w-3.5 animate-spin rounded-full border-[1.5px] border-border border-t-primary" />
                LOADING TELEMETRY
              </div>
            ) : (
              <>
                {tab === "overview" && (
                  <>
                    <div className="mb-4 grid grid-cols-1 gap-2.5 sm:grid-cols-3">
                      <StatCard label="Active Users (7d)" value={stats.activeUsers ?? 0} sub="unique users" delay={0} />
                      <StatCard label="Queries Run" value={stats.totalQueries ?? 0} delay={60} />
                      <StatCard label="Tokens Used" value={stats.totalTokens > 1000 ? `${(stats.totalTokens / 1000).toFixed(1)}k` : (stats.totalTokens ?? 0)} sub="Claude API" delay={120} />
                    </div>

                    <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
                      <Card className="gap-0 p-4" style={fadeUp(160)}>
                        <div className="mb-3.5 font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground/70">Activity · Last 7 Days</div>
                        <MiniBar data={dailyActivity} />
                      </Card>
                      <Card className="gap-0 p-4" style={fadeUp(200)}>
                        <div className="mb-3.5 font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground/70">Logins per User</div>
                        <LoginBarChart data={loginsByUser} />
                      </Card>
                    </div>

                    <Card className="gap-0 overflow-hidden p-0" style={fadeUp(100)}>
                      <div className="flex items-center justify-between border-b border-border/60 px-4 py-3 font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground/70">
                        <span>Recent Activity</span>
                        <div className="flex items-center gap-1.5 text-primary">
                          <div className="h-[5px] w-[5px] animate-pulse rounded-full bg-primary" />
                          <span className="text-[9px] tracking-[0.1em]">LIVE</span>
                        </div>
                      </div>
                      {events.slice(0, 8).map((e, i) => <ActivityRow key={e.id} event={e} index={i} />)}
                      {events.length === 0 && <div className="p-10 text-center font-mono text-[10px] tracking-[0.1em] text-muted-foreground/60">NO EVENTS YET</div>}
                    </Card>
                  </>
                )}

                {tab === "activity" && (
                  <Card className="gap-0 overflow-hidden p-0" style={fadeUp(0)}>
                    <div className="flex items-center justify-between border-b border-border/60 px-4 py-3 font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground/70">
                      <span>All Events · Last 50</span>
                      <div className="flex items-center gap-1.5 text-primary">
                        <div className="h-[5px] w-[5px] animate-pulse rounded-full bg-primary" />
                        <span className="text-[9px] tracking-[0.1em]">LIVE</span>
                      </div>
                    </div>
                    {events.map((e, i) => <ActivityRow key={e.id} event={e} index={i} />)}
                    {events.length === 0 && <div className="p-10 text-center font-mono text-[10px] tracking-[0.1em] text-muted-foreground/60">NO EVENTS YET · START LOGGING FROM YOUR API ROUTES</div>}
                  </Card>
                )}

                {tab === "users" && (
                  <div className="flex flex-col gap-2">
                    {users.map((u, i) => <UserRow key={u.id} user={u} index={i} />)}
                    {users.length === 0 && <div className="p-10 text-center font-mono text-[10px] tracking-[0.1em] text-muted-foreground/60">NO USERS PROVISIONED</div>}
                  </div>
                )}
              </>
            )}
          </div>
        </Card>
      </div>
    </>
  );
}
