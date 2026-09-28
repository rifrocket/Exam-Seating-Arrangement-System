import { Ban } from "lucide-react";
import { useMemo } from "react";
import { RoomOut, SeatAssignmentOut } from "@/lib/api";

/**
 * Renders the physical seat layout (rows x columns) for every room a
 * generation's assignments touch, using the room's own `rows`/`columns`/
 * `blocked_seat_numbers` (already exposed by GET /rooms) to place each
 * seat_number at its real row/column — the same row-major numbering
 * RectangularRoomTopology uses on the backend
 * (row = floor((seat_number-1)/columns), column = (seat_number-1)%columns) —
 * never inferred from assignment list order. Visualization only: nothing
 * here is clickable, editable, or persisted.
 */

// Literal Tailwind class names (not template-built) so the JIT scanner
// picks them all up. Cycles by course_code's alphabetical position, so
// the same course always gets the same color across rooms within one
// generation — colors repeat past 8 courses, which is fine since the
// course code is always shown as text too (color is never the only cue).
const COURSE_PALETTE = [
  { bg: "bg-blue-100", border: "border-blue-300", text: "text-blue-800", dot: "bg-blue-500" },
  { bg: "bg-purple-100", border: "border-purple-300", text: "text-purple-800", dot: "bg-purple-500" },
  { bg: "bg-amber-100", border: "border-amber-300", text: "text-amber-800", dot: "bg-amber-500" },
  { bg: "bg-emerald-100", border: "border-emerald-300", text: "text-emerald-800", dot: "bg-emerald-500" },
  { bg: "bg-rose-100", border: "border-rose-300", text: "text-rose-800", dot: "bg-rose-500" },
  { bg: "bg-cyan-100", border: "border-cyan-300", text: "text-cyan-800", dot: "bg-cyan-500" },
  { bg: "bg-orange-100", border: "border-orange-300", text: "text-orange-800", dot: "bg-orange-500" },
  { bg: "bg-indigo-100", border: "border-indigo-300", text: "text-indigo-800", dot: "bg-indigo-500" },
] as const;

const OCCUPIED_SINGLE_COURSE = {
  bg: "bg-brand-50",
  border: "border-brand-500/40",
  text: "text-brand-700",
  dot: "bg-brand-600",
};

interface SeatCell {
  seatNumber: number;
  row: number;
  column: number;
  state: "occupied" | "empty" | "blocked";
  assignment?: SeatAssignmentOut;
}

function buildSeatGrid(room: RoomOut, assignmentsForRoom: SeatAssignmentOut[]): SeatCell[] | null {
  if (room.rows === null || room.columns === null) {
    return null; // no configured topology — nothing to draw a grid from
  }
  const byNumber = new Map(assignmentsForRoom.map((a) => [a.seat_number, a]));
  const blocked = new Set(room.blocked_seat_numbers);
  const cells: SeatCell[] = [];
  const totalSeats = room.rows * room.columns;
  for (let seatNumber = 1; seatNumber <= totalSeats; seatNumber++) {
    const zeroBased = seatNumber - 1;
    const row = Math.floor(zeroBased / room.columns);
    const column = zeroBased % room.columns;
    const assignment = byNumber.get(seatNumber);
    const state: SeatCell["state"] = blocked.has(seatNumber)
      ? "blocked"
      : assignment
        ? "occupied"
        : "empty";
    cells.push({ seatNumber, row, column, state, assignment });
  }
  return cells;
}

function SeatCellView({
  cell,
  courseColor,
}: {
  cell: SeatCell;
  courseColor: (typeof COURSE_PALETTE)[number] | typeof OCCUPIED_SINGLE_COURSE | null;
}) {
  const seatLabel = String(cell.seatNumber).padStart(2, "0");

  if (cell.state === "blocked") {
    return (
      <div
        role="img"
        aria-label={`Seat ${cell.seatNumber}, blocked, cannot be used`}
        title={`Seat ${cell.seatNumber} — blocked`}
        className="flex h-[72px] w-[84px] flex-col items-center justify-center gap-1 rounded-md border border-border-strong bg-neutral-bg text-neutral-text"
      >
        <Ban className="h-3.5 w-3.5" />
        <span className="text-[10px] font-medium leading-none">{seatLabel}</span>
        <span className="text-[9px] leading-none">Blocked</span>
      </div>
    );
  }

  if (cell.state === "empty") {
    return (
      <div
        role="img"
        aria-label={`Seat ${cell.seatNumber}, empty, available`}
        title={`Seat ${cell.seatNumber} — empty`}
        className="flex h-[72px] w-[84px] flex-col items-center justify-center gap-1 rounded-md border border-dashed border-border-strong bg-surface-card text-text-muted"
      >
        <span className="text-[10px] font-medium leading-none">{seatLabel}</span>
        <span className="text-[9px] leading-none">Empty</span>
      </div>
    );
  }

  const assignment = cell.assignment;
  const colors = courseColor ?? OCCUPIED_SINGLE_COURSE;
  const ariaLabel = assignment
    ? `Seat ${cell.seatNumber}, occupied, ${assignment.course_code}, ${assignment.student_name}, ID ${assignment.student_number}`
    : `Seat ${cell.seatNumber}, occupied`;

  return (
    <div
      role="img"
      aria-label={ariaLabel}
      title={ariaLabel}
      className={`flex h-[72px] w-[84px] flex-col items-center justify-center gap-0.5 overflow-hidden rounded-md border px-1 text-center ${colors.bg} ${colors.border} ${colors.text}`}
    >
      <span className="text-[10px] font-medium leading-none opacity-70">{seatLabel}</span>
      {assignment && (
        <>
          <span className="max-w-full truncate text-[10px] font-semibold leading-tight">
            {assignment.course_code}
          </span>
          <span className="max-w-full truncate text-[9px] leading-tight opacity-90">
            {assignment.student_number}
          </span>
        </>
      )}
    </div>
  );
}

function RoomSeatMap({
  room,
  assignmentsForRoom,
  colorForCourse,
}: {
  room: RoomOut;
  assignmentsForRoom: SeatAssignmentOut[];
  colorForCourse: (courseCode: string) => (typeof COURSE_PALETTE)[number] | null;
}) {
  const cells = useMemo(() => buildSeatGrid(room, assignmentsForRoom), [room, assignmentsForRoom]);

  if (!cells) {
    return (
      <div className="rounded-md border border-dashed border-border p-4 text-xs text-text-secondary">
        Room {room.code} has no configured physical layout (rows/columns), so its seats
        can&apos;t be drawn as a grid — see the assignment table above for its seat numbers.
      </div>
    );
  }

  const rows = room.rows as number;
  const columns = room.columns as number;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline gap-2">
        <h4 className="text-sm font-semibold text-text-primary">Room {room.code}</h4>
        <span className="text-xs text-text-secondary">
          {rows}×{columns}
        </span>
      </div>
      <div className="scrollbar-thin overflow-x-auto rounded-md border border-border bg-surface p-3">
        <div
          className="grid gap-1.5"
          style={{
            gridTemplateColumns: `repeat(${columns}, 84px)`,
            gridTemplateRows: `repeat(${rows}, 72px)`,
            width: "max-content",
          }}
        >
          {cells.map((cell) => (
            <div key={cell.seatNumber} style={{ gridRow: cell.row + 1, gridColumn: cell.column + 1 }}>
              <SeatCellView
                cell={cell}
                courseColor={
                  cell.state === "occupied" && cell.assignment
                    ? colorForCourse(cell.assignment.course_code)
                    : null
                }
              />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Legend({ courses }: { courses: { code: string; color: (typeof COURSE_PALETTE)[number] }[] }) {
  return (
    <div className="flex flex-col gap-2 text-xs text-text-secondary">
      <div className="flex flex-wrap items-center gap-4">
        <span className="flex items-center gap-1.5">
          <span className={`h-3 w-3 rounded-sm border ${OCCUPIED_SINGLE_COURSE.border} ${OCCUPIED_SINGLE_COURSE.bg}`} />
          Occupied
        </span>
        <span className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-sm border border-dashed border-border-strong bg-surface-card" />
          Empty
        </span>
        <span className="flex items-center gap-1.5">
          <Ban className="h-3.5 w-3.5" />
          Blocked
        </span>
      </div>
      {courses.length > 1 && (
        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-2">
          <span className="font-medium text-text-primary">Courses:</span>
          {courses.map(({ code, color }) => (
            <span key={code} className="flex items-center gap-1.5">
              <span className={`h-2.5 w-2.5 rounded-full ${color.dot}`} />
              {code}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function SeatMap({ assignments, rooms }: { assignments: SeatAssignmentOut[]; rooms: RoomOut[] }) {
  const roomsById = useMemo(() => new Map(rooms.map((r) => [r.id, r])), [rooms]);

  const assignmentsByRoomId = useMemo(() => {
    const map = new Map<number, SeatAssignmentOut[]>();
    for (const assignment of assignments) {
      const list = map.get(assignment.room_id);
      if (list) {
        list.push(assignment);
      } else {
        map.set(assignment.room_id, [assignment]);
      }
    }
    return map;
  }, [assignments]);

  // Alphabetical, deterministic assignment of a palette slot per course
  // code, shared across every room this generation touches.
  const courseColors = useMemo(() => {
    const uniqueCourses = Array.from(new Set(assignments.map((a) => a.course_code))).sort();
    const map = new Map<string, (typeof COURSE_PALETTE)[number]>();
    uniqueCourses.forEach((code, index) => {
      map.set(code, COURSE_PALETTE[index % COURSE_PALETTE.length]);
    });
    return map;
  }, [assignments]);

  const roomIds = Array.from(assignmentsByRoomId.keys());

  if (roomIds.length === 0) {
    return null;
  }

  const showCourseLegend = courseColors.size > 1;
  const colorForCourse = (courseCode: string) => courseColors.get(courseCode) ?? null;

  return (
    <div className="flex flex-col gap-4">
      <h4 className="text-sm font-semibold text-text-primary">Physical Seat Map</h4>
      <Legend
        courses={
          showCourseLegend
            ? Array.from(courseColors.entries()).map(([code, color]) => ({ code, color }))
            : []
        }
      />
      <div className="flex flex-col gap-5">
        {roomIds.map((roomId) => {
          const room = roomsById.get(roomId);
          const roomAssignments = assignmentsByRoomId.get(roomId) ?? [];
          if (!room) {
            return (
              <div
                key={roomId}
                className="rounded-md border border-dashed border-border p-4 text-xs text-text-secondary"
              >
                Room details unavailable for room id {roomId}.
              </div>
            );
          }
          return (
            <RoomSeatMap
              key={roomId}
              room={room}
              assignmentsForRoom={roomAssignments}
              colorForCourse={colorForCourse}
            />
          );
        })}
      </div>
    </div>
  );
}
