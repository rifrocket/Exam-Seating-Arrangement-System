"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { CsvImportButton } from "@/components/ui/CsvImportButton";
import { SeatingStatusBadge } from "@/components/ui/Badge";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { SearchInput } from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import {
  ExamWithGenerations,
  importScheduleCsv,
  fetchExamsWithGenerations,
} from "@/lib/api";

const PAGE_SIZE = 10;

type Tab = "all" | "upcoming" | "past" | "not-generated";

const TABS: { key: Tab; label: string }[] = [
  { key: "all", label: "All Exams" },
  { key: "upcoming", label: "Upcoming" },
  { key: "past", label: "Past" },
  { key: "not-generated", label: "Not Generated" },
];

export default function ExamsPage() {
  const [examsWithGenerations, setExamsWithGenerations] = useState<
    ExamWithGenerations[]
  >([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("all");
  const [filter, setFilter] = useState("");
  const [pageOffset, setPageOffset] = useState(0);

  async function load() {
    setIsLoading(true);
    setError(null);
    try {
      const data = await fetchExamsWithGenerations(100);
      setExamsWithGenerations(data);
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

  const filtered = useMemo(() => {
    const query = filter.trim().toLowerCase();
    return examsWithGenerations
      .filter(({ exam }) => {
        if (tab === "upcoming") return exam.exam_date >= today;
        if (tab === "past") return exam.exam_date < today;
        return true;
      })
      .filter(({ latest }) => (tab === "not-generated" ? latest === null : true))
      .filter(
        ({ exam }) =>
          !query ||
          exam.course_code.toLowerCase().includes(query) ||
          exam.course_name.toLowerCase().includes(query),
      )
      .sort((a, b) => a.exam.exam_date.localeCompare(b.exam.exam_date));
  }, [examsWithGenerations, tab, filter, today]);

  const pageItems = filtered.slice(pageOffset, pageOffset + PAGE_SIZE);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Exams"
        description="View and manage all scheduled exams"
        action={
          <CsvImportButton
            label="Import Schedule CSV"
            onImport={importScheduleCsv}
            onResult={() => {
              setImportError(null);
              load();
            }}
            onError={setImportError}
          />
        }
      />

      {importError && <ErrorState message={importError} />}

      <Card>
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap gap-1 rounded-md bg-surface p-1">
            {TABS.map((t) => (
              <button
                key={t.key}
                onClick={() => {
                  setTab(t.key);
                  setPageOffset(0);
                }}
                className={`rounded px-3 py-1.5 text-xs font-medium transition-colors ${
                  tab === t.key
                    ? "bg-white text-text-primary shadow-sm"
                    : "text-text-secondary hover:text-text-primary"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
          <SearchInput
            value={filter}
            onChange={(v) => {
              setFilter(v);
              setPageOffset(0);
            }}
            placeholder="Search by course code or name…"
          />
        </div>

        {error ? (
          <div className="p-6">
            <ErrorState message={error} onRetry={load} />
          </div>
        ) : isLoading ? (
          <TableSkeleton rows={8} columns={6} />
        ) : filtered.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No exams found"
              description="Import a schedule CSV to create exams, or adjust your filters."
            />
          </div>
        ) : (
          <>
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
                {pageItems.map(({ exam, latest }) => (
                  <Tr key={exam.id}>
                    <Td>
                      {exam.exam_date}
                      {exam.day_label ? ` (${exam.day_label})` : ""}
                    </Td>
                    <Td>{exam.time_slot}</Td>
                    <Td className="font-medium text-text-primary">
                      {exam.course_code} — {exam.course_name}
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
            <Pagination
              total={filtered.length}
              limit={PAGE_SIZE}
              offset={pageOffset}
              onPageChange={setPageOffset}
            />
          </>
        )}
      </Card>
    </div>
  );
}
