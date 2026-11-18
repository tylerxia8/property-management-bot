"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, API_BASE, clearToken, getToken, setToken } from "../../lib/api";
import WorkflowPanel from "./workflow-panel";

type Home = {
  lease_id: string;
  unit_id: string;
  property_name: string;
  unit_label: string;
};
type Summary = {
  id: string;
  ticket_number: number;
  description: string;
  status: string;
  priority: string;
  emergency: boolean;
  category: string;
  created_at: string;
  property_name: string | null;
  unit_label: string | null;
};
type Ticket = Summary & {
  analysis?: {
    status: "ready" | "unavailable" | "failed" | "stale";
    summary: string;
    next_action: string;
    follow_up: string[];
    images_analyzed: number;
    video_frames_analyzed: number;
    source?: "rules" | "model" | null;
    trade?: string | null;
    repair_steps?: string[];
  } | null;
  notification_status?: string | null;
  verification: string;
  handoff: boolean;
  next_questions: string[];
  missing_fields: string[];
  safety_message: string | null;
  intake: { field_key: string; status: string; value_text: string | null }[];
  messages: { id: string; body: string; created_at: string }[];
  media: { id: string; status: string; rejection_reason: string | null; content_type: string | null }[];
  history: { status: string; reason: string | null; created_at: string }[];
};
type Attachment = {
  file: File;
  key: string;
  slot?: { id: string; upload_url: string; required_headers: Record<string, string> };
  uploaded?: boolean;
};
const categories = {
  general: "Something else",
  leak: "Plumbing or leak",
  hvac: "Heating or cooling",
  electrical: "Electrical",
  appliance: "Appliance",
  structural: "Wall, ceiling or roof",
  pest_mold: "Pests or mold",
  lock: "Door or lock",
};
const fieldLabels: Record<string, string> = {
  exact_location: "Location",
  onset_frequency: "When it happens",
  media: "Photos and videos",
  contact: "Contact preferences",
  access_windows: "Access availability",
  entry_safety: "Entry and safety",
};
const statusNames: Record<string, string> = {
  INTAKE_OPEN: "Understanding the problem",
  TRIAGE_PENDING: "Home verification needed",
  MANAGER_REVIEW: "Preparing repair plan",
  ASSIGNMENT_PENDING: "Repair plan ready",
  ASSIGNED: "Assigned",
  SCHEDULING: "Scheduling",
  SCHEDULED: "Scheduled",
  IN_PROGRESS: "In progress",
  COMPLETION_REVIEW: "Completion review",
  COMPLETED: "Completed",
  CLOSED: "Closed",
  WAITING_TENANT: "One detail needed",
  WAITING_PARTS: "Waiting for parts",
  WAITING_APPROVAL: "Waiting for an update",
  CANCELED: "Canceled",
  REOPENED: "Reopened",
};
const label = (status: string) => statusNames[status] || status;
const priority = (p: string) =>
  p === "EMERGENCY"
    ? "Emergency"
    : p === "URGENT_TRIAGE"
      ? "Urgent review"
      : "Routine review";
const date = (v: string) =>
  new Date(v).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
async function read(path: string, init?: RequestInit) {
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await api(path, { ...init, signal: AbortSignal.timeout(180000) });
      if (attempt < 2 && (!init?.method || init.method === "GET") && (response.status === 429 || response.status >= 500)) {
        await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
        continue;
      }
      const body = await response.json();
      if (!response.ok)
        throw new Error(body.error?.message || "We couldn't save that change. Please try again.");
      return body;
    } catch (error) {
      if (attempt < 2 && (!init?.method || init.method === "GET") && (error instanceof TypeError || error instanceof DOMException && error.name === "TimeoutError")) {
        await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
        continue;
      }
      throw error;
    }
  }
}

export default function MaintenanceWorkspace({
  manager = false,
}: {
  manager?: boolean;
}) {
  const router = useRouter();
  const [ready, setReady] = useState(false),
    [allowed, setAllowed] = useState(false),
    [photosEnabled, setPhotosEnabled] = useState(false);
  const [homes, setHomes] = useState<Home[]>([]),
    [home, setHome] = useState("");
  const [items, setItems] = useState<Summary[]>([]),
    [cursor, setCursor] = useState<string | null>(null),
    [ticket, setTicket] = useState<Ticket | null>(null);
  const [description, setDescription] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [followUp, setFollowUp] = useState("");
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const lock = useRef(false),
    request = useRef<{ fingerprint: string; key: string } | null>(null),
    heading = useRef<HTMLHeadingElement>(null);
  const savedTicket = useRef<string | null>(null);
  const analysisRequest = useRef<{ id: string; key: string } | null>(null);
  const followUpRequest = useRef<{ body: string; key: string } | null>(null);
  async function loadList(more = false) {
    const result = await read(
      `/v1/maintenance-tickets?limit=${manager ? 30 : 8}${more && cursor ? `&before=${cursor}` : ""}`,
    );
    setItems((old) => (more ? [...old, ...result.items] : result.items));
    setCursor(result.next_cursor);
  }
  function show(value: Ticket, focus = false) {
    setTicket(value);
    setFollowUp("");
    followUpRequest.current = null;
    analysisRequest.current = null;
    const url = new URL(window.location.href);
    url.searchParams.set("ticket", value.id);
    window.history.replaceState(null, "", url);
    if (focus) setTimeout(() => heading.current?.focus(), 0);
  }
  async function refresh(id: string) {
    const value = await read(`/v1/maintenance-tickets/${id}`);
    setTicket(value);
    return value;
  }
  useEffect(() => {
    let active = true;
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    (async () => {
      try {
        const context = await read("/v1/maintenance-context");
        if (!active) return;
        setHomes(context.homes);
        setHome(context.homes[0]?.lease_id || "");
        setAllowed(context.can_manage);
        setPhotosEnabled(context.photos_enabled);
        if (manager && !context.can_manage) {
          setReady(true);
          return;
        }
        const list = await read(`/v1/maintenance-tickets?limit=${manager ? 30 : 8}`);
        if (!active) return;
        setItems(list.items);
        setCursor(list.next_cursor);
        const id = new URL(window.location.href).searchParams.get("ticket");
        if (id) {
          const value = await read(
            `/v1/maintenance-tickets/${encodeURIComponent(id)}`,
          );
          if (active) show(value);
        }
      } catch (e) {
        if (active)
          setError(
            e instanceof Error
              ? e.message
              : "The workspace could not be loaded.",
          );
      } finally {
        if (active) setReady(true);
      }
    })();
    return () => {
      active = false;
    };
  }, [manager, router]);
  useEffect(() => {
    if (!ticket || !["PENDING", "QUEUED", "ACCEPTED", "SENDING"].includes(ticket.notification_status || "")) return;
    let active = true;
    let polling = false;
    let attempts = 0;
    const timer = setInterval(async () => {
      if (polling || lock.current) return;
      if (++attempts > 20) { clearInterval(timer); return; }
      polling = true;
      try {
        const value = await read(`/v1/maintenance-tickets/${ticket.id}`);
        if (active) setTicket(value);
      } catch {
        if (active) setNotice("Your request is saved. Refresh to check the latest notification status.");
      } finally {
        polling = false;
      }
    }, 3000);
    return () => { active = false; clearInterval(timer); };
  }, [ticket?.id, ticket?.notification_status]);
  async function run(name: string, action: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (e) {
      setError(
        e instanceof TypeError
          ? "Connection lost. Your details remain on this page. Retry the action or refresh your saved requests."
          : e instanceof Error
            ? e.message
            : "The result could not be confirmed. Check your requests before trying again.",
      );
    } finally {
      lock.current = false;
      setBusy("");
    }
  }
  async function analyze(id: string) {
    if (analysisRequest.current?.id !== id)
      analysisRequest.current = { id, key: crypto.randomUUID() };
    setTicket((current) => current?.analysis ? { ...current, analysis: { ...current.analysis, status: "stale" } } : current);
    try {
      const value = await read(`/v1/maintenance-tickets/${id}/analyze`, {
        method: "POST",
        headers: { "Idempotency-Key": analysisRequest.current.key },
      });
      setTicket(value);
      analysisRequest.current = null;
      setNotice(value.analysis?.status === "ready"
        ? "Your repair plan is ready. See the next step below."
        : "Your request is saved. Prepare the repair plan below.");
    } catch {
      setNotice("Your request is saved. The repair plan could not finish; retry planning below.");
    }
  }
  function stage(files: FileList | null) {
    if (!files) return;
    const incoming = Array.from(files);
    if (attachments.filter((item) => !item.slot).length + incoming.length + (ticket?.media.length || 0) > 10) {
      setError("You can attach up to 10 files per request.");
      return;
    }
    for (const file of incoming) {
      const isVideo = /\.(mp4|mov)$/i.test(file.name);
      if (!/\.(jpe?g|png|heic|heif|mp4|mov)$/i.test(file.name)) {
        setError("Choose a JPEG, PNG, HEIC, HEIF, MP4 or MOV file.");
        return;
      }
      if (file.size > (isVideo ? 200 : 20) * 1024 * 1024) {
        setError(isVideo ? "Choose a video smaller than 200 MB and no longer than 2 minutes." : "Choose a photo smaller than 20 MB.");
        return;
      }
    }
    setError("");
    setAttachments((old) => [...old, ...incoming.map((file) => ({ file, key: crypto.randomUUID() }))]);
  }
  async function finishAttachments(id: string) {
    let uploadError: unknown;
    try {
      for (const attachment of attachments) {
        await upload(attachment, id);
        setAttachments((old) => old.filter((item) => item.key !== attachment.key));
      }
    } catch (error) {
      uploadError = error;
    }
    await analyze(id);
    await loadList();
    if (uploadError) throw uploadError;
  }
  async function report(event: FormEvent) {
    event.preventDefault();
    await run("report", async () => {
      if (!savedTicket.current) {
        const selected = homes.find((h) => h.lease_id === home);
        const payload = {
          description: description.trim(),
          ...(selected ? { unit_id: selected.unit_id, lease_id: selected.lease_id } : {}),
        };
        const fingerprint = JSON.stringify(payload);
        if (request.current?.fingerprint !== fingerprint)
          request.current = { fingerprint, key: crypto.randomUUID() };
        const value = await read("/v1/maintenance-tickets", {
          method: "POST",
          headers: { "Idempotency-Key": request.current!.key },
          body: fingerprint,
        });
        savedTicket.current = value.id;
        show(value, true);
      }
      setNotice("Your request is saved. Finishing attachments and assessment...");
      await finishAttachments(savedTicket.current!);
    });
  }
  async function sendFollowUp(event: FormEvent) {
    event.preventDefault();
    if (!ticket) return;
    await run("followup", async () => {
      const body = followUp.trim();
      if (followUpRequest.current?.body !== body)
        followUpRequest.current = { body, key: crypto.randomUUID() };
      const value = await read(`/v1/maintenance-tickets/${ticket.id}/messages`, {
        method: "POST",
        headers: { "Idempotency-Key": followUpRequest.current.key },
        body: JSON.stringify({ body, field_key: "general" }),
      });
      setTicket(value);
      setFollowUp("");
      followUpRequest.current = null;
      analysisRequest.current = null;
      await analyze(ticket.id);
      await loadList();
    });
  }
  async function upload(attachment: Attachment, ticketId: string) {
    const { file } = attachment;
    if (attachment.slot) {
      const current: Ticket = await read(`/v1/maintenance-tickets/${ticketId}`);
      if (current.media.some((media) => media.id === attachment.slot?.id && media.status === "READY")) return;
    }
    const isVideo = /\.(mp4|mov)$/i.test(file.name);
    if (!/\.(jpe?g|png|heic|heif|mp4|mov)$/i.test(file.name))
      throw new Error("Choose a JPEG, PNG, HEIC, HEIF, MP4 or MOV file.");
    const limit = (isVideo ? 200 : 20) * 1024 * 1024;
    if (file.size > limit)
      throw new Error(isVideo ? "Choose a video smaller than 200 MB and no longer than 2 minutes." : "Choose a photo smaller than 20 MB.");
    const bytes = await file.arrayBuffer();
    const hash = Array.from(
      new Uint8Array(await crypto.subtle.digest("SHA-256", bytes)),
    )
      .map((n) => n.toString(16).padStart(2, "0"))
      .join("");
    const contentType = isVideo
      ? (/\.mov$/i.test(file.name) ? "video/quicktime" : "video/mp4")
      : /\.hei[cf]$/i.test(file.name)
      ? "image/heic"
      : /\.png$/i.test(file.name)
        ? "image/png"
        : "image/jpeg";
    const slot = await read(
      `/v1/maintenance-tickets/${ticketId}/media-uploads`,
      {
        method: "POST",
        headers: { "Idempotency-Key": attachment.key },
        body: JSON.stringify({
          filename: file.name,
          content_type: contentType,
          size_bytes: file.size,
          sha256: hash,
        }),
      },
    );
    attachment.slot = slot;
    if (!attachment.uploaded) {
      const response = await fetch(`${API_BASE}${slot.upload_url}`, {
        signal: AbortSignal.timeout(180000),
        method: "POST",
        headers: slot.required_headers,
        body: bytes,
      });
      if (!response.ok)
        throw new Error("The attachment did not finish uploading. Your request is saved. Retry the remaining attachments.");
      attachment.uploaded = true;
    }
    const result = await read(`/v1/media/${slot.id}/complete`, {
      method: "POST",
    });
    if (result.status !== "READY")
      throw new Error(
        "This attachment could not be accepted. Try another photo or a video no longer than 2 minutes, or continue without attachments.",
      );
    analysisRequest.current = null;
  }
  async function openPhoto(id: string, isVideo: boolean) {
    await run("photo", async () => {
      const result = await read(`/v1/media/${id}/download`);
      const response = await fetch(`${API_BASE}${result.download_url}`, { signal: AbortSignal.timeout(180000) });
      if (!response.ok)
        throw new Error("This attachment is unavailable. Please try again.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = isVideo ? `maintenance-video-${id}.mp4` : `maintenance-photo-${id}.jpg`;
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
  async function managerDemo() {
    await run("switch", async () => {
      const result = await read("/v1/demo/session", {
        method: "POST",
        body: JSON.stringify({ role: "property_manager" }),
      });
      setToken(result.token);
      router.push("/maintenance/manage");
    });
  }
  function newRequest() {
    setTicket(null);
    setDescription("");
    setAttachments([]);
    savedTicket.current = null;
    analysisRequest.current = null;
    followUpRequest.current = null;
    setNotice("");
    setError("");
    request.current = null;
    window.history.replaceState(null, "", window.location.pathname);
  }
  const attachmentPicker = (
    <div className="photo-section">
      {photosEnabled ? (
        <label className="photo-upload">
          Photos or videos <span className="optional-label">Optional</span>
          <input type="file" multiple accept=".jpg,.jpeg,.png,.heic,.heif,.mp4,.mov" disabled={!!busy} onChange={(event) => { stage(event.target.files); event.target.value = ""; }} />
          <small>Up to 10 files. Photos up to 20 MB; videos up to 200 MB and 2 minutes. Only record if safe.</small>
        </label>
      ) : <p className="field-help">Attachments are unavailable here. You can still send your description.</p>}
      {attachments.length ? (
        <ul className="photo-list">
          {attachments.map((attachment) => (
            <li key={attachment.key}>
              <span>{attachment.file.name}</span>
              <button type="button" className="secondary-button" disabled={!!busy} onClick={() => setAttachments((old) => old.filter((item) => item.key !== attachment.key))}>Remove</button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
  return (
    <>
      <p>
        <Link href="/">Home</Link>
      </p>
      <div className="row">
        <div>
          <p className="eyebrow">
            {manager ? "MANAGER WORKSPACE" : "RESIDENT CARE"}
          </p>
          <h1>{manager ? "Maintenance queue" : "Maintenance"}</h1>
        </div>
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
      <p>
        {manager
          ? "Review requests, inspect photos and videos, and keep residents informed with clear status updates."
          : "Tell us what happened. Add a photo or video if you can, and we’ll help work out the next step."}
      </p>
      <div className="maintenance-warning">
        <strong>Immediate danger?</strong> Leave the area if safe and call 911
        or your local emergency service. For a suspected gas leak, call from
        outside and do not operate electrical switches. This website does not
        contact emergency services or dispatch contractors.
      </div>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="maintenance-success" role="status">
          {notice}
        </p>
      ) : null}
      {!ready ? (
        <p role="status">Loading your maintenance workspace...</p>
      ) : manager && !allowed ? (
        <div className="card">
          <h2>Manager access required</h2>
          <p>Switch to a property manager account to review requests.</p>
        </div>
      ) : (
        <>
          <div className="maintenance-toolbar">
            <h2>
              {ticket
                ? "Request details"
                : manager
                  ? "Requests to review"
                  : "New repair request"}
            </h2>
            <div>
              {manager ? <Link href="/maintenance/phone">Phone inbox</Link> : null}
              {manager ? <Link href="/maintenance/jobs">Repair board</Link> : null}
              {ticket && !manager ? (
                <button type="button" disabled={!!busy} onClick={newRequest}>
                  New request
                </button>
              ) : null}
              {process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" && !manager ? (
                <button
                  type="button"
                  className="secondary-button"
                  disabled={!!busy}
                  onClick={() => void managerDemo()}
                >
                  Open manager queue
                </button>
              ) : null}
              {allowed &&
              !manager &&
              process.env.NEXT_PUBLIC_DEMO_FIXTURE !== "sample" ? (
                <Link href="/maintenance/manage">Open manager queue</Link>
              ) : null}
            </div>
          </div>
          {!ticket && !manager ? (
            <form className="maintenance-intake" onSubmit={report}>
              <div className="form-intro">
                <h3>What needs fixing?</h3>
                <p>Describe the problem in your own words.</p>
              </div>
              {homes.length > 1 ? (
                <label>
                  Your home
                  <select value={home} onChange={(event) => setHome(event.target.value)} required disabled={!!busy}>
                    {homes.map((item) => <option key={item.lease_id} value={item.lease_id}>{item.property_name} / Unit {item.unit_label}</option>)}
                  </select>
                </label>
              ) : !homes.length ? <p className="inline-note">Your manager will confirm which home this request is for.</p> : null}
              <label>
                What needs attention?
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={5000}
                  required
                  disabled={!!busy}
                  placeholder="For example: Water drips from the pipe under the kitchen sink when I run the tap."
                  aria-describedby="description-help"
                />
              </label>
              <p id="description-help" className="field-help">
                Required *. Describe what you can observe. Don't dismantle
                equipment or put yourself at risk.
              </p>
              {attachmentPicker}
              <button type="submit" disabled={!!busy || !description.trim()}>
                {busy === "report" ? "Sending request..." : "Send request"}
              </button>
            </form>
          ) : null}
          {ticket ? (
            <section
              className="maintenance-detail"
              aria-labelledby="ticket-heading"
            >
              <div className="ticket-summary">
                <div>
                  <p className="eyebrow">
                    {manager
                      ? "MAINTENANCE REQUEST"
                      : "SAVED MAINTENANCE REQUEST"}
                  </p>
                  <h2 id="ticket-heading" ref={heading} tabIndex={-1}>
                    Ticket {ticket.ticket_number}
                  </h2>
                  <p>
                    {ticket.property_name
                      ? `${ticket.property_name} / Unit ${ticket.unit_label}`
                      : "Home awaiting verification"}{" "}
                    <span className="muted">/ {date(ticket.created_at)}</span>
                  </p>
                </div>
                <div className="ticket-badges">
                  <span
                    className={`status-pill ${ticket.emergency ? "danger" : ""}`}
                  >
                    {priority(ticket.priority)}
                  </span>
                  <span className="status-pill">{label(ticket.status)}</span>
                </div>
              </div>
              {ticket.safety_message ? (
                <div className="emergency-panel" role="alert">
                  <h3>Safety comes first</h3>
                  {ticket.safety_message
                    .split(" Do not operate")
                    .map((part, i) => (
                      <p key={i}>{i ? "Do not operate" + part : part}</p>
                    ))}
                  <p>
                    Do not wait for a reply here. No emergency call or
                    contractor dispatch has been made.
                  </p>
                </div>
              ) : null}
              <div className="ticket-body">
                <section className="question-panel" aria-live="polite">
                  <h3>Maintenance delivery</h3>
                  <p>{ticket.notification_status === "SIMULATED"
                    ? "Routed to the simulated maintenance inbox. No real person has been contacted. A visit still needs to be arranged."
                    : ticket.notification_status === "SUPPRESSED"
                      ? "No maintenance notification was sent because this request was closed or canceled."
                    : ticket.notification_status === "DELIVERED"
                      ? "The maintenance notification was delivered. A visit has not been confirmed."
                      : ["SENT", "ACCEPTED", "SENDING", "QUEUED"].includes(ticket.notification_status || "")
                        ? "The maintenance notification is with the phone provider. Delivery and a visit are not yet confirmed."
                        : ticket.notification_status === "PENDING"
                          ? "Preparing the maintenance notification. This will update automatically."
                          : ticket.notification_status === "DELIVERY_UNKNOWN"
                            ? "The notification result is uncertain. Your manager needs to confirm delivery before sending again."
                            : ["FAILED", "UNDELIVERED"].includes(ticket.notification_status || "")
                              ? "The maintenance notification failed. Your manager can still see this request and needs to arrange the repair."
                              : "Saved in the manager queue. Maintenance notifications are not connected, so nobody has been contacted."}</p>
                  {manager ? <Link href="/maintenance/phone">Open maintenance inbox</Link> : null}
                </section>
                <div className="ticket-description">
                  <h3>Reported issue</h3>
                  <p>{ticket.description}</p>
                  <span className="category-label">
                    {categories[ticket.category as keyof typeof categories] ||
                      "General maintenance"}
                  </span>
                </div>
                <div className="next-step">
                  <h3>What happens next</h3>
                  <p>
                    {ticket.emergency
                      ? "Seek emergency help now. Your report is saved, but this website cannot arrange emergency assistance."
                      : ["COMPLETED", "CLOSED", "CANCELED"].includes(
                              ticket.status,
                            )
                          ? "This request is no longer active. Contact your manager if the problem returns."
                          : ticket.status === "IN_PROGRESS"
                            ? "Your manager has marked the repair in progress. Check the activity below for their latest note."
                            : ticket.status === "SCHEDULED"
                              ? "Your manager has marked a visit as scheduled. Confirm the time and entry arrangements directly with them."
                              : ticket.status.startsWith("WAITING_")
                                ? ticket.analysis?.next_action || "The repair needs more information or parts. Read the next step below."
                                : ticket.status === "COMPLETION_REVIEW"
                                  ? "Work has been marked ready for review. Your manager will confirm the outcome before closing this request."
                                  : [
                                        "ASSIGNED",
                                        "SCHEDULING",
                                        "ASSIGNMENT_PENDING",
                                      ].includes(ticket.status)
                                    ? ticket.analysis?.next_action || "Use the repair plan below to arrange an inspection and confirm access."
                                    : "First identify the problem, then work out the repair. No manager review is needed to prepare the plan."}
                  </p>
                </div>
                    {ticket.analysis?.status === "ready" ? (
                      <div className="question-panel">
                        <h3>What needs fixing</h3>
                        <p>{ticket.analysis.summary}</p>
                        <h3>How to resolve it</h3>
                        {ticket.analysis.trade ? <p><strong>Suitable trade:</strong> {ticket.analysis.trade}</p> : null}
                        <ol>{ticket.analysis.repair_steps?.map((step) => <li key={step}>{step}</li>)}</ol>
                        <h3>Next step</h3>
                        <p>{ticket.analysis.next_action}</p>
                        <p className="field-help">{ticket.analysis.source === "rules" ? "Description-based plan. A technician must confirm the cause." : "AI-assisted plan. A technician must confirm the cause."}</p>
                        {ticket.analysis.images_analyzed || ticket.analysis.video_frames_analyzed ? <p className="field-help">Reviewed {ticket.analysis.images_analyzed} photo(s) and {ticket.analysis.video_frames_analyzed} video frame(s). Video audio was not assessed.</p> : null}
                        {ticket.analysis.follow_up.length ? <ul>{ticket.analysis.follow_up.map((question) => <li key={question}>{question}</li>)}</ul> : null}
                      </div>
                    ) : (
                      <div className="question-panel">
                        <h3>Prepare the repair plan</h3>
                        <p>{busy ? "Working out the problem and next step..." : "Use the description to identify the problem, a suitable trade, and the steps needed to resolve it."}</p>
                        {!busy && !attachments.length ? <button type="button" className="secondary-button" onClick={() => void run("analyze", async () => { await analyze(ticket.id); await loadList(); })}>Prepare repair plan</button> : null}
                      </div>
                    )}
                {manager && ticket.intake?.some(
                  (f) => fieldLabels[f.field_key] && f.value_text,
                ) ? (
                  <details className="intake-details">
                    <summary>Details provided</summary>
                    <dl>
                      {ticket.intake
                        .filter((f) => fieldLabels[f.field_key] && f.value_text)
                        .map((f) => (
                          <div key={f.field_key}>
                            <dt>{fieldLabels[f.field_key]}</dt>
                            <dd>{f.value_text}</dd>
                          </div>
                        ))}
                    </dl>
                  </details>
                ) : null}
                <section className="photo-section">
                  <h3>
                    Photos and videos <span className="optional-label">Optional</span>
                  </h3>
                  <p>
                    Only record if safe. Use fictional, non-sensitive
                    photos and videos in this public demo.
                  </p>
                  <ul className="photo-list">
                    {ticket.media?.map((m, i) => (
                      <li key={m.id}>
                        <span>
                          {m.content_type?.startsWith("video/") ? "Video" : "Photo"} {i + 1} /{" "}
                          {m.status === "READY"
                            ? "Attached"
                            : m.status === "REJECTED"
                              ? "Not accepted"
                              : "Upload incomplete"}
                        </span>
                        {m.status === "READY" ? (
                          <button
                            className="secondary-button"
                            disabled={!!busy}
                            onClick={() => void openPhoto(m.id, !!m.content_type?.startsWith("video/"))}
                          >
                            Download {m.content_type?.startsWith("video/") ? "video" : "photo"} {i + 1}
                          </button>
                        ) : (
                          <span>
                            {m.rejection_reason ||
                              "Try attaching the file again."}
                          </span>
                        )}
                      </li>
                    ))}
                  </ul>
                  {!manager ? attachmentPicker : null}
                  {!manager && attachments.length ? (
                    <button type="button" disabled={!!busy} onClick={() => void run("upload", () => finishAttachments(ticket.id))}>
                      {busy ? "Finishing attachments..." : "Send remaining attachments"}
                    </button>
                  ) : null}
                </section>
                {!manager && ["INTAKE_OPEN", "TRIAGE_PENDING", "MANAGER_REVIEW", "WAITING_TENANT", "ASSIGNMENT_PENDING"].includes(ticket.status) ? (
                  <>
                    <form onSubmit={sendFollowUp}>
                      <div className="form-intro">
                        <h3>
                          {ticket.emergency
                            ? "Add information when safe"
                            : "Add a follow-up"}
                        </h3>
                        <p>
                          Share an update or answer a question above.
                          Your original request stays saved.
                        </p>
                      </div>
                      <label>
                        Follow-up
                        <textarea
                          value={followUp}
                          onChange={(e) => setFollowUp(e.target.value)}
                          maxLength={5000}
                          required
                        />
                      </label>
                      <button disabled={!!busy || !followUp.trim()}>
                        {busy === "followup" ? "Saving..." : "Send follow-up"}
                      </button>
                    </form>
                  </>
                ) : null}
                <WorkflowPanel key={ticket.id} ticketId={ticket.id} onChange={() => { void run("refresh", async () => { await refresh(ticket.id); await loadList(); }); }} />
                <section className="request-history">
                  <h3>Request activity</h3>
                  <ol>
                    <li>
                      <strong>Request received</strong>
                      <time>{date(ticket.created_at)}</time>
                      <p>{ticket.description}</p>
                    </li>
                    {[
                      ...(ticket.messages || []).map((m) => ({
                        id: m.id,
                        title: "Follow-up added",
                        body: m.body,
                        at: m.created_at,
                      })),
                      ...(ticket.history || []).map((h, i) => ({
                        id: `status-${i}`,
                        title: label(h.status),
                        body: h.reason,
                        at: h.created_at,
                      })),
                    ]
                      .sort((a, b) => a.at.localeCompare(b.at))
                      .map((m) => (
                        <li key={m.id}>
                          <strong>{m.title}</strong>
                          <time>{date(m.at)}</time>
                          {m.body ? <p>{m.body}</p> : null}
                        </li>
                      ))}
                  </ol>
                </section>
              </div>
            </section>
          ) : null}
          <section className="request-list-section">
            <div className="section-heading request-list-heading">
              <div>
                <h2>
                  {manager ? "All maintenance requests" : "Your requests"}
                  <span className="request-count">{items.length}{cursor ? "+" : ""}</span>
                </h2>
                <p>
                  {manager
                    ? "Newest first. Emergency flags stay visible until a manager explicitly clears them."
                    : "Track your repairs and hear back from your manager."}
                </p>
              </div>
              <button
                type="button"
                className="secondary-button request-refresh"
                aria-label="Refresh requests"
                disabled={!!busy}
                onClick={() =>
                  void run("refresh", async () => {
                    await loadList();
                    if (ticket) await refresh(ticket.id);
                    setNotice("Requests refreshed.");
                  })
                }
              >
                <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true"><path d="M20 7v5h-5M4 17v-5h5"/><path d="M6.1 7a7 7 0 0 1 11.5-1L20 9M4 15l2.4 3A7 7 0 0 0 17.9 17"/></svg>
                {busy === "refresh" ? "Refreshing..." : "Refresh"}
              </button>
            </div>
            {items.length ? (
              <ul className="maintenance-request-list">
                {items.map((item) => (
                  <li key={item.id}>
                    <button
                      className={`request-item ${ticket?.id === item.id ? "selected" : ""}`}
                      disabled={!!busy || attachments.length > 0}
                      aria-current={ticket?.id === item.id ? "true" : undefined}
                      onClick={() =>
                        void run("open", async () => {
                          show(
                            await read(`/v1/maintenance-tickets/${item.id}`),
                            true,
                          );
                        })
                      }
                    >
                      <span className={`request-item-icon ${item.emergency ? "is-emergency" : ""}`} aria-hidden="true">
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 6.5a5 5 0 0 0-6.6 6.6L3 18a2.1 2.1 0 0 0 3 3l4.9-4.9a5 5 0 0 0 6.6-6.6l-3 3-3-3 3-3Z"/></svg>
                      </span>
                      <span className="request-item-main">
                        <span className="request-number">
                          Request #{item.ticket_number}<span aria-hidden="true"> &middot; </span>{categories[item.category as keyof typeof categories] || "Maintenance"}
                        </span>
                        <strong>{item.description}</strong>
                        <span>
                          {item.property_name
                            ? `${item.property_name} / Unit ${item.unit_label}`
                            : "Home awaiting verification"}
                        </span>
                      </span>
                      <span className="request-item-state">
                        <span className={`request-status ${["COMPLETED", "CLOSED"].includes(item.status) ? "is-complete" : ""}`}>
                          <span className="request-status-dot" aria-hidden="true" />{label(item.status)}
                        </span>
                        <span className="request-item-date">{date(item.created_at)}</span>
                        {item.priority !== "ROUTINE_REVIEW_PENDING" ? (
                          <span className={`request-priority ${item.emergency ? "is-emergency" : ""}`}>{priority(item.priority)}</span>
                        ) : null}
                      </span>
                      <span className="request-item-arrow" aria-hidden="true"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="m9 6 6 6-6 6" /></svg></span>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="card">
                <h3>
                  {manager ? "No requests to review yet." : "A fresh start."}
                </h3>
                <p>
                  {manager
                    ? "Resident requests will appear here after they are saved."
                    : "Your maintenance requests will appear here once you report an issue."}
                </p>
              </div>
            )}
            {cursor ? (
              <button
                type="button"
                className="secondary-button"
                disabled={!!busy}
                onClick={() =>
                  void run("more", async () => {
                    await loadList(true);
                  })
                }
              >
                Load older requests
              </button>
            ) : null}
          </section>
        </>
      )}
    </>
  );
}
