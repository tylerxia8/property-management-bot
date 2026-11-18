"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";
import { enterDemoRole } from "../lib/demo";
import Icon from "./ui/workspace-icon";
import styles from "./maintenance-shell.module.css";

export default function WorkspaceShell({ children, demo }: { children: ReactNode; demo: boolean }) {
  const pathname = usePathname();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function open(role: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const ticket = new URL(window.location.href).searchParams.get("ticket");
      const destination = await enterDemoRole(role);
      const target = new URL(destination, window.location.origin);
      if (ticket) target.searchParams.set("ticket", ticket);
      if (new URL(window.location.href).searchParams.get("past") === "1") target.searchParams.set("past", "1");
      window.location.assign(target.pathname + target.search);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }
  const views = [{ label: "Tenant view", href: "/maintenance", role: "tenant" }, { label: "Manager view", href: "/maintenance/review", role: "property_manager" }, { label: "Repairman view", href: "/maintenance/jobs", role: "contractor" }];
  return <div className={styles.app}>
    <header className={styles.bar}>
      <Link className={styles.home} href="/" aria-label="Home"><Icon name="house" /></Link>
      <nav className={styles.views} aria-label="Maintenance views">{views.map(view => demo
        ? <button key={view.href} type="button" disabled={busy} aria-current={pathname === view.href ? "page" : undefined} onClick={() => void open(view.role)}>{view.label}</button>
        : <Link key={view.href} href={view.href} onClick={event => {
          const ticket = new URL(window.location.href).searchParams.get("ticket");
          if (!ticket) return;
          event.preventDefault();
          window.location.assign(`${view.href}?ticket=${encodeURIComponent(ticket)}${new URL(window.location.href).searchParams.get("past") === "1" ? "&past=1" : ""}`);
        }} aria-current={pathname === view.href ? "page" : undefined}>{view.label}</Link>)}</nav>
      {demo && <span className={styles.badge}>Demo</span>}
    </header>
    <main id="main" className={styles.content}>{error && <p className={styles.error} role="alert">{error}</p>}{children}</main>
  </div>;
}
