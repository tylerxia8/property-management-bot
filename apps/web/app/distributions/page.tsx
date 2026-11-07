"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "../../lib/api";

type Property = { id: string; name: string };
type Party = { id: string; display_name: string };
type Item = { id: string; kind: string; amount_cents: number; status: string; provider_key: string };
type Batch = {
  id: string;
  status: string;
  snapshot_hash: string | null;
  total_cents: number;
  submitted: boolean;
  items: Item[];
};
type ExportBody = {
  batch_id: string;
  duplicate_download: boolean;
  settled: boolean;
  artifact: { submitted: boolean; settled: boolean; items: { id: string }[] };
};

export default function DistributionsPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [canDraft, setCanDraft] = useState(false);
  const [canApprove, setCanApprove] = useState(false);
  const [properties, setProperties] = useState<Property[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [partyId, setPartyId] = useState("");
  const [asOf, setAsOf] = useState("2026-11-22");
  const [batch, setBatch] = useState<Batch | null>(null);
  const [stepSubject, setStepSubject] = useState("");
  const [stepPassword, setStepPassword] = useState("");
  const [reason, setReason] = useState("");
  const [exported, setExported] = useState<ExportBody | null>(null);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    const batchId = new URLSearchParams(window.location.search).get("batch");
    void start(batchId);
  }, [router]);

  async function start(batchId: string | null) {
    const meResponse = await api("/v1/me");
    if (!meResponse.ok) {
      router.replace("/login");
      return;
    }
    const me = await meResponse.json();
    const draft = me.capabilities.includes("distributions.draft");
    const approve = me.capabilities.includes("distributions.approve");
    setCanDraft(draft);
    setCanApprove(approve);
    if (draft) {
      const propertyResponse = await api("/v1/properties");
      const propertyBody = await propertyResponse.json();
      if (propertyResponse.ok) {
        setProperties(propertyBody.items);
        if (propertyBody.items[0]) setPropertyId(propertyBody.items[0].id);
      }
      const partyResponse = await api("/v1/parties");
      if (partyResponse.ok) {
        const partyBody = await partyResponse.json();
        setParties(partyBody.items);
        const owner = partyBody.items.find((item: Party) => item.display_name === "Elm Owner");
        setPartyId(owner?.id ?? partyBody.items[0]?.id ?? "");
      }
    }
    if (batchId && (draft || approve)) {
      const loaded = await api(`/v1/distribution-batches/${batchId}`);
      if (loaded.ok) setBatch(await loaded.json());
    }
    setReady(true);
  }

  async function createDestination(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await api("/v1/payee-destinations", {
      method: "POST",
      body: JSON.stringify({ party_id: partyId, masked_label: "****1000" }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "The destination was not saved.");
      return;
    }
    setNotice(`Destination version ${body.version} saved for the masked label.`);
  }

  async function draft(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await api("/v1/distribution-batches", {
      method: "POST",
      body: JSON.stringify({
        property_id: propertyId,
        as_of: asOf,
        management_party_id: null,
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "The draft was not created.");
      return;
    }
    setBatch(body);
    setExported(null);
    router.replace(`/distributions?batch=${body.id}`);
  }

  async function validateBatch() {
    if (!batch) return;
    setError("");
    const response = await api(`/v1/distribution-batches/${batch.id}/validate`, { method: "POST" });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Validation did not reserve funds.");
      return;
    }
    setBatch(body);
  }

  async function stepUp(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await api("/v1/auth/local/step-up", {
      method: "POST",
      body: JSON.stringify({ subject: stepSubject, password: stepPassword }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Step-up failed.");
      return;
    }
    setNotice("Dev/test step-up recorded. This is not production MFA.");
  }

  async function approve(event: FormEvent) {
    event.preventDefault();
    if (!batch?.snapshot_hash) return;
    setError("");
    const response = await api(`/v1/distribution-batches/${batch.id}/approve`, {
      method: "POST",
      body: JSON.stringify({
        snapshot_hash: batch.snapshot_hash,
        reason,
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Approval was not recorded.");
      return;
    }
    setBatch(body);
  }

  async function exportBatch() {
    if (!batch) return;
    setError("");
    const response = await api(`/v1/distribution-batches/${batch.id}/export`, { method: "POST" });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Export failed.");
      return;
    }
    setExported(body);
  }

  async function submitDisabled() {
    if (!batch) return;
    setError("");
    const response = await api(`/v1/distribution-batches/${batch.id}/submit`, {
      method: "POST",
      body: JSON.stringify({ posting_date: asOf, scripts: {} }),
    });
    const body = await response.json();
    setNotice(body.error?.code ?? body.status ?? "Submit returned no code.");
  }

  return (
    <>
      <p>
        <Link href="/">Home</Link>
      </p>
      <h1>Distribution approval</h1>
      <p className="banner">
        Bank submission is disabled. Export does not mark the batch submitted or settled.
        A dev/test step-up is a local password check, not production MFA.
      </p>
      {error ? <p className="alert">{error}</p> : null}
      {notice ? <p>{notice}</p> : null}
      {ready && canDraft ? (
        <>
          <form onSubmit={createDestination}>
            <label>
              Property
              <select value={propertyId} onChange={(event) => setPropertyId(event.target.value)}>
                {properties.map((property) => (
                  <option key={property.id} value={property.id}>
                    {property.name}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Payee
              <select value={partyId} onChange={(event) => setPartyId(event.target.value)}>
                {parties.map((party) => (
                  <option key={party.id} value={party.id}>
                    {party.display_name}
                  </option>
                ))}
              </select>
            </label>
            <button type="submit">Save masked destination</button>
          </form>
          <form onSubmit={draft}>
            <label>
              As of
              <input type="date" value={asOf} onChange={(event) => setAsOf(event.target.value)} required />
            </label>
            <button type="submit">Draft distribution</button>
          </form>
        </>
      ) : null}
      {batch ? (
        <section>
          <h2>Batch {batch.status}</h2>
          <p>Batch id {batch.id}</p>
          <p>Submitted: {String(batch.submitted)}</p>
          <p>Total cents: {batch.total_cents}</p>
          {batch.snapshot_hash ? <p>Snapshot {batch.snapshot_hash}</p> : null}
          <ul>
            {batch.items.map((item) => (
              <li key={item.id}>
                Item {item.kind} {item.amount_cents} cents {item.status}
              </li>
            ))}
          </ul>
          {ready && canDraft && batch.status === "DRAFT" ? (
            <button type="button" onClick={() => void validateBatch()}>
              Validate reservations
            </button>
          ) : null}
        </section>
      ) : null}
      {ready && canApprove && batch ? (
        <>
          <form onSubmit={stepUp}>
            <label>
              Step-up subject
              <input value={stepSubject} onChange={(event) => setStepSubject(event.target.value)} autoComplete="username" required />
            </label>
            <label>
              Step-up password
              <input
                type="password"
                value={stepPassword}
                onChange={(event) => setStepPassword(event.target.value)}
                autoComplete="current-password"
                required
              />
            </label>
            <button type="submit">Record step-up</button>
          </form>
          <form onSubmit={approve}>
            <label>
              Approval reason
              <textarea value={reason} onChange={(event) => setReason(event.target.value)} required />
            </label>
            <p>Approval lifetime comes from the server policy. This form cannot set it.</p>
            <button type="submit">Approve snapshot</button>
          </form>
          <p>
            <button type="button" onClick={() => void exportBatch()}>
              Export instructions
            </button>{" "}
            <button type="button" onClick={() => void submitDisabled()}>
              Submit to provider
            </button>
          </p>
        </>
      ) : null}
      {exported ? (
        <section>
          <h2>Export</h2>
          <p>Export batch {exported.batch_id}</p>
          <p>Export settled: {String(exported.settled)}</p>
          <p>Export submitted: {String(exported.artifact.submitted)}</p>
          <p>{exported.duplicate_download ? "Duplicate download" : "First download"}</p>
        </section>
      ) : null}
      <p>
        <button
          type="button"
          onClick={() => {
            clearToken();
            router.push("/login");
          }}
        >
          Sign out
        </button>
      </p>
    </>
  );
}
