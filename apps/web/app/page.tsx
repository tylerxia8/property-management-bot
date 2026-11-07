import Link from "next/link";
import DemoEntry from "./demo-entry";

export default function HomePage() {
  return (
    <>
      <div className="page-intro">
        <p className="eyebrow">PROPERTY OPERATIONS, TOGETHER</p>
        <h1>Your portfolio, in focus.</h1>
        <p>
          A clearer day starts here. Keep rent, leasing, and resident care
          moving in one workspace.
        </p>
      </div>
      {process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" ? <DemoEntry /> : null}
      {process.env.NEXT_PUBLIC_DEMO_FIXTURE !== "sample" ? (
        <p className="quick-links">
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
      ) : null}
    </>
  );
}
