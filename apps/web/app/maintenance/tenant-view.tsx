"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE, getToken } from "../../lib/api";
import WorkflowPanel, { workflowRequest as read } from "./workflow-panel";
import styles from "./tenant.module.css";

type Home = { lease_id: string; unit_id: string; property_name: string; unit_label: string };
type RequestSummary = { id: string; ticket_number: number; description: string; status: string; created_at: string };
type Ticket = RequestSummary & {
  analysis?: { status: string; summary: string; follow_up: string[] } | null;
  notification_status?: string | null;
  safety_message?: string | null;
  media: { id: string; status: string; content_type: string | null; rejection_reason: string | null }[];
  messages: { id: string; body: string; created_at: string }[];
  history: { status: string; reason: string | null; created_at: string }[];
};
type Attachment = { file: File; key: string; uploaded?: boolean; slot?: { id: string; upload_url: string; required_headers: Record<string, string> } };
const statuses: Record<string, string> = {
  INTAKE_OPEN: "Request received", TRIAGE_PENDING: "Request received", MANAGER_REVIEW: "Property manager reviewing", ASSIGNMENT_PENDING: "Property manager reviewing", ASSIGNED: "Repair worker assigned", SCHEDULING: "Arranging a visit", SCHEDULED: "Visit arranged", IN_PROGRESS: "Repair underway", COMPLETION_REVIEW: "Ready for you to check", COMPLETED: "Fixed", CLOSED: "Fixed", WAITING_TENANT: "Your reply is needed", WAITING_PARTS: "Waiting for parts", WAITING_APPROVAL: "Repair team is reviewing", CANCELED: "Canceled", REOPENED: "Reported again",
};
const statusName = (value: string) => statuses[value] || "Request in progress";
const nextStep = (value: string) => value === "COMPLETION_REVIEW" ? "Check the repair and tell us if it is fixed." : value === "WAITING_TENANT" ? "Open your request to reply." : ["COMPLETED", "CLOSED"].includes(value) ? "Still a problem? You can reopen this request." : value === "SCHEDULED" ? "Open your request to check the visit details." : value === "CANCELED" ? "No visit is planned for this request." : "We’ll show your next step here when it’s ready.";
const date = (value: string) => new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });

export default function TenantView() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [homes, setHomes] = useState<Home[]>([]);
  const [home, setHome] = useState("");
  const [manager, setManager] = useState(false);
  const [photosEnabled, setPhotosEnabled] = useState(false);
  const [showPast, setShowPast] = useState(false);
  const [pageCount, setPageCount] = useState(1);
  const [listLoading, setListLoading] = useState(false);
  const listGeneration = useRef(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [items, setItems] = useState<RequestSummary[]>([]);
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [description, setDescription] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const lock = useRef(false);
  const saved = useRef<string | null>(null);
  const creation = useRef<{ body: string; key: string } | null>(null);
  const analysis = useRef<{ id: string; key: string } | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  async function loadList() {
    const generation = ++listGeneration.current;
    setListLoading(true);
    try {
      const collected: RequestSummary[] = [];
      let cursor: string | null = null;
      for (let page = 0; page < pageCount; page++) {
        const result = await read(`/v1/maintenance-tickets?limit=8&view=${showPast ? "past" : "active"}${cursor ? `&before=${encodeURIComponent(cursor)}` : ""}`);
        collected.push(...result.items);
        cursor = result.next_cursor;
        if (!cursor) break;
      }
      if (generation !== listGeneration.current) return;
      setItems(collected);
      setNextCursor(cursor);
    } finally { if (generation === listGeneration.current) setListLoading(false); }
  }
  async function refresh(id: string) {
    const result = await read(`/v1/maintenance-tickets/${encodeURIComponent(id)}`);
    if (["COMPLETED", "CLOSED", "CANCELED"].includes(result.status) && !showPast) {
      newRequest();
    } else {
      setTicket(result);
      if (showPast && !["COMPLETED", "CLOSED", "CANCELED"].includes(result.status)) { setShowPast(false); setPageCount(1); }
    }
  }
  async function run(action: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try { await action(); }
    catch (value) { setError(value instanceof Error ? value.message : "We couldn’t finish that. Your details are still here. Please try again."); }
    finally { lock.current = false; setBusy(false); }
  }
  function show(value: Ticket) {
    setTicket(value);
    if (["COMPLETED", "CLOSED", "CANCELED"].includes(value.status)) setShowPast(true);
    analysis.current = null;
    const url = new URL(window.location.href);
    url.searchParams.set("ticket", value.id);
    window.history.replaceState(null, "", url);
    setTimeout(() => heading.current?.focus(), 0);
  }
  useEffect(() => {
    if (new URL(window.location.href).searchParams.get("past") === "1") setShowPast(true);
  }, []);
  useEffect(() => {
    const url = new URL(window.location.href);
    if (showPast) url.searchParams.set("past", "1");
    else url.searchParams.delete("past");
    window.history.replaceState(null, "", url);
  }, [showPast]);
  useEffect(() => {
    let active = true;
    if (!getToken()) { router.replace("/login"); return; }
    (async () => {
      try {
        const context = await read("/v1/maintenance-context");
        if (!active) return;
        setHomes(context.homes);
        setHome(context.homes[0]?.lease_id || "");
        setPhotosEnabled(context.photos_enabled);
        setManager(context.can_manage);
        const list = await read("/v1/maintenance-tickets?limit=8&view=active");
        if (!active) return;
        setItems(list.items);
        setNextCursor(list.next_cursor);
        const id = new URL(window.location.href).searchParams.get("ticket");
        if (id) {
          const value = await read(`/v1/maintenance-tickets/${encodeURIComponent(id)}`);
          if (active) show(value);
        }
      } catch (value) { if (active) setError(value instanceof Error ? value.message : "Your requests couldn’t be loaded."); }
      finally { if (active) setReady(true); }
    })();
    return () => { active = false; };
  }, [router]);
  useEffect(() => {
    if (!ticket) return;
    let active = true;
    let polling = false;
    const id = ticket.id;
    const timer = setInterval(async () => {
      if (polling || lock.current || document.visibilityState !== "visible") return;
      polling = true;
      try {
        const value = await read(`/v1/maintenance-tickets/${encodeURIComponent(id)}`);
        if (active) {
          setError(current => current === "Couldn’t refresh this repair. Retrying automatically." ? "" : current);
          if (["COMPLETED", "CLOSED", "CANCELED"].includes(value.status) && !showPast) newRequest();
          else if (showPast && !["COMPLETED", "CLOSED", "CANCELED"].includes(value.status)) { setTicket(value); setShowPast(false); setPageCount(1); }
          else setTicket(value);
        }
      } catch { if (active) setError("Couldn’t refresh this repair. Retrying automatically."); }
      finally { polling = false; }
    }, 10000);
    return () => { active = false; clearInterval(timer); };
  }, [ticket?.id, showPast, pageCount]);

  useEffect(() => {
    if (!ready) return;
    const load = () => { void loadList().catch(value => setError(value instanceof Error ? value.message : "Your requests couldn’t be loaded.")); };
    load();
    const timer = setInterval(() => { if (!lock.current && document.visibilityState === "visible") load(); }, 10000);
    return () => { listGeneration.current++; clearInterval(timer); };
  }, [showPast, pageCount, ready]);

  async function analyze(id: string) {
    if (analysis.current?.id !== id) analysis.current = { id, key: crypto.randomUUID() };
    try {
      const result = await read(`/v1/maintenance-tickets/${id}/analyze`, { method: "POST", headers: { "Idempotency-Key": analysis.current.key } });
      setTicket(result);
      analysis.current = null;
      setNotice(result.analysis?.status === "ready" ? "Your request is saved." : "Your request is saved. The repair team can review it.");
    } catch { setNotice("Your request is saved. Automatic assessment is unavailable; the repair team can review it."); }
  }
  function stage(files: FileList | null) {
    if (!files) return;
    const incoming = Array.from(files);
    if (attachments.length + incoming.length + (saved.current ? ticket?.media.length || 0 : 0) > 10) { setError("Choose up to 10 photos or videos."); return; }
    for (const file of incoming) {
      const video = /\.(mp4|mov)$/i.test(file.name);
      if (!/\.(jpe?g|png|heic|heif|mp4|mov)$/i.test(file.name)) { setError("Choose JPEG, PNG, HEIC, HEIF, MP4 or MOV files."); return; }
      if (file.size > (video ? 200 : 20) * 1024 * 1024) { setError(video ? "Videos must be smaller than 200 MB and no longer than 2 minutes." : "Photos must be smaller than 20 MB."); return; }
    }
    setError("");
    setAttachments(old => [...old, ...incoming.map(file => ({ file, key: crypto.randomUUID() }))]);
  }
  async function upload(attachment: Attachment, id: string) {
    if (attachment.slot) {
      const current: Ticket = await read(`/v1/maintenance-tickets/${id}`);
      if (current.media.some(item => item.id === attachment.slot?.id && item.status === "READY")) return;
    }
    const file = attachment.file;
    const bytes = await file.arrayBuffer();
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))).map(n => n.toString(16).padStart(2, "0")).join("");
    const contentType = /\.mov$/i.test(file.name) ? "video/quicktime" : /\.mp4$/i.test(file.name) ? "video/mp4" : /\.hei[cf]$/i.test(file.name) ? "image/heic" : /\.png$/i.test(file.name) ? "image/png" : "image/jpeg";
    const slot = await read(`/v1/maintenance-tickets/${id}/media-uploads`, { method: "POST", headers: { "Idempotency-Key": attachment.key }, body: JSON.stringify({ filename: file.name, content_type: contentType, size_bytes: file.size, sha256: hash }) });
    attachment.slot = slot;
    if (!attachment.uploaded) {
      const response = await fetch(`${API_BASE}${slot.upload_url}`, { method: "POST", signal: AbortSignal.timeout(180000), headers: slot.required_headers, body: bytes });
      if (!response.ok) throw new Error("Your request is saved, but an attachment didn’t upload. Retry the remaining files below.");
      attachment.uploaded = true;
    }
    const result = await read(`/v1/media/${slot.id}/complete`, { method: "POST", headers: { "Idempotency-Key": attachment.key } });
    if (result.status !== "READY") throw new Error("Your request is saved, but this attachment wasn’t accepted. Remove it or try another file.");
    analysis.current = null;
  }
  async function send(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      if (!saved.current) {
        const selected = homes.find(item => item.lease_id === home);
        const body = JSON.stringify({ description: description.trim(), ...(selected ? { unit_id: selected.unit_id, lease_id: selected.lease_id } : {}) });
        if (creation.current?.body !== body) creation.current = { body, key: crypto.randomUUID() };
        const value = await read("/v1/maintenance-tickets", { method: "POST", headers: { "Idempotency-Key": creation.current.key }, body });
        saved.current = value.id;
        show(value);
      }
      let uploadError: unknown;
      try {
        for (const attachment of attachments) {
          await upload(attachment, saved.current!);
          setAttachments(old => old.filter(item => item.key !== attachment.key));
        }
      } catch (value) { uploadError = value; }
      await analyze(saved.current!);
      await loadList();
      if (uploadError) throw uploadError;
    });
  }
  function newRequest() {
    setShowPast(false);
    setPageCount(1);
    setTicket(null);
    setDescription("");
    setAttachments([]);
    setNotice("");
    setError("");
    saved.current = null;
    creation.current = null;
    analysis.current = null;
    window.history.replaceState(null, "", window.location.pathname);
  }
  const visibleItems = items.filter(item => showPast === ["COMPLETED", "CLOSED", "CANCELED"].includes(item.status));
  const picker = <div className={styles.attachments}>
    {photosEnabled ? <label><span className={styles.attachmentHeading}>Photos or videos <span className={styles.optional}>Optional</span></span><input type="file" multiple accept=".jpg,.jpeg,.png,.heic,.heif,.mp4,.mov" disabled={busy} onChange={event => { stage(event.target.files); event.target.value = ""; }} /><small className={styles.attachmentHelp}><span>Photos up to 20 MB · Videos up to 200 MB and 2 minutes</span><span>Only record if it’s safe.</span></small></label> : <small>Photos are unavailable here. Your description is enough to send a request.</small>}
    {attachments.length > 0 && <ul>{attachments.map(item => <li key={item.key}><span>{item.file.name}</span><button type="button" disabled={busy} onClick={() => setAttachments(old => old.filter(value => value.key !== item.key))}>Remove</button></li>)}</ul>}
  </div>;
  if (!ready) return <section className={styles.page}><p role="status">Loading your repairs…</p></section>;
  return <section className={styles.page}>
    <header className={styles.header}><div><p className={styles.eyebrow}>YOUR HOME</p><h1>Repairs</h1><p>Tell us what’s wrong. We’ll help with the next step.</p></div>{(ticket || showPast) && <button type="button" disabled={busy || attachments.length > 0} onClick={newRequest}>New request</button>}</header>
    {error && <p className={styles.error} role="alert">{error}</p>}
    {notice && <p className={styles.notice} role="status">{notice}</p>}
    {manager && !homes.length ? <section className={styles.card}><h2>You’re signed in as a manager</h2><p>Use the repair queue to help residents, or switch to a tenant account to report a problem with your own home.</p><Link href="/maintenance/manage">Open repair queue →</Link></section> : !ticket ? showPast ? null : <section className={styles.card}><h2>What needs fixing?</h2><form onSubmit={send}>
      {homes.length > 1 && <label>Which home?<select value={home} onChange={event => setHome(event.target.value)} disabled={busy}>{homes.map(item => <option key={item.lease_id} value={item.lease_id}>{item.property_name} · {item.unit_label}</option>)}</select></label>}
      {homes.length === 1 && <p className={styles.home}>{homes[0].property_name} · {homes[0].unit_label}</p>}
      <label htmlFor="repair-description">Describe the problem<textarea id="repair-description" required maxLength={5000} rows={4} value={description} disabled={busy} onChange={event => setDescription(event.target.value)} placeholder="For example: the shower has no hot water, even after running it for a few minutes." /></label>
      {picker}<button className={styles.primary} disabled={busy || !description.trim()}>{busy ? "Sending…" : "Send request"}</button>
    </form><p className={styles.safety}>Immediate danger? Get somewhere safe and call emergency services.</p></section> : <section className={styles.detail}>
      <div className={styles.card}><div className={styles.requestTop}><span className={styles.badge}>{statusName(ticket.status)}</span><span>Request #{ticket.ticket_number}</span></div><h2 ref={heading} tabIndex={-1}>{ticket.description}</h2>
        {ticket.safety_message && <p className={styles.safety}>{ticket.safety_message}</p>}
        {ticket.analysis?.status === "ready" && ticket.analysis.summary && <p className={styles.understood}>{ticket.analysis.summary}</p>}
        {saved.current === ticket.id && attachments.length > 0 && <form onSubmit={send}><h3>Finish your attachments</h3>{picker}<button disabled={busy}>{busy ? "Uploading…" : "Retry remaining files"}</button></form>}
        {["BLOCKED", "FAILED", "SIMULATED", "UNDELIVERED", "DELIVERY_UNKNOWN"].includes(ticket.notification_status || "") && <p className={styles.delivery}>{ticket.notification_status === "SIMULATED" ? "Demo request saved; no notification was sent." : "Request saved. The notification hasn’t been delivered yet."}</p>}
      </div>
      <WorkflowPanel key={ticket.id} ticketId={ticket.id} audience="tenant" onChange={() => { void run(async () => { await refresh(ticket.id); await loadList(); }); }} />
    </section>}
    <section className={styles.requests}><div className={styles.requestTop}><h2>{showPast ? "Past repairs" : "Your requests"}</h2><button type="button" disabled={busy || attachments.length > 0} aria-pressed={showPast} onClick={() => { if (ticket) newRequest(); setPageCount(1); setShowPast(!showPast); }}>{showPast ? "Back to active repairs" : "Past repairs"}</button><button type="button" disabled={busy} onClick={() => { void run(async () => { await loadList(); if (ticket) await refresh(ticket.id); }); }}>Refresh</button></div>
      {visibleItems.length ? <div className={styles.list}>{visibleItems.map(item => <button className={styles.request} key={item.id} disabled={busy || attachments.length > 0} aria-pressed={ticket?.id === item.id} onClick={() => { void run(async () => { const value = await read(`/v1/maintenance-tickets/${item.id}`); setNotice(""); show(value); }); }}><span className={styles.requestTop}><strong>{statusName(item.status)}</strong><small>{date(item.created_at)}</small></span><span className={styles.problem}>{item.description}</span><span className={styles.next}>{nextStep(item.status)}</span></button>)}</div> : <p>{showPast ? "No past repairs yet." : "No repairs need attention right now."}</p>}
      {nextCursor && <button type="button" disabled={busy || listLoading} onClick={() => setPageCount(value => value + 1)}>{listLoading ? "Loading…" : "Load more requests"}</button>}
    </section>
  </section>;
}
