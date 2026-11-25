import { useCallback, useEffect, useMemo, useState } from "react";
import { CitationPanel } from "./components/CitationPanel";
import { ChatPanel } from "./components/ChatPanel";
import { DocumentList } from "./components/DocumentList";
import { CloseIcon, MenuIcon } from "./components/Icons";
import { UploadZone } from "./components/UploadZone";
import { api, ApiError } from "./lib/api";
import type { ChatMessage, ChatMode, DocumentInfo, Health } from "./lib/types";

const uid = () => Math.random().toString(36).slice(2, 10);
const errMsg = (e: unknown) => (e instanceof ApiError || e instanceof Error ? e.message : "Unexpected error");

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [docsLoading, setDocsLoading] = useState(true);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [uploading, setUploading] = useState(false);
  const [toasts, setToasts] = useState<{ id: string; text: string; kind: "error" | "info" }[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [mode, setMode] = useState<ChatMode>("ask");
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [activeLabel, setActiveLabel] = useState<string | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(false);

  const toast = useCallback((text: string, kind: "error" | "info" = "error") => {
    const id = uid();
    setToasts((t) => [...t, { id, text, kind }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);

  const refreshDocs = useCallback(async () => {
    try {
      const docs = await api.listDocuments();
      setDocuments(docs);
      setSelected((sel) => new Set([...sel].filter((id) => docs.some((d) => d.id === id && d.status === "ready"))));
    } catch (e) {
      toast(errMsg(e));
    } finally {
      setDocsLoading(false);
    }
  }, [toast]);

  // Check backend health on load, and keep retrying while it is unreachable.
  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const check = async () => {
      try {
        const h = await api.health();
        if (cancelled) return;
        setHealth(h);
        setHealthError(null);
        void refreshDocs();
      } catch (e) {
        if (cancelled) return;
        setHealthError(errMsg(e));
        timer = setTimeout(check, 4000);
      }
    };
    void check();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [refreshDocs]);

  // Poll while any document is still being indexed.
  const anyProcessing = documents.some((d) => d.status === "processing");
  useEffect(() => {
    if (!anyProcessing) return;
    const t = setInterval(() => void refreshDocs(), 1500);
    return () => clearInterval(t);
  }, [anyProcessing, refreshDocs]);

  const onFiles = async (files: File[]) => {
    setUploading(true);
    for (const f of files) {
      try {
        await api.uploadDocument(f);
        toast(`Uploaded ${f.name}. Indexing…`, "info");
      } catch (e) {
        toast(`${f.name}: ${errMsg(e)}`);
      }
    }
    setUploading(false);
    void refreshDocs();
  };

  const onDelete = async (doc: DocumentInfo) => {
    if (!window.confirm(`Delete "${doc.filename}"? This removes the file and its index.`)) return;
    try {
      await api.deleteDocument(doc.id);
      toast(`Deleted ${doc.filename}`, "info");
      void refreshDocs();
    } catch (e) {
      toast(errMsg(e));
    }
  };

  const onReindex = async (doc: DocumentInfo) => {
    try {
      await api.reindexDocument(doc.id);
      void refreshDocs();
    } catch (e) {
      toast(errMsg(e));
    }
  };

  const toggle = (id: string) =>
    setSelected((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });

  const readyDocs = documents.filter((d) => d.status === "ready");
  const scopeLabel = selected.size
    ? `${selected.size} selected document${selected.size > 1 ? "s" : ""}`
    : `all ${readyDocs.length} document${readyDocs.length === 1 ? "" : "s"}`;
  const llmReady = !!health?.llm_configured;
  const agentAvailable = llmReady && health?.llm_provider === "anthropic";

  const disabledReason = healthError
    ? "Backend unavailable"
    : !readyDocs.length
      ? anyProcessing
        ? "Indexing your document…"
        : health?.demo_mode
          ? "No sample documents are loaded"
          : "Upload a PDF to start asking questions"
      : null;

  const send = async (question: string) => {
    const userMsg: ChatMessage = { id: uid(), role: "user", content: question };
    const history = messages
      .filter((m) => !m.error)
      .map((m) => ({ role: m.role, content: m.role === "assistant" ? (m.response?.answer ?? "") : m.content }))
      .filter((m) => m.content)
      .slice(-8);
    setMessages((ms) => [...ms, userMsg]);
    setPending(true);
    try {
      const response = await api.ask({
        question,
        document_ids: selected.size ? [...selected] : null,
        history,
        mode,
      });
      const msg: ChatMessage = { id: uid(), role: "assistant", content: response.answer, response, mode };
      setMessages((ms) => [...ms, msg]);
      setActiveMessageId(msg.id);
      setActiveLabel(null);
    } catch (e) {
      setMessages((ms) => [...ms, { id: uid(), role: "assistant", content: "", error: errMsg(e) }]);
    } finally {
      setPending(false);
      // Keep the demo's "questions left today" counter current.
      if (health?.demo_mode) api.health().then(setHealth).catch(() => {});
    }
  };

  const activeCitations = useMemo(
    () => messages.find((m) => m.id === activeMessageId)?.response?.citations ?? [],
    [messages, activeMessageId],
  );

  const onCite = (messageId: string, label: string) => {
    setActiveMessageId(messageId);
    setActiveLabel(label);
    setSourcesOpen(true);
  };

  const maxMb = health?.limits.max_upload_mb ?? 25;
  const demo = !!health?.demo_mode;
  const questionsLeft = health?.limits.daily_questions_remaining;

  const sidebar = (
    <div className="flex h-full flex-col gap-4 p-4">
      <div className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500 font-bold text-white">D</div>
        <div>
          <h1 className="text-base font-semibold leading-tight text-white">DocuMind AI</h1>
          <p className="text-[11px] text-slate-500">Grounded document research</p>
        </div>
      </div>
      {demo ? (
        <div className="rounded-xl border border-indigo-500/30 bg-indigo-500/10 p-3 text-xs text-indigo-100" role="note">
          <p className="font-semibold">Live demo</p>
          <p className="mt-1 text-indigo-200/80">
            Ask questions about the sample documents below. Uploading and deleting are turned off in
            this public demo.
          </p>
        </div>
      ) : (
        <UploadZone maxMb={maxMb} uploading={uploading} onFiles={onFiles} onError={toast} />
      )}
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-500">Library</h2>
        {selected.size > 0 && (
          <button type="button" className="text-xs text-indigo-300 hover:text-indigo-200" onClick={() => setSelected(new Set())}>
            Clear selection
          </button>
        )}
      </div>
      <div className="-mr-2 min-h-0 flex-1 overflow-y-auto pr-2">
        <DocumentList
          documents={documents}
          loading={docsLoading}
          selected={selected}
          onToggle={toggle}
          onDelete={onDelete}
          onReindex={onReindex}
          readOnly={demo}
        />
      </div>
      <footer className="space-y-1 border-t border-slate-800 pt-3 text-[11px] text-slate-500">
        {healthError ? (
          <p className="text-rose-300">⚠ {healthError}</p>
        ) : health ? (
          <>
            <p>
              LLM:{" "}
              <span className={llmReady ? "text-emerald-300" : "text-amber-300"}>
                {health.llm_provider === "extractive"
                  ? "retrieval-only (no LLM)"
                  : llmReady
                    ? health.model
                    : "not configured"}
              </span>
            </p>
            <p>Embeddings: {health.embedding_model}</p>
            {questionsLeft !== undefined && <p>Questions left today: {questionsLeft}</p>}
          </>
        ) : (
          <p>Connecting…</p>
        )}
      </footer>
    </div>
  );

  return (
    <div className="flex h-dvh overflow-hidden bg-slate-950">
      <a href="#question" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-50 focus:rounded focus:bg-indigo-600 focus:px-3 focus:py-1.5">
        Skip to question
      </a>

      {/* Sidebar: static on lg, drawer on small screens */}
      <aside className="hidden w-80 shrink-0 border-r border-slate-800 bg-slate-950 lg:block" aria-label="Documents">
        {sidebar}
      </aside>
      {sidebarOpen && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label="Documents">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSidebarOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-80 max-w-[85vw] border-r border-slate-800 bg-slate-950">
            <button type="button" className="absolute right-3 top-4 text-slate-400" onClick={() => setSidebarOpen(false)} aria-label="Close documents">
              <CloseIcon />
            </button>
            {sidebar}
          </aside>
        </div>
      )}

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between border-b border-slate-800 px-4 py-2.5 lg:hidden">
          <button type="button" onClick={() => setSidebarOpen(true)} className="text-slate-300" aria-label="Open documents">
            <MenuIcon />
          </button>
          <span className="text-sm font-semibold">DocuMind AI</span>
          <button type="button" onClick={() => setSourcesOpen(true)} className="text-xs text-indigo-300" aria-label="Open sources">
            Sources ({activeCitations.length})
          </button>
        </header>
        {health && !llmReady && health.llm_provider === "anthropic" && (
          <div className="border-b border-amber-500/30 bg-amber-500/10 px-4 py-2 text-xs text-amber-200" role="status">
            ANTHROPIC_API_KEY is not set on the server. Add it to <code>.env</code> and restart the backend, or set{" "}
            <code>LLM_PROVIDER=extractive</code> for offline passage retrieval.
          </div>
        )}
        <div className="min-h-0 flex-1">
          <ChatPanel
            messages={messages}
            pending={pending}
            disabledReason={disabledReason}
            mode={mode}
            agentAvailable={agentAvailable}
            scopeLabel={scopeLabel}
            activeMessageId={activeMessageId}
            activeLabel={activeLabel}
            maxChars={health?.limits.max_question_chars ?? 2000}
            suggestions={health?.suggested_questions}
            onModeChange={setMode}
            onSend={send}
            onCite={onCite}
            onSelectMessage={(id) => setActiveMessageId(id)}
          />
        </div>
      </main>

      <aside
        className={`${sourcesOpen ? "fixed inset-y-0 right-0 z-40 w-96 max-w-[90vw] shadow-2xl" : "hidden"} border-l border-slate-800 bg-slate-950 xl:static xl:block xl:w-96 xl:shadow-none`}
        aria-label="Sources panel"
      >
        <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-200">Sources</h2>
          <button type="button" className="text-slate-400 xl:hidden" onClick={() => setSourcesOpen(false)} aria-label="Close sources">
            <CloseIcon />
          </button>
        </div>
        <div className="h-[calc(100%-49px)] overflow-y-auto">
          <CitationPanel citations={activeCitations} activeLabel={activeLabel} onSelect={setActiveLabel} />
        </div>
      </aside>

      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex max-w-sm flex-col gap-2" aria-live="assertive">
        {toasts.map((t) => (
          <div
            key={t.id}
            role={t.kind === "error" ? "alert" : "status"}
            className={`pointer-events-auto rounded-lg border px-3 py-2 text-sm shadow-lg ${
              t.kind === "error" ? "border-rose-500/40 bg-rose-950 text-rose-100" : "border-slate-700 bg-slate-900 text-slate-100"
            }`}
          >
            {t.text}
          </div>
        ))}
      </div>
    </div>
  );
}
