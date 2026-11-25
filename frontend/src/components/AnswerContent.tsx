import ReactMarkdown from "react-markdown";
import { citationLabelFromHref, linkifyCitations } from "../lib/citations";
import type { Citation } from "../lib/types";

interface Props {
  answer: string;
  citations: Citation[];
  activeLabel: string | null;
  onCite: (label: string) => void;
}

export function AnswerContent({ answer, citations, activeLabel, onCite }: Props) {
  const byLabel = new Map(citations.map((c) => [c.label, c]));
  return (
    <div className="prose-answer text-sm leading-relaxed text-slate-200">
      <ReactMarkdown
        skipHtml
        components={{
          a: ({ href, children }) => {
            const label = citationLabelFromHref(href);
            const cite = label ? byLabel.get(label) : undefined;
            if (label && cite) {
              const active = label === activeLabel;
              return (
                <button
                  type="button"
                  onClick={() => onCite(label)}
                  className={`mx-0.5 inline-flex items-center rounded-md px-1.5 py-px align-baseline text-[11px] font-semibold transition-colors ${
                    active
                      ? "bg-indigo-500 text-white"
                      : "bg-indigo-500/20 text-indigo-200 hover:bg-indigo-500/40"
                  }`}
                  aria-label={`Citation ${label}: ${cite.document_name}, page ${cite.page_number}`}
                  title={`${cite.document_name} · p. ${cite.page_number}`}
                >
                  {label}
                </button>
              );
            }
            // Non-citation links from model output: render as plain text (no navigation).
            return <span>{children}</span>;
          },
          img: () => null,
        }}
      >
        {linkifyCitations(answer, citations)}
      </ReactMarkdown>
    </div>
  );
}
