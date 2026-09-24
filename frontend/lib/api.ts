// Thin fetch wrappers around the backend API. No data-fetching framework —
// the app is small enough that plain fetch + React state is the simplest
// clean approach for this milestone.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ValidationErrorOut {
  line_number: number | null;
  field: string | null;
  message: string;
}

export interface ConflictOut {
  kind: string;
  key: string;
  line_number: number;
  existing_value: string;
  incoming_value: string;
}

export interface RegistrationImportResult {
  status: "success" | "partial" | "failed";
  rows_read: number;
  students_created: number;
  students_existing: number;
  courses_created: number;
  courses_existing: number;
  registrations_created: number;
  registrations_existing: number;
  duplicate_rows: number;
  validation_errors: ValidationErrorOut[];
  conflicts: ConflictOut[];
}

export interface StudentOut {
  id: number;
  student_number: string;
  full_name: string;
}

export interface CourseOut {
  id: number;
  code: string;
  name: string;
}

export interface PageMeta {
  total: number;
  limit: number;
  offset: number;
}

export interface Page<T> {
  items: T[];
  meta: PageMeta;
}

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return body?.detail ?? `Request failed with status ${response.status}`;
  } catch {
    return `Request failed with status ${response.status}`;
  }
}

export async function importRegistrationsCsv(
  file: File,
): Promise<RegistrationImportResult> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}/registrations/import`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await readErrorDetail(response));
  }
  return response.json();
}

export async function fetchStudents(
  limit = 50,
  offset = 0,
): Promise<Page<StudentOut>> {
  const response = await fetch(
    `${API_BASE_URL}/students?limit=${limit}&offset=${offset}`,
  );
  if (!response.ok) {
    throw new Error(await readErrorDetail(response));
  }
  return response.json();
}

export async function fetchCourses(
  limit = 50,
  offset = 0,
): Promise<Page<CourseOut>> {
  const response = await fetch(
    `${API_BASE_URL}/courses?limit=${limit}&offset=${offset}`,
  );
  if (!response.ok) {
    throw new Error(await readErrorDetail(response));
  }
  return response.json();
}
