"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, clearToken, getToken } from "../../lib/api";

type Review = {
  id: string;
  reason: string;
  prospect_state: string;
  final_housing_decision: boolean;
};

export default function ReviewsPage() {
  const router = useRouter();
  const [items, setItems] = useState<Review[]>([]);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    void load();
  }, [router]);

  async function load() {
    const response = await api("/v1/human-reviews");
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Reviews are unavailable.");
      return;
    }
    setItems(body.items);
    setLoaded(true);
  }

  async function allow(id: string) {
    setError("");
    const response = await api(`/v1/human-reviews/${id}/resolve`, {
      method: "POST",
      body: JSON.stringify({
        resolution: "EXCEPTION",
        reason: "Manager recorded an exception so a tour can be requested.",
      }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "The review was not resolved.");
      return;
    }
    setMessage(
      body.final_housing_decision
        ? "A final housing decision was recorded."
        : "Exception recorded. No final housing decision was recorded.",
    );
    await load();
  }

  return (
    <>
      <p>
        <Link href="/">Home</Link>
      </p>
      <div className="row">
        <h1>Human review</h1>
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
      <p>This queue does not approve or deny housing.</p>
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
      {message ? <p>{message}</p> : null}
      {loaded && items.length === 0 && !error ? (
        <div className="card">
          <h2>A little breathing room.</h2>
          <p>
            There are no pending reviews. New prospect exceptions will appear
            here.
          </p>
        </div>
      ) : null}
      <ul className="review-list">
        {items.map((item) => (
          <li key={item.id}>
            {item.prospect_state}: {item.reason}{" "}
            <button type="button" onClick={() => void allow(item.id)}>
              Record exception
            </button>
          </li>
        ))}
      </ul>
    </>
  );
}
