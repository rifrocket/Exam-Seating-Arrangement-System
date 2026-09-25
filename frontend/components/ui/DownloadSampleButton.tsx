"use client";

import { Download } from "lucide-react";
import { Button } from "./Button";
import { downloadTextFile } from "@/lib/sampleData";

export function DownloadSampleButton({
  filename,
  buildContent,
}: {
  filename: string;
  buildContent: () => string;
}) {
  return (
    <Button
      variant="secondary"
      icon={<Download className="h-4 w-4" />}
      onClick={() => downloadTextFile(filename, buildContent())}
    >
      Download Sample CSV
    </Button>
  );
}
