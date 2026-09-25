"use client";

import { useEffect, useState } from "react";
import { Card, CardHeader, StatCard } from "@/components/ui/Card";
import { CsvImportButton } from "@/components/ui/CsvImportButton";
import { ImportSummary } from "@/components/ui/ImportSummary";
import { Pagination } from "@/components/ui/Pagination";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import {
  CourseOut,
  RegistrationImportResult,
  StudentOut,
  fetchCourses,
  fetchStudents,
  importRegistrationsCsv,
} from "@/lib/api";

const PAGE_SIZE = 10;

export default function RegistrationsPage() {
  const [result, setResult] = useState<RegistrationImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [students, setStudents] = useState<StudentOut[]>([]);
  const [studentsTotal, setStudentsTotal] = useState(0);
  const [studentsOffset, setStudentsOffset] = useState(0);

  const [courses, setCourses] = useState<CourseOut[]>([]);
  const [coursesTotal, setCoursesTotal] = useState(0);
  const [coursesOffset, setCoursesOffset] = useState(0);

  const [isLoading, setIsLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  async function loadStudents(offset: number) {
    const page = await fetchStudents(PAGE_SIZE, offset);
    setStudents(page.items);
    setStudentsTotal(page.meta.total);
    setStudentsOffset(offset);
  }

  async function loadCourses(offset: number) {
    const page = await fetchCourses(PAGE_SIZE, offset);
    setCourses(page.items);
    setCoursesTotal(page.meta.total);
    setCoursesOffset(offset);
  }

  async function loadAll() {
    setIsLoading(true);
    setListError(null);
    try {
      await Promise.all([loadStudents(0), loadCourses(0)]);
    } catch (error) {
      setListError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Student Registrations"
        description="Import and manage student course registrations"
        action={
          <CsvImportButton
            label="Import CSV"
            onImport={importRegistrationsCsv}
            onResult={(res) => {
              setResult(res);
              setImportError(null);
              loadAll();
            }}
            onError={setImportError}
          />
        }
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard label="Total Students" value={studentsTotal} tone="brand" />
        <StatCard label="Total Courses" value={coursesTotal} tone="success" />
        <StatCard
          label="Total Registrations"
          value={result ? result.registrations_created + result.registrations_existing : "—"}
          tone="warning"
        />
      </div>

      {importError && <ErrorState message={importError} />}

      {result && (
        <ImportSummary
          status={result.status}
          stats={[
            { label: "Rows read", value: result.rows_read },
            { label: "Students created", value: result.students_created },
            { label: "Students existing", value: result.students_existing },
            { label: "Courses created", value: result.courses_created },
            { label: "Courses existing", value: result.courses_existing },
            { label: "Registrations created", value: result.registrations_created },
            { label: "Registrations existing", value: result.registrations_existing },
            { label: "Duplicate rows", value: result.duplicate_rows },
          ]}
          validationErrors={result.validation_errors}
          conflicts={result.conflicts}
        />
      )}

      {listError && <ErrorState message={listError} onRetry={loadAll} />}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        <Card>
          <CardHeader title="Students" description={`${studentsTotal} total`} />
          {isLoading ? (
            <TableSkeleton />
          ) : students.length === 0 ? (
            <div className="p-6">
              <EmptyState
                title="No students imported yet"
                description="Import a registration CSV to populate students and courses."
              />
            </div>
          ) : (
            <>
              <Table>
                <Thead>
                  <Tr>
                    <Th>Student ID</Th>
                    <Th>Name</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {students.map((student) => (
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
                total={studentsTotal}
                limit={PAGE_SIZE}
                offset={studentsOffset}
                onPageChange={loadStudents}
              />
            </>
          )}
        </Card>

        <Card>
          <CardHeader title="Courses" description={`${coursesTotal} total`} />
          {isLoading ? (
            <TableSkeleton columns={2} />
          ) : courses.length === 0 ? (
            <div className="p-6">
              <EmptyState
                title="No courses imported yet"
                description="Courses are created automatically from registration data."
              />
            </div>
          ) : (
            <>
              <Table>
                <Thead>
                  <Tr>
                    <Th>Code</Th>
                    <Th>Name</Th>
                  </Tr>
                </Thead>
                <Tbody>
                  {courses.map((course) => (
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
                total={coursesTotal}
                limit={PAGE_SIZE}
                offset={coursesOffset}
                onPageChange={loadCourses}
              />
            </>
          )}
        </Card>
      </div>
    </div>
  );
}
