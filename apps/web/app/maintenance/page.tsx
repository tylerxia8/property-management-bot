"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "../../lib/api";

type Ticket = {
  id: string;
  ticket_number: number;
  status: string;
  emergency: boolean;
  next_questions: string[];
  safety_message: string | null;
  model_adapter: string;
};

export default function MaintenancePage() {
  const router = useRouter();
  const [description, setDescription] = useState("");
  const [followUp, setFollowUp] = useState("");
  const [ticket, setTicket] = useState<Ticket | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!getToken()) router.replace("/login");
  }, [router]);

  async function report(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await api("/v1/maintenance-tickets", {
      method: "POST",
      body: JSON.stringify({ description }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "The report was not saved.");
      return;
    }
    setTicket(body);
  }

  async function sendFollowUp(event: FormEvent) {
    event.preventDefault();
    if (!ticket) return;
    setError("");
    const response = await api(`/v1/maintenance-tickets/${ticket.id}/messages`, {
      method: "POST",
      body: JSON.stringify({ body: followUp }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "The follow-up was not saved.");
      return;
    }
    setTicket(body);
    setFollowUp("");
  }

  return (
    <>
      <p>
        <Link href="/">Home</Link>
      </p>
      <div className="row">
        <h1>Maintenance</h1>
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
        Questions come from reviewed templates. The model adapter is disabled. This screen does not contact emergency
        services or send a message to a contractor.
      </p>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      <form onSubmit={report}>
        <label>
          What needs attention?
          <textarea value={description} onChange={(event) => setDescription(event.target.value)} required />
        </label>
        <button type="submit">Report issue</button>
      </form>
      {ticket ? (
        <section>
          <h2>Ticket {ticket.ticket_number}</h2>
          <p>Status: {ticket.status}</p>
          <p>Model adapter: {ticket.model_adapter}</p>
          {ticket.safety_message ? <p>{ticket.safety_message}</p> : null}
          {ticket.next_questions.length ? (
            <ul>
              {ticket.next_questions.map((question) => (
                <li key={question}>{question}</li>
              ))}
            </ul>
          ) : (
            <p>No further template questions on this turn.</p>
          )}
          <form onSubmit={sendFollowUp}>
            <label>
              Follow-up
              <textarea value={followUp} onChange={(event) => setFollowUp(event.target.value)} required />
            </label>
            <button type="submit">Send follow-up</button>
          </form>
        </section>
      ) : null}
    </>
  );
}
