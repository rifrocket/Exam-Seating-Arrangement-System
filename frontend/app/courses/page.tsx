"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/Card";
import { Pagination } from "@/components/ui/Pagination";
import { PageHeader } from "@/components/ui/PageHeader";
import { SearchInput } from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { CourseOut, fetchCourses } from "@/lib/api";

const PAGE_SIZE = 20;

export default function CoursesPage() {
  const [courses, setCourses] = useState<CourseOut[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  async function load(newOffset: number) {
    setIsLoading(true);
    setError(null);
    try {
      const page = await fetchCourses(PAGE_SIZE, newOffset);
      setCourses(page.items);
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
    if (!query) return courses;
    return courses.filter(
      (c) =>
        c.code.toLowerCase().includes(query) ||
        c.name.toLowerCase().includes(query),
    );
  }, [courses, filter]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Courses"
        description="View all courses created from registration data"
      />

      <Card>
        <div className="border-b border-border p-4">
          <SearchInput
            value={filter}
            onChange={setFilter}
            placeholder="Search by course code or name on this page…"
          />
        </div>

        {error ? (
          <div className="p-6">
            <ErrorState message={error} onRetry={() => load(offset)} />
          </div>
        ) : isLoading ? (
          <TableSkeleton rows={8} columns={2} />
        ) : courses.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No courses yet"
              description="Courses are created automatically when you import registrations."
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-6">
            <EmptyState title="No courses match your search on this page" />
          </div>
        ) : (
          <>
            <Table>
              <Thead>
                <Tr>
                  <Th>Course Code</Th>
                  <Th>Course Name</Th>
                </Tr>
              </Thead>
              <Tbody>
                {filtered.map((course) => (
                  <Tr key={course.id}>
                    <Td className="font-mono text-xs text-text-secondary">
                      {course.code}
                    </Td>
                    <Td className="font-medium text-text-primary">
                      {course.name}
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
