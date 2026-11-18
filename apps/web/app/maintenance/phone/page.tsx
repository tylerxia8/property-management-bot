"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, API_BASE, getToken } from "../../../lib/api";
import styles from "./phone.module.css";

type PhoneEvent = {
  id: string;
  channel: "SMS" | "VOICEMAIL";
  direction: "INBOUND" | "OUTBOUND";
  recipient_kind: "RESIDENT" | "MAINTENANCE";
  body: string;
  from_number: string;
  to_number: string;
  ticket_id: string;
  ticket_number: number;
  status: string;
  created_at: string;
};
type Inbox = {
  mode: "simulated" | "twilio";
  configured: boolean;
  phone_number: string | null;
  simulation_enabled: boolean;
  maintenance_number: string | null;
  events: PhoneEvent[];
};
type Attachment = {
  file: File;
  key: string;
  slot?: { id: string; upload_url: string; required_headers: Record<string, string> };
  uploaded?: boolean;
};

async function read(path: string, init: RequestInit = {}) {
  const safe = !init.method || init.method === "GET" || new Headers(init.headers).has("Idempotency-Key");
  for (let attempt = 0; ; attempt++) {
    try {
      const response = await api(path, { ...init, signal: AbortSignal.timeout(60000) });
      if (safe && attempt < 2 && (response.status === 429 || response.status >= 500)) {
        await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
        continue;
      }
      const result = await response.json();
      if (!response.ok) throw new Error(result.error?.message || "The request could not be completed. Please retry.");
      return result;
    } catch (error) {
      if (safe && attempt < 2 && (error instanceof TypeError || error instanceof DOMException && error.name === "TimeoutError")) {
        await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
        continue;
      }
      throw error;
    }
  }
}

export default function MaintenancePhone() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [allowed, setAllowed] = useState(false);
  const [photosEnabled, setPhotosEnabled] = useState(false);
  const [inbox, setInbox] = useState<Inbox | null>(null);
  const [channel, setChannel] = useState<"SMS" | "VOICEMAIL">("SMS");
  const [number, setNumber] = useState("+15550100101");
  const [body, setBody] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const [selected, setSelected] = useState("");
  const [reply, setReply] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saved, setSaved] = useState<PhoneEvent | null>(null);
  const lock = useRef(false);
  const intakeRequest = useRef<{ body: string; key: string } | null>(null);
  const replyRequest = useRef<{ body: string; key: string } | null>(null);

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
        setAllowed(context.can_manage);
        setPhotosEnabled(context.photos_enabled);
        if (context.can_manage) {
          const result = await read("/v1/maintenance-phone");
          if (active) setInbox(result);
        }
      } catch (failure) {
        if (active) setError(failure instanceof Error ? failure.message : "The phone inbox could not load.");
      } finally {
        if (active) setReady(true);
      }
    })();
    return () => { active = false; };
  }, [router]);

  async function run(action: () => Promise<void>) {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Please try again.");
    } finally {
      lock.current = false;
      setBusy(false);
    }
  }

  async function upload(attachment: Attachment, ticketId: string) {
    if (attachment.slot) {
      const ticket = await read(`/v1/maintenance-tickets/${ticketId}`);
      if (ticket.media.some((media: { id: string; status: string }) => media.id === attachment.slot?.id && media.status === "READY")) return;
    }
    const bytes = await attachment.file.arrayBuffer();
    const hash = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", bytes))).map((n) => n.toString(16).padStart(2, "0")).join("");
    const name = attachment.file.name;
    const contentType = /\.mov$/i.test(name) ? "video/quicktime" : /\.mp4$/i.test(name) ? "video/mp4" : /\.hei[cf]$/i.test(name) ? "image/heic" : /\.png$/i.test(name) ? "image/png" : "image/jpeg";
    const slot = await read(`/v1/maintenance-tickets/${ticketId}/media-uploads`, {
      method: "POST",
      headers: { "Idempotency-Key": attachment.key },
      body: JSON.stringify({ filename: name, content_type: contentType, size_bytes: attachment.file.size, sha256: hash }),
    });
    attachment.slot = slot;
    if (!attachment.uploaded) {
      const response = await fetch(`${API_BASE}${slot.upload_url}`, {
        method: "POST", headers: slot.required_headers, body: bytes, signal: AbortSignal.timeout(180000),
      });
      if (!response.ok) throw new Error("Your request is saved, but an attachment did not upload. Retry to finish it.");
      attachment.uploaded = true;
    }
    const result = await read(`/v1/media/${slot.id}/complete`, { method: "POST" });
    if (result.status !== "READY") throw new Error("This attachment was not accepted. Remove it to continue, or retry. Videos must be no longer than two minutes.");
  }

  async function simulate(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      let received = saved;
      if (!received) {
        const payload = JSON.stringify({ channel, from_number: number.trim(), body: body.trim() });
        if (intakeRequest.current?.body !== payload) intakeRequest.current = { body: payload, key: crypto.randomUUID() };
        received = await read("/v1/maintenance-phone/simulate", {
          method: "POST", headers: { "Idempotency-Key": intakeRequest.current.key }, body: payload,
        }) as PhoneEvent;
        setSaved(received);
        setSelected(received.ticket_id);
      }
      for (const attachment of attachments) {
        await upload(attachment, received.ticket_id);
        setAttachments((old) => old.filter((item) => item.key !== attachment.key));
      }
      setSaved(null);
      setBody("");
      intakeRequest.current = null;
      setNotice(`Simulated ${channel === "SMS" ? "text" : "voicemail transcript"} saved as request #${received.ticket_number}. No external message was sent.`);
      setInbox(await read("/v1/maintenance-phone"));
    });
  }

  async function sendReply(event: FormEvent) {
    event.preventDefault();
    await run(async () => {
      const payload = JSON.stringify({ ticket_id: selected, body: reply.trim() });
      if (replyRequest.current?.body !== payload) replyRequest.current = { body: payload, key: crypto.randomUUID() };
      const result: PhoneEvent = await read("/v1/maintenance-phone/replies", {
        method: "POST", headers: { "Idempotency-Key": replyRequest.current.key }, body: payload,
      });
      setReply("");
      replyRequest.current = null;
      setNotice(result.status === "SIMULATED" ? "Reply saved in the simulated conversation. No external message was sent." : "Reply queued for the phone provider. Check its delivery status in the inbox.");
      setInbox(await read("/v1/maintenance-phone"));
    });
  }

  const threads = Array.from(new Map((inbox?.events || []).map((event) => [event.ticket_id, event])).values());
  const events = (inbox?.events || []).filter((event) => !selected || event.ticket_id === selected);
  const canReply = (inbox?.events || []).some((event) => event.ticket_id === selected && event.direction === "INBOUND" && event.from_number !== "anonymous");
  const simulated = inbox?.mode === "simulated";
  const simulationEnabled = inbox?.simulation_enabled === true;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div><p className={styles.eyebrow}>RESIDENT COMMUNICATIONS</p><h1>Maintenance phone</h1><p>Texts, voicemail transcripts, and the requests they start.</p></div>
        <Link href="/maintenance/manage">Open maintenance queue ↗</Link>
      </header>
      {error && <p role="alert" className={styles.error}>{error}</p>}
      {notice && <p role="status" className={styles.notice}>{notice}</p>}
      {!ready ? <p role="status">Loading phone inbox…</p> : !allowed ? <section className={styles.card}><h2>Manager access required</h2><p>Sign in with a manager account to use the maintenance phone inbox.</p><Link href="/maintenance">Go to resident maintenance</Link></section> : !inbox ? <button onClick={() => void run(async () => setInbox(await read("/v1/maintenance-phone")))} disabled={busy}>Retry loading inbox</button> : <>
        <section className={styles.banner}>
          <div><span className={styles.badge}>{simulated ? "SIMULATED PHONE" : "CONNECTED PHONE"}</span><h2>{inbox.phone_number || "Maintenance line"}</h2><p>{simulated ? "Try a resident text or voicemail without connecting a phone provider. Every message is saved here; no external texts or calls are sent." : "Texts and voicemail transcripts arrive here. Replies are queued for delivery; their status appears in the conversation."}</p></div>
          <span className={styles.private}>{simulated ? "Maintenance alerts: simulated" : inbox.maintenance_number ? `Maintenance alerts: ${inbox.maintenance_number}` : "Maintenance alerts: not connected"}</span>
        </section>
        <div className={styles.columns}>
          <section className={styles.card}>
            <h2>Simulate a resident message</h2><p className={styles.muted}>Messages from the same number stay with its open repair. Start with “New:” to report a separate problem. The caller’s home still needs verification.</p>
            <form onSubmit={simulate}>
              <fieldset disabled={busy || !simulationEnabled || !!saved} className={styles.fields}>
                <label>Message type<select value={channel} onChange={(event) => setChannel(event.target.value as "SMS" | "VOICEMAIL")}><option value="SMS">Text message</option><option value="VOICEMAIL">Voicemail transcript</option></select></label>
                <label>Resident phone number<input type="tel" required pattern="\+[1-9][0-9]{7,14}" value={number} onChange={(event) => setNumber(event.target.value)} /></label>
                <label>{channel === "SMS" ? "Text message" : "Voicemail transcript"}<textarea required maxLength={4000} rows={5} value={body} onChange={(event) => setBody(event.target.value)} placeholder="The kitchen sink is leaking underneath the cabinet. It started this morning." /></label>
                {channel === "VOICEMAIL" && <p className={styles.muted}>Paste the words the resident would leave in a voicemail. This demo does not record or transcribe audio.</p>}
                {photosEnabled && <label>Photos or videos <span className={styles.optional}>(optional)</span><input type="file" multiple accept=".jpg,.jpeg,.png,.heic,.heif,.mp4,.mov" onChange={(event) => {
                  const files = Array.from(event.target.files || []);
                  event.target.value = "";
                  if (attachments.length + files.length > 10) { setError("Choose up to 10 attachments."); return; }
                  if (files.some((file) => !/\.(jpe?g|png|heic|heif|mp4|mov)$/i.test(file.name) || file.size > (/\.(mp4|mov)$/i.test(file.name) ? 200 : 20) * 1024 * 1024)) { setError("Choose JPEG, PNG, HEIC or HEIF photos up to 20 MB, or MP4/MOV videos up to 200 MB."); return; }
                  setError("");
                  setAttachments((old) => [...old, ...files.map((file) => ({ file, key: crypto.randomUUID() }))]);
                }} /><span className={styles.muted}>Up to 10 files. Photos: 20 MB. Videos: 200 MB, two minutes. Saved through the secure request upload flow.</span></label>}
              </fieldset>
              {attachments.length > 0 && <ul className={styles.attachments}>{attachments.map((attachment) => <li key={attachment.key}><span>{attachment.file.name}</span><button type="button" disabled={busy} onClick={() => setAttachments((old) => old.filter((item) => item.key !== attachment.key))}>Remove</button></li>)}</ul>}
              {saved && <p className={styles.notice}>Request #{saved.ticket_number} is saved. Retry to finish the remaining attachments without creating another request.</p>}
              <button disabled={busy || !simulationEnabled || !body.trim()}>{busy ? "Saving…" : saved ? "Finish saved request" : "Simulate incoming message"}</button>
            </form>
          </section>
          <section className={styles.card}>
            <div className={styles.inboxHeading}><h2>Phone inbox</h2><button type="button" disabled={busy} onClick={() => void run(async () => setInbox(await read("/v1/maintenance-phone")))}>Refresh</button></div>
            <label className={styles.filter}>Conversation<select value={selected} onChange={(event) => { setSelected(event.target.value); setReply(""); }}><option value="">All recent activity</option>{threads.map((thread) => <option key={thread.ticket_id} value={thread.ticket_id}>Request #{thread.ticket_number}</option>)}</select></label>
            <div className={styles.events}>
              {events.length === 0 ? <div className={styles.empty}><h3>Your line is quiet</h3><p>Simulate a message to see the resident conversation and its maintenance request here.</p></div> : events.map((event) => <article key={event.id} className={`${styles.message} ${event.direction === "OUTBOUND" ? styles.outbound : ""}`}>
                <div className={styles.messageMeta}><strong>{event.recipient_kind === "MAINTENANCE" ? "Maintenance notification" : event.direction === "OUTBOUND" ? "Text to resident" : event.channel === "SMS" ? "Resident text" : "Voicemail transcript"}</strong><time dateTime={event.created_at}>{new Date(event.created_at).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</time></div>
                <span className={styles.muted}>{event.direction === "OUTBOUND" ? `To ${event.to_number}` : event.from_number}</span><p className={styles.messageBody}>{event.body}</p>
                <div className={styles.messageMeta}><Link href={`/maintenance/manage?ticket=${encodeURIComponent(event.ticket_id)}`}>Request #{event.ticket_number} ↗</Link><span>{event.status.toLowerCase().replaceAll("_", " ")}</span></div>
              </article>)}
            </div>
            <form className={styles.reply} onSubmit={sendReply}><label>Manager reply<textarea rows={3} maxLength={1600} required value={reply} disabled={busy || !canReply || simulated && !simulationEnabled} onChange={(event) => setReply(event.target.value)} placeholder={selected ? "Ask a follow-up question or share an update…" : "Select a conversation to reply…"} /></label><button disabled={busy || !canReply || simulated && !simulationEnabled || !reply.trim()}>{simulated ? "Save simulated text reply" : "Queue text reply"}</button><p className={styles.muted}>{selected && !canReply ? "There is no resident reply number for this request. Open the maintenance request to post an update." : "Replies appear in this inbox and the maintenance request."}</p></form>
          </section>
        </div>
      </>}
    </div>
  );
}
