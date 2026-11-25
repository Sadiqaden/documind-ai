from app.container import Container
from app.schemas import ChatTurn
from app.services.qa import NO_RESULTS_MESSAGE, QAService, history_to_messages
from tests.conftest import FakeLLM, text_response


def _qa(container: Container, llm: FakeLLM | None) -> QAService:
    return QAService(container.retriever, llm, top_k=4, min_relevance=0.08)


def test_answer_with_valid_citations(container: Container, indexed: dict[str, str]) -> None:
    def respond(system, messages, tools):  # type: ignore[no-untyped-def]
        prompt = messages[-1]["content"]
        assert 'document="solar.pdf" page="2"' in prompt
        return text_response("Monocrystalline panels reach 20-23% efficiency [S1].")

    llm = FakeLLM(respond)
    res = _qa(container, llm).answer("What efficiency do monocrystalline panels reach?", None, [])
    assert not res.insufficient_evidence
    assert res.citations[0].document_name == "solar.pdf"
    assert res.citations[0].page_number == 2
    assert res.warnings == []


def test_fabricated_citation_is_removed(container: Container, indexed: dict[str, str]) -> None:
    llm = FakeLLM([text_response("Panels are efficient [S1]. Also see page 99 [S42].")])
    res = _qa(container, llm).answer("panel efficiency", None, [])
    assert "S42" not in res.answer
    assert all(c.label != "S42" for c in res.citations)
    assert any("S42" in w for w in res.warnings)


def test_no_retrieval_means_no_llm_call(container: Container, indexed: dict[str, str]) -> None:
    llm = FakeLLM([])
    res = _qa(container, llm).answer("quantum chromodynamics gluon field", None, [])
    assert res.insufficient_evidence and res.answer == NO_RESULTS_MESSAGE
    assert res.citations == [] and llm.calls == []


def test_model_reported_insufficient_evidence(
    container: Container, indexed: dict[str, str]
) -> None:
    llm = FakeLLM([text_response("INSUFFICIENT_EVIDENCE\nThe documents don't state the price.")])
    res = _qa(container, llm).answer("What is the price of solar panels?", None, [])
    assert res.insufficient_evidence
    assert res.answer.startswith("The documents don't state")
    assert "INSUFFICIENT" not in res.answer


def test_uncited_answer_gets_warning(container: Container, indexed: dict[str, str]) -> None:
    llm = FakeLLM([text_response("Panels are pretty good.")])
    res = _qa(container, llm).answer("panel efficiency", None, [])
    assert res.citations == [] and any("no verifiable citations" in w for w in res.warnings)


def test_extractive_mode_cites_real_pages(container: Container, indexed: dict[str, str]) -> None:
    res = _qa(container, None).answer("espresso extraction time", None, [])
    assert res.provider == "extractive"
    assert res.citations and res.citations[0].document_name == "coffee.pdf"
    assert "[S1]" in res.answer


def test_history_is_alternating_and_starts_with_user() -> None:
    h = [
        ChatTurn(role="assistant", content="hi"),
        ChatTurn(role="user", content="q1"),
        ChatTurn(role="user", content="q1b"),
        ChatTurn(role="assistant", content="a1"),
        ChatTurn(role="user", content="dangling"),
    ]
    msgs = history_to_messages(h)
    assert [m["role"] for m in msgs] == ["user", "assistant"]
    assert "q1b" in msgs[0]["content"]
