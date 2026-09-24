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

export interface WarningOut {
  kind: string;
  line_number: number | null;
  message: string;
}

export interface RoomOut {
  id: number;
  code: string;
  capacity: number;
}

export interface RoomImportResult {
  status: "success" | "partial" | "failed";
  rows_read: number;
  rooms_created: number;
  rooms_existing: number;
  duplicate_rows: number;
  validation_errors: ValidationErrorOut[];
  conflicts: ConflictOut[];
}

export interface ScheduleImportResult {
  status: "success" | "partial" | "failed";
  rows_read: number;
  exams_created: number;
  exams_existing: number;
  exam_rooms_created: number;
  exam_rooms_existing: number;
  duplicate_rows: number;
  validation_errors: ValidationErrorOut[];
  conflicts: ConflictOut[];
  warnings: WarningOut[];
}

export interface ExamOut {
  id: number;
  course_id: number;
  course_code: string;
  course_name: string;
  exam_date: string;
  time_slot: string;
  day_label: string | null;
  expected_student_count: number;
  room_count: number;
}

export interface ExamRoomOut {
  id: number;
  room_id: number;
  room_code: string;
  room_capacity: number;
  allocated_students: number;
}

export interface ExamDetailOut {
  id: number;
  course_id: number;
  course_code: string;
  course_name: string;
  exam_date: string;
  time_slot: string;
  day_label: string | null;
  expected_student_count: number;
  exam_rooms: ExamRoomOut[];
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

async function uploadCsv<T>(path: string, file: File): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    body: formData,
  });
  if (!response.ok) {
    throw new Error(await readErrorDetail(response));
  }
  return response.json();
}

async function fetchPage<T>(
  path: string,
  limit: number,
  offset: number,
): Promise<Page<T>> {
  const response = await fetch(
    `${API_BASE_URL}${path}?limit=${limit}&offset=${offset}`,
  );
  if (!response.ok) {
    throw new Error(await readErrorDetail(response));
  }
  return response.json();
}

export function importRegistrationsCsv(
  file: File,
): Promise<RegistrationImportResult> {
  return uploadCsv<RegistrationImportResult>("/registrations/import", file);
}

export function fetchStudents(limit = 50, offset = 0): Promise<Page<StudentOut>> {
  return fetchPage<StudentOut>("/students", limit, offset);
}

export function fetchCourses(limit = 50, offset = 0): Promise<Page<CourseOut>> {
  return fetchPage<CourseOut>("/courses", limit, offset);
}

export function importRoomsCsv(file: File): Promise<RoomImportResult> {
  return uploadCsv<RoomImportResult>("/rooms/import", file);
}

export function fetchRooms(limit = 50, offset = 0): Promise<Page<RoomOut>> {
  return fetchPage<RoomOut>("/rooms", limit, offset);
}

export function importScheduleCsv(file: File): Promise<ScheduleImportResult> {
  return uploadCsv<ScheduleImportResult>("/schedules/import", file);
}

export function fetchExams(limit = 50, offset = 0): Promise<Page<ExamOut>> {
  return fetchPage<ExamOut>("/exams", limit, offset);
}

export async function fetchExam(examId: number): Promise<ExamDetailOut> {
  const response = await fetch(`${API_BASE_URL}/exams/${examId}`);
  if (!response.ok) {
    throw new Error(await readErrorDetail(response));
  }
  return response.json();
}
