import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import App from "../App";

const health = {
  status: "ok", llm_provider: "anthropic", llm_configured: true, model: "claude-opus-5-5",
  embedding_model: "hash-v1-1024", documents: 1, indexed_chunks: 3, demo_mode: false, suggested_questions: [],
  limits: { max_upload_mb: 25, max_pages: 500, max_question_chars: 2000, rate_limit_per_minute: 30 },
};
const doc = {
  id: "a".repeat(32), filename: "solar.pdf", size_bytes: 2048, page_count: 3, chunk_count: 3,
  status: "ready", error: null, stale_index: false, created_at: "", updated_at: "",
};

type Handler = (url: string, init?: RequestInit) => { status?: number; body?: unknown };

function mockFetch(handler: Handler) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const { status = 200, body } = handler(url, init);
    return new Response(status === 204 ? null : JSON.stringify(body), {
      status, headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => vi.unstubAllGlobals());

describe("App", () => {
  it("asks a question and shows a grounded answer with citations", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (url === "/api/health") return { body: health };
      if (url === "/api/documents") return { body: { documents: [doc] } };
      if (url === "/api/chat") {
        const req = JSON.parse(String(init?.body));
        expect(req.question).toBe("How efficient are panels?");
        expect(req.mode).toBe("ask");
        return {
          body: {
            answer: "Monocrystalline panels reach 20-23% [S1].",
            citations: [{ label: "S1", document_id: doc.id, document_name: "solar.pdf", page_number: 2, excerpt: "Monocrystalline silicon panels typically reach 20 to 23 percent", score: 0.7 }],
            insufficient_evidence: false, provider: "anthropic", model: "claude-opus-5-5", tool_trace: [], warnings: [],
          },
        };
      }
      return { status: 404, body: { detail: "nope" } };
    });

    render(<App />);
    expect(await screen.findByText("solar.pdf")).toBeInTheDocument();
    const box = screen.getByLabelText("Ask a question");
    await waitFor(() => expect(box).not.toBeDisabled());
    await userEvent.type(box, "How efficient are panels?{Enter}");

    const chip = await screen.findByRole("button", { name: "Citation S1: solar.pdf, page 2" });
    await userEvent.click(chip);
    expect(screen.getByRole("link", { name: "Open solar.pdf at page 2" })).toHaveAttribute(
      "href", `/api/documents/${doc.id}/file#page=2`,
    );
    expect(screen.getByText(/Monocrystalline silicon panels typically/)).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith("/api/chat", expect.objectContaining({ method: "POST" }));
  });

  it("shows the insufficient-evidence state and API errors", async () => {
    let call = 0;
    mockFetch((url) => {
      if (url === "/api/health") return { body: health };
      if (url === "/api/documents") return { body: { documents: [doc] } };
      call += 1;
      if (call === 1) {
        return { body: { answer: "The documents don't cover pricing.", citations: [], insufficient_evidence: true,
          provider: "anthropic", model: "m", tool_trace: [], warnings: [] } };
      }
      return { status: 429, body: { detail: "Rate limit exceeded. Please slow down." } };
    });
    render(<App />);
    const box = await screen.findByLabelText("Ask a question");
    await waitFor(() => expect(box).not.toBeDisabled());
    await userEvent.type(box, "price?{Enter}");
    expect(await screen.findByText("Insufficient evidence in documents")).toBeInTheDocument();
    await userEvent.type(box, "again{Enter}");
    expect(await screen.findByText(/Rate limit exceeded/)).toBeInTheDocument();
  });

  it("disables chat until a document is ready and warns when the key is missing", async () => {
    mockFetch((url) => {
      if (url === "/api/health") return { body: { ...health, llm_configured: false } };
      return { body: { documents: [] } };
    });
    render(<App />);
    expect(await screen.findByText(/ANTHROPIC_API_KEY is not set/)).toBeInTheDocument();
    expect(screen.getByLabelText("Ask a question")).toBeDisabled();
    expect(screen.getByText(/No documents yet/)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: "Research agent" })).toBeDisabled();
  });

  it("rejects non-PDF uploads client-side", async () => {
    const fetchMock = mockFetch((url) => (url === "/api/health" ? { body: health } : { body: { documents: [] } }));
    render(<App />);
    const input = document.getElementById("pdf-upload") as HTMLInputElement;
    await userEvent.upload(input, new File(["hello"], "notes.txt", { type: "text/plain" }), { applyAccept: false });
    expect(await screen.findByText(/"notes.txt" is not a PDF/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalledWith("/api/documents", expect.objectContaining({ method: "POST" }));
  });

  it("shows a read-only library and demo questions in demo mode", async () => {
    let healthCalls = 0;
    mockFetch((url) => {
      if (url === "/api/health") {
        healthCalls += 1;
        return {
          body: {
            ...health, demo_mode: true,
            suggested_questions: ["How much is the home office stipend?"],
            limits: { ...health.limits, daily_questions_remaining: healthCalls === 1 ? 200 : 199 },
          },
        };
      }
      if (url === "/api/documents") return { body: { documents: [doc] } };
      return { body: { answer: "750 USD [S1].", citations: [{ label: "S1", document_id: doc.id,
        document_name: "solar.pdf", page_number: 3, excerpt: "stipend of 750", score: 0.6 }],
        insufficient_evidence: false, provider: "anthropic", model: "m", tool_trace: [], warnings: [] } };
    });
    render(<App />);
    expect(await screen.findByText("Live demo")).toBeInTheDocument();
    expect(document.getElementById("pdf-upload")).toBeNull();
    expect(await screen.findByText("solar.pdf")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Delete solar.pdf/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Re-index solar.pdf/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Open solar.pdf" })).toBeInTheDocument();
    expect(screen.getByText("Questions left today: 200")).toBeInTheDocument();

    const box = screen.getByLabelText("Ask a question");
    await waitFor(() => expect(box).not.toBeDisabled());
    await userEvent.click(screen.getByRole("button", { name: "How much is the home office stipend?" }));
    expect(box).toHaveValue("How much is the home office stipend?");
    expect(box).toHaveFocus();
    await userEvent.type(box, "{Enter}");
    expect(await screen.findByRole("button", { name: /Citation S1/ })).toBeInTheDocument();
    expect(await screen.findByText("Questions left today: 199")).toBeInTheDocument();
  });
});
