"use client";

import { FileDown } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { StatusBadge } from "@/components/ui/Badge";
import { LinkButton } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { PageHeader } from "@/components/ui/PageHeader";
import { SearchInput } from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import {
  ExamOut,
  SeatingGenerationOut,
  fetchExamsWithGenerations,
  rangesReportUrl,
  seatingReportUrl,
} from "@/lib/api";

interface Row {
  exam: ExamOut;
  generation: SeatingGenerationOut;
}

export default function ReportsPage() {
  const [rows, setRows] = useState<Row[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchExamsWithGenerations(100);
      const flattened = data
        .flatMap((e) => e.generations.map((generation) => ({ exam: e.exam, generation })))
        // A generation with zero assignments has no report to produce
        // (the backend returns 409 for it) — leave it out here rather
        // than offering a link that's guaranteed to fail.
        .filter(({ generation }) => generation.total_assigned > 0);
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

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Reports"
        description="Download seating and ID-range PDF reports for a completed generation"
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
          <TableSkeleton rows={6} columns={5} />
        ) : filtered.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No reports available yet"
              description="Generate seating for an exam with at least one assigned student to produce reports."
            />
          </div>
        ) : (
          <Table>
            <Thead>
              <Tr>
                <Th>Generation</Th>
                <Th>Exam</Th>
                <Th>Status</Th>
                <Th>Created</Th>
                <Th>Reports</Th>
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
                  <Td className="whitespace-nowrap text-xs text-text-secondary">
                    {generation.created_at ?? "—"}
                  </Td>
                  <Td>
                    <div className="flex flex-wrap gap-2">
                      <LinkButton
                        href={seatingReportUrl(generation.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        size="sm"
                        icon={<FileDown className="h-3.5 w-3.5" />}
                      >
                        Seating PDF
                      </LinkButton>
                      <LinkButton
                        href={rangesReportUrl(generation.id)}
                        target="_blank"
                        rel="noopener noreferrer"
                        size="sm"
                        icon={<FileDown className="h-3.5 w-3.5" />}
                      >
                        ID Range PDF
                      </LinkButton>
                    </div>
                  </Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
