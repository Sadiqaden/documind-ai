import { citationLabelFromHref, linkifyCitations } from "../lib/citations";
import { formatBytes, validatePdfFile } from "../lib/api";
import type { Citation } from "../lib/types";

const cite = (label: string, page = 1): Citation => ({
  label, document_id: "d1", document_name: "a.pdf", page_number: page, excerpt: "x", score: 0.5,
});

describe("linkifyCitations", () => {
  it("turns known markers into citation links", () => {
    expect(linkifyCitations("Fact [S1].", [cite("S1")])).toBe("Fact [S1](#cite-S1).");
  });
  it("expands grouped markers", () => {
    expect(linkifyCitations("x [S1, S2]", [cite("S1"), cite("S2")])).toBe("x [S1](#cite-S1) [S2](#cite-S2)");
  });
  it("drops markers that have no matching citation", () => {
    expect(linkifyCitations("x [S9] y [S1, S7]", [cite("S1")])).toBe("x  y [S1](#cite-S1)");
  });
  it("parses citation hrefs only", () => {
    expect(citationLabelFromHref("#cite-S3")).toBe("S3");
    expect(citationLabelFromHref("https://evil.example")).toBeNull();
    expect(citationLabelFromHref(undefined)).toBeNull();
  });
});

describe("file validation", () => {
  it("accepts PDFs under the limit", () => {
    expect(validatePdfFile(new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" }), 1)).toBeNull();
  });
  it("rejects non-PDFs, empty and oversized files", () => {
    expect(validatePdfFile(new File(["hi"], "a.txt", { type: "text/plain" }), 1)).toMatch(/not a PDF/);
    expect(validatePdfFile(new File([], "a.pdf", { type: "application/pdf" }), 1)).toMatch(/empty/);
    const big = new File([new Uint8Array(2 * 1024 * 1024)], "b.pdf", { type: "application/pdf" });
    expect(validatePdfFile(big, 1)).toMatch(/exceeds the 1 MB/);
  });
  it("formats bytes", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(3 * 1024 * 1024)).toBe("3.0 MB");
  });
});
