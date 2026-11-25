from app.services.citations import SourceRegistry, validate_citations


def _registry() -> SourceRegistry:
    r = SourceRegistry()
    r.add("c1", "d1", "solar.pdf", 2, "Monocrystalline panels reach 20-23%.", 0.9)
    r.add("c2", "d1", "solar.pdf", 3, "LFP batteries offer 6000 cycles.", 0.7)
    r.add("c3", "d2", "coffee.pdf", 1, "Espresso takes 25-30 seconds.", 0.5)
    return r


def test_registry_labels_and_dedup() -> None:
    r = _registry()
    assert list(r.sources) == ["S1", "S2", "S3"]
    again = r.add("c1", "d1", "solar.pdf", 2, "dup", 0.1)
    assert again.label == "S1" and len(r) == 3


def test_valid_citations_map_to_real_document_pages() -> None:
    v = validate_citations("Panels reach 23% [S1]. Batteries last 6000 cycles [S2].", _registry())
    assert v.invalid_labels == []
    assert [(c.label, c.document_name, c.page_number) for c in v.citations] == [
        ("S1", "solar.pdf", 2),
        ("S2", "solar.pdf", 3),
    ]


def test_invented_citations_are_stripped() -> None:
    v = validate_citations("Claim A [S9]. Claim B [S1, S7]. Claim C [S2].", _registry())
    assert v.invalid_labels == ["S9", "S7"]
    assert "[S9]" not in v.text and "S7" not in v.text
    assert "Claim A." in v.text
    assert "[S1]" in v.text
    assert [c.label for c in v.citations] == ["S1", "S2"]


def test_citations_ordered_by_first_use_and_unique() -> None:
    v = validate_citations("x [S3] y [S1] z [S3, S1]", _registry())
    assert [c.label for c in v.citations] == ["S3", "S1"]


def test_no_citations() -> None:
    v = validate_citations("Plain answer.", _registry())
    assert v.citations == [] and v.text == "Plain answer."


def test_lowercase_or_malformed_markers_are_not_citations() -> None:
    v = validate_citations("see [s1] and [Source 1] and (S2)", _registry())
    assert v.citations == []
