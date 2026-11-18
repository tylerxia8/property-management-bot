"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken } from "../../lib/api";

type Property = { id: string; name: string };
type Party = { id: string; display_name: string };
type Unit = { id: string; label: string };
type Lease = { id: string; agreed_rent_cents: number; label: string };
type Account = { id: string; property_id: string; property_name: string; balance_cents: number; next_outcome: "settle" | "timeout" | "fail" };
type Transaction = { id: string; account_id: string; kind: "RECEIPT" | "PAYOUT"; channel: "ZELLE" | "VENMO"; amount_cents: number; status: "SETTLED" | "FAILED"; reference: string; created_at: string; item_id: string | null; receipt_id: string | null };
type Batch = { id: string; property_id: string; status: string; total_cents: number; items: { id: string; status: string }[] };
type Snapshot = { simulator: true; bank_contacted: false; enabled: boolean; accounts: Account[]; transactions: Transaction[]; batches: Batch[] };
type Switches = { messaging_enabled: boolean; calendar_enabled: boolean; payment_enabled: boolean };

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

async function read<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await api(path, { ...init, signal: AbortSignal.timeout(15000) });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error?.message ?? "The request could not be completed.");
  return body as T;
}

export default function BankingPage() {
  const router = useRouter();
  const [data, setData] = useState<Snapshot | null>(null);
  const [properties, setProperties] = useState<Property[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [leases, setLeases] = useState<Lease[]>([]);
  const [canApprove, setCanApprove] = useState(false);
  const [canReceive, setCanReceive] = useState(false);
  const [switches, setSwitches] = useState<Switches | null>(null);
  const [propertyId, setPropertyId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [leaseId, setLeaseId] = useState("");
  const [payerId, setPayerId] = useState("");
  const [amount, setAmount] = useState("");
  const [channel, setChannel] = useState<"ZELLE" | "VENMO">("ZELLE");
  const [postingDate, setPostingDate] = useState("");
  const [reference, setReference] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingLeases, setLoadingLeases] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const inFlight = useRef(false);
  const account = data?.accounts.find((item) => item.id === accountId);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    setPostingDate(new Date().toLocaleDateString("en-CA", { timeZone: "America/Chicago" }));
    void (async () => {
      try {
        const me = await read<{ capabilities: string[] }>("/v1/me");
        const approve = me.capabilities.includes("distributions.approve");
        const receive = me.capabilities.includes("receipts.write") && me.capabilities.includes("allocations.write");
        if (!approve && !receive) throw new Error("Your account does not have access to the simulated bank.");
        const [snapshot, propertyList, partyList, flags] = await Promise.all([
          read<Snapshot>("/v1/simulated-bank"),
          read<{ items: Property[] }>("/v1/properties"),
          read<{ items: Party[] }>("/v1/parties"),
          approve ? read<Switches>("/v1/kill-switches") : Promise.resolve(null),
        ]);
        if (!active) return;
        setCanApprove(approve);
        setCanReceive(receive);
        setData(snapshot);
        setProperties(propertyList.items);
        setParties(partyList.items);
        setSwitches(flags);
        setPropertyId(propertyList.items[0]?.id ?? "");
        setAccountId(snapshot.accounts[0]?.id ?? "");
        setPayerId(partyList.items[0]?.id ?? "");
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : "The simulated bank could not be loaded.");
      }
    })();
    return () => { active = false; };
  }, [router]);

  useEffect(() => {
    let active = true;
    setLeases([]);
    setLeaseId("");
    if (!account?.property_id || !canReceive) return;
    setLoadingLeases(true);
    void (async () => {
      try {
        const units = await read<{ items: Unit[] }>(`/v1/properties/${account.property_id}/units`);
        const groups = await Promise.all(units.items.map(async (unit) => {
          const result = await read<{ items: Omit<Lease, "label">[] }>(`/v1/units/${unit.id}/leases`);
          return result.items.map((lease) => ({ ...lease, label: `${unit.label} · ${money.format(lease.agreed_rent_cents / 100)} rent` }));
        }));
        if (!active) return;
        const available = groups.flat();
        setLeases(available);
        setLeaseId(available[0]?.id ?? "");
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : "Leases could not be loaded.");
      } finally {
        if (active) setLoadingLeases(false);
      }
    })();
    return () => { active = false; };
  }, [account?.property_id, canReceive]);

  async function mutate(path: string, body: object, message: string) {
    if (inFlight.current) return false;
    inFlight.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const serialized = JSON.stringify(body);
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${path}:${serialized}`));
      const storageKey = `grok_simulated_request_${Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("")}`;
      let key = sessionStorage.getItem(storageKey);
      if (!key) {
        key = crypto.randomUUID();
        sessionStorage.setItem(storageKey, key);
      }
      const snapshot = await read<Snapshot>(path, { method: "POST", headers: { "Idempotency-Key": key }, body: serialized });
      sessionStorage.removeItem(storageKey);
      setData(snapshot);
      setAccountId((current) => current || snapshot.accounts[0]?.id || "");
      setNotice(message);
      try {
        setData(await read<Snapshot>("/v1/simulated-bank"));
      } catch {
        setError("The request succeeded, but the latest bank history could not be refreshed. Refresh the page before continuing.");
      }
      return true;
    } catch (failure) {
      setError(`${failure instanceof Error ? failure.message : "The result could not be confirmed."} If the connection was interrupted, retry the same details to safely recover the result.`);
      return false;
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  function receiveRent(event: FormEvent) {
    event.preventDefault();
    if (!/^\d+(\.\d{1,2})?$/.test(amount)) {
      setError("Enter a positive dollar amount with no more than two decimal places.");
      return;
    }
    const [dollars, cents = ""] = amount.split(".");
    const amountCents = Number(dollars) * 100 + Number(cents.padEnd(2, "0"));
    if (!Number.isSafeInteger(amountCents) || amountCents <= 0) {
      setError("Enter a positive amount within the supported range.");
      return;
    }
    void mutate("/v1/simulated-bank/receipts", { account_id: accountId, lease_id: leaseId, payer_party_id: payerId, amount_cents: amountCents, channel, posting_date: postingDate, reference: reference.trim() }, "Simulated rent received, cleared, and allocated. No bank was contacted.").then((saved) => {
      if (saved) {
        setAmount("");
        setReference("");
      }
    });
  }

  async function changePayments() {
    if (!switches || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const flags = await read<Switches>("/v1/kill-switches", { method: "PUT", body: JSON.stringify({ ...switches, payment_enabled: !switches.payment_enabled }) });
      setSwitches(flags);
      setNotice(flags.payment_enabled ? "Approved simulated payouts are enabled." : "New simulated payouts are paused.");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The payout switch could not be changed.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  async function switchWorkspace(role: string) {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await read<{ token: string }>("/v1/demo/session", { method: "POST", body: JSON.stringify({ role }) });
      setToken(result.token);
      window.location.reload();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "The demo workspace could not be opened.");
      inFlight.current = false;
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Simulated banking</h1>
      <p className="banner">Fictional money only. Zelle and Venmo are simulated. No Wells Fargo account is connected and no real payments are sent.</p>
      {process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" ? <p>Demo workspace: <button type="button" disabled={busy || canReceive} onClick={() => void switchWorkspace("accounting_staff")}>Receive rent as accountant</button>{" "}<button type="button" disabled={busy || canApprove} onClick={() => void switchWorkspace("property_manager")}>Approve payouts as manager</button></p> : null}
      {error ? <p className="alert" role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {!data && !error ? <p role="status">Loading the simulated bank…</p> : null}
      {data && !data.enabled ? <p>Simulated banking is unavailable in this environment.</p> : null}
      {data?.enabled ? (
        <>
          <section>
            <h2>Accounts</h2>
            <p>Rent received into these accounts funds approved payouts. Each property keeps its own funds.</p>
            {canApprove && process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" ? <p><button type="button" disabled={busy} onClick={() => void mutate("/v1/simulated-bank/demo-setup", {}, "Fictional banking setup ready with a zero-fee, zero-reserve agreement. Enable simulated payouts separately before approval.")}>Set up fictional banking example</button> This prepares the seeded fictional property with an owner, agreement, account, and destination. This does not change the payout switch.</p> : null}
            {data.accounts.length ? <ul>{data.accounts.map((item) => <li key={item.id}><strong>{item.property_name}</strong>: {money.format(item.balance_cents / 100)} simulated balance</li>)}</ul> : <p>No simulated accounts yet. A manager can create one below.</p>}
            {canApprove ? <form onSubmit={(event) => { event.preventDefault(); void mutate("/v1/simulated-bank/accounts", { property_id: propertyId }, "Simulated account ready. Receive fictional rent to fund it."); }}>
              <label>Property<select value={propertyId} onChange={(event) => setPropertyId(event.target.value)} required disabled={busy}>{properties.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
              <button type="submit" disabled={busy || !propertyId}>Create simulated account</button>
            </form> : null}
          </section>
          {canReceive ? <section>
            <h2>Receive simulated rent</h2>
            <p>Record a fictional tenant payment. An existing ownership period and property agreement are required; that agreement determines fees and owner allocations.</p>
            <form onSubmit={receiveRent}>
              <label>Receiving account<select value={accountId} onChange={(event) => setAccountId(event.target.value)} required disabled={busy}><option value="">Choose an account</option>{data.accounts.map((item) => <option key={item.id} value={item.id}>{item.property_name}</option>)}</select></label>
              <label>Lease<select value={leaseId} onChange={(event) => setLeaseId(event.target.value)} required disabled={busy || loadingLeases}><option value="">{loadingLeases ? "Loading leases…" : "Choose a lease"}</option>{leases.map((item) => <option key={item.id} value={item.id}>{item.label}</option>)}</select></label>
              {account && !loadingLeases && !leases.length ? <p>This property needs a lease before rent can be received. <Link href="/accounting">Open rent & accounting</Link>.</p> : null}
              <label>Payer<select value={payerId} onChange={(event) => setPayerId(event.target.value)} required disabled={busy}>{parties.map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}</select></label>
              <label>Payment method<select value={channel} onChange={(event) => setChannel(event.target.value as "ZELLE" | "VENMO")} disabled={busy}><option value="ZELLE">Zelle (simulated)</option><option value="VENMO">Venmo (simulated)</option></select></label>
              <label>Amount (USD)<input inputMode="decimal" value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="1500.00" required disabled={busy} /></label>
              <label>Posting date<input type="date" value={postingDate} onChange={(event) => setPostingDate(event.target.value)} required disabled={busy} /></label>
              <label>Payment reference<input value={reference} onChange={(event) => setReference(event.target.value)} maxLength={80} required disabled={busy} /></label>
              <button type="submit" disabled={busy || !leaseId || !accountId || !reference.trim()}>Receive simulated rent</button>
            </form>
          </section> : null}
          <section>
            <h2>Approved payouts</h2>
            <p>Prepare a distribution, validate its funding, and approve the exact amounts and recipients. Approval automatically sends the simulated payments.</p>
            <p><Link href="/distributions">Prepare and approve payouts</Link></p>
            {canApprove && switches ? <p>Simulated payouts are {switches.payment_enabled ? "enabled" : "paused"}. <button type="button" onClick={() => void changePayments()} disabled={busy}>{switches.payment_enabled ? "Pause payouts" : "Enable simulated payouts"}</button></p> : null}
            {canApprove ? <label>Reconciliation posting date<input type="date" value={postingDate} onChange={(event) => setPostingDate(event.target.value)} required disabled={busy} /></label> : null}
            {canApprove && data.accounts.length ? <form onSubmit={(event) => event.preventDefault()}>
              <label>Simulation account<select value={accountId} onChange={(event) => setAccountId(event.target.value)} required disabled={busy}><option value="">Choose an account</option>{data.accounts.map((item) => <option key={item.id} value={item.id}>{item.property_name}</option>)}</select></label>
              <label>Next payout outcome<select value={account?.next_outcome ?? "settle"} onChange={(event) => { if (accountId) void mutate(`/v1/simulated-bank/accounts/${accountId}/outcome`, { outcome: event.target.value }, "Next simulated payout outcome saved."); }} disabled={busy || !accountId}><option value="settle">Successful payment</option><option value="timeout">Accepted, but response times out</option><option value="fail">Declined before sending</option></select></label>
              <p>A timeout keeps the payment uncertain until reconciliation. Reconciliation checks the original payment without sending it again.</p>
            </form> : null}
            {data.batches.length ? <ul>{data.batches.map((batch) => <li key={batch.id}><Link href={`/distributions?batch=${encodeURIComponent(batch.id)}`}>{properties.find((item) => item.id === batch.property_id)?.name ?? "Property"} · {money.format(batch.total_cents / 100)}</Link> · {batch.status}{canApprove && batch.items.some((item) => item.status === "UNKNOWN") ? <> <button type="button" disabled={busy || !postingDate} onClick={() => void mutate(`/v1/simulated-bank/batches/${batch.id}/reconcile`, { posting_date: postingDate }, "Original simulated payment reconciled. No duplicate transfer was sent.")}>Reconcile uncertain payment</button></> : null}</li>)}</ul> : <p>No distribution batches yet.</p>}
          </section>
          <section>
            <h2>Simulated transaction history</h2>
            {data.transactions.length ? <div style={{ overflowX: "auto" }}><table><thead><tr><th scope="col">Date</th><th scope="col">Property</th><th scope="col">Payment</th><th scope="col">Amount</th><th scope="col">Status</th><th scope="col">Reference</th></tr></thead><tbody>{data.transactions.map((item) => <tr key={item.id}><td>{new Date(item.created_at).toLocaleString("en-US", { timeZone: "America/Chicago" })}</td><td>{data.accounts.find((entry) => entry.id === item.account_id)?.property_name ?? "Property"}</td><td>{item.kind === "RECEIPT" ? "Rent received" : "Payout"} · {item.channel === "ZELLE" ? "Zelle" : "Venmo"}</td><td>{item.kind === "RECEIPT" ? "+" : "−"}{money.format(item.amount_cents / 100)}</td><td>{item.status}</td><td>{item.reference}</td></tr>)}</tbody></table></div> : <p>No simulated transactions yet.</p>}
          </section>
        </>
      ) : null}
    </>
  );
}
