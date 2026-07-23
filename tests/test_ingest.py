"""Tests for the agentic ingest loop (with a stubbed model)."""

from __future__ import annotations

from conftest import FakeClient, assistant_final, assistant_tool_turn, tool_call

from meetmin.ingest import ingest_transcript
from meetmin.wikitools import WikiTools


def _tools(tmp_path):
    (tmp_path / "meeting_dialog").mkdir()
    (tmp_path / "meeting_dialog" / "m1.md").write_text("raw dialog text")
    return WikiTools(tmp_path, read_only_dirs=("meeting_dialog",))


def test_ingest_executes_tool_calls_and_writes_files(tmp_path):
    tools = _tools(tmp_path)
    client = FakeClient([
        # Turn 1: read the (absent) index, then write minutes + a topic page.
        assistant_tool_turn(
            tool_call("read_file", {"path": "wiki/index.md"}),
            tool_call("write_file", {"path": "minutes/m1.md", "content": "# Minutes\n"}),
            tool_call("write_file", {"path": "wiki/topics/led-zeppelin.md", "content": "# Led Zeppelin\n"}),
            tool_call("append_file", {"path": "wiki/log.md", "content": "## m1\n"}),
        ),
        # Turn 2: final answer, no tool calls -> loop ends.
        assistant_final("Ingested m1: wrote minutes and 1 topic page."),
    ])

    used_tools, notes = ingest_transcript(
        client, "fake-model", tools,
        system_prompt="SYS",
        transcript_relpath="meeting_dialog/m1.md",
        transcript_text="raw dialog text",
        minutes_relpath="minutes/m1.md",
        temperature=0.0, max_tokens=100, max_steps=10,
    )

    assert used_tools is True
    assert (tmp_path / "minutes" / "m1.md").read_text() == "# Minutes\n"
    assert (tmp_path / "wiki" / "topics" / "led-zeppelin.md").exists()
    assert (tmp_path / "wiki" / "log.md").read_text() == "## m1\n"
    # Tools were offered to the model on every call.
    assert all("tools" in call for call in client.chat.completions.calls)
    assert notes[-1].startswith("Ingested m1")


def test_ingest_reports_tool_errors_without_crashing(tmp_path):
    tools = _tools(tmp_path)
    client = FakeClient([
        assistant_tool_turn(
            # Writing to a read-only source must come back as an error result,
            # not raise, so the model could recover.
            tool_call("write_file", {"path": "meeting_dialog/m1.md", "content": "x"}),
        ),
        assistant_final("done"),
    ])
    used_tools, notes = ingest_transcript(
        client, "fake-model", tools,
        system_prompt="SYS", transcript_relpath="meeting_dialog/m1.md",
        transcript_text="t", minutes_relpath="minutes/m1.md",
        temperature=0.0, max_tokens=100, max_steps=10,
    )
    assert used_tools is True
    assert (tmp_path / "meeting_dialog" / "m1.md").read_text() == "raw dialog text"
    assert any("read-only" in n or "ERROR" in n for n in notes)


def test_ingest_no_tool_use_signals_fallback(tmp_path):
    tools = _tools(tmp_path)
    client = FakeClient([assistant_final("Here are the minutes: ...")])
    used_tools, notes = ingest_transcript(
        client, "fake-model", tools,
        system_prompt="SYS", transcript_relpath="meeting_dialog/m1.md",
        transcript_text="t", minutes_relpath="minutes/m1.md",
        temperature=0.0, max_tokens=100, max_steps=10,
    )
    assert used_tools is False


def test_ingest_stops_at_max_steps(tmp_path):
    tools = _tools(tmp_path)
    # Every turn asks for another tool call; loop must stop at max_steps.
    client = FakeClient([
        assistant_tool_turn(tool_call("list_files", {"subdir": "."}))
        for _ in range(10)
    ])
    used_tools, notes = ingest_transcript(
        client, "fake-model", tools,
        system_prompt="SYS", transcript_relpath="meeting_dialog/m1.md",
        transcript_text="t", minutes_relpath="minutes/m1.md",
        temperature=0.0, max_tokens=100, max_steps=3,
    )
    assert used_tools is True
    assert len(client.chat.completions.calls) == 3
    assert any("stopped after" in n for n in notes)
