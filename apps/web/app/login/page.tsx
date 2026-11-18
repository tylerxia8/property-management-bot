"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../../lib/api";
import DemoEntry from "../demo-entry";
import styles from "../maintenance-shell.module.css";

export default function LoginPage() {
  const router = useRouter();
  const demo = process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample";
  const [subject, setSubject] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await api("/v1/auth/local/login", { method: "POST", body: JSON.stringify({ subject, password }), signal: AbortSignal.timeout(15000) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message || "Sign-in failed.");
      setToken(body.token);
      let roles: string[] = [];
      for (let attempt = 0; attempt < 3; attempt++) {
        try {
          const profile = await api("/v1/me", { signal: AbortSignal.timeout(10000) });
          if (!profile.ok) throw new Error("Your account could not be loaded.");
          roles = (await profile.json()).roles;
          break;
        } catch (failure) {
          if (attempt === 2) throw failure;
          await new Promise(resolve => setTimeout(resolve, 400 * 2 ** attempt));
        }
      }
      router.push(roles.includes("contractor") ? "/maintenance/jobs" : roles.includes("property_manager") ? "/maintenance/review" : "/maintenance");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }
  return <section className={styles.landing}>
    <h1>Maintenance</h1>
    <p>{demo ? "Choose a view." : "Sign in to see your repairs."}</p>
    {demo ? <DemoEntry /> : <form onSubmit={onSubmit}>
      <label>Email<input value={subject} onChange={event => setSubject(event.target.value)} autoComplete="username" required /></label>
      <label>Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete="current-password" required /></label>
      <button type="submit" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</button>
    </form>}
    {error && <p className={styles.error} role="alert">{error}</p>}
  </section>;
}
