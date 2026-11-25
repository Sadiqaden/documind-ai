# DocuMind AI

An AI document research assistant. Upload PDFs, ask questions, and get answers grounded in your
documents, with clickable citations that go to the exact document and page.

- **Quick answer mode**: one retrieval pass, then one Claude call that must cite its sources.
- **Research agent mode**: Claude uses explicit, bounded tools (`list_documents`,
  `search_documents`, `read_document`) to search and summarize across documents.
- **Citations are enforced on the server.** The model can only cite passage IDs it was actually
  shown. The backend removes any other citation before the answer reaches the UI, and maps the rest
  to real file names and page numbers. When the evidence is weak, the assistant says so.

## Architecture

```
┌────────────── Frontend (React + TS + Vite + Tailwind) ──────────────┐
│ Sidebar: upload zone, document library (select / re-index / delete) │
│ Chat: quick answer | research agent, Markdown answers, citation chips│
│ Sources panel: excerpt, relevance, "open PDF at page N" deep link    │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ /api (no secrets in the browser)
┌───────────────────────────────▼──────────────────────────────────────┐
│ FastAPI backend                                                      │
│  api/documents.py  upload → validate → store as <uuid>.pdf           │
│                    → BackgroundTask: Indexer                         │
│  services/pdf.py        pypdf text extraction, per page              │
│  services/chunking.py   sentence-packed chunks, never span pages     │
│  services/embeddings.py hash (default, offline) | fastembed (semantic)│
│  services/vector_store  numpy cosine + keyword hybrid over SQLite    │
│  services/qa.py         retrieve → threshold → Claude → validate     │
│  services/agent.py      bounded tool loop (steps/tools/output caps)  │
│  services/citations.py  S# source registry + citation validation     │
│  services/llm.py        Anthropic SDK provider (key stays here)      │
│  ratelimit.py           per-IP sliding-window limiter                │
│  SQLite: documents, pages, chunks (+ float32 embedding BLOBs)        │
└──────────────────────────────────────────────────────────────────────┘
```

**Request flow (quick answer).** Embed the question, run hybrid search (70% cosine + 30% keyword
coverage), and drop hits below `MIN_RELEVANCE` or below 30% of the best score. If nothing is left,
the server returns "insufficient evidence" **without calling the LLM**. Otherwise the passages go
to Claude as `<source id="S1" document="x.pdf" page="3">` blocks. Claude answers with `[S#]`
markers, or starts with `INSUFFICIENT_EVIDENCE`. The server then checks every marker against the
registry, removes unknown ones (and adds a warning), and returns structured citations.

**Agent bounds.** `AGENT_MAX_STEPS` model calls at most (default 5). At most 4 tool calls run per
step; extra calls get an error result. Search returns at most 8 passages, and a page read covers
at most 5 pages and 12k characters. Each request registers at most 60 sources. On the last step the
model is told the tool budget is used up. Tool schemas use `strict: true` with
`additionalProperties: false`, and the server also validates tool inputs. The agent only sees the
documents the user selected.

**Claude settings.** The default model is `claude-opus-5-5` with adaptive thinking and
`output_config.effort` (default `medium`, configurable). Refusal fallback is on by default: the
`server-side-fallback-2026-07-01` beta with `fallbacks: "default"`, so a safety decline is retried
on a fallback model. Turn it off with `ANTHROPIC_REFUSAL_FALLBACK=false`. A `refusal` stop reason
shows up as insufficient evidence.

## Setup (local development)

Requirements: Python 3.11+, Node 20+.

```bash
cp .env.example .env          # then set ANTHROPIC_API_KEY in .env
```

Backend:

```bash
cd backend
python3.12 -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/uvicorn app.main:app --reload --port 8000
```

(If you use `uv`: `uv venv -p 3.12 .venv && uv pip install -p .venv -e ".[dev]"`.)

Frontend (proxies `/api` to `localhost:8000`):

```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173
```

Sample documents live in `backend/demo_docs/` (a fictional remote-work policy and a solar energy
primer). Upload them to try the app, or regenerate them with:

```bash
backend/.venv/bin/python samples/make_sample_pdf.py   # writes backend/demo_docs/*.pdf
```

### Two answer modes

| Mode | Setting | Cost | What a question returns |
|---|---|---|---|
| **Claude** | `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` | Pay per question | A written answer with `[S#]` citations; research agent available |
| **Retrieval-only** | `LLM_PROVIDER=extractive` | Free, no key | The most relevant passages quoted exactly, each with a page citation |

Retrieval-only mode runs the same pipeline (extraction, chunking, embeddings, hybrid search,
relevance thresholds, citation validation) and stops before the LLM call. The public demo of this
project runs in this mode. To switch to Claude, add a key, set `LLM_PROVIDER=anthropic` and
restart; no code changes are needed.

## Configuration

All settings are environment variables (see [.env.example](.env.example)). The backend reads `.env`
from `backend/` or the repo root.

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `anthropic` | `anthropic` or `extractive` (retrieval-only, free) |
| `ANTHROPIC_API_KEY` | – | **Required** for `anthropic`. Backend only. |
| `ANTHROPIC_MODEL` | `claude-opus-5-5` | Claude model ID |
| `ANTHROPIC_EFFORT` | `medium` | `low`…`max`; trades depth for cost/latency |
| `ANTHROPIC_MAX_TOKENS` | `16000` | Output cap per call |
| `ANTHROPIC_REFUSAL_FALLBACK` | `true` | Server-side refusal fallback (beta) |
| `EMBEDDING_PROVIDER` | `hash` | `hash` (offline) or `fastembed` (semantic) |
| `MAX_UPLOAD_MB` / `MAX_PAGES` | `25` / `500` | Upload limits |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | `1000` / `150` | Characters |
| `TOP_K` / `MIN_RELEVANCE` | `6` / `0.08` | Retrieval breadth and floor |
| `RATE_LIMIT_PER_MINUTE` | `30` | Chat/search per IP (uploads: half) |
| `AGENT_MAX_STEPS` | `5` | Max model calls per agent run |
| `CORS_ORIGINS` | `http://localhost:5173,…` | Allowed browser origins |

**Semantic embeddings:** run `pip install -e ".[semantic]"`, set `EMBEDDING_PROVIDER=fastembed`,
restart, then re-index your documents (they are flagged "stale"). The first run downloads the
`BAAI/bge-small-en-v1.5` ONNX model.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Provider/model status and limits (never returns secrets) |
| `GET` | `/api/documents` | List documents |
| `POST` | `/api/documents` | Upload a PDF (multipart `file`) → `202`, indexed in background |
| `GET` | `/api/documents/{id}` | Document status |
| `GET` | `/api/documents/{id}/file` | The PDF (inline; supports `#page=N`) |
| `POST` | `/api/documents/{id}/reindex` | Re-extract, re-chunk, re-embed |
| `DELETE` | `/api/documents/{id}` | Delete file and index |
| `POST` | `/api/chat` | `{question, document_ids?, history?, mode: "ask"\|"agent"}` |
| `POST` | `/api/search` | Raw retrieval results (debugging) |

Interactive docs are at `http://localhost:8000/docs`.

## Testing

```bash
cd backend && .venv/bin/pytest            # 65 tests
cd backend && .venv/bin/ruff check app tests && .venv/bin/mypy app
cd frontend && npm test                   # 16 tests (Vitest + Testing Library)
cd frontend && npm run lint && npm run typecheck && npm run build
```

What the tests cover:

- **PDF**: safe filenames (path traversal, unicode, HTML), magic bytes, size and page limits,
  encrypted, corrupt and text-free PDFs, page-number preservation.
- **Chunking**: size limits, overlap, chunks never crossing pages.
- **Retrieval**: the correct document *and page* ranks first; document filtering; off-topic queries
  fall below the threshold; deleted documents leave the index.
- **Citation validation**: invented labels are stripped, real labels map to the right document and
  page, ordering and deduplication are correct, malformed markers are ignored.
- **QA**: no LLM call when nothing relevant is found, insufficient-evidence handling, warnings for
  uncited answers, offline extractive mode.
- **Agent**: strict tool schemas, search→answer and summarize flows, the step limit, the per-step
  tool cap, tool errors, document-selection enforcement.
- **Demo mode**: sample documents load at startup (idempotent, repairs failed ones), the library
  is read-only (403), the daily question cap, the question-length limit, and the agent step cap.
- **API**: the full upload→index→chat→delete lifecycle, 413/415/400/404/422/429/503, re-indexing,
  no secret leakage in `/api/health`.
- **Frontend**: citation chips and deep links, Markdown rendering (no raw HTML or external links),
  insufficient-evidence and error states, a disabled chat with a missing key or no documents, and
  client-side upload validation, and the read-only demo layout.

LLM calls in tests go through a scripted `FakeLLM`. The tests never touch the network or need a key.

## Screenshots

To add screenshots to this README:

1. Start the app (demo mode loads the sample documents for you), or upload the PDFs from
   `backend/demo_docs/`.
2. Ask something like *"How much is the home office stipend?"* and click a citation chip.
3. Take a 1440×900 browser screenshot. Save it as `docs/screenshot-chat.png` and add
   `![Chat](docs/screenshot-chat.png)` here. Good extra shots: the library with
   processing/failed states, and a research-agent answer with its "Agent steps" expanded.

## Public demo mode

For a public portfolio demo, set `DEMO_MODE=true`. Visitors can ask questions and open citations,
but they can't change anything, and your API spend is capped:

| Setting | Default | Effect |
|---|---|---|
| `DEMO_MODE` | `false` | Turns demo mode on |
| `DEMO_DOCS_DIR` | `./demo_docs` | PDFs indexed at startup (baked into the Docker image) |
| `DEMO_RATE_LIMIT_PER_MINUTE` | `6` | Questions/searches per visitor IP per minute |
| `DEMO_DAILY_QUESTION_LIMIT` | `200` | Questions per UTC day **across all visitors** |
| `DEMO_MAX_QUESTION_CHARS` | `500` | Longest question accepted |
| `DEMO_AGENT_MAX_STEPS` | `3` | Model calls per research-agent answer |

In demo mode:
- Every PDF in `DEMO_DOCS_DIR` is indexed at startup. This is safe to repeat: existing documents
  are matched by filename and only re-indexed if they aren't ready.
- Upload, delete and re-index return `403`, and the UI hides those controls and shows a "Live demo"
  note, one-click sample questions and a "questions left today" counter.
- The daily cap is the main cost guard. Worst case per day is about `DEMO_DAILY_QUESTION_LIMIT`
  questions (agent answers make up to `DEMO_AGENT_MAX_STEPS` model calls each). **Also set a
  monthly spend limit for your key in the Anthropic Console**, because the counter resets when the
  server restarts.

To demo your own documents, put PDFs in `backend/demo_docs/` and edit `DEMO_QUESTIONS` in
`backend/app/services/demo.py` to match them.

## Deployment (Docker Compose)

```bash
cp .env.example .env    # set ANTHROPIC_API_KEY
docker compose up --build
# open http://localhost:8080
```

- `frontend`: nginx serves the built app and proxies `/api` to the backend (`client_max_body_size
  30m`, CSP and nosniff headers).
- `backend`: Python 3.12 slim, runs as a non-root user, single uvicorn worker. Data is stored in the
  `documind-data` volume. The backend is reachable only on the internal compose network.
- To deploy publicly as a portfolio demo: set `DEMO_MODE=true`, serve it over HTTPS (for example
  a reverse proxy such as Caddy, or your host's TLS), and set an Anthropic spend limit. Outside
  demo mode, put authentication in front of it. Keep `MAX_UPLOAD_MB` in sync with the nginx body
  limit.

## Security notes

- The API key is read only by the backend (`pydantic.SecretStr`). It is never logged or returned,
  and never bundled into the frontend. `.env` is git-ignored.
- Uploads: size is checked while reading (never more than limit + 1 byte in memory); `%PDF` magic,
  MIME type and extension are checked; files are stored under random UUID names; display names are
  sanitized.
- Document text is treated as untrusted. The prompts say source text is data, not instructions.
  Citations are checked on the server. The UI renders Markdown with raw HTML disabled, and links in
  model output don't navigate.
- These measures are reasonable for a portfolio or internal tool. They have **not** had a security
  audit, so don't treat this as production-hardened.

## Known limitations

- **No authentication or multi-tenancy.** Anyone who can reach the server sees all documents. For
  a public site use demo mode (read-only); for private documents, add auth first.
- **Default embeddings are lexical, not semantic.** The `hash` embedder matches words and
  sub-words, not synonyms. Questions worded differently from the text can rank the wrong page
  first, and an off-topic question that shares a common word (e.g. "policy") can still pass the
  threshold. Claude then answers `INSUFFICIENT_EVIDENCE`, but offline mode shows the passage. Use
  `EMBEDDING_PROVIDER=fastembed` for real semantic search.
- **No OCR.** Scanned or image-only PDFs are rejected with a clear error.
- **In-process limits.** The rate limiter and vector cache live in one process, so run a single
  worker. The brute-force numpy search suits roughly tens of thousands of chunks.
- **No streaming.** Answers arrive in full; long agent runs can take tens of seconds.
- Chat history lives only in the browser and is lost on reload.
- Indexing runs in FastAPI background tasks; a restart during indexing marks the document `failed`
  (re-index it).
- Citations point to pages, not exact text positions in the PDF viewer.

## Remaining manual setup

1. **Anthropic API key:** create one at console.anthropic.com and put `ANTHROPIC_API_KEY=...` in
   the repo-root `.env`. Without it, chat returns a clear 503 and the UI shows a banner. If the
   Docker stack is already running, apply the change with
   `docker compose up -d --force-recreate backend`.
2. Make sure your account can use `claude-opus-5-5`. If the refusal-fallback beta is rejected for
   your account, set `ANTHROPIC_REFUSAL_FALLBACK=false`.
3. Optional: install the `semantic` extra and switch to `fastembed`.
4. For a public deployment: `DEMO_MODE=true`, HTTPS, and a monthly spend limit on your Anthropic
   key (Console → Limits).
