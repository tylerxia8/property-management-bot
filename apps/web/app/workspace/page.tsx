"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { workflowRequest } from "../maintenance/workflow-panel";
import styles from "./workspace.module.css";

type Project = "guest_recovery" | "cleaner_scheduler";
type Data = { mode: "demo" | "workspace"; apps: { project: Project; url: string }[]; properties: { external_property_id: string; unit_id: string; name: string; label: string }[]; units: { id: string; name: string; label: string }[] };
const names = { guest_recovery: "Guest Recovery", cleaner_scheduler: "Cleaner Scheduling" };

export default function Workspace() {
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [connection, setConnection] = useState<{ token: string; expires_at: string; mode: string; source: Project } | null>(null);
  const [pending, setPending] = useState<{ path: string; body: string; key: string } | null>(null);
  useEffect(() => { void workflowRequest("/v1/maintenance-workspace").then(setData).catch(value => setError(value.message)); }, []);
  async function save(event: FormEvent<HTMLFormElement>, path: string) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    const body = JSON.stringify(Object.fromEntries(new FormData(event.currentTarget)));
    const command = pending?.path === path && pending.body === body ? pending : { path, body, key: crypto.randomUUID() };
    setPending(command);
    try {
      const result = await workflowRequest(path, { method: "POST", headers: { "Idempotency-Key": command.key }, body });
      setPending(null);
      if (path.endsWith("connections")) setConnection(result);
      else setData(await workflowRequest("/v1/maintenance-workspace"));
      setNotice(path.endsWith("connections") ? "Connection token created. Copy it into the other app’s connection settings." : "Saved.");
    } catch (value) { setError(value instanceof Error ? value.message : "Unable to save."); }
    finally { setBusy(false); }
  }
  return <section className={styles.workspace}>
    <h1>Your Airbnb workspace</h1>
    <p>Guest issues, cleaning, and repairs in one place.</p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <nav className={styles.apps} aria-label="Airbnb projects"><Link href="/maintenance/review"><strong>Maintenance</strong><span>Review requests and coordinate repairs</span></Link>{data?.apps.map(app => <a key={app.project} href={app.url} target="_blank" rel="noopener noreferrer"><strong>{names[app.project]}</strong><span>Open workspace ↗</span></a>)}</nav>
    {!data && !error && <p>Loading workspace…</p>}
    {data?.mode === "demo" && <p role="status">This is a demo maintenance workspace. You can set up links and preview connections, but real guest imports stay blocked until real accounts and homes are configured.</p>}
    {data && <>
      <details className={styles.setup}><summary>Connect your apps</summary><p>Each app keeps its own sign-in. Connections share selected requests and repair status; they do not send guest messages or change cleaning schedules.</p>
        <form onSubmit={event => void save(event, "/v1/maintenance-workspace/apps")}><label>App<select name="project">{Object.entries(names).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label><label>Workspace address<input name="url" type="url" required placeholder="https://your-app.example.com" /></label><button disabled={busy}>Save workspace link</button></form>
        <form onSubmit={event => void save(event, "/v1/maintenance-connections")}><label>Connection for<select name="source">{Object.entries(names).map(([key, name]) => <option key={key} value={key}>{name}</option>)}</select></label><button disabled={busy}>Create connection token</button></form>
        {connection && <section><strong>{names[connection.source]} connection</strong><p>Expires {new Date(connection.expires_at).toLocaleString()}. Keep this token private.</p>{connection.mode === "demo" && <p>Demo workspace: real guest imports are blocked. Use real accounts and homes before activating data exchange.</p>}<label>Connection token<textarea readOnly rows={4} value={connection.token} onFocus={event => event.currentTarget.select()} /></label><button type="button" onClick={() => setConnection(null)}>Hide token</button></section>}
      </details>
      <details className={styles.setup}><summary>Match properties</summary><p>Match the Hospitable property ID to its exact maintenance home. Names alone are not used to match properties.</p>
        <form onSubmit={event => void save(event, "/v1/maintenance-property-links")}><label>Hospitable property ID<input name="external_property_id" required pattern="[0-9a-fA-F-]{36}" placeholder="Property UUID from Hospitable" /></label><label>Maintenance home<select name="unit_id" required defaultValue=""><option value="" disabled>Choose the matching home</option>{data.units.map(unit => <option key={unit.id} value={unit.id}>{unit.name} · {unit.label}</option>)}</select></label><button disabled={busy}>Match property</button></form>
        {data.properties.length > 0 ? <ul>{data.properties.map(property => <li key={property.external_property_id}><strong>{property.name} · {property.label}</strong><br /><small>{property.external_property_id}</small><form onSubmit={event => void save(event, "/v1/maintenance-property-links/unlink")}><input type="hidden" name="external_property_id" value={property.external_property_id} /><button disabled={busy}>Remove unused match</button></form></li>)}</ul> : <p>No properties matched yet.</p>}
      </details>
    </>}
  </section>;
}
