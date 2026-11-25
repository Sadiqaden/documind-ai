import type { AskResponse, ChatMode, DocumentInfo, Health } from "./types";

const BASE = import.meta.env.VITE_API_BASE ?? "";

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("Cannot reach the DocuMind server. Is the backend running?", 0);
  }
  if (!res.ok) {
    let detail = `Request failed (HTTP ${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
    } catch {
      // Non-JSON body: typically the dev proxy / nginx when the backend is down.
      if ([502, 503, 504].includes(res.status)) detail = "Cannot reach the DocuMind server. Is the backend running?";
    }
    if (res.status === 429) {
      const retry = res.headers.get("Retry-After");
      if (retry) detail += ` Retry in ${retry}s.`;
    }
    throw new ApiError(detail, res.status);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  health: () => request<Health>("/api/health"),
  listDocuments: () =>
    request<{ documents: DocumentInfo[] }>("/api/documents").then((r) => r.documents),
  uploadDocument: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentInfo>("/api/documents", { method: "POST", body: form });
  },
  deleteDocument: (id: string) =>
    request<void>(`/api/documents/${encodeURIComponent(id)}`, { method: "DELETE" }),
  reindexDocument: (id: string) =>
    request<DocumentInfo>(`/api/documents/${encodeURIComponent(id)}/reindex`, { method: "POST" }),
  ask: (body: {
    question: string;
    document_ids: string[] | null;
    history: { role: "user" | "assistant"; content: string }[];
    mode: ChatMode;
  }) =>
    request<AskResponse>("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  fileUrl: (id: string, page?: number) =>
    `${BASE}/api/documents/${encodeURIComponent(id)}/file${page ? `#page=${page}` : ""}`,
};

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function validatePdfFile(file: File, maxMb: number): string | null {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (!isPdf) return `"${file.name}" is not a PDF.`;
  if (file.size === 0) return `"${file.name}" is empty.`;
  if (file.size > maxMb * 1024 * 1024) return `"${file.name}" exceeds the ${maxMb} MB limit.`;
  return null;
}
