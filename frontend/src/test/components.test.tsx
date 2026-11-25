import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AnswerContent } from "../components/AnswerContent";
import { CitationPanel } from "../components/CitationPanel";
import type { Citation } from "../lib/types";

const citations: Citation[] = [
  { label: "S1", document_id: "abc", document_name: "solar.pdf", page_number: 2, excerpt: "Panels reach 23%.", score: 0.81 },
  { label: "S2", document_id: "abc", document_name: "solar.pdf", page_number: 3, excerpt: "LFP 6000 cycles.", score: 0.6 },
];

describe("AnswerContent", () => {
  it("renders clickable citation chips with document/page labels", async () => {
    const onCite = vi.fn();
    render(<AnswerContent answer="Panels reach 23% [S1]. Batteries [S2]. Fake [S9]." citations={citations} activeLabel={null} onCite={onCite} />);
    const chip = screen.getByRole("button", { name: "Citation S1: solar.pdf, page 2" });
    await userEvent.click(chip);
    expect(onCite).toHaveBeenCalledWith("S1");
    expect(screen.getByRole("button", { name: /Citation S2/ })).toBeInTheDocument();
    expect(screen.queryByText("S9")).not.toBeInTheDocument();
  });

  it("does not render raw HTML or external links from model output", () => {
    const { container } = render(
      <AnswerContent answer={'<img src=x onerror="alert(1)"> [click](https://evil.example)'} citations={[]} activeLabel={null} onCite={() => {}} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(screen.getByText("click")).toBeInTheDocument();
  });
});

describe("CitationPanel", () => {
  it("lists sources with deep links to the cited page", () => {
    render(<CitationPanel citations={citations} activeLabel="S2" onSelect={() => {}} />);
    const link = screen.getByRole("link", { name: "Open solar.pdf at page 3" });
    expect(link).toHaveAttribute("href", "/api/documents/abc/file#page=3");
    expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(screen.getByText("Panels reach 23%.")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { pressed: true })).toHaveLength(1);
  });

  it("shows an empty state", () => {
    render(<CitationPanel citations={[]} activeLabel={null} onSelect={() => {}} />);
    expect(screen.getByText(/Sources for the selected answer appear here/)).toBeInTheDocument();
  });
});
