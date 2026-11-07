import type { ReactNode } from "react";
import "./globals.css";

export const metadata = {
  title: "Grok Bot",
  description: "Property management foundation shell",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <a href="#main">Skip to content</a>
        <div className="shell">
          <p className="banner">
            Local development shell. Provider submission is disabled.
            This shell does not make a final housing decision.
            Sign-in on this shell is not production OIDC or MFA.
          </p>
          {process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" ? (
            <p className="banner">
              Fixture sample. Cedar Fixture House and Fixture Sample Co are fictional.
              Payment, messaging, and calendar outbound stay off.
              The screening ratio and tour schedule are labeled fixture, not organization rules.
              This demo does not record a final housing decision.
            </p>
          ) : null}
          <main id="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
