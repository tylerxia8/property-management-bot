"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";
import { demoDestinations } from "../lib/demo";

const scenarios = [
  { role: "accounting_staff", title: "1. Record rent", detail: "Record a check and see why received money is different from available funds." },
  { role: "prospect", title: "2. Prequalify a prospect", detail: "Collect preliminary information, request human review, and explore tour times." },
  { role: "tenant", title: "3. Report a repair", detail: "Describe a leak, answer follow-up questions, and demonstrate emergency escalation." },
  { role: "property_manager", title: "4. Review as manager", detail: "Review a prospect exception using the fictional property's sample policy." },
  { role: "owner", title: "5. View an owner statement", detail: "Inspect a fictional ledger snapshot with no bank transfer." },
];

export default function DemoEntry() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function enter(role: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await api("/v1/demo/session", { method: "POST", body: JSON.stringify({ role }) });
      const body = await response.json();
      if (!response.ok) throw new Error(body.error?.message ?? "The sample could not be opened.");
      setToken(body.token);
      router.push(demoDestinations[role]);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The local demo is unavailable. Start it and try again.");
    } finally {
      setBusy(false);
    }
  }

  return <section aria-labelledby="demo-heading">
    <h2 id="demo-heading">Choose a walkthrough</h2>
    <p>Each button opens a fictional role. Return Home to switch roles. Changes stay in this local sample.</p>
    {error ? <p role="alert" className="alert">{error}</p> : null}
    <div className="demo-grid">{scenarios.map(scenario => <article className="demo-card" key={scenario.role}>
      <h3>{scenario.title}</h3><p>{scenario.detail}</p>
      <button type="button" disabled={busy} onClick={() => void enter(scenario.role)}>{scenario.title}</button>
    </article>)}</div>
    <p>Maintenance questions use reviewed templates. No AI model, bank, messaging service, or external calendar is connected.</p>
  </section>;
}
