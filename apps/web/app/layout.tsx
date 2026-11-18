import type { ReactNode } from "react";
import "./globals.css";
import WorkspaceShell from "./workspace-shell";

export const metadata = {
  title: "Maintenance",
  description:
    "Report a problem and follow the repair.",
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
