import { useRef, useState, type DragEvent } from "react";
import { validatePdfFile } from "../lib/api";
import { Spinner, UploadIcon } from "./Icons";

interface Props {
  maxMb: number;
  uploading: boolean;
  onFiles: (files: File[]) => void;
  onError: (msg: string) => void;
}

export function UploadZone({ maxMb, uploading, onFiles, onError }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  const handle = (list: FileList | null) => {
    if (!list?.length) return;
    const files = Array.from(list);
    const ok: File[] = [];
    for (const f of files) {
      const err = validatePdfFile(f, maxMb);
      if (err) onError(err);
      else ok.push(f);
    }
    if (ok.length) onFiles(ok);
    if (inputRef.current) inputRef.current.value = "";
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    handle(e.dataTransfer.files);
  };

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={onDrop}
      className={`rounded-xl border-2 border-dashed p-4 text-center transition-colors ${
        dragging ? "border-indigo-400 bg-indigo-500/10" : "border-slate-700 hover:border-slate-500"
      }`}
    >
      <input
        ref={inputRef}
        id="pdf-upload"
        type="file"
        accept="application/pdf,.pdf"
        multiple
        className="sr-only"
        onChange={(e) => handle(e.target.files)}
        disabled={uploading}
      />
      <label
        htmlFor="pdf-upload"
        className="flex cursor-pointer flex-col items-center gap-1.5 text-sm text-slate-300 focus-within:outline-none"
      >
        {uploading ? <Spinner className="text-indigo-400" /> : <UploadIcon className="text-indigo-400" />}
        <span className="font-medium">{uploading ? "Uploading…" : "Upload PDFs"}</span>
        <span className="text-xs text-slate-500">Drag & drop or click · max {maxMb} MB</span>
      </label>
    </div>
  );
}
