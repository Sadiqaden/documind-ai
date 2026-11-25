import { useEffect, useRef } from "react";
import { api } from "../lib/api";
import type { Citation } from "../lib/types";
import { ExternalIcon } from "./Icons";

interface Props {
  citations: Citation[];
  activeLabel: string | null;
  onSelect: (label: string) => void;
}

export function CitationPanel({ citations, activeLabel, onSelect }: Props) {
  const refs = useRef(new Map<string, HTMLLIElement>());

  useEffect(() => {
    if (activeLabel) refs.current.get(activeLabel)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeLabel]);

  if (!citations.length) {
    return (
      <p className="p-4 text-sm text-slate-500">
        Sources for the selected answer appear here. Click a citation chip like{" "}
        <span className="rounded bg-indigo-500/20 px-1 text-xs text-indigo-200">S1</span> to jump to its passage.
      </p>
    );
  }
  return (
    <ul className="space-y-2 p-3" aria-label="Sources">
      {citations.map((c) => {
        const active = c.label === activeLabel;
        return (
          <li
            key={c.label}
            ref={(el) => {
              if (el) refs.current.set(c.label, el);
              else refs.current.delete(c.label);
            }}
          >
            <article
              className={`rounded-lg border p-3 transition-colors ${
                active ? "border-indigo-500 bg-indigo-500/10" : "border-slate-800 bg-slate-900/60"
              }`}
            >
              <header className="flex items-center justify-between gap-2">
                <button
                  type="button"
                  onClick={() => onSelect(c.label)}
                  className="flex min-w-0 items-center gap-2 text-left"
                  aria-pressed={active}
                >
                  <span className="shrink-0 rounded bg-indigo-500/25 px-1.5 text-xs font-semibold text-indigo-200">
                    {c.label}
                  </span>
                  <span className="truncate text-sm font-medium text-slate-200" title={c.document_name}>
                    {c.document_name}
                  </span>
                </button>
                <a
                  href={api.fileUrl(c.document_id, c.page_number)}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-xs text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  aria-label={`Open ${c.document_name} at page ${c.page_number}`}
                >
                  p. {c.page_number} <ExternalIcon width={13} height={13} />
                </a>
              </header>
              <blockquote className="mt-2 border-l-2 border-slate-700 pl-2 text-xs leading-relaxed text-slate-400">
                {c.excerpt}
              </blockquote>
              <p className="mt-1.5 text-[10px] uppercase tracking-wide text-slate-600">
                relevance {c.score.toFixed(2)}
              </p>
            </article>
          </li>
        );
      })}
    </ul>
  );
}
