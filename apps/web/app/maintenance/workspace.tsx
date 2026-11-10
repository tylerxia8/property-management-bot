"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, API_BASE, clearToken, getToken, setToken } from "../../lib/api";

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
  INTAKE_OPEN: "Request received",
  TRIAGE_PENDING: "Home verification needed",
  MANAGER_REVIEW: "Under manager review",
  ASSIGNMENT_PENDING: "Awaiting assignment",
  ASSIGNED: "Assigned",
  SCHEDULING: "Scheduling",
  SCHEDULED: "Scheduled",
  IN_PROGRESS: "In progress",
  COMPLETION_REVIEW: "Completion review",
  COMPLETED: "Completed",
  CLOSED: "Closed",
  WAITING_TENANT: "Waiting for resident",
  WAITING_PARTS: "Waiting for parts",
  WAITING_APPROVAL: "Waiting for approval",
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
  const response = await api(path, init);
  const body = await response.json();
  if (!response.ok)
    throw new Error(
      body.error?.message || "We couldn't save that change. Please try again.",
    );
  return body;
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
  const [description, setDescription] = useState(""),
    [category, setCategory] = useState(""),
    [location, setLocation] = useState(""),
    [onset, setOnset] = useState(""),
    [contact, setContact] = useState(""),
    [access, setAccess] = useState(""),
    [safety, setSafety] = useState("");
  const [followUp, setFollowUp] = useState(""),
    [field, setField] = useState(""),
    [status, setStatus] = useState("MANAGER_REVIEW"),
    [reason, setReason] = useState("");
  const [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  const lock = useRef(false),
    request = useRef<{ fingerprint: string; key: string } | null>(null),
    heading = useRef<HTMLHeadingElement>(null);
  const uploadInput = useRef<HTMLInputElement>(null);
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
    setField(
      value.missing_fields.find(
        (key: string) => fieldLabels[key] && key !== "media",
      ) || "general",
    );
    setStatus(value.status);
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
  async function report(event: FormEvent) {
    event.preventDefault();
    await run("report", async () => {
      const selected = homes.find((h) => h.lease_id === home);
      const payload = {
        description: description.trim(),
        ...(category ? { category } : {}),
        ...(selected
          ? { unit_id: selected.unit_id, lease_id: selected.lease_id }
          : {}),
        location: location.trim() || null,
        onset: onset.trim() || null,
        contact: contact.trim() || null,
        preferred_access_windows: access.trim() ? [access.trim()] : null,
        safety_concerns: safety.trim() || null,
      };
      const fingerprint = JSON.stringify(payload);
      if (request.current?.fingerprint !== fingerprint)
        request.current = { fingerprint, key: crypto.randomUUID() };
      const value = await read("/v1/maintenance-tickets", {
        method: "POST",
        headers: { "Idempotency-Key": request.current!.key },
        body: fingerprint,
      });
      show(value, true);
      setNotice(
        "Your request is saved. You can return to it from Your requests.",
      );
      await loadList();
    });
  }
  async function sendFollowUp(event: FormEvent) {
    event.preventDefault();
    if (!ticket) return;
    await run("followup", async () => {
      const value = await read(
        `/v1/maintenance-tickets/${ticket.id}/messages`,
        {
          method: "POST",
          body: JSON.stringify({
            body: followUp.trim(),
            field_key: field || "general",
          }),
        },
      );
      setTicket(value);
      setFollowUp("");
      setField(
        value.missing_fields.find(
          (key: string) => fieldLabels[key] && key !== "media",
        ) || "general",
      );
      setNotice("Follow-up saved.");
      await loadList();
    });
  }
  async function skipPhoto() {
    if (!ticket) return;
    await run("skip", async () => {
      setTicket(
        await read(`/v1/maintenance-tickets/${ticket.id}`, {
          method: "PATCH",
          body: JSON.stringify({
            field_key: "media",
            status: "NOT_PRACTICAL",
            reason: "Resident chose to continue without photos or videos.",
          }),
        }),
      );
      setNotice("Your request stays open without photos or videos.");
    });
  }
  async function handoff() {
    if (!ticket) return;
    await run("handoff", async () => {
      setTicket(
        await read(`/v1/maintenance-tickets/${ticket.id}/messages`, {
          method: "POST",
          body: JSON.stringify({
            body: "Please hand off this request to the manager. That's all for now.",
          }),
        }),
      );
      setNotice(
        "Intake finished. Your request is available for manager review; no notification was sent.",
      );
      await loadList();
    });
  }
  async function upload(file: File) {
    if (!ticket) return;
    await run("upload", async () => {
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
        `/v1/maintenance-tickets/${ticket.id}/media-uploads`,
        {
          method: "POST",
          body: JSON.stringify({
            filename: file.name,
            content_type: contentType,
            size_bytes: file.size,
            sha256: hash,
          }),
        },
      );
      const response = await fetch(`${API_BASE}${slot.upload_url}`, {
        method: "POST",
        headers: slot.required_headers,
        body: bytes,
      });
      if (!response.ok)
        throw new Error(
          "The attachment did not finish uploading. Your maintenance request is still saved.",
        );
      const result = await read(`/v1/media/${slot.id}/complete`, {
        method: "POST",
      });
      await refresh(ticket.id);
      if (result.status !== "READY")
        throw new Error(
          "This attachment could not be accepted. Try another photo or a video no longer than 2 minutes, or continue without attachments.",
        );
      setNotice(
        "Attachment saved. Metadata is removed from the downloadable copy.",
      );
    });
    if (uploadInput.current) uploadInput.current.value = "";
  }
  async function openPhoto(id: string, isVideo: boolean) {
    await run("photo", async () => {
      const result = await read(`/v1/media/${id}/download`);
      const response = await fetch(`${API_BASE}${result.download_url}`);
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
  async function update(event: FormEvent) {
    event.preventDefault();
    if (!ticket) return;
    await run("status", async () => {
      await read(`/v1/maintenance-tickets/${ticket.id}/transitions`, {
        method: "POST",
        body: JSON.stringify({
          action: status === "CANCELED" ? "cancel" : "set_status",
          status,
          reason: reason.trim(),
        }),
      });
      await refresh(ticket.id);
      setReason("");
      setNotice(
        "Status updated. The resident can see this change in their request.",
      );
      await loadList();
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
    setLocation("");
    setOnset("");
    setContact("");
    setAccess("");
    setSafety("");
    setCategory("");
    setNotice("");
    setError("");
    request.current = null;
    window.history.replaceState(null, "", window.location.pathname);
  }
  const questionFields =
    ticket?.missing_fields.filter((key: string) => fieldLabels[key]) || [];
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
          : "Tell us what's wrong. We'll keep the details together so your property manager can plan the repair."}
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
                <span className="step-label">01 / THE PROBLEM</span>
                <h3>A few details go a long way.</h3>
                <p>
                  Required fields are marked *. You can add photos and videos after saving
                  your request.
                </p>
              </div>
              {homes.length ? (
                <label>
                  Your home *
                  <select
                    value={home}
                    onChange={(e) => setHome(e.target.value)}
                    required
                  >
                    {homes.map((h) => (
                      <option key={h.lease_id} value={h.lease_id}>
                        {h.property_name} / Unit {h.unit_label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <p className="inline-note">
                  No tenancy is linked to this account. You can still report an
                  issue; your manager will need to confirm the home.
                </p>
              )}
              <label>
                Type of issue
                <select
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                >
                  <option value="">Choose automatically</option>
                  {Object.entries(categories).map(([key, value]) => (
                    <option key={key} value={key}>
                      {value}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                What needs attention?
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  maxLength={5000}
                  required
                  placeholder="For example: Water drips from the pipe under the kitchen sink when I run the tap."
                  aria-describedby="description-help"
                />
              </label>
              <p id="description-help" className="field-help">
                Required *. Describe what you can observe. Don't dismantle
                equipment or put yourself at risk.
              </p>
              <label>
                Exact location
                <input
                  value={location}
                  onChange={(e) => setLocation(e.target.value)}
                  maxLength={500}
                  placeholder="Kitchen, under the sink"
                />
              </label>
              <label>
                When did it start?
                <input
                  value={onset}
                  onChange={(e) => setOnset(e.target.value)}
                  maxLength={500}
                  placeholder="Yesterday; only when the tap runs"
                />
              </label>
              <div className="form-intro">
                <span className="step-label">02 / PLANNING THE VISIT</span>
                <p>
                  These details are optional. Availability is a preference, not
                  a confirmed appointment or permission to enter.
                </p>
              </div>
              <label>
                Contact preferences
                <input
                  value={contact}
                  onChange={(e) => setContact(e.target.value)}
                  maxLength={500}
                  placeholder="Best way and time to reach you"
                />
              </label>
              <label>
                Preferred access windows
                <input
                  value={access}
                  onChange={(e) => setAccess(e.target.value)}
                  maxLength={500}
                  placeholder="Weekdays after 3pm"
                />
              </label>
              <label>
                Safety concerns or entry instructions
                <textarea
                  value={safety}
                  onChange={(e) => setSafety(e.target.value)}
                  maxLength={1000}
                  placeholder="For example: A dog is in the home. Please call before arriving. Do not include keys or door codes."
                />
              </label>
              <button type="submit" disabled={!!busy || !description.trim()}>
                {busy === "report" ? "Saving request..." : "Report issue"}
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
                      : manager
                        ? "Review the resident's details and attachments, then save a status with a clear note. Arrange any dispatch or visit directly; this website does not send notifications."
                        : ["COMPLETED", "CLOSED", "CANCELED"].includes(
                              ticket.status,
                            )
                          ? "This request is no longer active. Contact your manager if the problem returns."
                          : ticket.status === "IN_PROGRESS"
                            ? "Your manager has marked the repair in progress. Check the activity below for their latest note."
                            : ticket.status === "SCHEDULED"
                              ? "Your manager has marked a visit as scheduled. Confirm the time and entry arrangements directly with them."
                              : ticket.status.startsWith("WAITING_")
                                ? "Your manager needs more information, parts, or approval before the repair can continue. Read their latest note below."
                                : ticket.status === "COMPLETION_REVIEW"
                                  ? "Work has been marked ready for review. Your manager will confirm the outcome before closing this request."
                                  : [
                                        "ASSIGNED",
                                        "SCHEDULING",
                                        "ASSIGNMENT_PENDING",
                                      ].includes(ticket.status)
                                    ? "Your manager is coordinating the repair. Check the activity below and confirm any visit directly."
                                    : ticket.handoff
                                      ? "Your details are ready for your manager to review. Check back here for status updates. A visit has not been scheduled."
                                      : "Add any missing details below, then finish intake. Your manager can review the request even if you can't provide every detail."}
                  </p>
                </div>
                {ticket.intake?.some(
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
                  {!manager && photosEnabled ? (
                    <label className="photo-upload">
                      {busy === "upload"
                        ? "Uploading and checking attachment..."
                        : "Attach a photo or video"}
                      <input
                        ref={uploadInput}
                        type="file"
                        accept=".jpg,.jpeg,.png,.heic,.heif,.mp4,.mov"
                        disabled={!!busy || ticket.media?.length >= 10}
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) void upload(file);
                        }}
                      />
                      <small>
                        Photos: JPEG, PNG, HEIC or HEIF, up to 20 MB. Videos: MP4 or MOV, up to 200 MB and 2 minutes. Up to 10 files per request. Videos may take a minute to process; keep this page open.
                      </small>
                    </label>
                  ) : !manager ? (
                    <p>
                      Photo and video attachments are unavailable in this environment.
                      Your report can continue without them.
                    </p>
                  ) : null}
                  {!manager && ticket.missing_fields.includes("media") ? (
                    <button
                      type="button"
                      className="secondary-button"
                      disabled={!!busy}
                      onClick={() => void skipPhoto()}
                    >
                      Continue without photos or videos
                    </button>
                  ) : null}
                </section>
                {manager ? (
                  <form onSubmit={update}>
                    <div className="form-intro">
                      <h3>Update this request</h3>
                      <p>
                        Record a status and a clear note for the resident.
                        Dispatch remains manual.
                      </p>
                    </div>
                    <label>
                      Status
                      <select
                        value={status}
                        onChange={(e) => setStatus(e.target.value)}
                      >
                        {Object.entries(statusNames).map(([key, value]) => (
                          <option key={key} value={key}>
                            {value}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      Update note
                      <textarea
                        value={reason}
                        onChange={(e) => setReason(e.target.value)}
                        required
                        maxLength={2000}
                        placeholder="What changed, and what should the resident expect next?"
                      />
                    </label>
                    <button disabled={!!busy || !reason.trim()}>
                      {busy === "status" ? "Saving..." : "Save status update"}
                    </button>
                  </form>
                ) : (
                  <>
                    {ticket.next_questions.length ? (
                      <div className="question-panel">
                        <h3>A little more detail</h3>
                        <ul>
                          {ticket.next_questions.map((q) => (
                            <li key={q}>{q}</li>
                          ))}
                        </ul>
                      </div>
                    ) : null}
                    <form onSubmit={sendFollowUp}>
                      <div className="form-intro">
                        <h3>
                          {ticket.emergency
                            ? "Add information when safe"
                            : "Add a follow-up"}
                        </h3>
                        <p>
                          Answer one question at a time, or share an update.
                          Your original request stays saved.
                        </p>
                      </div>
                      {!ticket.emergency && questionFields.length ? (
                        <label>
                          What is this about?
                          <select
                            value={field}
                            onChange={(e) => setField(e.target.value)}
                          >
                            <option value="general">General update</option>
                            {questionFields
                              .filter((k) => k !== "media")
                              .map((k) => (
                                <option key={k} value={k}>
                                  {fieldLabels[k]}
                                </option>
                              ))}
                          </select>
                        </label>
                      ) : null}
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
                    {!ticket.handoff && !ticket.emergency ? (
                      <button
                        className="secondary-button"
                        disabled={!!busy}
                        onClick={() => void handoff()}
                      >
                        Finish intake for manager review
                      </button>
                    ) : null}
                  </>
                )}
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
                      disabled={!!busy}
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
