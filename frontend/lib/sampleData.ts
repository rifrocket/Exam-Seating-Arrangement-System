/**
 * Small, internally-consistent synthetic demo dataset: 20 fictional
 * students across 2 courses, 2 rooms sized to exactly fit them, and a
 * 2-exam schedule referencing those same courses and rooms. This is the
 * canonical "download sample → import → generate seating" demo path —
 * every file references identifiers the other files also use, and the
 * column layout matches the existing backend parsers exactly (no new CSV
 * format introduced).
 */

interface SampleStudent {
  id: string;
  name: string;
  courseCode: string;
}

const COURSE_NAMES: Record<string, string> = {
  CS101: "Introduction to Computer Science",
  MATH101: "Calculus I",
};

const SAMPLE_STUDENTS: SampleStudent[] = [
  { id: "10001", name: "Alex Johnson", courseCode: "CS101" },
  { id: "10002", name: "Jamie Smith", courseCode: "CS101" },
  { id: "10003", name: "Taylor Brown", courseCode: "CS101" },
  { id: "10004", name: "Morgan Davis", courseCode: "CS101" },
  { id: "10005", name: "Casey Wilson", courseCode: "CS101" },
  { id: "10006", name: "Jordan Miller", courseCode: "CS101" },
  { id: "10007", name: "Riley Moore", courseCode: "CS101" },
  { id: "10008", name: "Avery Taylor", courseCode: "CS101" },
  { id: "10009", name: "Quinn Anderson", courseCode: "CS101" },
  { id: "10010", name: "Drew Thomas", courseCode: "CS101" },
  { id: "10011", name: "Sam Jackson", courseCode: "MATH101" },
  { id: "10012", name: "Charlie White", courseCode: "MATH101" },
  { id: "10013", name: "Reese Harris", courseCode: "MATH101" },
  { id: "10014", name: "Skyler Martin", courseCode: "MATH101" },
  { id: "10015", name: "Peyton Thompson", courseCode: "MATH101" },
  { id: "10016", name: "Rowan Garcia", courseCode: "MATH101" },
  { id: "10017", name: "Emerson Martinez", courseCode: "MATH101" },
  { id: "10018", name: "Finley Robinson", courseCode: "MATH101" },
  { id: "10019", name: "Hayden Clark", courseCode: "MATH101" },
  { id: "10020", name: "Sawyer Lewis", courseCode: "MATH101" },
];

const SAMPLE_ROOMS = [
  { code: "401", capacity: 10 },
  { code: "402", capacity: 10 },
];

const SAMPLE_EXAMS = [
  { courseCode: "CS101", time: "09:00-11:00", roomCode: "401" },
  { courseCode: "MATH101", time: "13:00-15:00", roomCode: "402" },
];

export function buildSampleRegistrationsCsv(): string {
  const header = "student_id,student_name,subject_code,subject_name";
  const rows = SAMPLE_STUDENTS.map(
    (s) => `${s.id},${s.name},${s.courseCode},${COURSE_NAMES[s.courseCode]}`,
  );
  return [header, ...rows].join("\n") + "\n";
}

export function buildSampleRoomsCsv(): string {
  const header = "index,room,capacity";
  const rows = SAMPLE_ROOMS.map((r, i) => `${i + 1},${r.code},${r.capacity}`);
  return [header, ...rows].join("\n") + "\n";
}

/**
 * The schedule date is computed relative to today (7 days out) rather
 * than hardcoded, so the sample exams always show up under the
 * Dashboard/Exams "Upcoming" filter no matter when someone runs the demo.
 */
export function buildSampleScheduleCsv(referenceDate: Date = new Date()): string {
  const examDate = new Date(referenceDate);
  examDate.setDate(examDate.getDate() + 7);

  const dayName = examDate.toLocaleDateString("en-US", { weekday: "long" });
  const day = String(examDate.getDate());
  const month = examDate.toLocaleDateString("en-US", { month: "short" });
  const year = String(examDate.getFullYear()).slice(-2);
  const dateStr = `${day}-${month}-${year}`; // matches the backend's "%d-%b-%y" format

  const studentsByCourse = SAMPLE_STUDENTS.reduce<Record<string, number>>((acc, s) => {
    acc[s.courseCode] = (acc[s.courseCode] ?? 0) + 1;
    return acc;
  }, {});

  const header =
    "Day,Date,Time,Course Code,Course Name,No. of Students,Room(s),No. of Students/ Room";
  const rows = SAMPLE_EXAMS.map((exam) => {
    const room = SAMPLE_ROOMS.find((r) => r.code === exam.roomCode);
    const totalStudents = studentsByCourse[exam.courseCode] ?? 0;
    return [
      dayName,
      dateStr,
      exam.time,
      exam.courseCode,
      COURSE_NAMES[exam.courseCode],
      totalStudents,
      exam.roomCode,
      room?.capacity ?? totalStudents,
    ].join(",");
  });
  return [header, ...rows].join("\n") + "\n";
}

export function downloadTextFile(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
