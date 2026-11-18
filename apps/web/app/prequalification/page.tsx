"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "../../lib/api";

type Prospect = { id: string; disclosure: string; property_id: string | null };
type Listing = { id: string; property_id: string; display_label: string; asking_rent_cents: number };
type Intake = { questions: string[]; income_monthly_cents: number | null };
type Evaluation = { result: string; final_denial: boolean; formal_screening_permitted: boolean; missing_fields: string[]; configuration_code: string | null };
type Slot = { resource_id: string; starts_at: string; ends_at: string; timezone: string };
type Hold = { id: string; status: string; timezone: string; external_event_created: boolean };

const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const fieldNames: Record<string, string> = { household_income: "Household income", income_period: "Income period", lease_months: "Lease length", move_in_date: "Move-in date", occupant_count: "Number of occupants" };

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const read = !init.method || init.method === "GET";
  for (let attempt = 0; attempt < (read ? 3 : 1); attempt++) {
    let response: Response;
    try {
      response = await api(path, { ...init, signal: AbortSignal.timeout(15000) });
    } catch {
      if (!read || attempt === 2) throw new Error("We couldn't confirm the result. Please try again.");
      await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
      continue;
    }
    if (read && (response.status === 429 || response.status >= 500) && attempt < 2) {
      await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
      continue;
    }
    const body = await response.json();
    if (!response.ok) throw new Error(body.error?.message ?? "Your request could not be completed.");
    return body as T;
  }
  throw new Error("Your request could not be completed.");
}

export default function PrequalificationPage() {
  const router = useRouter();
  const [prospect, setProspect] = useState<Prospect | null>(null);
  const [listing, setListing] = useState<Listing | null>(null);
  const [income, setIncome] = useState("");
  const [period, setPeriod] = useState("");
  const [questions, setQuestions] = useState<string[]>([]);
  const [monthly, setMonthly] = useState<number | null>(null);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [slots, setSlots] = useState<Slot[]>([]);
  const [slotsLoaded, setSlotsLoaded] = useState(false);
  const [hold, setHold] = useState<Hold | null>(null);
  const [error, setError] = useState("");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  const [moveInDate, setMoveInDate] = useState("");
  const [leaseMonths, setLeaseMonths] = useState("12");
  const [occupants, setOccupants] = useState("");
  const [pets, setPets] = useState(false);
  const [assistanceAnimal, setAssistanceAnimal] = useState(false);
  const [rentalHistory, setRentalHistory] = useState("");

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setReady(true);
  }, [router]);

  async function perform(action: () => Promise<void>) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Your request could not be completed.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }

  function incomeCents() {
    if (!/^\d+(\.\d{1,2})?$/.test(income)) throw new Error("Enter household income in dollars, with up to two decimal places.");
    const [dollars, cents = ""] = income.split(".");
    const amount = Number(dollars) * 100 + Number(cents.padEnd(2, "0"));
    if (!Number.isSafeInteger(amount)) throw new Error("The income amount is too large.");
    return amount;
  }

  function start() {
    void perform(async () => {
      const available = await request<{ items: Listing[] }>("/v1/listings");
      if (!available.items.length) throw new Error("There are no available listings right now.");
      const selected = available.items[0];
      const created = await request<Prospect>("/v1/prospects", { method: "POST", body: JSON.stringify({ listing_id: selected.id }) });
      setListing(selected);
      setProspect(created);
    });
  }

  function saveIncome() {
    if (!prospect) return;
    void perform(async () => {
      const saved = await request<Intake>(`/v1/prospects/${prospect.id}/intake`, { method: "PATCH", body: JSON.stringify({ income_original_cents: incomeCents(), income_period: period || null }) });
      setQuestions(saved.questions);
      setMonthly(saved.income_monthly_cents);
    });
  }

  function evaluate(event: FormEvent) {
    event.preventDefault();
    if (!prospect) return;
    void perform(async () => {
      const saved = await request<Intake>(`/v1/prospects/${prospect.id}/intake`, {
        method: "PATCH",
        body: JSON.stringify({ move_in_date: moveInDate, lease_months: Number(leaseMonths), income_original_cents: incomeCents(), income_period: period || null, occupant_count: Number(occupants), pets_declared: pets, assistance_animal_requested: assistanceAnimal, rental_history: rentalHistory }),
      });
      setQuestions(saved.questions);
      setMonthly(saved.income_monthly_cents);
      setEvaluation(await request<Evaluation>(`/v1/prospects/${prospect.id}/evaluate`, { method: "POST" }));
    });
  }

  function loadSlots() {
    if (!listing) return;
    void perform(async () => {
      const available = await request<{ items: Slot[] }>(`/v1/tour-slots?property_id=${listing.property_id}`);
      setSlots(available.items);
      setSlotsLoaded(true);
    });
  }

  function requestHold(slot: Slot) {
    if (!prospect || !listing) return;
    void perform(async () => {
      setHold(await request<Hold>("/v1/appointments/holds", { method: "POST", body: JSON.stringify({ prospect_id: prospect.id, property_id: listing.property_id, resource_id: slot.resource_id, local_start: slot.starts_at, timezone: slot.timezone }) }));
    });
  }

  const resultTitle = evaluation?.result === "HUMAN_REVIEW" ? "Ready for manager review" : evaluation?.result === "PRELIMINARILY_QUALIFIED" ? "Ready for the next step" : "A few details need attention";

  return (
    <div className="prequalification">
      <nav className="pq-breadcrumb" aria-label="Breadcrumb"><Link href="/">Home</Link><span aria-hidden="true">/</span><span>Leasing</span></nav>
      <header className="pq-header">
        <div><h1>Prequalification</h1><p>Tell us about your household and when you’d like to move.</p></div>
        <button type="button" className="secondary-button" disabled={busy} onClick={() => { clearToken(); router.push("/login"); }}>Sign out</button>
      </header>
      {error ? <p className="alert" role="alert">{error}</p> : null}
      <div className="pq-layout">
        <div className="pq-main">
          {!prospect ? <section className="pq-intro">
            <span className="pq-section-number">BEFORE YOUR TOUR</span>
            <h2>Your rental inquiry</h2>
            <p>Share your move-in plans, household income, and rental history so the property manager can review your inquiry.</p>
            <dl className="pq-overview"><div><dt>Your plans</dt><dd>Move-in date and lease length</dd></div><div><dt>Your household</dt><dd>Occupants, income, and pets</dd></div><div><dt>Your history</dt><dd>Previous rentals, if applicable</dd></div></dl>
            <button type="button" onClick={start} disabled={!ready || busy}>{busy ? "Opening your form…" : "Start intake"}<span aria-hidden="true"> →</span></button>
          </section> : <form className="pq-form" onSubmit={evaluate} onChange={() => setEvaluation(null)} aria-busy={busy}>
            <fieldset disabled={busy}>
              <legend><span className="pq-section-number">01</span>Your plans</legend>
              <p className="pq-section-description">When are you hoping to make your next move?</p>
              <div className="pq-fields">
                <label>Desired move-in date<input type="date" value={moveInDate} onChange={(event) => setMoveInDate(event.target.value)} required /></label>
                <label>Lease duration (months)<input type="number" min="1" step="1" value={leaseMonths} onChange={(event) => setLeaseMonths(event.target.value)} required /></label>
              </div>
            </fieldset>
            <fieldset disabled={busy}>
              <legend><span className="pq-section-number">02</span>Your household</legend>
              <p className="pq-section-description">Include everyone who would live in the home.</p>
              <div className="pq-fields pq-household-fields">
                <label>Number of occupants<input type="number" min="1" step="1" value={occupants} onChange={(event) => setOccupants(event.target.value)} placeholder="e.g. 2" required /></label>
                <label>Household income (USD)<input inputMode="decimal" value={income} onChange={(event) => { setIncome(event.target.value); setMonthly(null); }} placeholder="4500.00" aria-describedby="pq-income-help" required /></label>
                <label>Income period<select value={period} onChange={(event) => { setPeriod(event.target.value); setMonthly(null); }} required><option value="">Choose a period</option><option value="weekly">Weekly</option><option value="biweekly">Every two weeks</option><option value="monthly">Monthly</option><option value="annual">Annually</option></select></label>
              </div>
              <p className="pq-field-note" id="pq-income-help">Approximate household income before taxes. Include any lawful sources of income.</p>
              <div className="pq-income-summary"><button type="button" className="pq-text-button" onClick={saveIncome} disabled={!income || busy}>Save income</button>{monthly !== null ? <span role="status">{money.format(monthly / 100)} per month, based on your entry</span> : null}</div>
              <div className="pq-checks">
                <label><input type="checkbox" checked={pets} onChange={(event) => setPets(event.target.checked)} /><span>I have pets</span></label>
                <label><input type="checkbox" checked={assistanceAnimal} onChange={(event) => setAssistanceAnimal(event.target.checked)} /><span>I’d like a private review of an assistance-animal request<small>Handled separately from pet information.</small></span></label>
              </div>
            </fieldset>
            <fieldset disabled={busy}>
              <legend><span className="pq-section-number">03</span>Rental history</legend>
              <p className="pq-section-description">A short summary is enough for this first step.</p>
              <label><span>Previous rentals <span className="pq-optional">Optional</span></span><textarea value={rentalHistory} onChange={(event) => setRentalHistory(event.target.value)} placeholder="Previous addresses and tenancy dates, or let us know this would be your first rental." /></label>
            </fieldset>
            {questions.length && !period ? <div className="pq-follow-up" role="status"><strong>Choose an income period</strong><p>Let us know whether that amount is weekly, every two weeks, monthly, or annual.</p></div> : null}
            <div className="pq-form-footer"><p>A property manager reviews exceptions and final housing decisions.</p><button type="submit" disabled={busy}>{busy ? "Saving your details…" : "Submit for review"}<span aria-hidden="true"> →</span></button></div>
          </form>}
          {evaluation ? <section className="pq-result" role="status"><span className="pq-section-number">YOUR INQUIRY</span><h2>{resultTitle}</h2><p>{evaluation.final_denial ? "A final decision has been recorded. Contact the property manager for details." : "This is a preliminary review, not a final housing decision."}</p>{evaluation.missing_fields.length ? <p>Please check: {evaluation.missing_fields.map((field) => fieldNames[field] ?? field.replaceAll("_", " ")).join(", ")}.</p> : null}<p>{evaluation.formal_screening_permitted ? "Formal screening can be arranged separately." : "Formal screening has not been started."}</p></section> : null}
          {prospect && listing ? <section className="pq-tours"><div className="pq-tours-header"><div><h2>Plan a visit</h2><p>Explore available times for a tour.</p></div><button type="button" className="secondary-button" disabled={busy} onClick={loadSlots}>{slotsLoaded ? "Refresh times" : "Show tour slots"}</button></div>
            {slotsLoaded && !slots.length ? <p>No tour times are available right now. Please check back later.</p> : null}
            {slots.length ? <ul className="pq-slot-list">{slots.map((slot) => <li key={`${slot.resource_id}:${slot.starts_at}`}><time dateTime={slot.starts_at}>{new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: slot.timezone, timeZoneName: "short" }).format(new Date(slot.starts_at))}</time><button type="button" className="secondary-button" disabled={busy || !!hold} onClick={() => requestHold(slot)}>Request this time</button></li>)}</ul> : null}
            {hold ? <div className="pq-hold" role="status"><strong>{hold.status === "HELD" ? "Tour time held" : hold.status.replaceAll("_", " ")}</strong><p>{hold.external_event_created ? "A calendar invitation has been created." : "This is a local hold. No calendar invitation has been sent."}</p></div> : null}
          </section> : null}
        </div>
        <aside className="pq-aside">
          {listing ? <div className="pq-property"><span className="pq-section-number">YOUR INQUIRY</span><h2>{listing.display_label}</h2><p>{money.format(listing.asking_rent_cents / 100)} <span>/ month</span></p></div> : null}
          <div className="pq-next"><h2>What happens next</h2><ol><li><strong>Share your details</strong><span>Complete this short introduction.</span></li><li><strong>Manager review</strong><span>A person handles exceptions and final decisions.</span></li><li><strong>Arrange a tour</strong><span>Find a time to see the home.</span></li></ol></div>
          <div className="pq-privacy"><h2>Before you submit</h2><p>No credit or background report is ordered at this stage. Income is self-reported and has not been verified.</p>{prospect ? <details><summary>About prequalification</summary><p>{prospect.disclosure}</p></details> : null}</div>
        </aside>
      </div>
    </div>
  );
}
