"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/ui/Badge";
import { Button, LinkButton } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SearchInput } from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { AssignmentsViewer } from "@/components/seating/AssignmentsViewer";
import {
  ExamOut,
  SeatAssignmentOut,
  SeatingGenerationOut,
  fetchAssignments,
  fetchExamsWithGenerations,
  rangesReportUrl,
  seatingReportUrl,
} from "@/lib/api";

interface Row {
  exam: ExamOut;
  generation: SeatingGenerationOut;
}

export default function SeatingGenerationsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  const [viewedId, setViewedId] = useState<number | null>(null);
  const [viewedAssignments, setViewedAssignments] = useState<SeatAssignmentOut[]>([]);
  const [viewError, setViewError] = useState<string | null>(null);
  const [isViewLoading, setIsViewLoading] = useState(false);

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchExamsWithGenerations(100);
      const flattened = data.flatMap((e) =>
        e.generations.map((generation) => ({ exam: e.exam, generation })),
      );
      flattened.sort((a, b) =>
        (b.generation.created_at ?? "").localeCompare(a.generation.created_at ?? ""),
      );
      setRows(flattened);
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

  const filtered = useMemo(() => {
    const query = filter.trim().toLowerCase();
    if (!query) return rows;
    return rows.filter(
      ({ exam }) =>
        exam.course_code.toLowerCase().includes(query) ||
        exam.course_name.toLowerCase().includes(query),
    );
  }, [rows, filter]);

  async function handleView(generationId: number) {
    setViewError(null);
    setIsViewLoading(true);
    try {
      const page = await fetchAssignments(generationId);
      setViewedId(generationId);
      setViewedAssignments(page.items);
    } catch (err) {
      setViewError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsViewLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Seating Generations"
        description="View seating arrangements and generate new ones from an exam's page"
      />

      <Card>
        <div className="border-b border-border p-4">
          <SearchInput
            value={filter}
            onChange={setFilter}
            placeholder="Search by course code or name…"
          />
        </div>

        {error ? (
          <div className="p-6">
            <ErrorState message={error} onRetry={load} />
          </div>
        ) : isLoading ? (
          <TableSkeleton rows={6} columns={7} />
        ) : filtered.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No seating generations yet"
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
                <Th>Actions</Th>
              </Tr>
            </Thead>
            <Tbody>
              {filtered.map(({ exam, generation }) => (
                <Tr key={generation.id}>
                  <Td className="font-medium text-text-primary">#{generation.id}</Td>
                  <Td>
                    <Link
                      href={`/exams/${exam.id}`}
                      className="text-brand-600 hover:underline"
                    >
                      {exam.course_code} — {exam.course_name}
                    </Link>
                  </Td>
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
                        onClick={() => handleView(generation.id)}
                      >
                        View Assignments
                      </Button>
                      {generation.total_assigned > 0 && (
                        <>
                          <LinkButton
                            href={seatingReportUrl(generation.id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            size="sm"
                          >
                            Seating PDF
                          </LinkButton>
                          <LinkButton
                            href={rangesReportUrl(generation.id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            size="sm"
                          >
                            ID Range PDF
                          </LinkButton>
                        </>
                      )}
                    </div>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>

      {isViewLoading && <TableSkeleton rows={3} columns={3} />}
      {viewError && <ErrorState message={viewError} />}
      {viewedId !== null && !isViewLoading && (
        <Card>
          <div className="p-5">
            <AssignmentsViewer
              title={`Assignments for generation #${viewedId}`}
              assignments={viewedAssignments}
            />
          </div>
        </Card>
      )}
    </div>
  );
}
