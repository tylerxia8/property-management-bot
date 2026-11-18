"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken, setToken } from "../../lib/api";

type Property = { id: string; name: string };
type Party = { id: string; display_name: string };
type Item = { id: string; recipient_id: string; kind: string; amount_cents: number; status: string; provider_key: string; destination_version: number | null; channel?: "ZELLE" | "VENMO" | "STRIPE_ACH" | null; destination_label?: string | null };
type Batch = { id: string; property_id: string; status: string; snapshot_hash: string | null; total_cents: number; submitted: boolean; items: Item[] };
type ExportBody = { batch_id: string; duplicate_download: boolean; settled: boolean; artifact: { submitted: boolean; settled: boolean; items: { id: string }[] } };
type SimulatedAccount = { property_id: string };

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

async function read<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await api(path, { ...init, signal: AbortSignal.timeout(15000) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message ?? "The request could not be completed.");
  return body as T;
}

async function post<T>(path: string, body?: object): Promise<T> {
  const serialized = body === undefined ? undefined : JSON.stringify(body);
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${path}:${serialized ?? ""}`));
  const storageKey = `grok_distribution_request_${Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
  let key = sessionStorage.getItem(storageKey);
  if (!key) {
    key = crypto.randomUUID();
    sessionStorage.setItem(storageKey, key);
  }
  const result = await read<T>(path, { method: "POST", headers: { "Idempotency-Key": key }, body: serialized });
  sessionStorage.removeItem(storageKey);
  return result;
}

export default function DistributionsPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [canDraft, setCanDraft] = useState(false);
  const [canApprove, setCanApprove] = useState(false);
  const [properties, setProperties] = useState<Property[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [accounts, setAccounts] = useState<SimulatedAccount[]>([]);
  const [stripeProperties, setStripeProperties] = useState<SimulatedAccount[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [partyId, setPartyId] = useState("");
  const [managementPartyId, setManagementPartyId] = useState("");
  const [destinationLabel, setDestinationLabel] = useState("");
  const [channel, setChannel] = useState<"ZELLE" | "VENMO">("ZELLE");
  const [asOf, setAsOf] = useState("");
  const [batch, setBatch] = useState<Batch | null>(null);
  const [stepSubject, setStepSubject] = useState("");
  const [stepPassword, setStepPassword] = useState("");
  const [reason, setReason] = useState("");
  const [exported, setExported] = useState<ExportBody | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const simulated = accounts.some((account) => account.property_id === (batch?.property_id ?? propertyId));
  const stripe = stripeProperties.some((account) => account.property_id === (batch?.property_id ?? propertyId));
  const uncertain = batch?.items.some((item) => item.status === "UNKNOWN") ?? false;
  const unpaid = batch && !uncertain && !batch.items.some((item) => item.status === "RETURNED") && batch.items.some((item) => ["DRAFT", "RESERVED", "APPROVED", "FAILED"].includes(item.status));
  const approvable = batch && ["VALIDATED", "APPROVED", "PARTIALLY_SETTLED", "FAILED"].includes(batch.status) && !uncertain && (!simulated || batch.items.some((item) => ["RESERVED", "APPROVED"].includes(item.status)));
  const demo = process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample";

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    setAsOf(new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" }));
    void (async () => {
      try {
        const me = await read<{ capabilities: string[] }>("/v1/me");
        const draft = me.capabilities.includes("distributions.draft");
        const approve = me.capabilities.includes("distributions.approve");
        if (!draft && !approve) throw new Error("Your account does not have access to distributions.");
        const [propertyList, partyList, simulatedResponse, stripeResponse] = await Promise.all([
          read<{ items: Property[] }>("/v1/properties"),
          read<{ items: Party[] }>("/v1/parties"),
          api("/v1/simulated-bank", { signal: AbortSignal.timeout(15000) }),
          api("/v1/stripe", { signal: AbortSignal.timeout(15000) }),
        ]);
        let simulatedAccounts: SimulatedAccount[] = [];
        let stripeAccounts: SimulatedAccount[] = [];
        if (stripeResponse.status !== 404) {
          const provider = await stripeResponse.json();
          if (!stripeResponse.ok) throw new Error(provider.error?.message ?? "Stripe status could not be loaded.");
          stripeAccounts = provider.properties;
        }
        if (simulatedResponse.status !== 404) {
          const simulation = await simulatedResponse.json();
          if (!simulatedResponse.ok) throw new Error(simulation.error?.message ?? "The payment environment could not be confirmed.");
          simulatedAccounts = simulation.accounts;
        }
        const batchId = new URLSearchParams(window.location.search).get("batch");
        const loaded = batchId ? await read<Batch>(`/v1/distribution-batches/${encodeURIComponent(batchId)}`) : null;
        if (!active) return;
        setCanDraft(draft);
        setCanApprove(approve);
        setProperties(propertyList.items);
        setParties(partyList.items);
        setAccounts(simulatedAccounts);
        setStripeProperties(stripeAccounts);
        setPropertyId(loaded?.property_id ?? propertyList.items[0]?.id ?? "");
        setPartyId(partyList.items[0]?.id ?? "");
        setBatch(loaded);
        setReady(true);
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : "The distribution workspace could not be loaded.");
      }
    })();
    return () => { active = false; };
  }, [router]);

  async function perform(action: () => Promise<void>) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (failure) {
      setError(`${failure instanceof Error ? failure.message : "The result could not be confirmed."} If the connection was interrupted, retry the same details to recover the original result.`);
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function createDestination(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      const result = await post<{ version: number }>("/v1/payee-destinations", { party_id: partyId, masked_label: destinationLabel.trim(), channel });
      setNotice(`Destination version ${result.version} saved. Draft a new batch to use the updated destination.`);
    });
  }

  function draft(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      const result = await post<Batch>("/v1/distribution-batches", { property_id: propertyId, as_of: asOf, management_party_id: managementPartyId || null });
      setBatch(result);
      setExported(null);
      router.replace(`/distributions?batch=${encodeURIComponent(result.id)}`);
    });
  }

  function validateBatch() {
    if (!batch) return;
    void perform(async () => { setBatch(await post<Batch>(`/v1/distribution-batches/${batch.id}/validate`)); });
  }

  function stepUp(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      await read("/v1/auth/local/step-up", { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ subject: stepSubject, password: stepPassword }) });
      setStepPassword("");
      setNotice("Dev/test step-up recorded. This is not production MFA.");
    });
  }

  function confirmDemoIdentity() {
    void perform(async () => {
      await post("/v1/simulated-bank/step-up");
      setNotice("Fictional manager identity confirmed for simulated approval. This is not production MFA.");
    });
  }

  function approve(event: FormEvent) {
    event.preventDefault();
    if (!batch?.snapshot_hash) return;
    void perform(async () => {
      const result = await post<Batch>(`/v1/distribution-batches/${batch.id}/approve`, { snapshot_hash: batch.snapshot_hash, reason: reason.trim(), posting_date: asOf });
      setBatch(result);
      setNotice(stripe ? "Approval recorded. Stripe sandbox payouts are queued; track transfers and bank payouts on the Stripe page." : simulated ? `Approval recorded. Simulated payout status: ${result.status}. No real money was sent.` : "Approval recorded. No live bank submission occurred.");
    });
  }

  function exportBatch() {
    if (!batch) return;
    void perform(async () => { setExported(await post<ExportBody>(`/v1/distribution-batches/${batch.id}/export`)); });
  }

  function submitDisabled() {
    if (!batch) return;
    void perform(async () => {
      const result = await post<Batch>(`/v1/distribution-batches/${batch.id}/submit`, { posting_date: asOf, scripts: {} });
      setBatch(result);
      setNotice(`Simulator returned ${result.status}. No bank was contacted.`);
    });
  }

  function cancelBatch() {
    if (!batch) return;
    void perform(async () => {
      setBatch(await post<Batch>(`/v1/distribution-batches/${batch.id}/cancel`));
      setNotice("Unpaid batch canceled and reserved funds released. Draft a fresh batch to retry declined payments.");
    });
  }

  function switchWorkspace(role: string) {
    void perform(async () => {
      const result = await post<{ token: string }>("/v1/demo/session", { role });
      setToken(result.token);
      window.location.reload();
    });
  }

  return (
    <>
      <p><Link href="/banking">Simulated banking & payment history</Link></p>
      <h1>Distribution approval</h1>
      <p className="banner">{stripe ? "Stripe sandbox only. Approval queues transfers and bank payouts. Test credentials cannot move real money." : simulated ? "Fictional money only. Approving this property's batch automatically sends simulated payments. No Wells Fargo account is connected." : "Live bank submission is disabled. Export does not mark the batch submitted or settled. Dev/test step-up is not production MFA."}</p>
      {demo ? <p>Demo workspace: <button type="button" disabled={busy || canDraft} onClick={() => switchWorkspace("accounting_staff")}>Prepare payouts as accountant</button>{" "}<button type="button" disabled={busy || canApprove} onClick={() => switchWorkspace("property_manager")}>Approve payouts as manager</button></p> : null}
      {error ? <p className="alert" role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {!ready && !error ? <p role="status">Loading distributions…</p> : null}
      {ready && canDraft ? <>
        <section>
          <h2>Payee destination</h2>
          <form onSubmit={createDestination}>
            <label>Payee<select value={partyId} onChange={(event) => setPartyId(event.target.value)} required disabled={busy}>{parties.map((party) => <option key={party.id} value={party.id}>{party.display_name}</option>)}</select></label>
            <label>Payment method<select value={channel} onChange={(event) => setChannel(event.target.value as "ZELLE" | "VENMO")} disabled={busy}><option value="ZELLE">Zelle</option><option value="VENMO">Venmo</option></select></label>
            <label>Masked destination label<input value={destinationLabel} onChange={(event) => setDestinationLabel(event.target.value)} maxLength={200} placeholder="Zelle email ending …example.test" required disabled={busy} /></label>
            <p>Use a fictional destination for simulation. Changing a destination invalidates earlier approval.</p>
            <button type="submit" disabled={busy || !partyId || !destinationLabel.trim()}>Save masked destination</button>
          </form>
        </section>
        <section>
          <h2>Prepare a payout batch</h2>
          <form onSubmit={draft}>
            <label>Property<select value={propertyId} onChange={(event) => { setPropertyId(event.target.value); setBatch(null); setExported(null); }} required disabled={busy}>{properties.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}</select></label>
            <label>As of<input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} required disabled={busy} /></label>
            <label>Management fee payee<select value={managementPartyId} onChange={(event) => setManagementPartyId(event.target.value)} disabled={busy}><option value="">Choose if management fees are outstanding</option>{parties.map((party) => <option key={party.id} value={party.id}>{party.display_name}</option>)}</select></label>
            <p>Outstanding management fees require a management payee and an active destination.</p>
            <button type="submit" disabled={busy || !propertyId}>Draft distribution</button>
          </form>
        </section>
      </> : null}
      {batch ? <section>
        <h2>Batch {batch.status}</h2>
        <p>{properties.find((property) => property.id === batch.property_id)?.name ?? "Property"} · Total {money.format(batch.total_cents / 100)}</p>
        <p>Batch id {batch.id}</p>
        <ul>{batch.items.map((item) => <li key={item.id}><strong>{parties.find((party) => party.id === item.recipient_id)?.display_name ?? item.recipient_id}</strong> · {item.kind} · {money.format(item.amount_cents / 100)} · {item.channel ?? "Payment method unavailable"} · {item.destination_label ?? "Destination unavailable"} · destination version {item.destination_version ?? "missing"} · {item.status}</li>)}</ul>
        {ready && canDraft && ["DRAFT", "VALIDATED"].includes(batch.status) ? <button type="button" disabled={busy} onClick={validateBatch}>Validate reservations</button> : null}
        {batch.status === "SETTLED" ? <p role="status">All items settled. <Link href="/banking">View simulated bank transactions</Link>.</p> : null}
        {uncertain ? <p role="status">Payments are queued, pending, or uncertain. <Link href={stripe ? "/stripe" : "/banking"}>{stripe ? "Track the approved Stripe jobs" : "Reconcile the original payment"}</Link> before taking further action.</p> : null}
        {batch.items.some((item) => item.status === "FAILED") ? <p>A declined simulated payment does not debit the bank account. Cancel the unpaid items to release their reservations, then draft a fresh batch. Completed payments are preserved.</p> : null}
        {canApprove && unpaid && batch.status !== "CANCELED" ? <button type="button" disabled={busy} onClick={cancelBatch}>Cancel unpaid items</button> : null}
      </section> : null}
      {ready && canApprove && approvable ? <section>
        <h2>Review and approve</h2>
        {demo && (simulated || stripe) ? <p><button type="button" disabled={busy} onClick={confirmDemoIdentity}>Confirm fictional manager identity</button></p> : <form onSubmit={stepUp}>
          <label>Step-up subject<input value={stepSubject} onChange={(event) => setStepSubject(event.target.value)} autoComplete="username" required disabled={busy} /></label>
          <label>Step-up password<input type="password" value={stepPassword} onChange={(event) => setStepPassword(event.target.value)} autoComplete="current-password" required disabled={busy} /></label>
          <button type="submit" disabled={busy}>Record step-up</button>
        </form>}
        <form onSubmit={approve}>
          <label>Payment posting date<input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} required disabled={busy} /></label>
          <label>Approval reason<textarea value={reason} onChange={(event) => setReason(event.target.value)} required disabled={busy} /></label>
          <p>{stripe ? "Review each Stripe ACH recipient, destination, and amount. Approval queues the sandbox payout worker; transferred funds and confirmed bank payments are tracked separately." : simulated ? "Review every recipient, destination, and amount above. Approval sends simulated money immediately when payouts are enabled." : "Approval lifetime comes from the server policy. This form cannot set it."}</p>
          <button type="submit" disabled={busy || !reason.trim() || !asOf}>{stripe ? "Approve Stripe sandbox payouts" : simulated ? "Approve and send simulated payments" : "Approve snapshot"}</button>
        </form>
      </section> : null}
      {ready && canApprove && batch && !simulated && !stripe && ["APPROVED", "PARTIALLY_SETTLED"].includes(batch.status) ? <p><button type="button" disabled={busy} onClick={exportBatch}>Export instructions</button>{" "}<button type="button" disabled={busy} onClick={submitDisabled}>Submit to provider</button></p> : null}
      {exported ? <section><h2>Export</h2><p>Export batch {exported.batch_id}</p><p>Export settled: {String(exported.settled)}</p><p>Export submitted: {String(exported.artifact.submitted)}</p><p>{exported.duplicate_download ? "Duplicate download" : "First download"}</p></section> : null}
      <p><button type="button" disabled={busy} onClick={() => { clearToken(); router.push("/login"); }}>Sign out</button></p>
    </>
  );
}
