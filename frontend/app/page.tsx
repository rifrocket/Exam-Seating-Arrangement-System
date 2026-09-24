import Link from "next/link";
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>Exam Seating Arrangement System</h1>
        <nav className={styles.nav}>
          <Link href="/registrations">Registrations →</Link>
          <Link href="/rooms">Rooms →</Link>
          <Link href="/schedule">Schedule →</Link>
        </nav>
      </main>
    </div>
  );
}
