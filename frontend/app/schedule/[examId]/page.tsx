"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ExamDetailOut, fetchExam } from "@/lib/api";
import styles from "../page.module.css";

export default function ExamDetailPage() {
  const params = useParams<{ examId: string }>();
  const examId = Number(params.examId);

  const [exam, setExam] = useState<ExamDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const detail = await fetchExam(examId);
        setExam(detail);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    }
    if (Number.isFinite(examId)) {
      load();
    }
  }, [examId]);

  return (
    <div className={styles.page}>
      <p className={styles.backLink}>
        <Link href="/schedule">← Back to schedule</Link>
      </p>

      {error && (
        <div className={styles.errorBanner} role="alert">
          {error}
        </div>
      )}

      {exam && (
        <>
          <div className={styles.header}>
            <h1>
              {exam.course_code} — {exam.course_name}
            </h1>
            <p>
              {exam.exam_date}
              {exam.day_label ? ` (${exam.day_label})` : ""} · {exam.time_slot}
            </p>
          </div>

          <div className={styles.summaryGrid}>
            <div className={styles.summaryCard}>
              <div className={styles.value}>
                {exam.expected_student_count}
              </div>
              <div className={styles.label}>Expected students</div>
            </div>
            <div className={styles.summaryCard}>
              <div className={styles.value}>{exam.exam_rooms.length}</div>
              <div className={styles.label}>Rooms</div>
            </div>
            <div className={styles.summaryCard}>
              <div className={styles.value}>
                {exam.exam_rooms.reduce(
                  (sum, er) => sum + er.allocated_students,
                  0,
                )}
              </div>
              <div className={styles.label}>Total allocated</div>
            </div>
          </div>

          <section>
            <h2>Rooms and allocations</h2>
            {exam.exam_rooms.length === 0 ? (
              <p className={styles.empty}>No rooms assigned yet.</p>
            ) : (
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th>Room</th>
                    <th>Capacity</th>
                    <th>Allocated students</th>
                  </tr>
                </thead>
                <tbody>
                  {exam.exam_rooms.map((examRoom) => (
                    <tr key={examRoom.id}>
                      <td>{examRoom.room_code}</td>
                      <td>{examRoom.room_capacity}</td>
                      <td>{examRoom.allocated_students}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </section>
        </>
      )}
    </div>
  );
}
