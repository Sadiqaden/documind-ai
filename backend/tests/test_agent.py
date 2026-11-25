from typing import Any

from app.container import Container
from app.services.agent import MAX_TOOLS_PER_STEP, TOOLS, AgentService
from app.services.llm import LLMResponse, ToolCall
from tests.conftest import FakeLLM, text_response


def tool_response(*calls: tuple[str, dict[str, Any]]) -> LLMResponse:
    tcs = [ToolCall(id=f"t{i}", name=n, input=a) for i, (n, a) in enumerate(calls)]
    return LLMResponse(
        text="",
        tool_calls=tcs,
        stop_reason="tool_use",
        model="fake-model",
        raw_content=[
            {"type": "tool_use", "id": t.id, "name": t.name, "input": t.input} for t in tcs
        ],
    )


def test_tool_definitions_are_strict_and_closed() -> None:
    names = {t["name"] for t in TOOLS}
    assert names == {"list_documents", "search_documents", "read_document"}
    for t in TOOLS:
        assert t["strict"] is True
        assert t["input_schema"]["additionalProperties"] is False
        assert set(t["input_schema"].get("required", [])) == set(t["input_schema"]["properties"])


def test_agent_search_then_answer(container: Container, indexed: dict[str, str]) -> None:
    llm = FakeLLM(
        [
            tool_response(
                (
                    "search_documents",
                    {"query": "battery charge cycles", "document_ids": [], "top_k": 3},
                )
            ),
            text_response("LFP batteries offer about 6000 cycles [S1]. Bogus [S77]."),
        ]
    )
    res = AgentService(container.db, container.retriever, llm, max_steps=4).run(
        "How many cycles do the batteries last?", None, []
    )
    assert [t.tool for t in res.tool_trace] == ["search_documents"]
    assert res.citations[0].document_name == "solar.pdf" and res.citations[0].page_number == 3
    assert "S77" not in res.answer
    # tool results were sent back in a single user message referencing the tool_use id
    tool_msg = llm.calls[1]["messages"][-1]
    assert tool_msg["role"] == "user" and tool_msg["content"][0]["tool_use_id"] == "t0"


def test_agent_summarize_with_read_document(container: Container, indexed: dict[str, str]) -> None:
    doc = indexed["solar"]
    llm = FakeLLM(
        [
            tool_response(("list_documents", {})),
            tool_response(
                (
                    "read_document",
                    {"document_id": doc, "mode": "outline", "start_page": 1, "end_page": 1},
                )
            ),
            text_response("The handbook covers PV history [S1], panels [S2] and batteries [S3]."),
        ]
    )
    res = AgentService(container.db, container.retriever, llm, max_steps=5).run(
        "Summarize the solar handbook", None, []
    )
    assert [c.page_number for c in res.citations] == [1, 2, 3]
    assert {c.document_name for c in res.citations} == {"solar.pdf"}


def test_agent_is_bounded_by_max_steps(container: Container, indexed: dict[str, str]) -> None:
    search = ("search_documents", {"query": "panels", "document_ids": [], "top_k": 2})
    llm = FakeLLM(lambda s, m, t: tool_response(search))  # never stops calling tools
    res = AgentService(container.db, container.retriever, llm, max_steps=3).run("q", None, [])
    assert len(llm.calls) == 3
    assert any("maximum number of agent steps" in w for w in res.warnings)
    assert res.insufficient_evidence
    # the final step was told the budget is exhausted
    last_user = llm.calls[2]["messages"][-1]["content"]
    assert any(b.get("type") == "text" and "budget exhausted" in b["text"] for b in last_user)


def test_per_step_tool_cap_and_errors(container: Container, indexed: dict[str, str]) -> None:
    calls = [
        (
            "read_document",
            {"document_id": "nope", "mode": "outline", "start_page": 1, "end_page": 1},
        )
    ]
    calls += [("search_documents", {"query": "x", "document_ids": [], "top_k": 1})] * (
        MAX_TOOLS_PER_STEP
    )
    llm = FakeLLM([tool_response(*calls), text_response("INSUFFICIENT_EVIDENCE\nnothing")])
    res = AgentService(container.db, container.retriever, llm, max_steps=3).run("q", None, [])
    assert res.tool_trace[0].is_error and "No ready document" in res.tool_trace[0].summary
    assert res.tool_trace[-1].is_error and "skipped" in res.tool_trace[-1].summary
    results = llm.calls[1]["messages"][-1]["content"]
    assert len([r for r in results if r["type"] == "tool_result"]) == len(calls)


def test_agent_respects_document_selection(container: Container, indexed: dict[str, str]) -> None:
    llm = FakeLLM(
        [
            tool_response(
                (
                    "read_document",
                    {
                        "document_id": indexed["solar"],
                        "mode": "pages",
                        "start_page": 1,
                        "end_page": 2,
                    },
                ),
                ("search_documents", {"query": "panel efficiency", "document_ids": [], "top_k": 5}),
            ),
            text_response("done"),
        ]
    )
    res = AgentService(container.db, container.retriever, llm, max_steps=3).run(
        "q", [indexed["coffee"]], []
    )
    assert res.tool_trace[0].is_error  # solar not in selection
    payload = llm.calls[1]["messages"][-1]["content"][1]["content"]
    assert "solar.pdf" not in payload
