from types import SimpleNamespace

from rejstrik.documents.answer import parse_answer, Answer, Citation


def _citation(cited_text, page):
    return SimpleNamespace(type="page_location", cited_text=cited_text, start_page_number=page)


def _text_block(text, citations=None):
    return SimpleNamespace(type="text", text=text, citations=citations)


def test_parse_answer_concatenates_text():
    content = [_text_block("Yes, there is a pledge "), _text_block("over the building.")]
    ans = parse_answer(content)
    assert isinstance(ans, Answer)
    assert ans.text == "Yes, there is a pledge over the building."
    assert ans.citations == []


def test_parse_answer_collects_page_citations():
    content = [
        _text_block("A pledge exists.", citations=[_citation("zástavní právo k budově", 43)]),
    ]
    ans = parse_answer(content)
    assert ans.citations == [Citation(cited_text="zástavní právo k budově", page=43)]


def test_parse_answer_ignores_non_text_blocks():
    content = [SimpleNamespace(type="thinking", thinking="..."), _text_block("Answer.")]
    ans = parse_answer(content)
    assert ans.text == "Answer."
