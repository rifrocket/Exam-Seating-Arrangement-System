"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Pagination } from "@/components/ui/Pagination";
import { PageHeader } from "@/components/ui/PageHeader";
import { SearchInput } from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { StudentOut, fetchStudents } from "@/lib/api";

const PAGE_SIZE = 20;

export default function StudentsPage() {
  const [students, setStudents] = useState<StudentOut[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  async function load(newOffset: number) {
    setIsLoading(true);
    setError(null);
    try {
      const page = await fetchStudents(PAGE_SIZE, newOffset);
      setStudents(page.items);
      setTotal(page.meta.total);
      setOffset(newOffset);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    load(0);
  }, []);

  const filtered = useMemo(() => {
    const query = filter.trim().toLowerCase();
    if (!query) return students;
    return students.filter(
      (s) =>
        s.student_number.toLowerCase().includes(query) ||
        s.full_name.toLowerCase().includes(query),
    );
  }, [students, filter]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Students"
        description="View all students and their registration information"
      />

      <Card>
        <div className="border-b border-border p-4">
          <SearchInput
            value={filter}
            onChange={setFilter}
            placeholder="Search by student ID or name on this page…"
          />
        </div>

        {error ? (
          <div className="p-6">
            <ErrorState message={error} onRetry={() => load(offset)} />
          </div>
        ) : isLoading ? (
          <TableSkeleton rows={8} columns={2} />
        ) : students.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No students yet"
              description="Import a registration CSV from the Registrations page to add students."
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-6">
            <EmptyState title="No students match your search on this page" />
          </div>
        ) : (
          <>
            <Table>
              <Thead>
                <Tr>
                  <Th>Student ID</Th>
                  <Th>Student Name</Th>
                </Tr>
              </Thead>
              <Tbody>
                {filtered.map((student) => (
                  <Tr key={student.id}>
                    <Td className="font-mono text-xs text-text-secondary">
                      {student.student_number}
                    </Td>
                    <Td className="font-medium text-text-primary">
                      {student.full_name}
                    </Td>
                  </Tr>
                ))}
              </Tbody>
            </Table>
            <Pagination
              total={total}
              limit={PAGE_SIZE}
              offset={offset}
              onPageChange={load}
            />
          </>
        )}
      </Card>
    </div>
  );
}
