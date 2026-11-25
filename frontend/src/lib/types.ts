export type DocStatus = "processing" | "ready" | "failed";

export interface DocumentInfo {
  id: string;
  filename: string;
  size_bytes: number;
  page_count: number;
  chunk_count: number;
  status: DocStatus;
  error: string | null;
  stale_index: boolean;
  created_at: string;
  updated_at: string;
}

export interface Citation {
  label: string;
  document_id: string;
  document_name: string;
  page_number: number;
  excerpt: string;
  score: number;
}

export interface ToolTrace {
  tool: string;
  input: Record<string, unknown>;
  summary: string;
  is_error: boolean;
}

export interface AskResponse {
  answer: string;
  citations: Citation[];
  insufficient_evidence: boolean;
  provider: string;
  model: string | null;
  tool_trace: ToolTrace[];
  warnings: string[];
}

export interface Health {
  status: string;
  llm_provider: string;
  llm_configured: boolean;
  model: string | null;
  embedding_model: string;
  documents: number;
  indexed_chunks: number;
  demo_mode: boolean;
  suggested_questions: string[];
  limits: Record<string, number>;
}

export type ChatMode = "ask" | "agent";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  response?: AskResponse;
  error?: string;
  mode?: ChatMode;
}
