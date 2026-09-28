"use client";

import { ArrowLeft, FileDown, Play, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { StatusBadge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Card, CardHeader, StatCard } from "@/components/ui/Card";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { AssignmentsViewer } from "@/components/seating/AssignmentsViewer";
import { CapacityDiagnostics } from "@/components/seating/CapacityDiagnostics";
import { SeatMap } from "@/components/seating/SeatMap";
import {
  ExaminationSessionOut,
  RoomOut,
  SeatAssignmentOut,
  SeatingGenerationOut,
  SeatingGenerationResult,
  fetchAssignments,
  fetchExaminationSession,
  fetchRooms,
  fetchSessionGenerations,
  generateSessionSeating,
  rangesReportUrl,
  seatMapReportUrl,
  seatingReportUrl,
} from "@/lib/api";

export default function ExaminationSessionDetailPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = Number(params.sessionId);

  const [session, setSession] = useState<ExaminationSessionOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [rooms, setRooms] = useState<RoomOut[]>([]);

  const [generations, setGenerations] = useState<SeatingGenerationOut[]>([]);
  const [isGenerating, setIsGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const [latest, setLatest] = useState<SeatingGenerationResult | null>(null);
  const [assignments, setAssignments] = useState<SeatAssignmentOut[]>([]);

  const [viewedGenerationId, setViewedGenerationId] = useState<number | null>(null);
  const [viewedAssignments, setViewedAssignments] = useState<SeatAssignmentOut[]>([]);
  const [viewError, setViewError] = useState<string | null>(null);
  const viewedSectionRef = useRef<HTMLDivElement>(null);

  async function loadRooms() {
    try {
      const page = await fetchRooms(200, 0);
      setRooms(page.items);
    } catch {
      // Non-fatal: the seat map simply won't render a physical grid
      // without room data — the assignment table above still works.
    }
  }

  async function loadSession() {
    try {
      const detail = await fetchExaminationSession(sessionId);
      setSession(detail);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function loadGenerations() {
    try {
      const page = await fetchSessionGenerations(sessionId);
      setGenerations(page.items);
    } catch {
      // Non-fatal: the session load already surfaces connectivity errors.
    }
  }

  useEffect(() => {
    if (Number.isFinite(sessionId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      loadSession();
      loadGenerations();
      loadRooms();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  async function handleGenerate() {
    setIsGenerating(true);
    setGenerateError(null);
    try {
      const result = await generateSessionSeating(sessionId, "constraint");
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

  useEffect(() => {
    if (viewedGenerationId !== null || viewError) {
      viewedSectionRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [viewedGenerationId, viewError]);

  const latestKnownStatus = generations.length > 0 ? generations[generations.length - 1].status : null;

  return (
    <div className="flex flex-col gap-6">
      <Link
        href="/examination-sessions"
        className="inline-flex w-fit items-center gap-1.5 text-sm font-medium text-text-secondary hover:text-text-primary"
      >
        <ArrowLeft className="h-4 w-4" />
        Examination Sessions
      </Link>

      {error && <ErrorState message={error} onRetry={loadSession} />}

      {!error && !session && <LoadingState label="Loading session…" />}

      {session && (
        <>
          <div>
            <h1 className="text-xl font-semibold text-text-primary">
              Session #{session.id}
            </h1>
            <p className="text-sm text-text-secondary">
              {session.exam_date} · {session.time_slot}
            </p>
          </div>

          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Courses" value={session.exams.length} tone="brand" />
            <StatCard label="Participants" value={session.participant_count} tone="neutral" />
            <StatCard label="Rooms" value={session.room_codes.length} tone="neutral" />
            <Card className="flex flex-col justify-center gap-1 p-4">
              <span className="text-xs font-medium text-text-secondary">Seating Status</span>
              {latestKnownStatus ? (
                <StatusBadge status={latestKnownStatus} />
              ) : (
                <span className="text-sm font-semibold text-text-secondary">Not Generated</span>
              )}
            </Card>
          </div>

          <Card>
            <CardHeader title="Courses" description={`${session.exams.length} course(s)`} />
            <Table>
              <Thead>
                <Tr>
                  <Th>Course Code</Th>
                  <Th>Course Name</Th>
                </Tr>
              </Thead>
              <Tbody>
                {session.exams.map((exam) => (
                  <Tr key={exam.exam_id}>
                    <Td className="font-medium text-text-primary">{exam.course_code}</Td>
                    <Td>{exam.course_name}</Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
          </Card>

          <Card>
            <CardHeader title="Rooms" description={`${session.room_codes.length} room(s)`} />
            {session.room_codes.length === 0 ? (
              <div className="p-6">
                <EmptyState title="No rooms scheduled for this session's exams yet." />
              </div>
            ) : (
              <div className="flex flex-wrap gap-2 p-5">
                {session.room_codes.map((code) => (
                  <span
                    key={code}
                    className="rounded-md border border-border bg-surface px-3 py-1.5 text-sm font-medium text-text-primary"
                  >
                    {code}
                  </span>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <CardHeader
              title="Generate Seating"
              description="Create a new seating arrangement using the constraint strategy"
              action={
                <Button onClick={handleGenerate} loading={isGenerating} icon={<Play className="h-4 w-4" />}>
                  {isGenerating ? "Generating…" : "Generate Seating"}
                </Button>
              }
            />

            <div className="flex flex-col gap-4 p-5">
              <p className="text-xs text-text-secondary">
                Constraint strategy: anti-cheating spatial separation enabled
              </p>
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

                  <div className="grid grid-cols-2 gap-3 sm:grid-cols-6">
                    <StatCard label="Registered" value={latest.total_registered} tone="neutral" />
                    <StatCard label="Scheduled" value={latest.scheduled_student_count} tone="neutral" />
                    <StatCard label="Physical Capacity" value={latest.total_physical_capacity} tone="neutral" />
                    <StatCard label="Usable Capacity" value={latest.total_usable_capacity} tone="neutral" />
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
                      <LinkButton
                        href={seatMapReportUrl(latest.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        icon={<FileDown className="h-3.5 w-3.5" />}
                      >
                        Seat Map PDF
                      </LinkButton>
                    </div>
                  )}

                  {assignments.length > 0 && (
                    <>
                      <AssignmentsViewer assignments={assignments} />
                      <SeatMap assignments={assignments} rooms={rooms} />
                    </>
                  )}
                </div>
              )}
            </div>
          </Card>

          <Card>
            <CardHeader title="Previous Generations" description={`${generations.length} generation(s)`} />
            {generations.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  title="No seating has been generated for this session yet"
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
                        <Td className="font-medium text-text-primary">#{generation.id}</Td>
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
                                <LinkButton
                                  href={seatMapReportUrl(generation.id)}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  size="sm"
                                >
                                  [Seat Map]
                                </LinkButton>
                              </>
                            )}
                          </div>
                        </Td>
                      </Tr>
                    ))}
                  </Tbody>
                </Table>

                <div ref={viewedSectionRef}>
                  {viewError && (
                    <div className="p-4">
                      <ErrorState message={viewError} />
                    </div>
                  )}

                  {viewedGenerationId !== null && (
                    <div className="flex flex-col gap-5 border-t border-border p-5">
                      <AssignmentsViewer
                        title={`Assignments for generation #${viewedGenerationId}`}
                        assignments={viewedAssignments}
                      />
                      <SeatMap assignments={viewedAssignments} rooms={rooms} />
                    </div>
                  )}
                </div>
              </>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
