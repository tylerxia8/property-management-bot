"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "../../lib/api";

type Statement = {
  id: string;
  version: number;
  snapshot_hash: string;
  unrestricted_cents: number | null;
  period_start: string;
  period_end: string;
  reason: string;
};

export default function StatementsPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [items, setItems] = useState<Statement[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void start();
  }, [router]);

  async function start() {
    const response = await api("/v1/statements");
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Statements are unavailable.");
      setReady(true);
      return;
    }
    setItems(body.items);
    setReady(true);
  }

  return (
    <>
      <p>
        <Link href="/">Home</Link>
      </p>
      <h1>Owner statements</h1>
      <p>This snapshot is not a bank balance confirmation. Another owner cannot open it.</p>
      {error ? <p className="alert">{error}</p> : null}
      {ready && items.length === 0 ? <p>No statement is visible for this sign-in.</p> : null}
      {items.map((item) => (
        <article className="card" key={item.id}>
          <h2>
            Version {item.version} · {item.period_start} to {item.period_end}
          </h2>
          <p>Unrestricted cents: {item.unrestricted_cents ?? 0}</p>
          <p>Snapshot {item.snapshot_hash}</p>
          <p>{item.reason}</p>
        </article>
      ))}
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
