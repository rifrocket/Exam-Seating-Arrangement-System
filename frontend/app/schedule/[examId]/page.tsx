"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import {
  ExamDetailOut,
  SeatAssignmentOut,
  SeatingGenerationOut,
  SeatingGenerationResult,
  fetchAssignments,
  fetchExam,
  fetchGenerations,
  generateSeating,
} from "@/lib/api";
import styles from "../page.module.css";

const STATUS_CLASS: Record<SeatingGenerationOut["status"], string> = {
  pending: "",
  success: styles.statusSuccess,
  partial: styles.statusPartial,
  failed: styles.statusFailed,
};

export default function ExamDetailPage() {
  const params = useParams<{ examId: string }>();
  const examId = Number(params.examId);

  const [exam, setExam] = useState<ExamDetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [generations, setGenerations] = useState<SeatingGenerationOut[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [latest, setLatest] = useState<SeatingGenerationResult | null>(null);
  const [assignments, setAssignments] = useState<SeatAssignmentOut[]>([]);

  async function loadExam() {
    try {
      const detail = await fetchExam(examId);
      setExam(detail);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function loadGenerations() {
    try {
      const page = await fetchGenerations(examId);
      setGenerations(page.items);
    } catch {
      // Non-fatal for the page: the exam detail above already surfaces load errors.
    }
  }

  useEffect(() => {
    // Load-on-mount/on-id-change from the backend API — see the same
    // rationale on the Registrations page for why this plain fetch-in-effect
    // pattern (no data-fetching library yet) is intentional here.
    if (Number.isFinite(examId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadExam();
      loadGenerations();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [examId]);

  async function handleGenerate() {
    setIsGenerating(true);
    setGenerateError(null);
    try {
      const result = await generateSeating(examId);
      setLatest(result);
      const assignmentPage = await fetchAssignments(result.id);
      setAssignments(assignmentPage.items);
      await loadGenerations();
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsGenerating(false);
    }
  }

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

          <section>
            <h2>Seating</h2>
            <div className={styles.uploadRow}>
              <button
                type="button"
                onClick={handleGenerate}
                disabled={isGenerating}
              >
                {isGenerating ? "Generating…" : "Generate seating (sequential)"}
              </button>
            </div>

            {generateError && (
              <div className={styles.errorBanner} role="alert">
                {generateError}
              </div>
            )}

            {latest && (
              <div>
                <p>
                  Status:{" "}
                  <span
                    className={`${styles.statusBadge} ${STATUS_CLASS[latest.status]}`}
                  >
                    {latest.status}
                  </span>
                </p>
                <div className={styles.summaryGrid}>
                  <div className={styles.summaryCard}>
                    <div className={styles.value}>{latest.total_registered}</div>
                    <div className={styles.label}>Registered</div>
                  </div>
                  <div className={styles.summaryCard}>
                    <div className={styles.value}>{latest.scheduled_student_count}</div>
                    <div className={styles.label}>Scheduled allocation</div>
                  </div>
                  <div className={styles.summaryCard}>
                    <div className={styles.value}>{latest.total_physical_capacity}</div>
                    <div className={styles.label}>Physical capacity</div>
                  </div>
                  <div className={styles.summaryCard}>
                    <div className={styles.value}>{latest.available_capacity}</div>
                    <div className={styles.label}>Seats used this run</div>
                  </div>
                  <div className={styles.summaryCard}>
                    <div className={styles.value}>{latest.total_assigned}</div>
                    <div className={styles.label}>Assigned</div>
                  </div>
                  <div className={styles.summaryCard}>
                    <div className={styles.value}>{latest.total_unassigned}</div>
                    <div className={styles.label}>Unassigned</div>
                  </div>
                </div>

                {latest.capacity_shortage && (
                  <div className={styles.errorBanner} role="alert">
                    <p>
                      {latest.total_unassigned} student(s) could not be
                      seated. Reason(s):
                    </p>
                    <ul className={styles.issueList}>
                      {latest.scheduled_allocation_shortage && (
                        <li>
                          Scheduled allocation shortage — {latest.total_registered}{" "}
                          registered vs. {latest.scheduled_student_count} seat(s)
                          scheduled. The rooms may have had physical room to
                          spare; the schedule simply didn&apos;t allocate enough.
                        </li>
                      )}
                      {latest.physical_capacity_shortage && (
                        <li>
                          Physical capacity shortage — the rooms assigned to
                          this exam have only {latest.total_physical_capacity}{" "}
                          physical seat(s) total, regardless of what was
                          scheduled.
                        </li>
                      )}
                    </ul>
                  </div>
                )}

                {latest.warnings.length > 0 && (
                  <ul className={styles.issueList}>
                    {latest.warnings.map((warning, index) => (
                      <li key={index}>{warning}</li>
                    ))}
                  </ul>
                )}

                {assignments.length > 0 && (
                  <table className={styles.dataTable}>
                    <thead>
                      <tr>
                        <th>Room</th>
                        <th>Seat</th>
                        <th>Student ID</th>
                        <th>Student name</th>
                      </tr>
                    </thead>
                    <tbody>
                      {assignments
                        .slice()
                        .sort((a, b) =>
                          a.room_code === b.room_code
                            ? a.seat_number - b.seat_number
                            : a.room_code.localeCompare(b.room_code),
                        )
                        .map((assignment) => (
                          <tr key={assignment.id}>
                            <td>{assignment.room_code}</td>
                            <td>{assignment.seat_number}</td>
                            <td>{assignment.student_number}</td>
                            <td>{assignment.student_name}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                )}
              </div>
            )}

            {generations.length > 0 && (
              <>
                <h3>Past generations ({generations.length})</h3>
                <table className={styles.dataTable}>
                  <thead>
                    <tr>
                      <th>Strategy</th>
                      <th>Status</th>
                      <th>Assigned / Registered</th>
                      <th>Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {generations.map((generation) => (
                      <tr key={generation.id}>
                        <td>{generation.strategy_name}</td>
                        <td>{generation.status}</td>
                        <td>
                          {generation.total_assigned} / {generation.total_registered}
                        </td>
                        <td>{generation.created_at ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </section>
        </>
      )}
    </div>
  );
}
