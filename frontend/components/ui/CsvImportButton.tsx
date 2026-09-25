"use client";

import { Upload } from "lucide-react";
import { useRef, useState } from "react";
import { Button } from "./Button";

/**
 * A single button that opens the OS file picker and immediately imports
 * the chosen CSV — one click instead of "choose file" then "import".
 * The underlying import call and its result handling are unchanged from
 * the previous two-step control; only the interaction is streamlined.
 */
export function CsvImportButton<T>({
  label = "Import CSV",
  onImport,
  onResult,
  onError,
}: {
  label?: string;
  onImport: (file: File) => Promise<T>;
  onResult: (result: T) => void;
  onError: (message: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;

    setIsUploading(true);
    try {
      const result = await onImport(file);
      onResult(result);
    } catch (error) {
      onError(error instanceof Error ? error.message : String(error));
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,text/csv"
        className="hidden"
        onChange={handleFileChange}
      />
      <Button
        icon={<Upload className="h-4 w-4" />}
        loading={isUploading}
        onClick={() => inputRef.current?.click()}
      >
        {isUploading ? "Importing…" : label}
      </Button>
    </>
  );
}
