import Link from "next/link";
import DemoEntry from "./demo-entry";

export default function HomePage() {
  return (
    <>
      <h1>Grok Bot</h1>
      {process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" ? (
        <DemoEntry />
      ) : null}
      <p>Manage rental operations with clear records and human oversight.</p>
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
