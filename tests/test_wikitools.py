"""Tests for the sandboxed file tools."""

from __future__ import annotations

import pytest

from meetmin.wikitools import ToolError, WikiTools, parse_arguments


@pytest.fixture
def tools(tmp_path):
    (tmp_path / "meeting_dialog").mkdir()
    (tmp_path / "meeting_dialog" / "m1.md").write_text("raw transcript")
    return WikiTools(tmp_path, read_only_dirs=("meeting_dialog",))


def test_write_read_roundtrip(tools):
    assert "wrote" in tools.write_file("wiki/topics/foo.md", "hello")
    assert tools.read_file("wiki/topics/foo.md") == "hello"


def test_write_creates_parent_dirs(tools, tmp_path):
    tools.write_file("wiki/index.md", "x")
    assert (tmp_path / "wiki" / "index.md").exists()


def test_append_file(tools):
    tools.write_file("wiki/log.md", "one\n")
    tools.append_file("wiki/log.md", "two\n")
    assert tools.read_file("wiki/log.md") == "one\ntwo\n"


def test_append_creates_when_absent(tools):
    tools.append_file("wiki/log.md", "first\n")
    assert tools.read_file("wiki/log.md") == "first\n"


def test_list_files_recursive(tools):
    tools.write_file("wiki/index.md", "x")
    tools.write_file("wiki/topics/a.md", "x")
    listing = tools.list_files("wiki")
    assert "wiki/index.md" in listing
    assert "wiki/topics/a.md" in listing


def test_read_missing_file_raises(tools):
    with pytest.raises(ToolError):
        tools.read_file("wiki/nope.md")


def test_path_escape_rejected(tools):
    with pytest.raises(ToolError):
        tools.read_file("../secrets.txt")
    with pytest.raises(ToolError):
        tools.write_file("../evil.md", "x")


def test_read_only_dir_write_rejected(tools):
    with pytest.raises(ToolError):
        tools.write_file("meeting_dialog/m1.md", "tampered")
    with pytest.raises(ToolError):
        tools.append_file("meeting_dialog/m1.md", "more")
    # ...but reading a source is fine.
    assert tools.read_file("meeting_dialog/m1.md") == "raw transcript"


def test_read_only_prefix_not_confused(tools):
    # "meeting_dialogs" must not be treated as the read-only "meeting_dialog".
    assert "wrote" in tools.write_file("meeting_dialogs_notes/x.md", "ok")


def test_dispatch_wraps_errors(tools):
    assert tools.dispatch("read_file", {"path": "missing.md"}).startswith("ERROR:")
    assert tools.dispatch("bogus_tool", {}).startswith("ERROR:")
    assert tools.dispatch("read_file", {}).startswith("ERROR: missing required argument")


def test_dispatch_happy_path(tools):
    assert "wrote" in tools.dispatch("write_file", {"path": "wiki/a.md", "content": "x"})
    assert tools.dispatch("read_file", {"path": "wiki/a.md"}) == "x"


def test_parse_arguments():
    assert parse_arguments('{"path": "a.md"}') == {"path": "a.md"}
    assert parse_arguments({"path": "a.md"}) == {"path": "a.md"}
    assert parse_arguments("") == {}
    with pytest.raises(ToolError):
        parse_arguments("{not json")
