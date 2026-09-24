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

export interface SeatingGenerationOut {
  id: number;
  exam_id: number;
  strategy_name: string;
  status: "pending" | "success" | "partial" | "failed";
  total_registered: number;
  total_assigned: number;
  total_unassigned: number;
  capacity_shortage: boolean;
  warnings: string[];
  created_at: string | null;
}

export interface SeatingGenerationResult extends SeatingGenerationOut {
  scheduled_student_count: number;
  total_physical_capacity: number;
  available_capacity: number;
  unassigned_student_ids: number[];
  // capacity_shortage (inherited) only answers "did anyone go unassigned?".
  // These two answer "why" and are not mutually exclusive.
  scheduled_allocation_shortage: boolean;
  physical_capacity_shortage: boolean;
}

export interface SeatAssignmentOut {
  id: number;
  room_id: number;
  room_code: string;
  student_id: number;
  student_number: string;
  student_name: string;
  seat_number: number;
}

export interface SeatAssignmentListResult {
  generation: SeatingGenerationOut;
  items: SeatAssignmentOut[];
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

export async function generateSeating(
  examId: number,
  strategy = "sequential",
): Promise<SeatingGenerationResult> {
  const response = await fetch(
    `${API_BASE_URL}/exams/${examId}/seating/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ strategy }),
    },
  );
  if (!response.ok) {
    throw new Error(await readErrorDetail(response));
  }
  return response.json();
}

export async function fetchGenerations(
  examId: number,
): Promise<Page<SeatingGenerationOut>> {
  return fetchPage<SeatingGenerationOut>(
    `/exams/${examId}/seating/generations`,
    50,
    0,
  );
}

export async function fetchAssignments(
  generationId: number,
): Promise<SeatAssignmentListResult> {
  const response = await fetch(
    `${API_BASE_URL}/seating/generations/${generationId}/assignments`,
  );
  if (!response.ok) {
    throw new Error(await readErrorDetail(response));
  }
  return response.json();
}
