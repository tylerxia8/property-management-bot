"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Me, Property, api, clearToken, getToken } from "../../lib/api";

const EMPTY = {
  name: "",
  address_line1: "",
  city: "",
  region: "NC",
  postal_code: "",
  country_code: "US",
  timezone: "America/New_York",
};

export default function PropertiesPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [items, setItems] = useState<Property[]>([]);
  const [error, setError] = useState("");
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const loadVersion = useRef(0);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
    return () => { loadVersion.current += 1; };
  }, [router]);

  async function load() {
    const version = ++loadVersion.current;
    const meResponse = await api("/v1/me");
    if (version !== loadVersion.current) return;
    if (meResponse.status === 401) {
      clearToken();
      router.replace("/login");
      return;
    }
    const meBody = await meResponse.json();
    if (version !== loadVersion.current) return;
    setMe(meBody);
    const listResponse = await api("/v1/properties");
    const listBody = await listResponse.json();
    if (version !== loadVersion.current) return;
    if (!listResponse.ok) {
      setError(listBody.error?.message ?? "Properties are unavailable.");
      setItems([]);
      return;
    }
    setItems(listBody.items);
  }

  async function onCreate(event: FormEvent) {
    event.preventDefault();
    if (saving) return;
    setSaving(true);
    loadVersion.current += 1;
    setError("");
    try {
      const response = await api("/v1/properties", {
        method: "POST",
        headers: { "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify(form),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(body.error?.message ?? "Create failed.");
        return;
      }
      loadVersion.current += 1;
      setForm(EMPTY);
      setItems(current => [...current.filter(item => item.id !== body.id), body]);
    } catch {
      setError("The property could not be saved. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  const canCreate = me?.capabilities.includes("properties.create") ?? false;

  return (
    <>
      <div className="row">
        <h1>Properties</h1>
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
      {me ? (
        <p>
          Signed in as {me.display_name} with local dev/test auth, not production OIDC or MFA.
          Capabilities: {me.capabilities.join(", ") || "none"}.
        </p>
      ) : null}
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {canCreate ? (
        <form onSubmit={onCreate}>
          <h2>Create property</h2>
          {(
            [
              ["name", "Name"],
              ["address_line1", "Address"],
              ["city", "City"],
              ["region", "Region"],
              ["postal_code", "Postal code"],
              ["country_code", "Country"],
              ["timezone", "Timezone"],
            ] as const
          ).map(([key, label]) => (
            <label key={key}>
              {label}
              <input
                value={form[key]}
                disabled={saving}
                onChange={(event) => setForm({ ...form, [key]: event.target.value })}
                required
              />
            </label>
          ))}
          <button type="submit" disabled={saving}>Create property</button>
        </form>
      ) : null}
      <ul>
        {items.map((item) => (
          <li key={item.id} className="card">
            <Link href={`/properties/${item.id}`}>{item.name}</Link>
            <div>
              {item.address_line1}, {item.city} {item.region} {item.postal_code} · {item.timezone} · version {item.version}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}
