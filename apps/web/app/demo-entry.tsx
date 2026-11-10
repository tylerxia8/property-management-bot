"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../lib/api";
import { demoDestinations } from "../lib/demo";
import Icon, { type IconName } from "./ui/workspace-icon";

const scenarios = [
  {
    role: "accounting_staff",
    title: "1. Record rent",
    detail:
      "Record a check and see why received money is different from available funds.",
  },
  {
    role: "prospect",
    title: "2. Prequalify a prospect",
    detail:
      "Collect preliminary information, request human review, and explore tour times.",
  },
  {
    role: "tenant",
    title: "3. Report a repair",
    detail:
      "Describe a leak, answer follow-up questions, and demonstrate emergency escalation.",
  },
  {
    role: "property_manager",
    title: "4. Review as manager",
    detail:
      "Review a prospect exception using the fictional property's sample policy.",
  },
  {
    role: "owner",
    title: "5. View an owner statement",
    detail: "Inspect a fictional ledger snapshot with no bank transfer.",
  },
];

export default function DemoEntry() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function enter(role: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const response = await api("/v1/demo/session", {
        method: "POST",
        body: JSON.stringify({ role }),
      });
      const body = await response.json();
      if (!response.ok)
        throw new Error(
          body.error?.message ?? "The sample could not be opened.",
        );
      setToken(body.token);
      router.push(demoDestinations[role]);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The local demo is unavailable. Start it and try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  const cards: { heading: string; icon: IconName; tag: string }[] = [
    {
      heading: "Every payment, accounted for.",
      icon: "rent",
      tag: "ACCOUNTING",
    },
    {
      heading: "A thoughtful first impression.",
      icon: "prospect",
      tag: "LEASING",
    },
    {
      heading: "Take care of what matters.",
      icon: "repair",
      tag: "RESIDENT CARE",
    },
    {
      heading: "Your judgment stays central.",
      icon: "review",
      tag: "HUMAN OVERSIGHT",
    },
    {
      heading: "Clarity for every owner.",
      icon: "statement",
      tag: "OWNER RECORDS",
    },
  ];
  return (
    <section className="walkthroughs" aria-labelledby="demo-heading">
      <div className="welcome-panel">
        <div>
          <span className="welcome-tag">MEET YOUR WORKSPACE</span>
          <h2>
            Less busywork.
            <br />
            More room for people.
          </h2>
          <p>
            Explore the everyday moments of property management, from the first
            inquiry to the owner statement.
          </p>
          <span className="welcome-caption">
            Fictional property · Real workflows · Human oversight
          </span>
        </div>
        <div className="house-art" aria-hidden="true">
          <svg viewBox="0 0 320 220" fill="none">
            <circle cx="174" cy="105" r="97" fill="#e5c9d0" />
            <path d="M40 195h248" stroke="#947a80" strokeWidth="2" />
            <path d="M89 99l74-59 76 59v95H89z" fill="#fffdf6" />
            <path
              d="M75 101l88-72 90 72"
              stroke="#4e2630"
              strokeWidth="10"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path d="M116 90h28v35h-28zm67 0h28v35h-28z" fill="#d0b7bd" />
            <path d="M149 145h30v49h-30z" fill="#4e2630" />
            <path d="M107 146h26v25h-26zm88 0h26v25h-26z" fill="#d0b7bd" />
            <path
              d="M55 194v-47m0 23c-33-4-23-43-7-33 0-26 38-19 28 7 22 11 2 33-21 26zm216 24v-32"
              stroke="#947a80"
              strokeWidth="3"
            />
            <circle cx="271" cy="149" r="20" fill="#947a80" />
            <path
              d="M135 206h59"
              stroke="#c3acb2"
              strokeWidth="3"
              strokeLinecap="round"
            />
          </svg>
        </div>
      </div>
      <div className="section-heading">
        <div>
          <h2 id="demo-heading">Choose a walkthrough</h2>
          <p>
            Step into a role and explore. Switch roles anytime from the sidebar.
          </p>
        </div>
        <span className="section-count">5 workflows</span>
      </div>
      {error ? (
        <p role="alert" className="alert">
          {error}
        </p>
      ) : null}
      <div className="demo-grid">
        {scenarios.map((scenario, index) => (
          <article className={`demo-card tone-${index}`} key={scenario.role}>
            <div className="card-top">
              <span className="workflow-icon">
                <Icon name={cards[index].icon} />
              </span>
              <span className="workflow-number">0{index + 1}</span>
            </div>
            <p className="eyebrow">{cards[index].tag}</p>
            <h3>{cards[index].heading}</h3>
            <p>{scenario.detail}</p>
            <button
              type="button"
              disabled={busy}
              onClick={() => void enter(scenario.role)}
            >
              <span>{scenario.title}</span>
              <Icon name="arrow" />
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
