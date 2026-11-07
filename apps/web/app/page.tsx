import Link from "next/link";

export default function HomePage() {
  return (
    <>
      <h1>Grok Bot</h1>
      <p>This shell talks to the API only. It does not open the database.</p>
      <p>
        <Link href="/login">Sign in</Link>
        {" · "}
        <Link href="/accounting">Receipts</Link>
        {" · "}
        <Link href="/maintenance">Maintenance</Link>
        {" · "}
        <Link href="/prequalification">Prequalification</Link>
      </p>
    </>
  );
}
