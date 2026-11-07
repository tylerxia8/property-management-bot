"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../../lib/api";
import { demoDestinations } from "../../lib/demo";

const DEMO_ROLES = [
  ["property_manager", "Property manager"],
  ["accounting_staff", "Accounting"],
  ["tenant", "Tenant"],
  ["prospect", "Prospect"],
  ["owner", "Owner"],
] as const;

export default function LoginPage() {
  const router = useRouter();
  const demo = process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample";
  const [subject, setSubject] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function enterRole(role: string) {
    setError("");
    const response = await api("/v1/demo/session", {
      method: "POST",
      body: JSON.stringify({ role }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "The fixture role was not opened.");
      return;
    }
    setToken(body.token);
    router.push(demoDestinations[role]);
  }

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    const response = await api("/v1/auth/local/login", {
      method: "POST",
      body: JSON.stringify({ subject, password }),
    });
    const body = await response.json();
    if (!response.ok) {
      setError(body.error?.message ?? "Sign-in failed.");
      return;
    }
    setToken(body.token);
    router.push("/properties");
  }

  return (
    <>
      <h1>Sign in</h1>
      <p>
        This sign-in works only when the API is running in development or test.
        It is not production OIDC or MFA.
      </p>
      {demo ? (
        <>
          <p>Choose a fictional role in the fixture sample. Production does not offer these buttons.</p>
          <div className="roles">
            {DEMO_ROLES.map(([role, label]) => (
              <button key={role} type="button" onClick={() => void enterRole(role)}>
                {label}
              </button>
            ))}
          </div>
        </>
      ) : null}
      {demo ? null : (
        <form onSubmit={onSubmit}>
          <label>
            Subject
            <input value={subject} onChange={(event) => setSubject(event.target.value)} autoComplete="username" required />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          <button type="submit">Sign in</button>
        </form>
      )}
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
    </>
  );
}
