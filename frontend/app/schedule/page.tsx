"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ExamOut,
  ScheduleImportResult,
  fetchExams,
  importScheduleCsv,
} from "@/lib/api";
import styles from "./page.module.css";

const STATUS_CLASS: Record<ScheduleImportResult["status"], string> = {
  success: styles.statusSuccess,
  partial: styles.statusPartial,
  failed: styles.statusFailed,
};

export default function SchedulePage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [result, setResult] = useState<ScheduleImportResult | null>(null);

  const [exams, setExams] = useState<ExamOut[]>([]);
  const [examsTotal, setExamsTotal] = useState(0);
  const [listError, setListError] = useState<string | null>(null);

  async function refreshExams() {
    try {
      const page = await fetchExams(100, 0);
      setExams(page.items);
      setExamsTotal(page.meta.total);
      setListError(null);
    } catch (error) {
      setListError(error instanceof Error ? error.message : String(error));
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshExams();
  }, []);

  async function handleImport() {
    if (!selectedFile) return;
    setIsUploading(true);
    setUploadError(null);
    setResult(null);
    try {
      const importResult = await importScheduleCsv(selectedFile);
      setResult(importResult);
      await refreshExams();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Schedule</h1>
        <p>
          Import a schedule CSV against already-imported courses and rooms.
        </p>
      </div>

      <section>
        <div className={styles.uploadRow}>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) =>
              setSelectedFile(event.target.files?.[0] ?? null)
            }
          />
          <button
            type="button"
            onClick={handleImport}
            disabled={!selectedFile || isUploading}
          >
            {isUploading ? "Importing…" : "Import"}
          </button>
        </div>

        {uploadError && (
          <div className={styles.errorBanner} role="alert">
            {uploadError}
          </div>
        )}

        {result && (
          <div>
            <p>
              Status:{" "}
              <span
                className={`${styles.statusBadge} ${STATUS_CLASS[result.status]}`}
              >
                {result.status}
              </span>
            </p>

            <div className={styles.summaryGrid}>
              <SummaryCard label="Rows read" value={result.rows_read} />
              <SummaryCard label="Exams created" value={result.exams_created} />
              <SummaryCard
                label="Exams existing"
                value={result.exams_existing}
              />
              <SummaryCard
                label="Exam rooms created"
                value={result.exam_rooms_created}
              />
              <SummaryCard
                label="Exam rooms existing"
                value={result.exam_rooms_existing}
              />
              <SummaryCard
                label="Duplicate rows"
                value={result.duplicate_rows}
              />
            </div>

            {result.validation_errors.length > 0 && (
              <>
                <h3>Validation errors ({result.validation_errors.length})</h3>
                <ul className={styles.issueList}>
                  {result.validation_errors.map((issue, index) => (
                    <li key={index}>
                      {issue.line_number != null
                        ? `Line ${issue.line_number}: `
                        : ""}
                      {issue.field ? `[${issue.field}] ` : ""}
                      {issue.message}
                    </li>
                  ))}
                </ul>
              </>
            )}

            {result.conflicts.length > 0 && (
              <>
                <h3>Conflicts ({result.conflicts.length})</h3>
                <ul className={styles.issueList}>
                  {result.conflicts.map((conflict, index) => (
                    <li key={index}>
                      Line {conflict.line_number}: {conflict.kind} for &quot;
                      {conflict.key}&quot; — stored &quot;
                      {conflict.existing_value}&quot; vs incoming &quot;
                      {conflict.incoming_value}&quot;
                    </li>
                  ))}
                </ul>
              </>
            )}

            {result.warnings.length > 0 && (
              <>
                <h3>Warnings ({result.warnings.length})</h3>
                <ul className={styles.issueList}>
                  {result.warnings.map((warning, index) => (
                    <li key={index}>
                      {warning.line_number != null
                        ? `Line ${warning.line_number}: `
                        : ""}
                      {warning.message}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
      </section>

      {listError && (
        <div className={styles.errorBanner} role="alert">
          {listError}
        </div>
      )}

      <section>
        <h2>Exams ({examsTotal})</h2>
        {exams.length === 0 ? (
          <p className={styles.empty}>No exams imported yet.</p>
        ) : (
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th>Course</th>
                <th>Date</th>
                <th>Time</th>
                <th>Expected students</th>
                <th>Rooms</th>
              </tr>
            </thead>
            <tbody>
              {exams.map((exam) => (
                <tr key={exam.id}>
                  <td>
                    <Link href={`/schedule/${exam.id}`}>
                      {exam.course_code} — {exam.course_name}
                    </Link>
                  </td>
                  <td>
                    {exam.exam_date}
                    {exam.day_label ? ` (${exam.day_label})` : ""}
                  </td>
                  <td>{exam.time_slot}</td>
                  <td>{exam.expected_student_count}</td>
                  <td>{exam.room_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}

function SummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className={styles.summaryCard}>
      <div className={styles.value}>{value}</div>
      <div className={styles.label}>{label}</div>
    </div>
  );
}
