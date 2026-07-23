"""Tests for the query command (with a stubbed model)."""

from __future__ import annotations

from conftest import FakeClient, assistant_final

from meetmin.ask import _parse_paths, answer_question, select_pages


def test_parse_paths_plain_array():
    assert _parse_paths('["topics/a.md", "topics/b.md"]') == ["topics/a.md", "topics/b.md"]


def test_parse_paths_with_surrounding_prose():
    text = 'Sure, these look relevant:\n["topics/led-zeppelin.md"]\nHope that helps!'
    assert _parse_paths(text) == ["topics/led-zeppelin.md"]


def test_parse_paths_empty_and_garbage():
    assert _parse_paths("[]") == []
    assert _parse_paths("no array here") == []
    assert _parse_paths("[not, valid, json") == []


def test_select_pages_returns_parsed_paths():
    client = FakeClient([assistant_final('["topics/prog-rock.md"]')])
    pages = select_pages(
        client, "fake-model", "index text", "when did prog come up?", 5,
        temperature=0.0, max_tokens=100,
    )
    assert pages == ["topics/prog-rock.md"]


def test_answer_question_includes_pages_in_context():
    client = FakeClient([assistant_final("Punk came up on 2026-07-01 (topics/punk.md).")])
    answer = answer_question(
        client, "fake-model", "when did punk come up?",
        {"topics/punk.md": "Punk emerged by 1976..."},
        temperature=0.0, max_tokens=100,
    )
    assert "Punk came up" in answer
    # The page content was passed into the prompt.
    sent = client.chat.completions.calls[0]["messages"][-1]["content"]
    assert "Punk emerged by 1976" in sent
    assert "topics/punk.md" in sent
