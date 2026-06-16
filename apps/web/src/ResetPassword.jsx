import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { supabase } from "./supabase";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function ResetPassword() {
  console.log('PATHNAME:', window.location.pathname)
  console.log('HASH:', window.location.hash)
  console.log('HREF:', window.location.href)

  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [done, setDone] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setTimeout(() => setMounted(true), 50);
  }, []);

  const handleSubmit = async () => {
    if (newPassword !== confirm) { setError("Passwords do not match."); return; }
    if (newPassword.length < 6) { setError("Password must be at least 6 characters."); return; }
    setLoading(true);
    setError(null);
    const { error } = await supabase.auth.updateUser({ password: newPassword });
    if (error) { setError(error.message); setLoading(false); return; }
    setDone(true);
    setTimeout(() => { window.location.href = "/"; }, 2000);
  };

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="flex h-12 flex-shrink-0 items-center border-b border-border px-5">
        <span className="text-[12px] font-medium uppercase tracking-[0.12em] text-primary">Augura</span>
      </div>

      <div className="flex flex-1 items-center justify-center px-5 py-12">
        <div
          className={`w-full max-w-[380px] transition-all duration-[400ms] ease-out ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"
          }`}
        >
          <Card className="gap-0 border-border p-6">
            <div className="mb-5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Set a new password
            </div>

            {done ? (
              <div className="rounded-lg border border-primary/30 bg-secondary px-3 py-2 text-center text-[12px] text-primary">
                Password updated — redirecting...
              </div>
            ) : (
              <>
                <div className="mb-3.5">
                  <label className="mb-1.5 block text-[12px] text-muted-foreground">New password</label>
                  <input
                    className="w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-[13px] font-light text-foreground outline-none transition-all placeholder:text-muted-foreground/50 focus:border-primary focus:bg-card focus:ring-2 focus:ring-primary/15"
                    type="password"
                    placeholder="••••••••••"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>

                <div className="mb-3.5">
                  <label className="mb-1.5 block text-[12px] text-muted-foreground">Confirm password</label>
                  <input
                    className="w-full rounded-lg border border-border bg-muted/40 px-3 py-2 text-[13px] font-light text-foreground outline-none transition-all placeholder:text-muted-foreground/50 focus:border-primary focus:bg-card focus:ring-2 focus:ring-primary/15"
                    type="password"
                    placeholder="••••••••••"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    autoComplete="new-password"
                  />
                </div>

                {error && (
                  <div className="mb-3.5 rounded-lg border border-[#C0392B]/30 bg-[#FCEBEB] px-3 py-2 text-[12px] text-[#C0392B]">
                    {error}
                  </div>
                )}

                <Button
                  className="w-full"
                  onClick={handleSubmit}
                  disabled={loading || !newPassword || !confirm}
                >
                  {loading && <Loader2 className="animate-spin" size={14} />}
                  {loading ? "Updating…" : "Update password"}
                </Button>
              </>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}
