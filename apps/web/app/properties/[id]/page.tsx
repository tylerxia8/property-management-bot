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

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [params.id, router]);

  async function load() {
    const meResponse = await api("/v1/me");
    if (!meResponse.ok) {
      router.replace("/login");
      return;
    }
    setMe(await meResponse.json());
    const propertyResponse = await api(`/v1/properties/${params.id}`);
    const propertyBody = await propertyResponse.json();
    if (!propertyResponse.ok) {
      setError(propertyBody.error?.message ?? "Property not found.");
      return;
    }
    setProperty(propertyBody);
    setName(propertyBody.name);
    const unitResponse = await api(`/v1/properties/${params.id}/units`);
    const unitBody = await unitResponse.json();
    if (unitResponse.ok) setUnits(unitBody.items);
  }

  async function onRename(event: FormEvent) {
    event.preventDefault();
    if (!property) return;
    setError("");
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
    await load();
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
      {property && canUpdate ? (
        <form onSubmit={onRename}>
          <label>
            Name
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>
          <button type="submit">Save changes</button>
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
