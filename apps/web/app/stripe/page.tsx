"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken, type Me } from "../../lib/api";

type Property = { id: string; name: string };
type Party = { id: string; display_name: string };
type Unit = { id: string; label: string };
type Lease = { id: string };
type Snapshot = {
  configured: boolean;
  sandbox: true;
  webhook_configured: boolean;
  worker_enabled: boolean;
  fee_payer: "MANAGEMENT";
  properties: { property_id: string; property_name: string; bank_account_id: string }[];
  recipients: { party_id: string; display_name: string; account_id: string | null; status: string; destination_id: string | null }[];
  rents: { id: string; property_id: string; lease_id: string; amount_cents: number; status: string; checkout_url: string | null; fee_cents: number; fee_due_cents: number }[];
  payouts: { id: string; batch_id: string; item_id: string; amount_cents: number; status: string; transfer_id: string | null; payout_id: string | null; last_error: string | null }[];
};

const dollars = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

async function request<T>(path: string, payload?: object): Promise<T> {
  const body = payload === undefined ? undefined : JSON.stringify(payload);
  const storageKey = `stripe-request:${path}:${body ?? ""}`;
  const key = body === undefined ? undefined : sessionStorage.getItem(storageKey) ?? crypto.randomUUID();
  if (key) sessionStorage.setItem(storageKey, key);
  for (let attempt = 0; attempt < 3; attempt++) {
    let response: Response;
    try {
      response = await api(path, {
        method: body === undefined ? "GET" : "POST",
        body,
        headers: key ? { "Idempotency-Key": key } : undefined,
        signal: AbortSignal.timeout(45000),
      });
    } catch {
      if (attempt === 2) throw new Error("The result could not be confirmed. Retry the same action; its request key is preserved.");
      await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
      continue;
    }
    if ((response.status === 429 || response.status >= 500) && attempt < 2) {
      await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
      continue;
    }
    const result = await response.json();
    if (!response.ok) throw new Error(result.error?.message ?? `Request failed (${response.status}).`);
    if (key) sessionStorage.removeItem(storageKey);
    return result as T;
  }
  throw new Error("The request could not be completed.");
}

export default function StripePage() {
  const router = useRouter();
  const [me, setMe] = useState<(Me & { organization_id: string }) | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [leases, setLeases] = useState<Lease[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [partyId, setPartyId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [leaseId, setLeaseId] = useState("");
  const [amount, setAmount] = useState("");
  const [reference, setReference] = useState("");
  const [postingDate, setPostingDate] = useState("");
  const [topups, setTopups] = useState<Record<string, string>>({});
  const [onboarding, setOnboarding] = useState("");
  const [checkout, setCheckout] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [error, setError] = useState("");
  const canManage = me?.roles.includes("property_manager") ?? false;
  const canCollect = !!me?.capabilities.includes("receipts.write") && me.capabilities.includes("allocations.write");

  async function perform(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The action could not be completed.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  async function refresh() {
    setSnapshot(await request<Snapshot>("/v1/stripe"));
  }

  useEffect(() => {
    setPostingDate(new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" }));
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void perform(async () => {
      const identity = await request<Me & { organization_id: string }>("/v1/me");
      setMe(identity);
      if (!identity.capabilities.includes("receipts.read") && !identity.capabilities.includes("distributions.approve")) {
        throw new Error("This role cannot view Stripe payments.");
      }
      await refresh();
      const [propertyData, partyData] = await Promise.all([
        request<{ items: Property[] }>("/v1/properties"),
        request<{ items: Party[] }>("/v1/parties"),
      ]);
      setProperties(propertyData.items);
      setParties(partyData.items);
      setPropertyId(propertyData.items[0]?.id ?? "");
      setPartyId(partyData.items[0]?.id ?? "");
    });
  }, [router]);

  useEffect(() => {
    let active = true;
    setUnits([]);
    setUnitId("");
    setLeases([]);
    setLeaseId("");
    if (propertyId && canCollect) {
      void request<{ items: Unit[] }>(`/v1/properties/${encodeURIComponent(propertyId)}/units`).then((body) => {
        if (!active) return;
        setUnits(body.items);
        setUnitId(body.items[0]?.id ?? "");
      }).catch((failure: Error) => { if (active) setError(failure.message); });
    }
    return () => { active = false; };
  }, [propertyId, canCollect]);

  useEffect(() => {
    let active = true;
    setLeases([]);
    setLeaseId("");
    if (unitId && canCollect) {
      void request<{ items: Lease[] }>(`/v1/units/${encodeURIComponent(unitId)}/leases`).then((body) => {
        if (!active) return;
        setLeases(body.items);
        setLeaseId(body.items[0]?.id ?? "");
      }).catch((failure: Error) => { if (active) setError(failure.message); });
    }
    return () => { active = false; };
  }, [unitId, canCollect]);

  function collect(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      if (!/^\d+(\.\d{1,2})?$/.test(amount)) throw new Error("Enter a positive dollar amount with at most two decimal places.");
      const [whole, fraction = ""] = amount.split(".");
      const cents = Number(whole) * 100 + Number(fraction.padEnd(2, "0"));
      if (!Number.isSafeInteger(cents) || cents <= 0) throw new Error("Enter a valid positive dollar amount.");
      const result = await request<{ checkout_url: string }>("/v1/stripe/rents", {
        property_id: propertyId, lease_id: leaseId, payer_party_id: partyId,
        amount_cents: cents, posting_date: postingDate, reference,
      });
      setCheckout(result.checkout_url);
      await refresh();
    });
  }

  return (
    <>
      <div className="row">
        <h1>Stripe sandbox</h1>
        <button disabled={busy || !snapshot} onClick={() => void perform(refresh)}>{busy ? "Working…" : "Refresh status"}</button>
      </div>
      <p>Test ACH rent collection and connected recipient payouts. Live payments are disabled. Management pays processing fees; owner rent remains gross.</p>
      {process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" ? <div className="row">
        <span>Demo role: {me?.roles.join(", ") ?? "Loading"}</span>
        {(["property_manager", "accounting_staff"] as const).map((role) => <button key={role} disabled={busy} onClick={() => void perform(async () => {
          const session = await request<{ token: string }>("/v1/demo/session", { role });
          setToken(session.token);
          window.location.assign("/stripe");
        })}>{role === "property_manager" ? "Use manager role" : "Use accountant role"}</button>)}
      </div> : null}
      {error ? <p className="alert" role="alert">{error}</p> : null}
      {!me && !error ? <p role="status">Loading Stripe workspace…</p> : null}
      {snapshot ? <>
        <section>
          <h2>Connection</h2>
          <p>Stripe: {snapshot.configured ? "Test key configured" : "Not configured"} · Webhook: {snapshot.webhook_configured ? "Configured" : "Not configured"} · Payout worker: {snapshot.worker_enabled ? "Enabled" : "Paused"}</p>
          {!snapshot.configured || !snapshot.webhook_configured ? <p>A server administrator must configure <code>STRIPE_SECRET_KEY</code> with a test key and <code>STRIPE_WEBHOOK_SECRET</code>. Enable approved payout processing with <code>STRIPE_WORKER_ENABLED</code>. Credentials stay on the server.</p> : null}
          <p>Only approved distribution batches enter the background payout worker. The worker sends while its kill switch is enabled. A transfer or submitted payout is separate from confirmation that the bank was paid.</p>
          <Link href="/distributions">Review and approve distributions</Link>
        </section>
        {canManage || canCollect ? <fieldset disabled={busy}>
          <legend>Choose property and party</legend>
          <label>Property<select value={propertyId} onChange={(event) => { setPropertyId(event.target.value); setUnitId(""); setLeaseId(""); }} required>
            <option value="">Select property</option>{properties.map((property) => <option key={property.id} value={property.id}>{property.name}</option>)}
          </select></label>
          <label>{canManage ? "Recipient" : "Rent payer"}<select value={partyId} onChange={(event) => setPartyId(event.target.value)} required>
            <option value="">Select party</option>{parties.map((party) => <option key={party.id} value={party.id}>{party.display_name}</option>)}
          </select></label>
        </fieldset> : null}
        {canManage ? <section>
          <h2>Prepare property and recipients</h2>
          <p>Register the property’s Stripe balance account, then complete bank details on Stripe’s hosted onboarding page. Refresh the recipient after onboarding to verify its payout destination.</p>
          <div className="row">
            <button disabled={busy || !propertyId} onClick={() => void perform(async () => {
              setSnapshot(await request<Snapshot>("/v1/stripe/properties", { property_id: propertyId }));
            })}>Register property account</button>
            <button disabled={busy || !partyId || !snapshot.configured} onClick={() => void perform(async () => {
              setOnboarding("");
              const result = await request<{ onboarding_url: string }>("/v1/stripe/recipients", { party_id: partyId });
              setOnboarding(result.onboarding_url);
              await refresh();
            })}>Create onboarding link</button>
          </div>
          {onboarding ? <p><a href={onboarding} target="_blank" rel="noopener noreferrer">Continue recipient onboarding on Stripe</a></p> : null}
        </section> : null}
        <section>
          <h2>Property accounts</h2>
          {snapshot.properties.length ? <ul>{snapshot.properties.map((property) => <li key={property.property_id}>{property.property_name} — {property.bank_account_id}</li>)}</ul> : <p>No property accounts registered.</p>}
          <h2>Recipients</h2>
          {snapshot.recipients.length ? snapshot.recipients.map((recipient) => <article key={recipient.party_id}>
            <h3>{recipient.display_name}</h3>
            <p>{recipient.status} · {recipient.account_id} · {recipient.destination_id ? "Verified destination recorded" : "No verified destination"}</p>
            {canManage ? <button disabled={busy || !snapshot.configured} onClick={() => void perform(async () => {
              setSnapshot(await request<Snapshot>(`/v1/stripe/recipients/${encodeURIComponent(recipient.party_id)}/refresh`, {}));
            })}>Refresh {recipient.display_name}</button> : null}
          </article>) : <p>No recipients onboarded.</p>}
        </section>
        {canCollect ? <section>
          <h2>Collect ACH rent</h2>
          <form onSubmit={collect}><fieldset disabled={busy || !snapshot.configured}>
            <legend>Tenant checkout</legend>
            <label>Unit<select value={unitId} onChange={(event) => { setUnitId(event.target.value); setLeaseId(""); }} required>
              <option value="">Select unit</option>{units.map((unit) => <option key={unit.id} value={unit.id}>{unit.label}</option>)}
            </select></label>
            <label>Lease<select value={leaseId} onChange={(event) => setLeaseId(event.target.value)} required>
              <option value="">Select lease</option>{leases.map((lease) => <option key={lease.id} value={lease.id}>{lease.id}</option>)}
            </select></label>
            <label>Rent amount (USD)<input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="decimal" placeholder="2000.00" required /></label>
            <label>Reference<input value={reference} onChange={(event) => setReference(event.target.value)} maxLength={80} required /></label>
            <button disabled={!propertyId || !partyId || !leaseId || !postingDate} type="submit">Create ACH checkout link</button>
          </fieldset></form>
          {checkout ? <p><a href={checkout} target="_blank" rel="noopener noreferrer">Open tenant ACH checkout</a></p> : null}
          <label>Posting date for rent and fee reimbursement<input type="date" value={postingDate} disabled={busy} onChange={(event) => setPostingDate(event.target.value)} required /></label>
        </section> : null}
        <section>
          <h2>Rent and processing fees</h2>
          <p>Refresh verifies settlement before importing cleared rent and its fee. Reimburse fees using an existing, verified management-funded Stripe top-up; this workspace does not initiate top-ups.</p>
          {snapshot.rents.length ? snapshot.rents.map((rent) => <article key={rent.id}>
            <h3>{dollars.format(rent.amount_cents / 100)} · {rent.status}</h3>
            <p>Rent {rent.id} · Lease {rent.lease_id}</p>
            <p>Stripe processing fee paid by management: {dollars.format(rent.fee_cents / 100)} · Reimbursement due: {dollars.format(rent.fee_due_cents / 100)}</p>
            {rent.checkout_url ? <p><a href={rent.checkout_url} target="_blank" rel="noopener noreferrer">Open ACH checkout</a></p> : null}
            {canCollect ? <fieldset disabled={busy || !snapshot.configured || !postingDate}>
              <legend>Verify rent {rent.id}</legend>
              <button onClick={() => void perform(async () => {
                setSnapshot(await request<Snapshot>(`/v1/stripe/rents/${encodeURIComponent(rent.id)}/refresh`, { posting_date: postingDate }));
              })}>Refresh settlement</button>
              {rent.fee_due_cents > 0 ? <form onSubmit={(event) => {
                event.preventDefault();
                void perform(async () => {
                  setSnapshot(await request<Snapshot>(`/v1/stripe/rents/${encodeURIComponent(rent.id)}/reimburse-fee`, { topup_id: topups[rent.id], posting_date: postingDate }));
                });
              }}>
                <p>The management top-up must equal the reimbursement due and include Stripe metadata: organization_id = {me?.organization_id}, rent_id = {rent.id}, purpose = management_processing_fee. Owner funds are not charged.</p>
                <label>Management top-up ID<input value={topups[rent.id] ?? ""} onChange={(event) => setTopups({ ...topups, [rent.id]: event.target.value })} placeholder="tu_…" pattern="tu_[A-Za-z0-9]+" required /></label>
                <button type="submit">Verify fee reimbursement</button>
              </form> : null}
            </fieldset> : null}
          </article>) : <p>No Stripe rent payments recorded.</p>}
        </section>
        <section>
          <h2>Approved payout jobs</h2>
          {snapshot.payouts.length ? snapshot.payouts.map((payout) => <article key={payout.id}>
            <h3>{dollars.format(payout.amount_cents / 100)} · {payout.status}</h3>
            <p><Link href={`/distributions?batch=${encodeURIComponent(payout.batch_id)}`}>Review batch {payout.batch_id}</Link></p>
            <p>Transfer: {payout.transfer_id ?? "Not created"} · Bank payout: {payout.payout_id ?? "Not created"}</p>
            {payout.last_error ? <p className="alert">{payout.last_error}</p> : null}
          </article>) : <p>No payout jobs recorded. Approve a validated distribution batch to queue one.</p>}
        </section>
      </> : null}
    </>
  );
}
