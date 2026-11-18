"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken } from "../../../lib/api";
import WorkflowPanel, { workflowRequest } from "../workflow-panel";
import styles from "../workflow.module.css";

type Job = { id: string; ticket_number: number; description: string; home: { property_name: string; unit_label: string } | null; job_status: string; status: string; priority: string; next_step: string; due_flags: string[] };
export default function RepairJobs({ audience = "repairman" }: { audience?: "repairman" | "manager" }) {
  const router = useRouter();
  const fetching = useRef(false);
  const selectedRequest = useRef("");
  const [showPast, setShowPast] = useState(false);
  const [pageCount, setPageCount] = useState(1);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [revision, setRevision] = useState(0);
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
    setLoading(true);
    fetching.current = true;
    setError("");
    (async () => {
      const items: Job[] = [];
      let cursor: string | null = null;
      for (let page = 0; page < pageCount; page++) {
        const result = await workflowRequest(`/v1/maintenance-workflow?view=${showPast ? "past" : "active"}${cursor ? `&before=${encodeURIComponent(cursor)}` : ""}`);
        if (!active) return;
        items.push(...result.items);
        cursor = result.next_cursor;
        if (!cursor) break;
      }
      const requested = new URL(window.location.href).searchParams.get("ticket");
      if (requested && !items.some(item => item.id === requested)) {
        try {
          const detail = await workflowRequest(`/v1/maintenance-tickets/${encodeURIComponent(requested)}/workflow`);
          if (showPast === ["COMPLETED", "CLOSED", "CANCELED"].includes(detail.ticket.status)) items.push({ ...detail.ticket, job_status: detail.assignment?.status || "UNASSIGNED", next_step: showPast ? "reopen" : detail.available_actions.find((action: string) => action !== "message") || "Waiting for the next update", due_flags: detail.follow_up_flags });
        } catch (value) { if ((value as { status?: number }).status !== 404 && (value as { status?: number }).status !== 403) throw value; }
      }
      return { items, next_cursor: cursor };
    })().then(result => {
      if (!active || !result) return;
      setJobs(result.items);
      setNextCursor(result.next_cursor);
      const requested = new URL(window.location.href).searchParams.get("ticket");
      const next = result.items.find((item: Job) => item.id === requested)?.id || result.items[0]?.id || "";
      select(next);
    }).catch(value => { if (active) setError(value instanceof Error ? value.message : "Unable to load repair jobs."); }).finally(() => { if (active) { fetching.current = false; setLoading(false); } });
    return () => { active = false; fetching.current = false; };
  }, [router, revision, showPast, pageCount]);
  useEffect(() => {
    const timer = setInterval(() => { if (!fetching.current && document.visibilityState === "visible") setRevision(value => value + 1); }, 10000);
    return () => clearInterval(timer);
  }, [showPast]);
  function select(id: string) {
    selectedRequest.current = id;
    setSelected(id);
    const url = new URL(window.location.href);
    if (id) url.searchParams.set("ticket", id);
    else url.searchParams.delete("ticket");
    window.history.replaceState(null, "", url);
  }
  const attention: Job[] = [];
  const repairs: Job[] = [];
  for (const job of jobs) {
    if (showPast !== ["COMPLETED", "CLOSED", "CANCELED"].includes(job.status)) continue;
    const active = !showPast;
    const unassigned = ["UNASSIGNED", "DECLINED"].includes(job.job_status) && !["INTAKE_OPEN", "TRIAGE_PENDING", "WAITING_TENANT"].includes(job.status);
    (active && (unassigned || job.priority !== "ROUTINE" || job.due_flags.length > 0) ? attention : repairs).push(job);
  }
  return <section className={styles.board}>
    <header className={styles.heading}><div><h1>{showPast ? "Past repairs" : audience === "manager" ? "Review repairs" : "My repairs"}</h1><p>{showPast ? "Open an earlier conversation or report that a problem has returned." : audience === "manager" ? "Review the problem, reply to the tenant, or pass it to a repairman." : "Your jobs, visits, and conversations."}</p></div><button className={styles.historyToggle} type="button" disabled={loading} aria-pressed={showPast} onClick={() => { select(""); setJobs([]); setPageCount(1); setShowPast(!showPast); }}>{showPast ? "Back to active repairs" : "Past repairs"}</button></header>
    {error && <div className={styles.error} role="alert">{error} <button onClick={() => setRevision(value => value + 1)}>Retry</button></div>}
    {loading && !jobs.length && <p role="status">Loading your repair jobs…</p>}
    {!loading && !error && !jobs.length && <section className={styles.panel}><h2>{showPast ? "No past repairs" : "No repairs waiting"}</h2><p>{showPast ? "Completed and canceled repairs will appear here." : "New requests and your assigned repairs will appear here."}</p><button type="button" onClick={() => setRevision(value => value + 1)}>Refresh repairs</button></section>}
    <div className={styles.layout}>{selected && <WorkflowPanel key={selected} ticketId={selected} audience={audience === "manager" ? undefined : "repairman"} onChange={() => { const id = selected; void workflowRequest(`/v1/maintenance-tickets/${id}/workflow`).then(detail => { if (selectedRequest.current !== id) return; if (showPast && !["COMPLETED", "CLOSED", "CANCELED"].includes(detail.ticket.status)) { setShowPast(false); setPageCount(1); } }).catch(value => { if (selectedRequest.current !== id) return; if ((value as { status?: number }).status === 404) select(""); else setError(value instanceof Error ? value.message : "Unable to refresh this repair."); }).finally(() => { if (selectedRequest.current === id || !selectedRequest.current) setRevision(value => value + 1); }); }} />}{[{ title: "Needs attention", items: attention }, { title: showPast ? "Past repairs" : attention.length ? "Other repairs" : "Repairs", items: repairs }].map(group => group.items.length > 0 && <section key={group.title}><h2 className={styles.repairsHeading}>{group.title}</h2><aside className={styles.jobs} aria-label={group.title}>{group.items.map(job => <button type="button" className={styles.job} key={job.id} aria-pressed={selected === job.id} onClick={() => select(job.id)}><span className={styles.heading}><small>Repair #{job.ticket_number}</small>{job.priority !== "ROUTINE" && !["COMPLETED", "CLOSED", "CANCELED"].includes(job.status) && <span className={styles.urgentBadge}>{job.priority === "EMERGENCY" ? "Emergency" : "Urgent"}</span>}</span><strong>{job.description}</strong><small>{[job.home?.property_name, job.home?.unit_label].filter(Boolean).join(" · ")}</small><strong>{({ assign: "Needs manager review", arrange_repair: "Accept & schedule", complete: "Finish repair", start_work: "Ready to start", confirm_completion: "Waiting for the tenant to check the repair", reopen: "Repair complete", availability: "Waiting for the next update", confirm_visit: "Waiting for the tenant to confirm a visit" } as Record<string, string>)[job.next_step] || job.next_step.replaceAll("_", " ")}</strong>{job.due_flags.length > 0 && <small>Follow-up: {job.due_flags.map(flag => flag.replaceAll("_", " ")).join(", ")}</small>}</button>)}</aside></section>)}{nextCursor && <button className={styles.historyToggle} type="button" disabled={loading} onClick={() => setPageCount(value => value + 1)}>{loading ? "Loading…" : "Load more repairs"}</button>}</div>
  </section>;
}
