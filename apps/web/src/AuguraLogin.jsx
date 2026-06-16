import { useState, useEffect } from "react";
import { Loader2 } from "lucide-react";
import { supabase } from "./supabase";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function AuguraLogin() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [mounted, setMounted] = useState(false);
  const [resetSent, setResetSent] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);

  useEffect(() => {
    setTimeout(() => setMounted(true), 50);
  }, []);

  const handleSignIn = async () => {
    setLoading(true);
    setError(null);
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setError(error.message);
    setLoading(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter") handleSignIn();
  };

  const handleForgotPassword = async () => {
    if (!email) { setError("Enter your email above first."); return; }
    setResetLoading(true);
    setError(null);
    await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: window.location.origin + '/reset-password',
    });
    setResetSent(true);
    setResetLoading(false);
  };

  const inputClass =
    "w-full rounded-lg border border-border bg-muted px-3 py-2 text-[13px] font-light text-foreground outline-none transition-colors placeholder:text-muted-foreground/50 focus:border-primary focus:bg-card focus:ring-2 focus:ring-primary/15";

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <div className="flex h-12 flex-shrink-0 items-center gap-2.5 border-b border-border px-5">
        <img src="/augura-wordmark-emerald.svg" alt="Augura" className="h-[15px]" />
      </div>

      <div className="flex flex-1 items-center justify-center px-5 py-12">
        <div
          className={`w-full max-w-[380px] transition-all duration-[400ms] ease-out ${
            mounted ? "translate-y-0 opacity-100" : "translate-y-3 opacity-0"
          }`}
        >
          <Card className="mb-3 rounded-lg border-border p-[14px_16px]">
            <div className="mb-[3px] flex items-center gap-2 text-[13px] font-medium text-foreground">
              Augura
              <span className="rounded-[3px] border border-primary/30 bg-secondary px-1.5 py-px font-mono text-[9px] tracking-[0.06em] text-primary">
                SECURE
              </span>
            </div>
            <div className="text-[11px] text-muted-foreground">Clinical Evidence Intelligence</div>
          </Card>

          <Card className="gap-0 rounded-lg border-border p-6">
            <div className="mb-5 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Sign in to your account
            </div>

            <div className="mb-3.5">
              <label className="mb-1.5 block text-[12px] text-muted-foreground">Email</label>
              <input
                className={inputClass}
                type="email"
                placeholder="you@institution.org"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onKeyDown={handleKeyDown}
                autoComplete="email"
              />
            </div>

            <div className="mb-3.5">
              <label className="mb-1.5 block text-[12px] text-muted-foreground">Password</label>
              <input
                className={inputClass}
                type="password"
                placeholder="••••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={handleKeyDown}
                autoComplete="current-password"
              />
            </div>

            {error && (
              <div className="mb-3.5 rounded-lg border border-[#C0392B]/30 bg-[#FCEBEB] px-3 py-2 text-[12px] text-[#C0392B]">
                {error}
              </div>
            )}

            <Button
              className="w-full"
              onClick={handleSignIn}
              disabled={loading || !email || !password}
            >
              {loading && <Loader2 className="h-3 w-3 animate-spin" />}
              {loading ? "Signing in…" : "Sign in"}
            </Button>

            {resetSent ? (
              <div className="mt-2.5 rounded-lg border border-primary/30 bg-secondary px-3 py-2 text-center text-[12px] text-primary">
                Check your email for a reset link
              </div>
            ) : (
              <button
                type="button"
                className="mt-2.5 block w-full text-center text-[12px] text-primary underline underline-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleForgotPassword}
                disabled={resetLoading}
              >
                {resetLoading ? "Sending…" : "Forgot or change password?"}
              </button>
            )}
          </Card>

          <div className="mt-3 rounded-lg border border-border bg-muted px-3.5 py-2.5 text-[11px] text-muted-foreground">
            Access is restricted to authorized users. Contact your Augura administrator to request access.
          </div>
        </div>
      </div>
    </div>
  );
}
