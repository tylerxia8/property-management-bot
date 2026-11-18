"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { api, API_BASE } from "../../lib/api";
import styles from "./workflow.module.css";

type Media = { id: string; content_type?: string; status?: string };
type Appointment = { id: string; assignment_id: string; starts_at: string; ends_at: string; timezone: string; status: string; entry_permission: string };
type Detail = {
  escalation?: { id: string; state: string; created_at: string; acknowledged_at: string | null } | null;
  issue_records: { id: string; title: string; status: string; evidence: string }[];
  issues: { key: string; title: string; status: "open" | "reported_resolved"; evidence: string }[];
  role: string;
  ticket: { id: string; verification: string; ticket_number: number; description: string; status: string; priority: string; home: { property_name: string; unit_label: string } | null };
  available_actions: string[];
  assignment: { id: string; status: string; contractor_profile_id: string; scope?: string } | null;
  work_order: { workflow_managed: boolean; completion_notes?: string } | null;
  appointments: Appointment[];
  availability: { windows: string[] };
  messages: { id: string; body: string; created_at: string; sender_label?: string; author_role?: string; media_ids: string[] }[];
  media: Media[];
  completion_media: Media[];
  follow_up_flags: string[];
  contractors: { id: string; name: string }[];
};
type Attachment = { file: File; key: string; id?: string; uploaded?: boolean; ready?: boolean; slot?: { id: string; upload_url: string; required_headers: Record<string, string> } };
const labels: Record<string, string> = {
  arrange_repair: "Accept & propose visit", assign: "Pass to repairman", accept: "Accept this job", decline: "Decline this job", message: "Ask a question", availability: "Share availability", propose_visit: "Propose a visit", confirm_visit: "Respond to a proposed visit", start_work: "Start repair", complete: "Finish repair", confirm_completion: "Yes, fixed", reopen: "Still a problem", resolve_self: "Confirm problem resolved",
};
const human = (value: string) => value.toLowerCase().replaceAll("_", " ");
const timestamp = (value: string, timezone?: string) => new Date(value).toLocaleString(undefined, { timeZone: timezone, dateStyle: "medium", timeStyle: "short" });
export async function workflowRequest(path: string, init: RequestInit = {}) {
  const retryable = !init.method || init.method === "GET" || new Headers(init.headers).has("Idempotency-Key");
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await api(path, { ...init, signal: init.signal || AbortSignal.timeout(30000) });
      if (retryable && attempt < 2 && (response.status === 429 || response.status >= 500)) {
        await new Promise(resolve => setTimeout(resolve, 500 * 2 ** attempt));
        continue;
      }
      let body;
      try {
        body = await response.json();
      } catch {
        throw new Error("The server could not process this request. Please retry in a moment.");
      }
      if (!response.ok) throw Object.assign(new Error(body.error?.message || body.detail || "The change could not be saved. Please retry."), { status: response.status });
      return body;
    } catch (error) {
      if (retryable && attempt < 2 && (error instanceof TypeError || error instanceof DOMException && error.name === "TimeoutError")) {
        await new Promise(resolve => setTimeout(resolve, 500 * 2 ** attempt));
        continue;
      }
      throw error;
    }
  }
}

export default function WorkflowPanel({ ticketId, onChange, audience }: { ticketId: string; onChange?: () => void; audience?: "tenant" | "repairman" }) {
  const [detail, setDetail] = useState<Detail | null>(null);
  const [selectedAction, setAction] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [revision, setRevision] = useState(0);
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [draft, setDraft] = useState("");
  const [chatFiles, setChatFiles] = useState<Attachment[]>([]);
  const chatPending = useRef<{ body: string; key: string; bot: boolean } | null>(null);
  const [chatError, setChatError] = useState("");
  const [syncError, setSyncError] = useState("");
  const [permission, setPermission] = useState(false);
  const [clock, setClock] = useState(() => Date.now());
  const lock = useRef(false);
  const generation = useRef(0);
  const conversation = useRef<HTMLDivElement>(null);
  const followChat = useRef(true);
  const pending = useRef<{ body: string; key: string } | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    let active = true;
    setDetail(null);
    setError("");
    setAction("");
    setAttachments([]);
    setPermission(false);
    pending.current = null;
    workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/workflow`).then(value => {
      if (active) setDetail(value);
    }).catch(value => { if (active) setError(value instanceof Error ? value.message : "Unable to load this repair."); });
    return () => { active = false; };
  }, [ticketId, revision]);
  useEffect(() => {
    generation.current++;
    setDraft("");
    setChatFiles([]);
    setChatError("");
    chatPending.current = null;
    followChat.current = true;
    return () => { generation.current++; };
  }, [ticketId]);
  const lastMessage = detail?.messages.at(-1)?.id;
  useEffect(() => {
    if (followChat.current && conversation.current) conversation.current.scrollTop = conversation.current.scrollHeight;
  }, [lastMessage]);
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    const refresh = async () => {
      if (!lock.current && document.visibilityState === "visible") {
        const version = generation.current;
        try {
          const latest: Detail = await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/workflow`);
          if (active && !lock.current && version === generation.current) { setDetail(latest); setSyncError(""); }
        } catch (error) {
          if (active && version === generation.current && error instanceof Error && "status" in error && error.status === 404) {
            setDetail(null);
            setError("This repair is no longer available to your account.");
            active = false;
            return;
          }
          if (active) setSyncError("Chat could not refresh. Reconnecting automatically…");
        }
      }
      if (active) timer = setTimeout(refresh, 5000);
    };
    timer = setTimeout(refresh, 5000);
    return () => { active = false; clearTimeout(timer); };
  }, [ticketId]);
  const visits = detail?.appointments.filter(visit => (visit.assignment_id === detail.assignment?.id) && ["REQUESTED", "CONFIRMED"].includes(visit.status) && new Date(visit.ends_at).getTime() > clock) || [];
  const proposedVisit = visits.find(visit => new Date(visit.starts_at).getTime() > clock && visit.entry_permission !== "GRANTED") || visits.find(visit => new Date(visit.starts_at).getTime() > clock);

  const proposalReady = visits.length > 0;
  const botConversation = detail?.role === "tenant" && !detail.assignment && ["INTAKE_OPEN", "TRIAGE_PENDING", "WAITING_TENANT", "MANAGER_REVIEW"].includes(detail.ticket.status);
  const tenant = detail?.role === "tenant" || audience === "tenant";
  const manager = detail?.role === "manager" && !audience;
  const primaryAction = ["assign", "confirm_completion", "confirm_visit", "start_work", "complete", "arrange_repair"].find(item => detail?.available_actions.includes(item) && (!["assign"].includes(item) || manager) && (item !== "confirm_visit" || proposedVisit && proposedVisit.entry_permission !== "GRANTED") && (item !== "arrange_repair" || !proposalReady)) || "";
  const action = selectedAction || (["confirm_visit", "confirm_completion", "assign"].includes(primaryAction) ? primaryAction : "");
  const actionLabel = action === "propose_visit" ? "Send visit proposal" : action === "arrange_repair" && detail?.assignment?.status === "ACCEPTED" ? "Update repair proposal" : labels[action];

  const localTime = (value?: string) => value ? new Date(new Date(value).getTime() - new Date(value).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : "";
  async function upload(attachment: Attachment) {
    if (attachment.ready && attachment.id) return attachment.id;
    if (attachment.slot) {
      const current: Detail = await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/workflow`);
      if (current.media.some(media => media.id === attachment.slot?.id && media.status === "READY")) {
        attachment.ready = true;
        attachment.id = attachment.slot.id;
        return attachment.id;
      }
    }
    const bytes = await attachment.file.arrayBuffer();
      const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))).map(value => value.toString(16).padStart(2, "0")).join("");
      attachment.slot = await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/media-uploads`, {
        method: "POST", headers: { "Idempotency-Key": attachment.key }, body: JSON.stringify({ filename: attachment.file.name, content_type: attachment.file.type || (/\.hei[cf]$/i.test(attachment.file.name) ? "image/heic" : /\.mov$/i.test(attachment.file.name) ? "video/quicktime" : /\.mp4$/i.test(attachment.file.name) ? "video/mp4" : /\.png$/i.test(attachment.file.name) ? "image/png" : "image/jpeg"), size_bytes: attachment.file.size, sha256: hash }),
      });
    const slot = attachment.slot!;
    attachment.id = slot.id;
    if (!attachment.uploaded) {
      const response = await fetch(`${API_BASE}${slot.upload_url}`, { method: "POST", headers: slot.required_headers, body: bytes, signal: AbortSignal.timeout(180000) });
      if (!response.ok) throw new Error("An attachment could not upload. Retry to continue with your saved files.");
      attachment.uploaded = true;
    }
    const result = await workflowRequest(`/v1/media/${slot.id}/complete`, { method: "POST", signal: AbortSignal.timeout(180000) });
    if (result.status !== "READY") throw new Error("This attachment was not accepted. Remove it and choose another photo or video.");
    attachment.ready = true;
    return slot.id;
  }
  async function openMedia(media: Media) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    try {
      const result = await workflowRequest(`/v1/media/${media.id}/download`);
      const response = await fetch(`${API_BASE}${result.download_url}`, { signal: AbortSignal.timeout(30000) });
      if (!response.ok) throw new Error("This attachment could not be downloaded.");
      const url = URL.createObjectURL(await response.blob());
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `repair-${media.id}.${media.content_type?.startsWith("video/") ? "mp4" : "jpg"}`;
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (value) { setError(value instanceof Error ? value.message : "Unable to download attachment."); }
    finally { lock.current = false; setBusy(false); }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || !detail) return;
    lock.current = true;
    const version = ++generation.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const fields = new FormData(event.currentTarget);
      const value = (key: string) => String(fields.get(key) || "").trim();
      const command: Record<string, unknown> = { action };
      if (action === "assign") Object.assign(command, { contractor_profile_id: value("contractor"), scope: value("text") });
      if (["decline", "reopen", "resolve_self"].includes(action)) command.reason = value("text");
      if (action === "availability") command.windows = value("text").split("\n").map(line => line.trim()).filter(Boolean);
      if (["arrange_repair", "propose_visit"].includes(action)) {
        const start = new Date(value("starts_at")), end = new Date(value("ends_at"));
        if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) throw new Error("Choose a visit end time after its start time.");
        Object.assign(command, { starts_at: start.toISOString(), ends_at: end.toISOString(), timezone });
      }
      if (action === "confirm_visit") Object.assign(command, { appointment_id: value("appointment"), entry_permission: permission ? "GRANTED" : "DENIED" });
      if (action === "arrange_repair") Object.assign(command, { scope: value("text") });
      if (["message", "complete"].includes(action)) {
        const mediaIds: string[] = [];
        for (const attachment of attachments) mediaIds.push(await upload(attachment));
        Object.assign(command, { [action === "message" ? "body" : "notes"]: value("text"), media_ids: mediaIds });
      }
      const body = JSON.stringify(command);
      if (pending.current?.body !== body) pending.current = { body, key: crypto.randomUUID() };
      await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/workflow`, { method: "POST", headers: { "Idempotency-Key": pending.current.key }, body });
      if (version !== generation.current) return;
      pending.current = null;
      form.current?.reset();
      setAttachments([]);
      setPermission(false);
      setAction("");
      if (action === "decline") {
        setDetail(null);
        setNotice("Job declined. It is no longer available to this maintenance account.");
        onChange?.();
        return;
      }
      setNotice("Saved to the shared repair record.");
      try {
        const latest = await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/workflow`);
        if (version === generation.current) setDetail(latest);
      } catch { if (version === generation.current) setError("Your change was saved. Refresh to see the latest repair details."); }
      if (version === generation.current) onChange?.();
    } catch (value) { if (version === generation.current) setError(value instanceof Error ? value.message : "Unable to save this change."); }
    finally { if (version === generation.current) { lock.current = false; setBusy(false); } }
  }
  async function sendChat(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (lock.current || !detail || !draft.trim()) return;
    lock.current = true;
    const version = ++generation.current;
    setBusy(true);
    setChatError("");
    try {
      if (chatFiles.length && !detail.assignment && detail.role === "contractor") {
        const body = JSON.stringify({ action: "accept" });
        await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/workflow`, { method: "POST", headers: { "Idempotency-Key": `chat-accept-${ticketId}` }, body });
      }
      const mediaIds: string[] = [];
      for (const attachment of chatFiles) mediaIds.push(await upload(attachment));
      const body = JSON.stringify({ action: "message", body: draft.trim(), media_ids: mediaIds });
      if (chatPending.current?.body !== body) chatPending.current = { body, key: crypto.randomUUID(), bot: Boolean(botConversation) };
      let latest: Detail;
      if (chatPending.current.bot) {
        await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/messages`, { method: "POST", headers: { "Idempotency-Key": chatPending.current.key }, body: JSON.stringify({ body: draft.trim(), field_key: "general" }) });
        await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/analyze`, { method: "POST", headers: { "Idempotency-Key": `${chatPending.current.key}-analysis` } });
        latest = await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/workflow`);
      } else {
        latest = await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(ticketId)}/workflow`, { method: "POST", headers: { "Idempotency-Key": chatPending.current.key }, body });
      }
      if (version !== generation.current) return;
      followChat.current = true;
      setDetail(latest);
      setDraft("");
      setChatFiles([]);
      chatPending.current = null;
      onChange?.();
    } catch (value) { if (version === generation.current) setChatError(value instanceof Error ? value.message : "Message could not be sent. Your draft is still here."); }
    finally { if (version === generation.current) { lock.current = false; setBusy(false); } }
  }
  const mediaLinks = (media: Media[]) => media.map(item => <button className={styles.attachment} key={item.id} type="button" disabled={busy} onClick={() => openMedia(item)}>Download {item.content_type?.startsWith("video/") ? "video" : "photo"}</button>);
  return <section className={styles.panel} aria-label="Shared repair workflow">
    <div className={styles.heading}><div><h2>{manager ? "Manage repair" : "Repair conversation"}</h2></div><button type="button" disabled={busy} onClick={() => setRevision(value => value + 1)}>Refresh</button></div>
    {error && <p className={styles.error} role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!detail ? <p>{error ? "Repair details are unavailable." : "Loading repair details…"}</p> : <>
      {!tenant && <p>{detail.ticket.description}</p>}
      {!tenant && detail.issue_records.length > 0 && <details className={styles.options}><summary>Repair brief</summary>{detail.issue_records.map(issue => <div key={issue.id}><strong>{issue.title} · {human(issue.status)}</strong><p className={styles.message}>{issue.evidence}</p></div>)}<p className={styles.muted}>Reported observations, not a confirmed diagnosis. The conversation below includes the checks already discussed.</p></details>}
      {manager && detail.ticket.verification !== "VERIFIED" && <p className={styles.muted}>Confirm the home before assigning a repairman. <a href={`/maintenance/manage?ticket=${encodeURIComponent(ticketId)}`}>Review home details</a></p>}
      {detail.ticket.priority !== "ROUTINE" && !["COMPLETED", "CLOSED", "CANCELED"].includes(detail.ticket.status) && <aside className={styles.urgentNotice}><strong>{detail.ticket.priority === "EMERGENCY" ? "Emergency request" : "Urgent request"}</strong><p>{detail.escalation?.state === "ACKNOWLEDGED" ? "The repair team has acknowledged this request." : tenant ? "Waiting for the repair team to acknowledge. For immediate danger, contact emergency services rather than waiting here." : "Acknowledge in chat, for example: “I’m on it” or “I’ll head over shortly.”"}</p></aside>}
      {visits.length > 0 && <p className={styles.visit}><strong>{timestamp(visits[0].starts_at, visits[0].timezone)} – {timestamp(visits[0].ends_at, visits[0].timezone)}</strong><br />Entry permission: {human(visits[0].entry_permission || "not granted")}</p>}
      <section className={styles.chat} aria-label="Repair chat">
        <div className={styles.heading}><h3>{botConversation ? "Stevie" : "Conversation"}</h3><span className={styles.muted}>Updates automatically</span></div>

        {botConversation && <p className={styles.muted}>Let’s understand the problem first. I’ll suggest safe checks or prepare the details for the property manager. You can ask for the property manager at any time.</p>}
        <div ref={conversation} onScroll={event => { const element = event.currentTarget; followChat.current = element.scrollHeight - element.scrollTop - element.clientHeight < 60; }} className={styles.conversation} role="log" tabIndex={0} aria-label="Repair messages" aria-relevant="additions">
          {detail.messages.length ? detail.messages.map(message => <article className={`${styles.bubble} ${message.author_role === detail.role ? styles.ownBubble : ""}`} key={message.id}>
            <div className={styles.heading}><strong>{message.author_role === "system" ? "Stevie" : message.sender_label || human(message.author_role || "participant")}</strong><time dateTime={message.created_at}>{timestamp(message.created_at)}</time></div>
            <p className={styles.message}>{message.body}</p><div className={styles.attachments}>{mediaLinks(detail.media.filter(item => message.media_ids.includes(item.id)))}</div>
          </article>) : <p className={styles.muted}>Start the conversation here. Discuss the problem before choosing a visit time.</p>}
        </div>
        {syncError && <p className={styles.muted} role="status">{syncError}</p>}
        {chatError && <p className={styles.error} role="alert">{chatError}</p>}
        {detail.available_actions.includes("message") ? <form className={styles.composer} onSubmit={sendChat}>
          <label><span className={styles.srOnly}>Message</span><textarea value={draft} onChange={event => setDraft(event.target.value)} disabled={busy} required maxLength={4000} rows={2} placeholder={manager ? "Reply here, or ask Stevie to pass this to a repairman…" : "Write a message about this repair…"} /></label>
          <details className={styles.chatUpload}><summary>Attach photos or videos</summary><label className={styles.muted}><span className={styles.srOnly}>Photos or videos</span><input type="file" multiple disabled={busy} accept=".jpg,.jpeg,.png,.heic,.heif,.mp4,.mov" onChange={event => {
            const files = Array.from(event.target.files || []);
            event.target.value = "";
            const limit = detail.work_order?.workflow_managed ? 20 : 10;
            if (chatFiles.length + files.length > 10 || detail.media.length + chatFiles.filter(item => !item.id).length + files.length > limit) { setChatError(`Choose up to 10 files per message; this repair supports ${limit} files in total.`); return; }
            if (files.some(file => !/\.(jpe?g|png|heic|heif|mp4|mov)$/i.test(file.name) || file.size > (/\.(mp4|mov)$/i.test(file.name) ? 200 : 20) * 1024 * 1024)) { setChatError("Choose photos up to 20 MB or videos up to 200 MB and 2 minutes."); return; }
            setChatError("");
            setChatFiles(old => [...old, ...files.map(file => ({ file, key: crypto.randomUUID() }))]);
          }} /></label></details>
          {chatFiles.map(item => <div className={styles.file} key={item.key}><span>{item.file.name}</span><button type="button" disabled={busy} onClick={() => setChatFiles(old => old.filter(file => file.key !== item.key))}>Remove</button></div>)}
          <button className={styles.primary} disabled={busy || !draft.trim()} type="submit">{busy ? "Please wait…" : "Send"}</button>
        </form> : <p className={styles.muted}>Messaging is unavailable for this repair.</p>}
      <div className={styles.quickActions}>
      {detail.available_actions.includes("resolve_self") && action !== "resolve_self" && <button type="button" disabled={busy} onClick={() => { setAction("resolve_self"); setError(""); }}>{detail.issues?.length > 1 ? "All problems are resolved" : "The problem is resolved"}</button>}
      {detail.available_actions.includes("reopen") && action !== "reopen" && action !== "confirm_completion" && <button type="button" disabled={busy} onClick={() => { setAction("reopen"); setError(""); }}>Still a problem</button>}
      {detail.available_actions.includes("complete") && action !== "complete" && <button className={styles.ask} type="button" disabled={busy} onClick={() => { setAction("complete"); setAttachments([]); setError(""); }}>Report repair finished</button>}
      {detail.available_actions.includes("decline") && action !== "decline" && <button type="button" disabled={busy} onClick={() => { setAction("decline"); setError(""); }}>Decline repair</button>}
      </div>
      {action && <section className={styles.next}><h3>{action === "confirm_completion" ? "Is the repair fixed?" : action === "confirm_visit" ? "Does this visit work for you?" : action ? actionLabel : "Latest update"}</h3>{action && !selectedAction && <p>{action === "confirm_visit" ? "Review the visit above and choose whether to allow entry." : action === "confirm_completion" ? "Check the repair, then let us know." : action === "arrange_repair" ? "Describe the work and propose a visit." : action === "complete" ? "Add your repair notes and a completion photo." : action === "start_work" ? "Record that you have started the repair." : "You need to complete this step to move the repair forward."}</p>}{selectedAction && <button type="button" disabled={busy} onClick={() => { setAction(""); setPermission(false); setAttachments([]); }}>Cancel</button>}
        {action === "resolve_self" && detail.issues?.length > 1 && <p>This closes every reported problem: {detail.issues.map(issue => issue.title).join(", ")}. State that all issues are fixed, or continue the chat about anything still wrong.</p>}
        {action === "propose_visit" && <p>The previous visit will be canceled. The tenant must confirm the new time and allow entry again.</p>}
        {action && <form ref={form} key={`${ticketId}-${action}`} onSubmit={submit}><fieldset disabled={busy} className={styles.fields}>
          {action === "assign" && <label>Repair worker<select name="contractor" required defaultValue={detail.contractors.length === 1 ? detail.contractors[0].id : ""}><option value="" disabled>Choose a worker</option>{detail.contractors.map(worker => <option key={worker.id} value={worker.id}>{worker.name}</option>)}</select></label>}
          {["assign", "decline", "message", "availability", "arrange_repair", "complete", "reopen", "resolve_self"].includes(action) && <label>{action === "availability" ? "Available dates and time windows (one per line, include your time zone)" : ["assign", "arrange_repair"].includes(action) ? "Scope of work" : action === "complete" ? "What was repaired and how was it checked?" : action === "message" ? "Message to everyone on this repair" : action === "resolve_self" ? "What fixed the problem?" : action === "reopen" ? "What is still wrong?" : "Reason"}<textarea name="text" required rows={4} maxLength={4000} defaultValue={action === "availability" ? detail.availability.windows.join("\n") : ["assign", "arrange_repair"].includes(action) ? detail.assignment?.scope || detail.ticket.description : ""} /></label>}
          {["arrange_repair", "propose_visit"].includes(action) && <><p>Enter times in your local time zone: <strong>{timezone}</strong>.</p><label>Visit start<input name="starts_at" type="datetime-local" defaultValue={localTime(visits[0]?.starts_at)} required /></label><label>Visit end<input name="ends_at" type="datetime-local" defaultValue={localTime(visits[0]?.ends_at)} required /></label></>}
          {action === "confirm_visit" && <><label>Proposed visit<select name="appointment" required onChange={() => setPermission(false)} defaultValue={proposedVisit?.id || ""}><option value="" disabled>Choose a proposed visit</option>{visits.filter(visit => new Date(visit.starts_at).getTime() > Date.now()).map(visit => <option key={visit.id} value={visit.id}>{timestamp(visit.starts_at, visit.timezone)} ({visit.timezone})</option>)}</select></label><label className={styles.checkbox}><input type="checkbox" checked={permission} onChange={event => setPermission(event.target.checked)} />I explicitly give permission to enter for this visit.</label><p>{permission ? "Submitting confirms this visit and records your entry permission." : "Submitting records that entry permission is denied. No entry is authorized. Send a message in the repair chat if you need a different time."}</p></>}
          {["message", "complete"].includes(action) && <><label>{action === "complete" ? "Completion photos (required)" : "Photos or videos (optional)"}<input type="file" accept={action === "complete" ? ".jpg,.jpeg,.png,.heic,.heif" : ".jpg,.jpeg,.png,.heic,.heif,.mp4,.mov"} multiple required={action === "complete" && !attachments.length} onChange={event => {
            const files = Array.from(event.target.files || []);
            event.target.value = "";
            const limit = detail.work_order?.workflow_managed ? 20 : 10;
            if (attachments.length + files.length > 10 || detail.media.length + attachments.filter(item => !item.id).length + files.length > limit) { setError(`Choose up to 10 files at a time; this repair supports ${limit} files in total.`); return; }
            if (files.some(file => !/\.(jpe?g|png|heic|heif|mp4|mov)$/i.test(file.name) || action === "complete" && /\.(mp4|mov)$/i.test(file.name) || file.size > (/\.(mp4|mov)$/i.test(file.name) ? 200 : 20) * 1024 * 1024)) { setError("Choose photos up to 20 MB or videos up to 200 MB. Completion evidence must include a photo."); return; }
            setError("");
            setAttachments(old => [...old, ...files.map(file => ({ file, key: crypto.randomUUID() }))]);
          }} /></label>{attachments.map(item => <div className={styles.file} key={item.key}><span>{item.file.name}{item.ready ? " · Ready" : ""}</span><button type="button" onClick={() => setAttachments(old => old.filter(file => file.key !== item.key))}>Remove</button></div>)}</>}
          {action === "confirm_completion" && <p>Confirm only after checking that the reported problem is resolved. You can reopen the repair if the issue returns.</p>}
          <button className={styles.primary} type="submit">{busy ? "Saving…" : action === "confirm_visit" && !permission ? "Record entry permission denied" : action === "confirm_visit" ? "Confirm visit & allow entry" : actionLabel || "Save"}</button>
        </fieldset></form>}{action === "confirm_completion" && detail.available_actions.includes("reopen") && <button type="button" disabled={busy} onClick={() => setAction("reopen")}>Still a problem</button>}</section>}
      </section>
      {detail.completion_media.length > 0 && <section><h3>Completion evidence</h3>{detail.work_order?.completion_notes && <p>{detail.work_order.completion_notes}</p>}<div className={styles.attachments}>{mediaLinks(detail.completion_media)}</div></section>}
      {detail.media.some(item => !detail.messages.some(message => message.media_ids.includes(item.id)) && !detail.completion_media.some(completion => completion.id === item.id)) && <details className={styles.options}><summary>Request photos & videos</summary><div className={styles.attachments}>{mediaLinks(detail.media.filter(item => !detail.messages.some(message => message.media_ids.includes(item.id)) && !detail.completion_media.some(completion => completion.id === item.id)))}</div></details>}

    </>}
  </section>;
}
