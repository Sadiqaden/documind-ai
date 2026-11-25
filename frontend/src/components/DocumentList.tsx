import { api, formatBytes } from "../lib/api";
import type { DocumentInfo } from "../lib/types";
import { ExternalIcon, FileIcon, RefreshIcon, Spinner, TrashIcon } from "./Icons";

interface Props {
  documents: DocumentInfo[];
  loading: boolean;
  selected: Set<string>;
  onToggle: (id: string) => void;
  onDelete: (doc: DocumentInfo) => void;
  onReindex: (doc: DocumentInfo) => void;
  readOnly?: boolean;
}

const statusStyle: Record<DocumentInfo["status"], string> = {
  ready: "bg-emerald-500/15 text-emerald-300",
  processing: "bg-amber-500/15 text-amber-300",
  failed: "bg-rose-500/15 text-rose-300",
};

export function DocumentList({ documents, loading, selected, onToggle, onDelete, onReindex, readOnly = false }: Props) {
  if (loading && !documents.length) {
    return (
      <div className="space-y-2" aria-busy="true" aria-label="Loading documents">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-14 animate-pulse rounded-lg bg-slate-800/60" />
        ))}
      </div>
    );
  }
  if (!documents.length) {
    return (
      <p className="rounded-lg border border-slate-800 p-4 text-center text-sm text-slate-500">
        No documents yet. Upload a PDF to get started.
      </p>
    );
  }
  return (
    <ul className="space-y-1.5" aria-label="Document library">
      {documents.map((d) => {
        const ready = d.status === "ready";
        return (
          <li key={d.id} className="group rounded-lg border border-slate-800 bg-slate-900/60 p-2.5 hover:border-slate-700">
            <div className="flex items-start gap-2">
              <input
                type="checkbox"
                className="mt-1 h-4 w-4 accent-indigo-500 disabled:opacity-40"
                checked={selected.has(d.id)}
                disabled={!ready}
                onChange={() => onToggle(d.id)}
                aria-label={`Include ${d.filename} in search`}
              />
              <FileIcon className="mt-0.5 shrink-0 text-slate-400" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-200" title={d.filename}>
                  {d.filename}
                </p>
                <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-xs text-slate-500">
                  <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 ${statusStyle[d.status]}`}>
                    {d.status === "processing" && <Spinner className="h-3 w-3" />}
                    {d.status}
                  </span>
                  {ready && <span>{d.page_count} pages</span>}
                  <span>{formatBytes(d.size_bytes)}</span>
                </p>
                {d.status === "failed" && d.error && (
                  <p className="mt-1 text-xs text-rose-300" role="alert">{d.error}</p>
                )}
                {d.stale_index && (
                  <p className="mt-1 text-xs text-amber-300">Indexed with a different embedding model — re-index.</p>
                )}
              </div>
            </div>
            <div className="mt-1.5 flex justify-end gap-1 opacity-80 group-hover:opacity-100">
              {ready && (
                <a
                  href={api.fileUrl(d.id)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  aria-label={`Open ${d.filename}`}
                  title="Open PDF"
                >
                  <ExternalIcon width={15} height={15} />
                </a>
              )}
              {!readOnly && (
                <>
                  <button
                    type="button"
                    onClick={() => onReindex(d)}
                    disabled={d.status === "processing"}
                    className="rounded p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-40"
                    aria-label={`Re-index ${d.filename}`}
                    title="Re-index"
                  >
                    <RefreshIcon width={15} height={15} />
                  </button>
                  <button
                    type="button"
                    onClick={() => onDelete(d)}
                    className="rounded p-1 text-slate-400 hover:bg-rose-500/10 hover:text-rose-300"
                    aria-label={`Delete ${d.filename}`}
                    title="Delete"
                  >
                    <TrashIcon width={15} height={15} />
                  </button>
                </>
              )}
            </div>
          </li>
        );
      })}
    </ul>
  );
}
