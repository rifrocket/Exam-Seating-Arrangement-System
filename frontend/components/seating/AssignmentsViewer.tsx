"use client";

import { useMemo, useState } from "react";
import { EmptyState } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { SeatAssignmentOut } from "@/lib/api";

export function AssignmentsViewer({
  title,
  assignments,
}: {
  title?: string;
  assignments: SeatAssignmentOut[];
}) {
  const [roomFilter, setRoomFilter] = useState("all");

  const rooms = useMemo(
    () => Array.from(new Set(assignments.map((a) => a.room_code))).sort(),
    [assignments],
  );

  const filtered = useMemo(
    () =>
      assignments
        .filter((a) => roomFilter === "all" || a.room_code === roomFilter)
        .sort((a, b) =>
          a.room_code === b.room_code
            ? a.seat_number - b.seat_number
            : a.room_code.localeCompare(b.room_code),
        ),
    [assignments, roomFilter],
  );

  if (assignments.length === 0) {
    return <EmptyState title="No assignments for this generation" />;
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        {title && (
          <h4 className="text-sm font-semibold text-text-primary">{title}</h4>
        )}
        <label className="ml-auto flex items-center gap-2 text-xs text-text-secondary">
          Room:
          <select
            value={roomFilter}
            onChange={(e) => setRoomFilter(e.target.value)}
            className="rounded-md border border-border bg-white px-2 py-1 text-xs text-text-primary focus:border-brand-500 focus:outline-none"
          >
            <option value="all">All Rooms</option>
            {rooms.map((room) => (
              <option key={room} value={room}>
                {room}
              </option>
            ))}
          </select>
        </label>
      </div>

      <Table>
        <Thead>
          <Tr>
            <Th>Room</Th>
            <Th>Seat</Th>
            <Th>Student</Th>
          </Tr>
        </Thead>
        <Tbody>
          {filtered.map((assignment) => (
            <Tr key={assignment.id}>
              <Td className="font-medium text-text-primary">
                {assignment.room_code}
              </Td>
              <Td>{assignment.seat_number}</Td>
              <Td>
                <span className="font-mono text-xs text-text-secondary">
                  {assignment.student_number}
                </span>{" "}
                — {assignment.student_name}
              </Td>
            </Tr>
          ))}
        </Tbody>
      </Table>
    </div>
  );
}
