"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { enterDemoRole } from "../lib/demo";
import Icon from "./ui/workspace-icon";
import styles from "./maintenance-shell.module.css";

export default function DemoEntry() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function enter(role: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      router.push(await enterDemoRole(role));
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }
  return <>{error && <p className={styles.error} role="alert">{error}</p>}<div className={styles.choices}>
    <button type="button" className={styles.choice} disabled={busy} onClick={() => void enter("tenant")}><Icon name="house" /><strong>I’m the tenant</strong><span>Report a problem, confirm a visit, and tell us when it’s fixed.</span><em>Open tenant view →</em></button>
    <button type="button" className={styles.choice} disabled={busy} onClick={() => void enter("property_manager")}><Icon name="review" /><strong>I’m the property manager</strong><span>Review requests, help tenants, and decide when a repairman is needed.</span><em>Open manager view →</em></button>
    <button type="button" className={styles.choice} disabled={busy} onClick={() => void enter("contractor")}><Icon name="repair" /><strong>I’m the repairman</strong><span>Handle repairs passed to you by the property manager.</span><em>Open repairman view →</em></button>
  </div></>;
}
