"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { CsvImportButton } from "@/components/ui/CsvImportButton";
import { ImportSummary } from "@/components/ui/ImportSummary";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { ExamOut, ScheduleImportResult, fetchExams, importScheduleCsv } from "@/lib/api";

export default function SchedulePage() {
  const [result, setResult] = useState<ScheduleImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [recentExams, setRecentExams] = useState<ExamOut[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  async function load() {
    setIsLoading(true);
    setListError(null);
    try {
      const page = await fetchExams(10, 0);
      setRecentExams(page.items);
      setTotal(page.meta.total);
    } catch (error) {
      setListError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load();
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Schedule Import"
        description="Import a schedule CSV against already-imported courses and rooms"
        action={
          <CsvImportButton
            label="Import Schedule CSV"
            onImport={importScheduleCsv}
            onResult={(res) => {
              setResult(res);
              setImportError(null);
              load();
            }}
            onError={setImportError}
          />
        }
      />

      {importError && <ErrorState message={importError} />}

      {result && (
        <ImportSummary
          status={result.status}
          stats={[
            { label: "Rows read", value: result.rows_read },
            { label: "Exams created", value: result.exams_created },
            { label: "Exams existing", value: result.exams_existing },
            { label: "Exam rooms created", value: result.exam_rooms_created },
            { label: "Exam rooms existing", value: result.exam_rooms_existing },
            { label: "Duplicate rows", value: result.duplicate_rows },
          ]}
          validationErrors={result.validation_errors}
          conflicts={result.conflicts}
          warnings={result.warnings}
        />
      )}

      <Card>
        <CardHeader
          title="Exams from this schedule"
          description={`${total} exam${total === 1 ? "" : "s"} total`}
          action={
            <Link href="/exams">
              <Button variant="ghost" size="sm" icon={<ArrowRight className="h-3.5 w-3.5" />}>
                Manage all exams
              </Button>
            </Link>
          }
        />

        {listError ? (
          <div className="p-6">
            <ErrorState message={listError} onRetry={load} />
          </div>
        ) : isLoading ? (
          <TableSkeleton rows={5} />
        ) : recentExams.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No exams imported yet"
              description="Import a schedule CSV referencing courses and rooms you've already imported."
            />
          </div>
        ) : (
          <Table>
            <Thead>
              <Tr>
                <Th>Course</Th>
                <Th>Date</Th>
                <Th>Time</Th>
                <Th>Expected</Th>
                <Th>Rooms</Th>
                <Th></Th>
              </Tr>
            </Thead>
            <Tbody>
              {recentExams.map((exam) => (
                <Tr key={exam.id}>
                  <Td className="font-medium text-text-primary">
                    {exam.course_code} — {exam.course_name}
                  </Td>
                  <Td>
                    {exam.exam_date}
                    {exam.day_label ? ` (${exam.day_label})` : ""}
                  </Td>
                  <Td>{exam.time_slot}</Td>
                  <Td>{exam.expected_student_count}</Td>
                  <Td>{exam.room_count}</Td>
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
      </Card>
    </div>
  );
}
