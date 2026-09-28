"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import {
  ExamOut,
  ExaminationSessionOut,
  createExaminationSession,
  fetchExaminationSessions,
  fetchExams,
} from "@/lib/api";

export default function ExaminationSessionsPage() {
  const [exams, setExams] = useState<ExamOut[]>([]);
  const [sessions, setSessions] = useState<ExaminationSessionOut[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedExamIds, setSelectedExamIds] = useState<number[]>([]);
  const [isCreating, setIsCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      const [examsPage, sessionsPage] = await Promise.all([
        fetchExams(200, 0),
        fetchExaminationSessions(),
      ]);
      setExams(examsPage.items);
      setSessions(sessionsPage.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, []);

  // Only exams sharing the first selected exam's date + time slot may be
  // picked together — a session groups one shared seating event, not an
  // arbitrary bundle of exams (see docs/architecture.md).
  const referenceExam = useMemo(
    () => exams.find((e) => e.id === selectedExamIds[0]) ?? null,
    [exams, selectedExamIds],
  );

  function isCompatible(exam: ExamOut): boolean {
    if (!referenceExam) return true;
    return exam.exam_date === referenceExam.exam_date && exam.time_slot === referenceExam.time_slot;
  }

  function toggleExam(examId: number) {
    setSelectedExamIds((current) =>
      current.includes(examId) ? current.filter((id) => id !== examId) : [...current, examId],
    );
  }

  async function handleCreate() {
    setIsCreating(true);
    setCreateError(null);
    try {
      await createExaminationSession(selectedExamIds);
      setSelectedExamIds([]);
      await load();
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsCreating(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Examination Sessions"
        description="Group compatible exams into a shared seating session for multi-course generation"
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {!error && isLoading && <LoadingState label="Loading exams and sessions…" />}

      {!error && !isLoading && (
        <>
          <Card>
            <CardHeader
              title="Create a Session"
              description="Select two or more exams with the same date and time slot"
              action={
                <Button
                  onClick={handleCreate}
                  loading={isCreating}
                  disabled={selectedExamIds.length === 0}
                >
                  Create Session
                </Button>
              }
            />
            <div className="flex flex-col gap-2 p-5">
              {createError && <ErrorState message={createError} />}
              {exams.length === 0 ? (
                <EmptyState
                  title="No exams available"
                  description="Import a schedule CSV first to create exams to group into a session."
                />
              ) : (
                <div className="flex flex-col gap-1">
                  {exams.map((exam) => {
                    const compatible = isCompatible(exam);
                    const checked = selectedExamIds.includes(exam.id);
                    return (
                      <label
                        key={exam.id}
                        className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm ${
                          compatible
                            ? "cursor-pointer hover:bg-surface"
                            : "cursor-not-allowed opacity-40"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={!compatible}
                          onChange={() => toggleExam(exam.id)}
                          className="h-4 w-4 rounded border-border"
                        />
                        <span className="font-medium text-text-primary">{exam.course_code}</span>
                        <span className="text-text-secondary">{exam.course_name}</span>
                        <span className="ml-auto text-xs text-text-secondary">
                          {exam.exam_date} · {exam.time_slot}
                        </span>
                      </label>
                    );
                  })}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Sessions" description={`${sessions.length} session(s)`} />
            {sessions.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  title="No examination sessions yet"
                  description="Create one above to seat multiple courses together."
                />
              </div>
            ) : (
              <Table>
                <Thead>
                  <Tr>
                    <Th>Date</Th>
                    <Th>Time</Th>
                    <Th>Courses</Th>
                    <Th>Participants</Th>
                    <Th>Rooms</Th>
                    <Th></Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {sessions.map((session) => (
                    <Tr key={session.id}>
                      <Td>{session.exam_date}</Td>
                      <Td>{session.time_slot}</Td>
                      <Td className="font-medium text-text-primary">
                        {session.exams.map((e) => e.course_code).join(", ")}
                      </Td>
                      <Td>{session.participant_count}</Td>
                      <Td>{session.room_codes.join(", ")}</Td>
                      <Td>
                        <Link href={`/examination-sessions/${session.id}`}>
                          <Button variant="secondary" size="sm">
                            View
                          </Button>
                        </Link>
                      </Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
