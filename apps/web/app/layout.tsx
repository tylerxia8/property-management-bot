import type { ReactNode } from "react";
import "./globals.css";
import WorkspaceShell from "./workspace-shell";

export const metadata = {
  title: "Grok Bot · Property workspace",
  description:
    "A clear workspace for rent, residents, maintenance, and owner records.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a className="skip-link" href="#main">
          Skip to content
        </a>
        <WorkspaceShell
          demo={process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample"}
        >
          {children}
        </WorkspaceShell>
      </body>
    </html>
  );
}
