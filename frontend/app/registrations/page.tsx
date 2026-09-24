"use client";

import { useEffect, useState } from "react";
import {
  CourseOut,
  RegistrationImportResult,
  StudentOut,
  fetchCourses,
  fetchStudents,
  importRegistrationsCsv,
} from "@/lib/api";
import styles from "./page.module.css";

const STATUS_CLASS: Record<RegistrationImportResult["status"], string> = {
  success: styles.statusSuccess,
  partial: styles.statusPartial,
  failed: styles.statusFailed,
};

export default function RegistrationsPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [result, setResult] = useState<RegistrationImportResult | null>(null);

  const [students, setStudents] = useState<StudentOut[]>([]);
  const [studentsTotal, setStudentsTotal] = useState(0);
  const [courses, setCourses] = useState<CourseOut[]>([]);
  const [coursesTotal, setCoursesTotal] = useState(0);
  const [listError, setListError] = useState<string | null>(null);

  async function refreshLists() {
    try {
      const [studentsPage, coursesPage] = await Promise.all([
        fetchStudents(50, 0),
        fetchCourses(50, 0),
      ]);
      setStudents(studentsPage.items);
      setStudentsTotal(studentsPage.meta.total);
      setCourses(coursesPage.items);
      setCoursesTotal(coursesPage.meta.total);
      setListError(null);
    } catch (error) {
      setListError(error instanceof Error ? error.message : String(error));
    }
  }

  useEffect(() => {
    // Load-on-mount from the backend API. There's no data-fetching library
    // in this project yet (deliberately, per the milestone scope), so this
    // is the plain fetch-in-effect pattern the new react-hooks rule below
    // is generally right to discourage in favor of one — not applicable here.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshLists();
  }, []);

  async function handleImport() {
    if (!selectedFile) return;
    setIsUploading(true);
    setUploadError(null);
    setResult(null);
    try {
      const importResult = await importRegistrationsCsv(selectedFile);
      setResult(importResult);
      await refreshLists();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Registrations</h1>
        <p>Import a registration CSV and verify the resulting data.</p>
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
              <SummaryCard
                label="Students created"
                value={result.students_created}
              />
              <SummaryCard
                label="Students existing"
                value={result.students_existing}
              />
              <SummaryCard
                label="Courses created"
                value={result.courses_created}
              />
              <SummaryCard
                label="Courses existing"
                value={result.courses_existing}
              />
              <SummaryCard
                label="Registrations created"
                value={result.registrations_created}
              />
              <SummaryCard
                label="Registrations existing"
                value={result.registrations_existing}
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
          </div>
        )}
      </section>

      {listError && (
        <div className={styles.errorBanner} role="alert">
          {listError}
        </div>
      )}

      <section className={styles.tablesGrid}>
        <div>
          <h2>Students ({studentsTotal})</h2>
          {students.length === 0 ? (
            <p className={styles.empty}>No students imported yet.</p>
          ) : (
            <table className={styles.dataTable}>
              <thead>
                <tr>
                  <th>Student ID</th>
                  <th>Name</th>
                </tr>
              </thead>
              <tbody>
                {students.map((student) => (
                  <tr key={student.id}>
                    <td>{student.student_number}</td>
                    <td>{student.full_name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div>
          <h2>Courses ({coursesTotal})</h2>
          {courses.length === 0 ? (
            <p className={styles.empty}>No courses imported yet.</p>
          ) : (
            <table className={styles.dataTable}>
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Name</th>
                </tr>
              </thead>
              <tbody>
                {courses.map((course) => (
                  <tr key={course.id}>
                    <td>{course.code}</td>
                    <td>{course.name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
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
