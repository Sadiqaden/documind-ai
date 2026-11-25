import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { ChatMessage, ChatMode } from "../lib/types";
import { AnswerContent } from "./AnswerContent";
import { SendIcon, SparkIcon, Spinner } from "./Icons";

interface Props {
  messages: ChatMessage[];
  pending: boolean;
  disabledReason: string | null;
  mode: ChatMode;
  agentAvailable: boolean;
  scopeLabel: string;
  activeMessageId: string | null;
  activeLabel: string | null;
  maxChars: number;
  suggestions?: string[];
  onModeChange: (m: ChatMode) => void;
  onSend: (q: string) => void;
  onCite: (messageId: string, label: string) => void;
  onSelectMessage: (messageId: string) => void;
}

const SUGGESTIONS = [
  "Summarize the key findings of this document.",
  "What are the main recommendations?",
  "List any numbers or statistics mentioned.",
];

export function ChatPanel(p: Props) {
  const [draft, setDraft] = useState("");
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [p.messages.length, p.pending]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    const q = draft.trim();
    if (!q || p.pending || p.disabledReason) return;
    p.onSend(q);
    setDraft("");
  };

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <section className="flex h-full min-h-0 flex-col" aria-label="Chat">
      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-6 sm:px-8" aria-live="polite">
        {!p.messages.length && (
          <div className="mx-auto mt-10 max-w-xl text-center">
            <SparkIcon width={32} height={32} className="mx-auto text-indigo-400" />
            <h2 className="mt-3 text-xl font-semibold text-slate-100">Ask your documents anything</h2>
            <p className="mt-2 text-sm text-slate-400">
              Answers are grounded in your PDFs with page-level citations. If the documents don't
              contain the answer, DocuMind will say so.
            </p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {(p.suggestions?.length ? p.suggestions : SUGGESTIONS).map((s) => (
                <button
                  key={s}
                  type="button"
                  disabled={!!p.disabledReason}
                  onClick={() => {
                    setDraft(s);
                    inputRef.current?.focus();
                  }}
                  className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 hover:border-indigo-500 hover:text-white disabled:opacity-40"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        <ol className="mx-auto max-w-3xl space-y-5">
          {p.messages.map((m) => (
            <li key={m.id} className={m.role === "user" ? "flex justify-end" : "flex justify-start"}>
              {m.role === "user" ? (
                <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-indigo-600 px-4 py-2.5 text-sm text-white">
                  {m.content}
                </div>
              ) : (
                <div
                  className={`w-full max-w-[95%] rounded-2xl rounded-bl-sm border px-4 py-3 ${
                    p.activeMessageId === m.id ? "border-indigo-500/60" : "border-slate-800"
                  } bg-slate-900`}
                  onClick={() => p.onSelectMessage(m.id)}
                >
                  {m.error ? (
                    <p className="text-sm text-rose-300" role="alert">⚠ {m.error}</p>
                  ) : m.response ? (
                    <>
                      {m.response.insufficient_evidence && (
                        <p className="mb-2 inline-block rounded bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-300">
                          Insufficient evidence in documents
                        </p>
                      )}
                      <AnswerContent
                        answer={m.response.answer}
                        citations={m.response.citations}
                        activeLabel={p.activeMessageId === m.id ? p.activeLabel : null}
                        onCite={(label) => p.onCite(m.id, label)}
                      />
                      {m.response.tool_trace.length > 0 && (
                        <details className="mt-3 text-xs text-slate-400">
                          <summary className="cursor-pointer select-none hover:text-slate-200">
                            Agent steps ({m.response.tool_trace.length})
                          </summary>
                          <ol className="mt-1.5 space-y-1 border-l border-slate-700 pl-3">
                            {m.response.tool_trace.map((t, i) => (
                              <li key={i} className={t.is_error ? "text-rose-300" : ""}>
                                <code className="text-indigo-300">{t.tool}</code> — {t.summary}
                              </li>
                            ))}
                          </ol>
                        </details>
                      )}
                      {m.response.warnings.map((w) => (
                        <p key={w} className="mt-2 text-xs text-amber-300">⚠ {w}</p>
                      ))}
                      <p className="mt-2 text-[10px] uppercase tracking-wide text-slate-600">
                        {m.mode === "agent" ? "agent · " : ""}
                        {m.response.provider === "extractive" ? "retrieval only" : m.response.provider}
                        {m.response.model ? ` · ${m.response.model}` : ""} · {m.response.citations.length} sources
                      </p>
                    </>
                  ) : null}
                </div>
              )}
            </li>
          ))}
          {p.pending && (
            <li className="flex items-center gap-2 text-sm text-slate-400" role="status">
              <Spinner className="text-indigo-400" />
              {p.mode === "agent" ? "Researching with tools…" : "Searching documents and drafting an answer…"}
            </li>
          )}
        </ol>
        <div ref={endRef} />
      </div>

      <form onSubmit={submit} className="border-t border-slate-800 bg-slate-950/80 px-4 py-3 sm:px-8">
        <div className="mx-auto max-w-3xl">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs">
            <div role="radiogroup" aria-label="Answer mode" className="inline-flex rounded-lg border border-slate-800 p-0.5">
              {(["ask", "agent"] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  role="radio"
                  aria-checked={p.mode === m}
                  disabled={m === "agent" && !p.agentAvailable}
                  onClick={() => p.onModeChange(m)}
                  title={m === "agent" && !p.agentAvailable ? "The research agent needs a Claude API key" : undefined}
                  className={`rounded-md px-2.5 py-1 font-medium transition-colors disabled:opacity-40 ${
                    p.mode === m ? "bg-slate-800 text-white" : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {m === "ask" ? "Quick answer" : "Research agent"}
                </button>
              ))}
            </div>
            <span className="text-slate-500">Searching: {p.scopeLabel}</span>
          </div>
          <div className="flex items-end gap-2 rounded-xl border border-slate-700 bg-slate-900 p-2 focus-within:border-indigo-500">
            <label htmlFor="question" className="sr-only">Ask a question</label>
            <textarea
              id="question"
              ref={inputRef}
              rows={1}
              value={draft}
              maxLength={p.maxChars}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={onKey}
              disabled={!!p.disabledReason}
              placeholder={p.disabledReason ?? "Ask a question about your documents…"}
              className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:outline-none disabled:cursor-not-allowed"
            />
            <button
              type="submit"
              disabled={!draft.trim() || p.pending || !!p.disabledReason}
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-500"
              aria-label="Send question"
            >
              {p.pending ? <Spinner /> : <SendIcon />}
            </button>
          </div>
          <p className="mt-1.5 text-[11px] text-slate-600">
            Enter to send · Shift+Enter for a new line · AI answers can be wrong — verify with the cited pages.
          </p>
        </div>
      </form>
    </section>
  );
}
