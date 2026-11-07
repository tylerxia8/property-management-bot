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
          <main id="main">{children}</main>
        </div>
      </body>
    </html>
  );
}
