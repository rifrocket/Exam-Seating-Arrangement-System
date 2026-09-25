"use client";

import { useEffect, useMemo, useState } from "react";
import { Card } from "@/components/ui/Card";
import { CsvImportButton } from "@/components/ui/CsvImportButton";
import { DownloadSampleButton } from "@/components/ui/DownloadSampleButton";
import { ImportSummary } from "@/components/ui/ImportSummary";
import { PageHeader } from "@/components/ui/PageHeader";
import { SearchInput } from "@/components/ui/SearchInput";
import { EmptyState, ErrorState, TableSkeleton } from "@/components/ui/States";
import { Table, Tbody, Td, Th, Thead, Tr } from "@/components/ui/Table";
import { RoomImportResult, RoomOut, fetchRooms, importRoomsCsv } from "@/lib/api";
import { buildSampleRoomsCsv } from "@/lib/sampleData";

export default function RoomsPage() {
  const [result, setResult] = useState<RoomImportResult | null>(null);
  const [importError, setImportError] = useState<string | null>(null);

  const [rooms, setRooms] = useState<RoomOut[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  async function load() {
    setIsLoading(true);
    setListError(null);
    try {
      const page = await fetchRooms(200, 0);
      setRooms(page.items);
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

  const filtered = useMemo(() => {
    const query = filter.trim().toLowerCase();
    if (!query) return rooms;
    return rooms.filter((r) => r.code.toLowerCase().includes(query));
  }, [rooms, filter]);

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Rooms"
        description="Manage exam rooms and their capacities"
        action={
          <>
            <DownloadSampleButton
              filename="sample-rooms.csv"
              buildContent={buildSampleRoomsCsv}
            />
            <CsvImportButton
              label="Import CSV"
              onImport={importRoomsCsv}
              onResult={(res) => {
                setResult(res);
                setImportError(null);
                load();
              }}
              onError={setImportError}
            />
          </>
        }
      />

      {importError && <ErrorState message={importError} />}

      {result && (
        <ImportSummary
          status={result.status}
          stats={[
            { label: "Rows read", value: result.rows_read },
            { label: "Rooms created", value: result.rooms_created },
            { label: "Rooms existing", value: result.rooms_existing },
            { label: "Duplicate rows", value: result.duplicate_rows },
          ]}
          validationErrors={result.validation_errors}
          conflicts={result.conflicts}
        />
      )}

      <Card>
        <div className="flex flex-col gap-3 border-b border-border p-4 sm:flex-row sm:items-center sm:justify-between">
          <span className="text-sm font-semibold text-text-primary">
            {total} room{total === 1 ? "" : "s"}
          </span>
          <SearchInput
            value={filter}
            onChange={setFilter}
            placeholder="Search by room code…"
          />
        </div>

        {listError ? (
          <div className="p-6">
            <ErrorState message={listError} onRetry={load} />
          </div>
        ) : isLoading ? (
          <TableSkeleton rows={6} columns={2} />
        ) : rooms.length === 0 ? (
          <div className="p-6">
            <EmptyState
              title="No rooms imported yet"
              description="Import a CSV with room and capacity columns (matching input/locations.csv)."
            />
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-6">
            <EmptyState title="No rooms match your search" />
          </div>
        ) : (
          <Table>
            <Thead>
              <Tr>
                <Th>Room</Th>
                <Th>Capacity</Th>
              </Tr>
            </Thead>
            <Tbody>
              {filtered.map((room) => (
                <Tr key={room.id}>
                  <Td className="font-medium text-text-primary">{room.code}</Td>
                  <Td>{room.capacity}</Td>
                </Tr>
              ))}
            </Tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}
