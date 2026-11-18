import Link from "next/link";
import DemoEntry from "./demo-entry";
import styles from "./maintenance-shell.module.css";

export default function HomePage() {
  return <section className={styles.landing}>
    <h1>Maintenance</h1>
    <p>Choose a view, or open your <Link href="/workspace">Airbnb workspace</Link>.</p>
    {process.env.NEXT_PUBLIC_DEMO_FIXTURE === "sample" ? <DemoEntry /> : <Link href="/login">Sign in to maintenance</Link>}
  </section>;
}
