"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { API_BASE, getToken } from "../../../lib/api";
import WorkflowPanel, { workflowRequest } from "../workflow-panel";
import styles from "./control.module.css";

type Property = { id: string; name: string };
type Worker = { id: string; name: string; approved: boolean; active: boolean; service_property_ids: string[]; service_categories: string[]; accepting_work: boolean; availability_note: string; max_open_jobs: number; version: number; open_jobs: number };
type Repair = { id: string; ticket_number: number; description: string; status: string; priority: string; owner_name: string | null; next_action: string; reason_codes: string[]; notification_status: string | null; last_activity_at: string };
type Operations = { requests: Repair[]; workers: Worker[]; properties: Property[]; worker_health: { phone_configured: boolean; history_configured: boolean; pending_notifications: number; failed_notifications: number; unknown_notifications: number }; background_worker: { status: string; heartbeat_at: string | null; last_success_at: string | null; last_error_type: string | null; failure_count: number } };
type Entry = { id: string; property_id: string; title: string; problem_key: string; model: string; part_details: string; instructions: string; verified: boolean; active: boolean; version: number; reference_media_ids: string[] };
type Knowledge = { entries: Entry[]; properties: Property[]; approved_instructions: string[]; problem_keys?: string[]; reference_media: { id: string; property_id: string; content_type: string; created_at: string }[] };
type Issue = { id: string; title: string; status: string; version: number; evidence: string };
type Issues = { items: Issue[] };
const categories = ["leak", "electrical", "hvac", "appliance", "structural", "pest_mold", "lock", "general"];
const problems = ["shower_leak", "shower_drain", "internet", "microwave", "fan", "furniture", "hot_water", "shower", "dishwasher", "oven", "hvac_filter", "hvac", "fridge_filter", "fridge", "bulb", "toilet", "remote", "pest", "lock", "odor", "sink", "laundry", "electrical", "mold", "structural", "leak"];
const human = (value: string) => value.toLowerCase().replaceAll("_", " ");
const date = (value: string | null) => value ? new Date(value).toLocaleString() : "Not recorded";
const message = (value: unknown) => value instanceof Error ? value.message : "Unable to complete this request.";

function useMutation() {
  const keys = useRef(new Map<string, string>());
  const lock = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  async function save<T>(path: string, method: string, data: object): Promise<T | null> {
    if (lock.current) return null;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    const body = JSON.stringify(data);
    const signature = `${method}:${path}:${body}`;
    const key = keys.current.get(signature) || crypto.randomUUID();
    keys.current.set(signature, key);
    try {
      const result = await workflowRequest(path, { method, headers: { "Idempotency-Key": key }, body });
      keys.current.delete(signature);
      setNotice("Saved.");
      return result as T;
    } catch (value) {
      setError(message(value));
      return null;
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }
  return { save, busy, error, notice };
}

function IssueEditor({ issue, ticketId, onChange }: { issue: Issue; ticketId: string; onChange: (data: Issues) => void }) {
  const [status, setStatus] = useState(["OPEN", "WAITING_PARTS", "RESOLUTION_REPORTED"].includes(issue.status) ? issue.status : "OPEN");
  const [note, setNote] = useState("");
  const mutation = useMutation();
  async function submit(event: FormEvent) {
    event.preventDefault();
    const result = await mutation.save<Issues>(`/v1/maintenance-tickets/${ticketId}/issues/${issue.id}/updates`, "POST", { version: issue.version, status, note });
    if (result) { setNote(""); onChange(result); }
  }
  return <form className={styles.form} onSubmit={submit}>
    <div><h3>{issue.title}</h3><span className={styles.badge}>{human(issue.status)}</span></div>
    {issue.evidence && <p>{issue.evidence}</p>}
    <label>Next status<select value={status} onChange={event => setStatus(event.target.value)}><option value="OPEN">Open</option><option value="WAITING_PARTS">Waiting for parts</option><option value="RESOLUTION_REPORTED">Repair reported complete</option></select></label>
    <label>Update note<textarea required maxLength={5000} value={note} onChange={event => setNote(event.target.value)} placeholder="What changed, and what still needs attention?" /></label>
    <p className={styles.muted}>Only the resident can confirm that this issue is fixed.</p>
    {mutation.error && <p role="alert" className={styles.error}>{mutation.error}</p>}
    {mutation.notice && <p role="status">{mutation.notice}</p>}
    <button disabled={mutation.busy}>{mutation.busy ? "Saving…" : "Save issue update"}</button>
  </form>;
}

function RequestDetail({ ticketId, onChange }: { ticketId: string; onChange: () => void }) {
  const [issues, setIssues] = useState<Issues | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    const load = () => workflowRequest(`/v1/maintenance-tickets/${ticketId}/issues`).then(data => { if (active) { setIssues(data); setError(""); } }).catch(value => { if (active) setError(message(value)); });
    void load();
    const timer = setInterval(() => void load(), 30000);
    return () => { active = false; clearInterval(timer); };
  }, [ticketId, revision]);
  return <div className={styles.detail}>
    <WorkflowPanel ticketId={ticketId} onChange={() => { onChange(); setRevision(value => value + 1); }} />
    <section className={styles.panel}><h2>Issues in this request</h2>
      {error && <p role="alert" className={styles.error}>{error} <button type="button" onClick={() => setRevision(value => value + 1)}>Retry</button></p>}
      {!issues && !error && <p role="status">Loading issues…</p>}
      {issues?.items.length === 0 && <p>No separate issues recorded yet.</p>}
      {issues?.items.map(issue => <IssueEditor key={`${issue.id}:${issue.version}`} issue={issue} ticketId={ticketId} onChange={data => { setIssues(data); onChange(); }} />)}
    </section>
  </div>;
}

function WorkerEditor({ worker, properties, onChange }: { worker: Worker; properties: Property[]; onChange: () => void }) {
  const [draft, setDraft] = useState(worker);
  const mutation = useMutation();
  async function submit(event: FormEvent) {
    event.preventDefault();
    const { version, approved, accepting_work, service_property_ids, service_categories, availability_note, max_open_jobs } = draft;
    const result = await mutation.save<Worker>(`/v1/maintenance-workers/${worker.id}`, "PATCH", { version, approved, accepting_work, service_property_ids, service_categories, availability_note, max_open_jobs });
    if (result) { setDraft(result); onChange(); }
  }
  return <form className={styles.form} onSubmit={submit}>
    <div><h2>{worker.name}</h2><p>{worker.open_jobs} open jobs · {worker.active ? "Active repair team account" : "No active repair team account"}</p></div>
    {draft.version < worker.version && <p className={styles.warning}>This profile changed since you began editing. <button type="button" onClick={() => setDraft(worker)}>Load latest settings</button></p>}
    <label className={styles.check}><input type="checkbox" checked={draft.approved} onChange={event => setDraft({ ...draft, approved: event.target.checked })} />Approved for repairs</label>
    <label className={styles.check}><input type="checkbox" checked={draft.accepting_work} onChange={event => setDraft({ ...draft, accepting_work: event.target.checked })} />Accepting new work</label>
    <label>Maximum open jobs<input type="number" min={1} max={50} required value={draft.max_open_jobs} onChange={event => setDraft({ ...draft, max_open_jobs: Number(event.target.value) })} /></label>
    <fieldset><legend>Properties served</legend><p className={styles.muted}>No selection means all properties in this organization.</p>{properties.map(property => <label className={styles.check} key={property.id}><input type="checkbox" checked={draft.service_property_ids.includes(property.id)} onChange={event => setDraft({ ...draft, service_property_ids: event.target.checked ? [...draft.service_property_ids, property.id] : draft.service_property_ids.filter(id => id !== property.id) })} />{property.name}</label>)}</fieldset>
    <fieldset><legend>Repair categories</legend><p className={styles.muted}>No selection means all repair categories.</p>{categories.map(category => <label className={styles.check} key={category}><input type="checkbox" checked={draft.service_categories.includes(category)} onChange={event => setDraft({ ...draft, service_categories: event.target.checked ? [...draft.service_categories, category] : draft.service_categories.filter(value => value !== category) })} />{human(category)}</label>)}</fieldset>
    <label>Availability note<textarea maxLength={1000} value={draft.availability_note} onChange={event => setDraft({ ...draft, availability_note: event.target.value })} placeholder="Working hours or upcoming time away" /></label>
    {mutation.error && <p role="alert" className={styles.error}>{mutation.error}</p>}{mutation.notice && <p role="status">{mutation.notice}</p>}
    <button disabled={mutation.busy}>{mutation.busy ? "Saving…" : "Save worker settings"}</button>
  </form>;
}

function ReferencePhoto({ id }: { id: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function download() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await workflowRequest(`/v1/media/${id}/download`);
      for (let attempt = 0; ; attempt++) {
        try {
          const response = await fetch(`${API_BASE}${result.download_url}`, { signal: AbortSignal.timeout(30000) });
          if (!response.ok) throw Object.assign(new Error("The photo could not be downloaded."), { status: response.status });
          const url = URL.createObjectURL(await response.blob());
          const anchor = document.createElement("a");
          anchor.href = url;
          anchor.download = `property-photo-${id}`;
          anchor.click();
          setTimeout(() => URL.revokeObjectURL(url), 1000);
          break;
        } catch (value) {
          const status = (value as { status?: number })?.status;
          if (attempt >= 2 || !(value instanceof TypeError || value instanceof DOMException && value.name === "TimeoutError" || status === 429 || status && status >= 500)) throw value;
          await new Promise(resolve => setTimeout(resolve, 500 * 2 ** attempt));
        }
      }
    } catch (value) { setError(message(value)); }
    finally { setBusy(false); }
  }
  return <div><button type="button" disabled={busy} onClick={() => void download()}>{busy ? "Downloading…" : "Download photo"}</button>{error && <p role="alert" className={styles.error}>{error}</p>}</div>;
}

function KnowledgeEditor({ entry, knowledge, onChange }: { entry: Entry | null; knowledge: Knowledge; onChange: () => void }) {
  const [draft, setDraft] = useState({ property_id: entry?.property_id || "", title: entry?.title || "", problem_key: entry?.problem_key || "sink", model: entry?.model || "", part_details: entry?.part_details || "", instructions: entry?.instructions || "", verified: entry?.verified || false, reference_media_ids: entry?.reference_media_ids || [] });
  const [saved, setSaved] = useState(entry);
  const mutation = useMutation();
  async function submit(event: FormEvent) {
    event.preventDefault();
    const { property_id, ...fields } = draft;
    const result = await mutation.save<Entry>(saved ? `/v1/maintenance-knowledge/${saved.id}` : "/v1/maintenance-knowledge", saved ? "PATCH" : "POST", saved ? { ...fields, version: saved.version } : { ...fields, property_id });
    if (result) { setSaved(result); onChange(); }
  }
  async function archive() {
    if (!saved) return;
    const result = await mutation.save<Entry>(`/v1/maintenance-knowledge/${saved.id}`, "PATCH", { version: saved.version, active: false });
    if (result) { setSaved(result); onChange(); }
  }
  return <form className={styles.form} onSubmit={submit}>
    <h2>{saved ? "Edit property guide" : "Add property guide"}</h2>
    <p className={styles.muted}>Record confirmed equipment details and choose a safe instruction. Do not enter access codes, passwords, or repair procedures.</p>
    {saved && !saved.active && <p role="status">This entry is archived. Create a new entry to replace it.</p>}
    {saved && entry && saved.id === entry.id && saved.version < entry.version && <p className={styles.warning}>This guide changed since you began editing. <button type="button" onClick={() => { setSaved(entry); setDraft({ property_id: entry.property_id, title: entry.title, problem_key: entry.problem_key, model: entry.model, part_details: entry.part_details, instructions: entry.instructions, verified: entry.verified, reference_media_ids: entry.reference_media_ids }); }}>Load latest guide</button></p>}
    <label>Property<select required disabled={Boolean(saved)} value={draft.property_id} onChange={event => setDraft({ ...draft, property_id: event.target.value, reference_media_ids: [], verified: false })}><option value="">Choose a property</option>{knowledge.properties.map(property => <option key={property.id} value={property.id}>{property.name}</option>)}</select></label>
    <label>Equipment name<input required maxLength={120} value={draft.title} onChange={event => setDraft({ ...draft, title: event.target.value, verified: false })} placeholder="Kitchen dishwasher" /></label>
    <label>Related problem<select value={draft.problem_key} onChange={event => setDraft({ ...draft, problem_key: event.target.value, verified: false })}>{(knowledge.problem_keys || problems).map(problem => <option key={problem} value={problem}>{human(problem)}</option>)}</select></label>
    <label>Model<input maxLength={120} value={draft.model} onChange={event => setDraft({ ...draft, model: event.target.value, verified: false })} placeholder="Manufacturer and model identifier" /></label>
    <label>Part details<input maxLength={300} value={draft.part_details} onChange={event => setDraft({ ...draft, part_details: event.target.value, verified: false })} placeholder="Filter dimensions or part identifier" /></label>
    <label>Approved instruction<select required value={draft.instructions} onChange={event => setDraft({ ...draft, instructions: event.target.value, verified: false })}><option value="">Choose an instruction</option>{knowledge.approved_instructions.map(instruction => <option key={instruction} value={instruction}>{instruction}</option>)}</select></label>
    <fieldset><legend>Control photos from requests</legend><p className={styles.muted}>Choose up to six existing photos from this property that support the equipment details.</p>{knowledge.reference_media.filter(media => media.property_id === draft.property_id).length === 0 && <p className={styles.muted}>No eligible photos for this property.</p>}{knowledge.reference_media.filter(media => media.property_id === draft.property_id).map(media => <div className={styles.photo} key={media.id}><label className={styles.check}><input type="checkbox" checked={draft.reference_media_ids.includes(media.id)} disabled={!draft.reference_media_ids.includes(media.id) && draft.reference_media_ids.length >= 6} onChange={event => setDraft({ ...draft, verified: false, reference_media_ids: event.target.checked ? [...draft.reference_media_ids, media.id] : draft.reference_media_ids.filter(id => id !== media.id) })} />Photo from {date(media.created_at)} · {media.content_type}</label><ReferencePhoto id={media.id} /></div>)}</fieldset>
    <label className={styles.check}><input type="checkbox" checked={draft.verified} onChange={event => setDraft({ ...draft, verified: event.target.checked })} />I have checked these details for this property.</label>
    {mutation.error && <p role="alert" className={styles.error}>{mutation.error}</p>}{mutation.notice && <p role="status">{mutation.notice}</p>}
    <div className={styles.actions}><button disabled={mutation.busy || saved?.active === false}>{mutation.busy ? "Saving…" : "Save guide"}</button>{saved?.active && <button type="button" className={styles.secondary} disabled={mutation.busy} onClick={() => void archive()}>Archive entry</button>}</div>
  </form>;
}

export default function MaintenanceControlPage() {
  const router = useRouter();
  const [tab, setTab] = useState("Needs attention");
  const [operations, setOperations] = useState<Operations | null>(null);
  const [knowledge, setKnowledge] = useState<Knowledge | null>(null);
  const [error, setError] = useState("");
  const [knowledgeError, setKnowledgeError] = useState("");
  const [forbidden, setForbidden] = useState(false);
  const [revision, setRevision] = useState(0);
  const [knowledgeRevision, setKnowledgeRevision] = useState(0);
  const [selected, setSelected] = useState("");
  const [workerId, setWorkerId] = useState("");
  const [entryId, setEntryId] = useState("");
  const [newEntry, setNewEntry] = useState(0);
  const [search, setSearch] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(true);
  const [showArchived, setShowArchived] = useState(false);
  useEffect(() => {
    let active = true;
    if (!getToken()) { router.replace("/login"); return; }
    workflowRequest("/v1/maintenance-operations").then(data => { if (active) { setOperations(data); setError(""); setForbidden(false); } }).catch(value => { if (active) { setError(message(value)); if ((value as { status?: number })?.status === 403) { setForbidden(true); setOperations(null); setKnowledge(null); } } });
    return () => { active = false; };
  }, [revision, router]);
  useEffect(() => {
    if (!getToken() || forbidden) return;
    let active = true;
    workflowRequest("/v1/maintenance-knowledge").then(data => { if (active) { setKnowledge(data); setKnowledgeError(""); } }).catch(value => { if (active) setKnowledgeError(message(value)); });
    return () => { active = false; };
  }, [knowledgeRevision, forbidden]);
  useEffect(() => {
    const timer = setInterval(() => { if (document.visibilityState === "visible") setRevision(value => value + 1); }, 30000);
    return () => clearInterval(timer);
  }, []);
  const requests = operations?.requests.filter(item => (!attentionOnly || item.reason_codes.length > 0) && `${item.ticket_number} ${item.description} ${item.owner_name || ""} ${item.status}`.toLowerCase().includes(search.toLowerCase())) || [];
  const worker = operations?.workers.find(item => item.id === workerId);
  const entry = knowledge?.entries.find(item => item.id === entryId) || null;
  const background = operations?.background_worker;
  return <main className={styles.desk}>
    <header className={styles.header}><div><p className={styles.eyebrow}>Maintenance</p><h1>Control desk</h1><p>Follow up on repairs and keep property guidance and team availability current.</p></div><nav className={styles.links}><Link href="/maintenance/manage">Request tools</Link><Link href="/maintenance">Tenant view</Link><Link href="/maintenance/jobs">Repairman view</Link></nav></header>
    {error && <div role="alert" className={styles.error}>{forbidden ? "This control desk is for property managers. Use the tenant or repairman view for your account." : error} {!forbidden && <button type="button" onClick={() => setRevision(value => value + 1)}>Retry</button>}</div>}
    {!operations && !error && <p role="status">Loading maintenance operations…</p>}
    {operations && <>
      <div className={styles.health}><div><strong>Background follow-up: {human(background!.status)}</strong><small>Last heartbeat: {date(background!.heartbeat_at)}</small>{background!.last_error_type && <small>Last error: {background!.last_error_type} · {background!.failure_count} failures</small>}</div><div><strong>Phone alerts: {operations.worker_health.phone_configured ? "Configured" : "Not configured"}</strong><small>{operations.worker_health.pending_notifications} pending · {operations.worker_health.failed_notifications} failed · {operations.worker_health.unknown_notifications} delivery unknown</small></div><div><strong>Historical reference: {operations.worker_health.history_configured ? "Configured" : "Not configured"}</strong><small>Delivery and background status are separate from a worker accepting a repair.</small></div></div>
      <div className={styles.tabs} role="tablist" aria-label="Maintenance controls">{["Needs attention", "Property guide", "Repair team"].map(name => <button key={name} type="button" role="tab" aria-selected={tab === name} onClick={() => setTab(name)}>{name}</button>)}</div>
      <section hidden={tab !== "Needs attention"} className={styles.tabPanel}>
        <div className={styles.toolbar}><label>Find a request<input type="search" placeholder="Request number, description, or owner" value={search} onChange={event => setSearch(event.target.value)} /></label><label>Show<select value={attentionOnly ? "attention" : "all"} onChange={event => setAttentionOnly(event.target.value === "attention")}><option value="attention">Needs attention</option><option value="all">All active requests</option></select></label><button type="button" onClick={() => setRevision(value => value + 1)}>Refresh</button></div>
        <div className={styles.columns}><aside className={styles.list} aria-label="Maintenance requests"><p className={styles.muted}>{requests.length} requests · Refreshes every 30 seconds</p>{requests.length === 0 && <p className={styles.panel}>No requests match this view.</p>}{requests.map(item => <button type="button" className={styles.card} key={item.id} aria-pressed={selected === item.id} onClick={() => setSelected(item.id)}><span className={styles.cardTop}>#{item.ticket_number}<span className={item.priority === "ROUTINE" ? styles.badge : styles.urgent}>{human(item.priority)}</span></span><strong>{item.description}</strong><span>{item.owner_name || "No worker assigned"} · {human(item.status)}</span><strong className={styles.next}>{item.next_action}</strong>{item.reason_codes.length > 0 && <span>{item.reason_codes.map(human).join(" · ")}</span>}<small>Notification: {item.notification_status ? human(item.notification_status) : "Not recorded"}</small><small>Last activity: {date(item.last_activity_at)}</small></button>)}</aside><div>{selected ? <RequestDetail key={selected} ticketId={selected} onChange={() => setRevision(value => value + 1)} /> : <div className={styles.empty}><h2>Select a request</h2><p>Review the conversation, next action, and each reported issue.</p></div>}</div></div>
      </section>
      <section hidden={tab !== "Property guide"} className={styles.tabPanel}>
        <div className={styles.toolbar}><h2>Property guide</h2><label className={styles.check}><input type="checkbox" checked={showArchived} onChange={event => setShowArchived(event.target.checked)} />Include archived entries</label><button type="button" onClick={() => { setEntryId(""); setNewEntry(value => value + 1); }}>Add guide</button></div>
        {knowledgeError && <p role="alert" className={styles.error}>{knowledgeError} <button type="button" onClick={() => setKnowledgeRevision(value => value + 1)}>Retry</button></p>}
        {!knowledge && !knowledgeError && <p role="status">Loading property guide…</p>}
        {knowledge && <div className={styles.columns}><aside className={styles.list}>{knowledge.entries.filter(item => showArchived || item.active).length === 0 && <p className={styles.panel}>No property guidance yet. Add equipment details you have checked.</p>}{knowledge.entries.filter(item => showArchived || item.active).map(item => <button type="button" className={styles.card} key={item.id} aria-pressed={entryId === item.id} onClick={() => setEntryId(item.id)}><strong>{item.title}</strong><span>{knowledge.properties.find(property => property.id === item.property_id)?.name}</span><small>{!item.active ? "Archived" : item.verified ? "Verified by a manager" : "Not verified"} · {human(item.problem_key)}</small></button>)}</aside><KnowledgeEditor key={entryId || `new:${newEntry}`} entry={entry} knowledge={knowledge} onChange={() => setKnowledgeRevision(value => value + 1)} /></div>}
      </section>
      <section hidden={tab !== "Repair team"} className={styles.tabPanel}><div className={styles.toolbar}><h2>Repair team</h2><p className={styles.muted}>Availability and coverage guide routing; they do not assign a request.</p></div><div className={styles.columns}><aside className={styles.list}>{operations.workers.length === 0 && <p className={styles.panel}>No worker profiles have been created. Use Request tools to add one.</p>}{operations.workers.map(item => <button type="button" className={styles.card} key={item.id} aria-pressed={workerId === item.id} onClick={() => setWorkerId(item.id)}><strong>{item.name}</strong><span>{item.open_jobs} / {item.max_open_jobs} open jobs</span><small>{!item.approved ? "Not approved" : !item.active ? "No active account" : item.accepting_work ? "Accepting work" : "Unavailable for new work"}</small></button>)}</aside>{worker ? <WorkerEditor key={worker.id} worker={worker} properties={operations.properties} onChange={() => setRevision(value => value + 1)} /> : <div className={styles.empty}><h2>Select a repair worker</h2><p>Set service coverage, capacity, and availability.</p></div>}</div></section>
    </>}
  </main>;
}
