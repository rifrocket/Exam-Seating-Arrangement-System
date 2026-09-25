"use client";

import {
  BookOpen,
  Building2,
  GraduationCap,
  Users,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { SeatingStatusBadge, StatusBadge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { StatCard } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import {
  ExamWithGenerations,
  fetchCourses,
  fetchExamsWithGenerations,
  fetchRooms,
  fetchStudents,
} from "@/lib/api";

interface Counts {
  students: number;
  courses: number;
  exams: number;
  rooms: number;
}

export default function DashboardPage() {
  const [counts, setCounts] = useState<Counts | null>(null);
  const [examsWithGenerations, setExamsWithGenerations] = useState<
    ExamWithGenerations[]
  >([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      const [studentsPage, coursesPage, roomsPage, examsPage] =
        await Promise.all([
          fetchStudents(1, 0),
          fetchCourses(1, 0),
          fetchRooms(1, 0),
          fetchExamsWithGenerations(100),
        ]);
      setCounts({
        students: studentsPage.meta.total,
        courses: coursesPage.meta.total,
        exams: examsPage.length,
        rooms: roomsPage.meta.total,
      });
      setExamsWithGenerations(examsPage);
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

  const today = new Date().toISOString().slice(0, 10);
  const upcoming = examsWithGenerations
    .filter((e) => e.exam.exam_date >= today)
    .sort((a, b) => a.exam.exam_date.localeCompare(b.exam.exam_date))
    .slice(0, 6);

  const recentGenerations = examsWithGenerations
    .flatMap((e) => e.generations.map((g) => ({ exam: e.exam, generation: g })))
    .sort((a, b) =>
      (b.generation.created_at ?? "").localeCompare(a.generation.created_at ?? ""),
    )
    .slice(0, 6);

  return (
    <div>
      <PageHeader
        title="Dashboard"
        description="Manage registrations, exams, rooms and generate seating arrangements"
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {!error && isLoading && <LoadingState label="Loading dashboard…" />}

      {!error && !isLoading && counts && (
        <div className="flex flex-col gap-6">
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard
              label="Total Students"
              value={counts.students}
              icon={<Users className="h-5 w-5" />}
              tone="brand"
            />
            <StatCard
              label="Courses"
              value={counts.courses}
              icon={<BookOpen className="h-5 w-5" />}
              tone="success"
            />
            <StatCard
              label="Exams"
              value={counts.exams}
              icon={<GraduationCap className="h-5 w-5" />}
              tone="warning"
            />
            <StatCard
              label="Rooms"
              value={counts.rooms}
              icon={<Building2 className="h-5 w-5" />}
              tone="neutral"
            />
          </div>

          <section className="rounded-lg border border-border bg-surface-card shadow-sm">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="text-sm font-semibold text-text-primary">
                Upcoming Exams
              </h2>
              <Link href="/exams">
                <Button variant="ghost" size="sm">
                  View All Exams →
                </Button>
              </Link>
            </div>
            {upcoming.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  title="No upcoming exams"
                  description="Import a schedule CSV to create exams from your course schedule."
                  action={
                    <Link href="/schedule">
                      <Button size="sm">Go to Schedule</Button>
                    </Link>
                  }
                />
              </div>
            ) : (
              <Table>
                <Thead>
                  <Tr>
                    <Th>Date</Th>
                    <Th>Time</Th>
                    <Th>Course</Th>
                    <Th>Expected</Th>
                    <Th>Rooms</Th>
                    <Th>Seating Status</Th>
                    <Th></Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {upcoming.map(({ exam, latest }) => (
                    <Tr key={exam.id}>
                      <Td>{exam.exam_date}</Td>
                      <Td>{exam.time_slot}</Td>
                      <Td className="font-medium text-text-primary">
                        {exam.course_code}
                      </Td>
                      <Td>{exam.expected_student_count}</Td>
                      <Td>{exam.room_count}</Td>
                      <Td>
                        <SeatingStatusBadge
                          hasGeneration={latest !== null}
                          status={latest?.status}
                        />
                      </Td>
                      <Td>
                        <Link href={`/exams/${exam.id}`}>
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
          </section>

          <section className="rounded-lg border border-border bg-surface-card shadow-sm">
            <div className="flex items-center justify-between border-b border-border px-5 py-4">
              <h2 className="text-sm font-semibold text-text-primary">
                Recent Seating Generations
              </h2>
              <Link href="/seating-generations">
                <Button variant="ghost" size="sm">
                  View All →
                </Button>
              </Link>
            </div>
            {recentGenerations.length === 0 ? (
              <div className="p-6">
                <EmptyState
                  title="No seating generated yet"
                  description="Open an exam and generate its seating to see results here."
                />
              </div>
            ) : (
              <Table>
                <Thead>
                  <Tr>
                    <Th>Generation</Th>
                    <Th>Exam</Th>
                    <Th>Status</Th>
                    <Th>Assigned</Th>
                    <Th>Unassigned</Th>
                    <Th>Created</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {recentGenerations.map(({ exam, generation }) => (
                    <Tr key={generation.id}>
                      <Td className="font-medium text-text-primary">
                        #{generation.id}
                      </Td>
                      <Td>
                        <Link
                          href={`/exams/${exam.id}`}
                          className="text-brand-600 hover:underline"
                        >
                          {exam.course_code}
                        </Link>
                      </Td>
                      <Td>
                        <StatusBadge status={generation.status} />
                      </Td>
                      <Td>{generation.total_assigned}</Td>
                      <Td>{generation.total_unassigned}</Td>
                      <Td>{generation.created_at ?? "—"}</Td>
                    </Tr>
                  ))}
                </Tbody>
              </Table>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
