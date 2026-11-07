"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "../../lib/api";

type Prospect = { id: string; disclosure: string; property_id: string | null };
type Evaluation = {
  result: string;
  final_denial: boolean;
  formal_screening_permitted: boolean;
  missing_fields: string[];
  configuration_code: string | null;
};
type Slot = { resource_id: string; starts_at: string; ends_at: string; timezone: string };
type Hold = { id: string; status: string; timezone: string; external_event_created: boolean };

export default function PrequalificationPage() {
  const router = useRouter();
  const [prospect, setProspect] = useState<Prospect | null>(null);
  const [propertyId, setPropertyId] = useState("");
  const [income, setIncome] = useState("100000");
  const [period, setPeriod] = useState("");
  const [questions, setQuestions] = useState<string[]>([]);
  const [monthly, setMonthly] = useState<number | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [hold, setHold] = useState<Hold | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [moveInDate, setMoveInDate] = useState(() => new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10));
  const [leaseMonths, setLeaseMonths] = useState("12");
  const [occupants, setOccupants] = useState("1");
  const [pets, setPets] = useState(false);
  const [assistanceAnimal, setAssistanceAnimal] = useState(false);
  const [rentalHistory, setRentalHistory] = useState("Prior tenancy dates only.");

  useEffect(() => {
    setReady(true);
    if (!getToken()) router.replace("/login");
  }, [router]);

  async function start(event: FormEvent) {
    event.preventDefault();
    setError("");
    const listings = await api("/v1/listings");
    const listingBody = await listings.json();
    if (!listings.ok || !listingBody.items?.length) {
      setError(listingBody.error?.message ?? "No listing is available.");
      return;
    }
    const listing = listingBody.items[0];
    const response = await api("/v1/prospects", {
      method: "POST",
      body: JSON.stringify({ listing_id: listing.id }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Intake did not start.");
      return;
    }
    setProspect(body);
    setPropertyId(listing.property_id);
  }

  async function saveIncome(event: FormEvent) {
    event.preventDefault();
    if (!prospect) return;
    setError("");
    const payload: { income_original_cents: number; income_period: string | null } = {
      income_original_cents: Number(income),
      income_period: period || null,
    };
    const response = await api(`/v1/prospects/${prospect.id}/intake`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Income was not saved.");
      return;
    }
    setQuestions(body.questions);
    setMonthly(body.income_monthly_cents);
  }

  async function evaluate(event: FormEvent) {
    event.preventDefault();
    if (!prospect) return;
    setError("");
    const saved = await api(`/v1/prospects/${prospect.id}/intake`, {
      method: "PATCH",
      body: JSON.stringify({
        move_in_date: moveInDate,
        lease_months: Number(leaseMonths),
        income_original_cents: Number(income),
        income_period: period || null,
        occupant_count: Number(occupants),
        pets_declared: pets,
        assistance_animal_requested: assistanceAnimal,
        rental_history: rentalHistory,
      }),
    });
    if (!saved.ok) {
      const body = await saved.json();
      setError(body.error?.message ?? "Intake details were not saved; evaluation has not run.");
      return;
    }
    const response = await api(`/v1/prospects/${prospect.id}/evaluate`, { method: "POST" });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Evaluation did not run.");
      return;
    }
    setEvaluation(body);
  }

  async function loadSlots() {
    if (!propertyId) return;
    const response = await api(`/v1/tour-slots?property_id=${propertyId}`);
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Slots are unavailable.");
      return;
    }
    setSlots(body.items);
  }

  async function requestHold(slot: Slot) {
    if (!prospect) return;
    setError("");
    const response = await api("/v1/appointments/holds", {
      method: "POST",
      body: JSON.stringify({
        prospect_id: prospect.id,
        property_id: propertyId,
        resource_id: slot.resource_id,
        local_start: slot.starts_at,
        timezone: slot.timezone,
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "The hold was not created.");
      return;
    }
    setHold(body);
  }

  return (
    <>
      <p>
        <Link href="/">Home</Link>
      </p>
      <div className="row">
        <h1>Prequalification</h1>
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
      <p>This page does not order a consumer report and does not send a calendar invitation.</p>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {prospect ? <p>{prospect.disclosure}</p> : null}
      {ready && !prospect ? (
        <form onSubmit={start}>
          <button type="submit">Start intake</button>
        </form>
      ) : null}
      {prospect ? (
        <form onSubmit={saveIncome}>
          <label>
            Household income in cents
            <input value={income} onChange={(event) => setIncome(event.target.value)} />
          </label>
          <label>
            Income period
            <input value={period} onChange={(event) => setPeriod(event.target.value)} placeholder="Leave blank to show the missing-period question" />
          </label>
          <button type="submit">Save income</button>
        </form>
      ) : null}
      {questions.length ? (
        <ul>
          {questions.map((question) => (
            <li key={question}>{question}</li>
          ))}
        </ul>
      ) : null}
      {monthly === null && questions.length ? <p>Monthly income was not calculated and was not treated as zero.</p> : null}
      {prospect ? (
        <form onSubmit={evaluate}>
          <p>Review these example details before evaluating. Income remains self-reported and unverified.</p>
          <label>Desired move-in date<input type="date" value={moveInDate} onChange={event => setMoveInDate(event.target.value)} required /></label>
          <label>Lease duration (months)<input type="number" min="1" value={leaseMonths} onChange={event => setLeaseMonths(event.target.value)} required /></label>
          <label>Occupant count<input type="number" min="1" value={occupants} onChange={event => setOccupants(event.target.value)} required /></label>
          <label><input type="checkbox" checked={pets} onChange={event => setPets(event.target.checked)} />Pets declared</label>
          <label><input type="checkbox" checked={assistanceAnimal} onChange={event => setAssistanceAnimal(event.target.checked)} />Request private assistance-animal review</label>
          <label>Relevant rental history<textarea value={rentalHistory} onChange={event => setRentalHistory(event.target.value)} /></label>
          <button type="submit">Evaluate</button>
        </form>
      ) : null}
      {evaluation ? (
        <section>
          <h2>Result {evaluation.result}</h2>
          <p>{evaluation.final_denial ? "Final denial recorded." : "This is not a final denial or a housing decision."}</p>
          <p>Formal screening permitted: {String(evaluation.formal_screening_permitted)}</p>
        </section>
      ) : null}
      {prospect && propertyId ? (
        <button type="button" onClick={() => void loadSlots()}>
          Show tour slots
        </button>
      ) : null}
      {slots.length ? (
        <ul>
          {slots.map((slot) => (
            <li key={slot.starts_at}>
              {slot.starts_at} ({slot.timezone}){" "}
              <button type="button" onClick={() => void requestHold(slot)}>
                Request hold
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {hold ? (
        <p>
          Hold {hold.status} in {hold.timezone}. External calendar event was {hold.external_event_created ? "created" : "not created"}.
        </p>
      ) : null}
    </>
  );
}
