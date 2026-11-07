"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { Me, Property, Unit, api, getToken } from "../../../lib/api";

export default function PropertyDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [property, setProperty] = useState<Property | null>(null);
  const [units, setUnits] = useState<Unit[]>([]);
  const [name, setName] = useState("");
  const [label, setLabel] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [params.id, router]);

  async function load(signal?: AbortSignal) {
    setLoading(true);
    try {
      const meResponse = await api("/v1/me", { signal });
      if (!meResponse.ok) {
        router.replace("/login");
        return;
      }
      setMe(await meResponse.json());
      const propertyResponse = await api(`/v1/properties/${params.id}`, { signal });
      const propertyBody = await propertyResponse.json();
      if (!propertyResponse.ok) {
        setError(propertyBody.error?.message ?? "Property not found.");
        return;
      }
      setProperty(propertyBody);
      setName(propertyBody.name);
      const unitResponse = await api(`/v1/properties/${params.id}/units`, { signal });
      const unitBody = await unitResponse.json();
      if (unitResponse.ok) setUnits(unitBody.items);
    } catch {
      if (!signal?.aborted) setError("The property could not be loaded. Refresh and try again.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  }

  async function onRename(event: FormEvent) {
    event.preventDefault();
    if (!property || loading || saving) return;
    setError("");
    setSaving(true);
    try {
      const response = await api(`/v1/properties/${property.id}`, {
        method: "PATCH",
        headers: { "If-Match": String(property.version) },
        body: JSON.stringify({ name }),
      });
      const body = await response.json();
      if (!response.ok) {
        setError(body.error?.message ?? "Rename failed.");
        return;
      }
      setProperty(body);
      setName(body.name);
    } catch {
      setError("The save result could not be confirmed. Refresh before trying again.");
    } finally {
      setSaving(false);
    }
  }

  async function onAddUnit(event: FormEvent) {
    event.preventDefault();
    if (!property) return;
    setError("");
    const response = await api(`/v1/properties/${property.id}/units`, {
      method: "POST",
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ label }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Unit was not added.");
      return;
    }
    setLabel("");
    await load();
  }

  const canUpdate = me?.capabilities.includes("properties.update") ?? false;
  const canAddUnit = me?.capabilities.includes("units.create") ?? false;

  return (
    <>
      <p>
        <Link href="/properties">Back to properties</Link>
      </p>
      <h1>{property?.name ?? "Property"}</h1>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {loading ? <p role="status">Loading property…</p> : null}
      {property && canUpdate && !loading ? (
        <form onSubmit={onRename}>
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} required disabled={saving} />
          </label>
          <button type="submit" disabled={saving || name === property.name}>{saving ? "Saving…" : "Save changes"}</button>
        </form>
      ) : null}
      <h2>Units</h2>
      <ul>
        {units.map((unit) => (
          <li key={unit.id}>{unit.label}</li>
        ))}
      </ul>
      {canAddUnit ? (
        <form onSubmit={onAddUnit}>
          <label>
            Unit label
            <input value={label} onChange={(event) => setLabel(event.target.value)} required />
          </label>
          <button type="submit">Add unit</button>
        </form>
      ) : null}
    </>
  );
}
