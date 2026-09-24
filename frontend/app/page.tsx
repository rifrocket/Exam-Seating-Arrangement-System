import Link from "next/link";
import styles from "./page.module.css";

export default function Home() {
  return (
    <div className={styles.page}>
      <main className={styles.main}>
        <h1>Exam Seating Arrangement System</h1>
        <p>
          <Link href="/registrations">Go to Registrations →</Link>
        </p>
      </main>
    </div>
  );
}
