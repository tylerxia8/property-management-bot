"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { api, setToken } from "../../lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [subject, setSubject] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

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
      {error ? (
        <p className="alert" role="alert">
          {error}
        </p>
      ) : null}
    </>
  );
}
