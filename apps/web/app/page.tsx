import Link from "next/link";

export default function HomePage() {
  return (
    <>
      <h1>Grok Bot</h1>
      {process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" ? (
        <ol>
          <li>Sign in as Accounting and open Receipts. The fixture check is in custody and is not available.</li>
          <li>Sign in as Tenant and open Maintenance. Report a drip, then send a gas follow-up. Nothing is contacted.</li>
          <li>Sign in as Prospect and open Prequalification. Leave the income period blank, then evaluate. A manager records the exception. No housing decision is made.</li>
        </ol>
      ) : null}
      <p>This shell talks to the API only. It does not open the database.</p>
      <p>
        <Link href="/login">Sign in</Link>
        {" · "}
        <Link href="/accounting">Receipts</Link>
        {" · "}
        <Link href="/maintenance">Maintenance</Link>
        {" · "}
        <Link href="/prequalification">Prequalification</Link>
        {" · "}
        <Link href="/distributions">Distributions</Link>
        {" · "}
        <Link href="/statements">Statements</Link>
      </p>
    </>
  );
}
