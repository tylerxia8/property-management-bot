"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";
import { api, setToken } from "../lib/api";
import Icon, { type IconName } from "./ui/workspace-icon";

const navigation: {
  label: string;
  href: string;
  icon: IconName;
  role?: string;
}[] = [
  { label: "Overview", href: "/", icon: "overview" },
  {
    label: "Rent & accounting",
    href: "/accounting",
    icon: "rent",
    role: "accounting_staff",
  },
  {
    label: "Leasing",
    href: "/prequalification",
    icon: "prospect",
    role: "prospect",
  },
  {
    label: "Maintenance",
    href: "/maintenance",
    icon: "repair",
    role: "tenant",
  },
  {
    label: "Maintenance queue",
    href: "/maintenance/manage",
    icon: "review",
    role: "property_manager",
  },
  {
    label: "Manager reviews",
    href: "/reviews",
    icon: "review",
    role: "property_manager",
  },
  {
    label: "Owner statements",
    href: "/statements",
    icon: "statement",
    role: "owner",
  },
];

export default function WorkspaceShell({
  children,
  demo,
}: {
  children: ReactNode;
  demo: boolean;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const current =
    navigation.find((item) => item.href === pathname)?.label ??
    (pathname.startsWith("/properties")
      ? "Properties"
      : pathname === "/login"
        ? "Choose your workspace"
        : "Distributions");

  async function open(role: string, href: string) {
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
          body.error?.message ?? "The workspace could not be opened.",
        );
      setToken(body.token);
      router.push(href);
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "The workspace is unavailable. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="app-frame">
      <aside className="sidebar">
        <Link className="brand" href="/" aria-label="Grok Bot overview">
          <span className="brand-mark">
            <Icon name="house" />
          </span>
          <span>
            grok<span className="brand-dot">.</span>
            <small>PROPERTY WORKSPACE</small>
          </span>
        </Link>
        <p className="nav-label">WORKSPACE</p>
        <nav className="workspace-nav" aria-label="Main navigation">
          {navigation.map((item) => {
            const active = pathname === item.href;
            const content = (
              <>
                <Icon name={item.icon} />
                <span>{item.label}</span>
                {active ? <span className="nav-indicator" /> : null}
              </>
            );
            return demo && item.role ? (
              <button
                type="button"
                className={`nav-item${active ? " active" : ""}`}
                aria-current={active ? "page" : undefined}
                disabled={busy}
                key={item.href}
                onClick={() => void open(item.role!, item.href)}
              >
                {content}
              </button>
            ) : (
              <Link
                className={`nav-item${active ? " active" : ""}`}
                href={item.href}
                aria-current={active ? "page" : undefined}
                key={item.href}
              >
                {content}
              </Link>
            );
          })}
        </nav>
        <div className="sidebar-bottom">
          {demo ? (
            <div className="sidebar-note">
              <span className="live-dot" /> A little room to explore
              <p>
                Five roles. One fictional property.
                <br />
                Make yourself at home.
              </p>
            </div>
          ) : null}
          <div className="organization">
            <span className="organization-avatar">{demo ? "F" : "G"}</span>
            <span>
              {demo ? "Fixture Sample Co" : "Grok Bot"}
              <small>
                {demo ? "Demo organization" : "Property operations"}
              </small>
            </span>
          </div>
        </div>
      </aside>
      <div className="workspace">
        <header className="workspace-header">
          <div className="breadcrumb">
            <span>Workspace</span>
            <span className="breadcrumb-slash">/</span>
            <strong>{current}</strong>
          </div>
          <span className="workspace-badge">
            <span className="live-dot" />
            {demo ? "Demo workspace" : "Development workspace"}
          </span>
        </header>
        <main className="shell" id="main">
          {error ? (
            <p className="alert" role="alert">
              {error}
            </p>
          ) : null}
          {children}
        </main>
        <footer className="workspace-footer">
          <p className="fixture-notice">
            {demo
              ? "Fixture sample. All data is fictional. Live payments, messaging, and calendars are off."
              : "Development environment. Live provider submission is disabled."}
          </p>
          <details>
            <summary>About this workspace</summary>
            <p>
              Local development shell. Provider submission is disabled. This
              shell does not make a final housing decision. Sign-in on this
              shell is not production OIDC or MFA.
            </p>
            {demo ? (
              <p>
                Cedar Fixture House and Fixture Sample Co are fictional.
                Screening rules and tour schedules are illustrative. Maintenance
                questions use reviewed templates; no AI model or external
                provider is connected.
              </p>
            ) : null}
          </details>
        </footer>
      </div>
    </div>
  );
}
