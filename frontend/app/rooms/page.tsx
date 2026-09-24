"use client";

import { useEffect, useState } from "react";
import { RoomImportResult, RoomOut, fetchRooms, importRoomsCsv } from "@/lib/api";
import styles from "./page.module.css";

export default function RoomsPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [result, setResult] = useState<RoomImportResult | null>(null);

  const [rooms, setRooms] = useState<RoomOut[]>([]);
  const [roomsTotal, setRoomsTotal] = useState(0);
  const [listError, setListError] = useState<string | null>(null);

  async function refreshRooms() {
    try {
      const page = await fetchRooms(200, 0);
      setRooms(page.items);
      setRoomsTotal(page.meta.total);
      setListError(null);
    } catch (error) {
      setListError(error instanceof Error ? error.message : String(error));
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    refreshRooms();
  }, []);

  async function handleImport() {
    if (!selectedFile) return;
    setIsUploading(true);
    setUploadError(null);
    setResult(null);
    try {
      const importResult = await importRoomsCsv(selectedFile);
      setResult(importResult);
      await refreshRooms();
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1>Rooms</h1>
        <p>Seed rooms from a CSV (matching input/locations.csv: room, capacity).</p>
      </div>

      <section>
        <div className={styles.uploadRow}>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) =>
              setSelectedFile(event.target.files?.[0] ?? null)
            }
          />
          <button
            type="button"
            onClick={handleImport}
            disabled={!selectedFile || isUploading}
          >
            {isUploading ? "Importing…" : "Import"}
          </button>
        </div>

        {uploadError && (
          <div className={styles.errorBanner} role="alert">
            {uploadError}
          </div>
        )}

        {result && (
          <div>
            <p>
              Status: {result.status} — {result.rooms_created} created,{" "}
              {result.rooms_existing} existing
            </p>

            {result.validation_errors.length > 0 && (
              <ul className={styles.issueList}>
                {result.validation_errors.map((issue, index) => (
                  <li key={index}>
                    {issue.line_number != null
                      ? `Line ${issue.line_number}: `
                      : ""}
                    {issue.message}
                  </li>
                ))}
              </ul>
            )}

            {result.conflicts.length > 0 && (
              <ul className={styles.issueList}>
                {result.conflicts.map((conflict, index) => (
                  <li key={index}>
                    Line {conflict.line_number}: room &quot;{conflict.key}
                    &quot; — stored capacity {conflict.existing_value} vs
                    incoming {conflict.incoming_value}
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {listError && (
        <div className={styles.errorBanner} role="alert">
          {listError}
        </div>
      )}

      <section>
        <h2>Rooms ({roomsTotal})</h2>
        {rooms.length === 0 ? (
          <p className={styles.empty}>No rooms imported yet.</p>
        ) : (
          <table className={styles.dataTable}>
            <thead>
              <tr>
                <th>Room</th>
                <th>Capacity</th>
              </tr>
            </thead>
            <tbody>
              {rooms.map((room) => (
                <tr key={room.id}>
                  <td>{room.code}</td>
                  <td>{room.capacity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
