"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "../../lib/api";

type Property = { id: string; name: string };
type Unit = { id: string; label: string };
type Party = { id: string; display_name: string };
type Lease = { id: string };
type Receipt = { status: string; available_cents: number; amount_cents: number; receipt_number: number };

export default function AccountingPage() {
  const router = useRouter();
  const [properties, setProperties] = useState<Property[]>([]);
  const [units, setUnits] = useState<Unit[]>([]);
  const [parties, setParties] = useState<Party[]>([]);
  const [leases, setLeases] = useState<Lease[]>([]);
  const [propertyId, setPropertyId] = useState("");
  const [unitId, setUnitId] = useState("");
  const [payerId, setPayerId] = useState("");
  const [amount, setAmount] = useState("200000");
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [balances, setBalances] = useState("");
  const [error, setError] = useState("");
  const [canWrite, setCanWrite] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void start();
  }, [router]);

  async function start() {
    const meResponse = await api("/v1/me");
    if (!meResponse.ok) {
      router.replace("/login");
      return;
    }
    const me = await meResponse.json();
    setCanWrite(me.capabilities.includes("receipts.write"));
    const propertyResponse = await api("/v1/properties");
    const propertyBody = await propertyResponse.json();
    if (!propertyResponse.ok) {
      setError(propertyBody.error?.message ?? "Properties are unavailable.");
      return;
    }
    setProperties(propertyBody.items);
    if (propertyBody.items[0]) setPropertyId(propertyBody.items[0].id);
    const partyResponse = await api("/v1/parties");
    if (partyResponse.ok) {
      const partyBody = await partyResponse.json();
      setParties(partyBody.items);
      if (partyBody.items[0]) setPayerId(partyBody.items[0].id);
    }
  }

  useEffect(() => {
    if (!propertyId) return;
    void api(`/v1/properties/${propertyId}/units`).then(async (response) => {
      if (!response.ok) return;
      const body = await response.json();
      setUnits(body.items);
      if (body.items[0]) setUnitId(body.items[0].id);
    });
    void api(`/v1/properties/${propertyId}/balances`).then(async (response) => {
      if (!response.ok) return;
      const body = await response.json();
      const cash = body.accounts.find((item: { code: string }) => item.code === "1010");
      const available = body.accounts.find((item: { code: string }) => item.code === "1030");
      setBalances(`Custody ${cash?.amount_cents ?? 0} cents; bank available ${available?.amount_cents ?? 0} cents.`);
    });
  }, [propertyId]);

  useEffect(() => {
    if (!unitId) return;
    void api(`/v1/units/${unitId}/leases`).then(async (response) => {
      if (!response.ok) return;
      const body = await response.json();
      setLeases(body.items);
    });
  }, [unitId]);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await api("/v1/receipts", {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({
        property_id: propertyId,
        unit_id: unitId,
        lease_id: leases[0]?.id,
        payer_party_id: payerId,
        method: "CHECK",
        amount_cents: Number(amount),
        received_at: new Date().toISOString(),
        posting_date: new Date().toISOString().slice(0, 10),
        reference: "masked-ui-check",
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "The receipt was not recorded.");
      return;
    }
    setReceipt(body);
  }

  return (
    <>
      <p>
        <Link href="/">Home</Link>
      </p>
      <div className="row">
        <h1>Receipts</h1>
        <button
          type="button"
          onClick={() => {
            clearToken();
            router.push("/login");
          }}
        >
          Sign out
        </button>
      </div>
      <p>Recorded checks stay in custody until a deposit is verified and made available. This screen does not submit money.</p>
      {balances ? <p>{balances}</p> : null}
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {canWrite ? (
        <form onSubmit={onSubmit}>
          <label>
            Property
            <select value={propertyId} onChange={(event) => setPropertyId(event.target.value)}>
              {properties.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Unit
            <select value={unitId} onChange={(event) => setUnitId(event.target.value)}>
              {units.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Payer
            <select value={payerId} onChange={(event) => setPayerId(event.target.value)}>
              {parties.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.display_name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Amount (cents)
            <input value={amount} onChange={(event) => setAmount(event.target.value)} inputMode="numeric" required />
          </label>
          <button type="submit">Record check</button>
        </form>
      ) : (
        <p>This role cannot record receipts.</p>
      )}
      {receipt ? (
        <p>
          Receipt {receipt.receipt_number} is {receipt.status}. Available cents: {receipt.available_cents}. Amount cents: {receipt.amount_cents}.
        </p>
      ) : null}
    </>
  );
}
