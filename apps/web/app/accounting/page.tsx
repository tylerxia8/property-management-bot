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
  const [canImport, setCanImport] = useState(false);
  const [bankFile, setBankFile] = useState<File | null>(null);
  const [importKey, setImportKey] = useState("");
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState("");

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
    setCanImport(me.capabilities.includes("bank_imports.write"));
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

  async function importBankCsv(event: FormEvent) {
    event.preventDefault();
    if (!bankFile || importing) return;
    setError("");
    setImportResult("");
    if (bankFile.size > 2 * 1024 * 1024) {
      setError("Choose a CSV file of at most 2 MiB.");
      return;
    }
    setImporting(true);
    try {
      let csvText: string;
      try {
        csvText = new TextDecoder("utf-8", { fatal: true }).decode(await bankFile.arrayBuffer());
      } catch {
        setError("The file could not be read as UTF-8. Export it as UTF-8 CSV and select it again.");
        return;
      }
      const response = await api("/v1/bank-imports", {
        method: "POST",
        headers: { "Idempotency-Key": importKey },
        body: JSON.stringify({ format: "canonical_csv_v1", csv_text: csvText }),
      });
      const body = await response.json();
      if (!response.ok) {
        const line = body.error?.details?.line;
        setError(`${body.error?.message ?? "The bank import failed."}${line ? ` Line ${line}.` : ""}`);
        return;
      }
      setImportResult(`Imported ${body.created} new transactions; ${body.existing} exact repeats. Ready for reconciliation.`);
    } catch {
      setError("The import result could not be confirmed. Retry this file to safely check the same request.");
    } finally {
      setImporting(false);
    }
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
      {canImport ? (
        <section aria-labelledby="bank-import-heading">
          <h2 id="bank-import-heading">Import bank transactions</h2>
          <p>
            Use a UTF-8 CSV with the columns bank_account_id, external_id, amount_cents, posted_on, in that order.
            Amounts are signed whole cents in USD; dates use YYYY-MM-DD. Use the existing bank account ID.
            Map your bank export to these columns first. Maximum 2 MiB and 10,000 rows.
          </p>
          <p>Importing adds reconciliation evidence. Deposits still require matching, verification, and availability review.</p>
          <form onSubmit={importBankCsv}>
            <label>
              Bank transaction CSV
              <input type="file" accept=".csv,text/csv" required disabled={importing} onChange={(event) => {
                setBankFile(event.target.files?.[0] ?? null);
                setImportKey(crypto.randomUUID());
                setImportResult("");
                setError("");
              }} />
            </label>
            <button type="submit" disabled={importing || !bankFile}>{importing ? "Importing…" : "Import transactions"}</button>
          </form>
          {importResult ? <p role="status">{importResult}</p> : null}
        </section>
      ) : null}
    </>
  );
}
