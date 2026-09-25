"use client";

import {
  ArrowLeft,
  Building2,
  CalendarClock,
  FileDown,
  Play,
  Sparkles,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { StatusBadge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Card, CardHeader, StatCard } from "@/components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { AssignmentsViewer } from "@/components/seating/AssignmentsViewer";
import { CapacityDiagnostics } from "@/components/seating/CapacityDiagnostics";
import {
  ExamDetailOut,
  SeatAssignmentOut,
  SeatingGenerationOut,
  SeatingGenerationResult,
  fetchAssignments,
  fetchExam,
  fetchGenerations,
  generateSeating,
  rangesReportUrl,
  seatingReportUrl,
} from "@/lib/api";

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

  const [viewedGenerationId, setViewedGenerationId] = useState<number | null>(null);
  const [viewedAssignments, setViewedAssignments] = useState<SeatAssignmentOut[]>([]);
  const [viewError, setViewError] = useState<string | null>(null);

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
      // Non-fatal: the exam detail load already surfaces connectivity errors.
    }
  }

  useEffect(() => {
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
      setViewedGenerationId(null);
      const assignmentPage = await fetchAssignments(result.id);
      setAssignments(assignmentPage.items);
      await loadGenerations();
    } catch (err) {
      setGenerateError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsGenerating(false);
    }
  }

  async function handleViewAssignments(generationId: number) {
    setViewError(null);
    try {
      const page = await fetchAssignments(generationId);
      setViewedGenerationId(generationId);
      setViewedAssignments(page.items);
    } catch (err) {
      setViewError(err instanceof Error ? err.message : String(err));
    }
  }

  const totalAllocated = exam?.exam_rooms.reduce((sum, er) => sum + er.allocated_students, 0) ?? 0;
  const totalCapacity = exam?.exam_rooms.reduce((sum, er) => sum + er.room_capacity, 0) ?? 0;
  const latestKnownStatus = generations.length > 0 ? generations[generations.length - 1].status : null;

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/exams"
        className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-text-secondary hover:text-text-primary"
      >
        <ArrowLeft className="h-4 w-4" />
        Exams
      </Link>

      {error && <ErrorState message={error} onRetry={loadExam} />}

      {!error && !exam && <LoadingState label="Loading exam…" />}

      {exam && (
        <>
          <div>
            <h1 className="text-xl font-semibold text-text-primary">
              {exam.course_name}
            </h1>
            <p className="text-sm text-text-secondary">{exam.course_code}</p>
            <p className="mt-1 flex items-center gap-1.5 text-sm text-text-secondary">
              <CalendarClock className="h-4 w-4" />
              {exam.exam_date}
              {exam.day_label ? ` (${exam.day_label})` : ""} · {exam.time_slot}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Expected Students"
              value={exam.expected_student_count}
              icon={<Users className="h-5 w-5" />}
              tone="brand"
            />
            <StatCard
              label="Scheduled Allocation"
              value={totalAllocated}
              icon={<Building2 className="h-5 w-5" />}
              tone="neutral"
            />
            <StatCard
              label="Physical Capacity"
              value={totalCapacity}
              icon={<Building2 className="h-5 w-5" />}
              tone="neutral"
            />
            <Card className="flex flex-col justify-center gap-1 p-4">
              <span className="text-xs font-medium text-text-secondary">
                Seating Status
              </span>
              {latestKnownStatus ? (
                <StatusBadge status={latestKnownStatus} />
              ) : (
                <span className="text-sm font-semibold text-text-secondary">
                  Not Generated
                </span>
              )}
            </Card>
          </div>

          <Card>
            <CardHeader
              title="Rooms for this exam"
              description={`${exam.exam_rooms.length} room(s)`}
            />
            {exam.exam_rooms.length === 0 ? (
              <div className="p-6">
                <EmptyState title="No rooms assigned to this exam yet." />
              </div>
            ) : (
              <Table>
                <Thead>
                  <Tr>
                    <Th>Room</Th>
                    <Th>Allocated Students</Th>
                    <Th>Physical Capacity</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {exam.exam_rooms.map((examRoom) => (
                    <Tr key={examRoom.id}>
                      <Td className="font-medium text-text-primary">
                        {examRoom.room_code}
                      </Td>
                      <Td>{examRoom.allocated_students}</Td>
                      <Td>{examRoom.room_capacity}</Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Generate Seating"
              description="Create a new seating arrangement using the sequential strategy"
              action={
                <Button
                  onClick={handleGenerate}
                  loading={isGenerating}
                  icon={<Play className="h-4 w-4" />}
                >
                  {isGenerating ? "Generating…" : "Generate Seating"}
                </Button>
              }
            />

            <div className="flex flex-col gap-4 p-5">
              {generateError && <ErrorState message={generateError} />}

              {latest && (
                <div className="flex flex-col gap-4">
                  <div className="flex items-center gap-2">
                    <Sparkles className="h-4 w-4 text-brand-600" />
                    <span className="text-sm font-medium text-text-primary">
                      Latest Generation #{latest.id}
                    </span>
                    <StatusBadge status={latest.status} />
                  </div>

                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
                    <StatCard label="Registered" value={latest.total_registered} tone="neutral" />
                    <StatCard label="Scheduled" value={latest.scheduled_student_count} tone="neutral" />
                    <StatCard label="Physical Capacity" value={latest.total_physical_capacity} tone="neutral" />
                    <StatCard label="Assigned" value={latest.total_assigned} tone="success" />
                    <StatCard
                      label="Unassigned"
                      value={latest.total_unassigned}
                      tone={latest.total_unassigned > 0 ? "danger" : "neutral"}
                    />
                  </div>

                  <CapacityDiagnostics result={latest} />

                  {latest.warnings.length > 0 && (
                    <ul className="flex flex-col gap-1">
                      {latest.warnings.map((warning, index) => (
                        <li
                          key={index}
                          className="rounded-md border border-warning-bg bg-warning-bg/60 px-3 py-1.5 text-xs text-warning-text"
                        >
                          {warning}
                        </li>
                      ))}
                    </ul>
                  )}

                  {latest.total_assigned > 0 && (
                    <div className="flex flex-wrap gap-2">
                      <LinkButton
                        href={seatingReportUrl(latest.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        icon={<FileDown className="h-3.5 w-3.5" />}
                      >
                        Seating PDF
                      </LinkButton>
                      <LinkButton
                        href={rangesReportUrl(latest.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        icon={<FileDown className="h-3.5 w-3.5" />}
                      >
                        ID Range PDF
                      </LinkButton>
                    </div>
                  )}

                  {assignments.length > 0 && (
                    <AssignmentsViewer assignments={assignments} />
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader
              title="Previous Generations"
              description={`${generations.length} generation(s)`}
            />
            {generations.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  title="No seating has been generated for this exam yet"
                  description="Use Generate Seating above to create the first arrangement."
                />
              </div>
            ) : (
              <>
                <Table>
                  <Thead>
                    <Tr>
                      <Th>Generation</Th>
                      <Th>Strategy</Th>
                      <Th>Status</Th>
                      <Th>Assigned</Th>
                      <Th>Unassigned</Th>
                      <Th>Created</Th>
                      <Th>Actions</Th>
                    </Tr>
                  </Thead>
                  <Tbody>
                    {[...generations].reverse().map((generation) => (
                      <Tr key={generation.id}>
                        <Td className="font-medium text-text-primary">
                          #{generation.id}
                        </Td>
                        <Td>{generation.strategy_name}</Td>
                        <Td>
                          <StatusBadge status={generation.status} />
                        </Td>
                        <Td>{generation.total_assigned}</Td>
                        <Td>{generation.total_unassigned}</Td>
                        <Td className="whitespace-nowrap text-xs text-text-secondary">
                          {generation.created_at ?? "—"}
                        </Td>
                        <Td>
                          <div className="flex flex-wrap gap-2">
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => handleViewAssignments(generation.id)}
                            >
                              View
                            </Button>
                            {generation.total_assigned > 0 && (
                              <>
                                <LinkButton
                                  href={seatingReportUrl(generation.id)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  size="sm"
                                >
                                  [PDF]
                                </LinkButton>
                                <LinkButton
                                  href={rangesReportUrl(generation.id)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  size="sm"
                                >
                                  [Ranges]
                                </LinkButton>
                              </>
                            )}
                          </div>
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>

                {viewError && (
                  <div className="p-4">
                    <ErrorState message={viewError} />
                  </div>
                )}

                {viewedGenerationId !== null && (
                  <div className="border-t border-border p-5">
                    <AssignmentsViewer
                      title={`Assignments for generation #${viewedGenerationId}`}
                      assignments={viewedAssignments}
                    />
                  </div>
                )}
              </>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
