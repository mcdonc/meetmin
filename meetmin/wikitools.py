"""Sandboxed file tools exposed to the ingest agent.

The ingest step (``meetmin-ingest``) is *agentic*: an LLM drives a loop of tool
calls to read raw transcripts and create/update the compiled wiki. This module
implements those tools and the OpenAI-compatible function schemas that describe
them.

All file access is confined to a single repo root. Paths are resolved and
checked so the model cannot read or write outside it, and the raw-sources
directory is read-only (transcripts are immutable per the wiki schema).
"""

from __future__ import annotations

import json
from pathlib import Path


class ToolError(Exception):
    """Raised when a tool call is invalid (bad path, write to a source, ...).

    The message is returned to the model as the tool result so it can recover,
    rather than aborting the whole ingest.
    """


class WikiTools:
    """File tools scoped to ``root``.

    ``read_only_dirs`` names top-level subdirectories the model may read but
    never write (the raw transcript sources).
    """

    def __init__(self, root: Path, read_only_dirs: tuple[str, ...] = ()) -> None:
        self.root = root.resolve()
        self.read_only_dirs = read_only_dirs

    # -- path handling ----------------------------------------------------

    def _resolve(self, relpath: str) -> Path:
        """Resolve ``relpath`` against the root, refusing escapes."""
        if not relpath or relpath.strip() != relpath:
            raise ToolError(f"invalid path: {relpath!r}")
        candidate = (self.root / relpath).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ToolError(f"path escapes repo root: {relpath!r}")
        return candidate

    def _check_writable(self, relpath: str) -> None:
        # Compare against the first path segment so "meeting_dialog/x.md" and
        # "meeting_dialog" are both caught, but "meeting_dialogs" is not.
        first = Path(relpath).parts[0] if Path(relpath).parts else ""
        if first in self.read_only_dirs:
            raise ToolError(
                f"{first}/ is read-only (raw sources); refusing to write {relpath!r}"
            )

    # -- tools ------------------------------------------------------------

    def list_files(self, subdir: str = ".") -> str:
        base = self._resolve(subdir)
        if not base.exists():
            return f"(no such directory: {subdir})"
        if not base.is_dir():
            raise ToolError(f"not a directory: {subdir!r}")
        entries = []
        for p in sorted(base.rglob("*")):
            if p.is_file():
                entries.append(str(p.relative_to(self.root)))
        return "\n".join(entries) if entries else "(empty)"

    def read_file(self, path: str) -> str:
        target = self._resolve(path)
        if not target.exists():
            raise ToolError(f"no such file: {path!r}")
        if not target.is_file():
            raise ToolError(f"not a file: {path!r}")
        return target.read_text()

    def write_file(self, path: str, content: str) -> str:
        self._check_writable(path)
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        return f"wrote {path} ({len(content)} chars)"

    def append_file(self, path: str, content: str) -> str:
        self._check_writable(path)
        target = self._resolve(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a") as fh:
            fh.write(content)
        return f"appended to {path} ({len(content)} chars)"

    # -- dispatch ---------------------------------------------------------

    #: Names of files written during the current run, in order (for reporting).
    def dispatch(self, name: str, arguments: dict) -> str:
        """Run tool ``name`` with keyword ``arguments``; return a text result."""
        try:
            if name == "list_files":
                return self.list_files(arguments.get("subdir", "."))
            if name == "read_file":
                return self.read_file(arguments["path"])
            if name == "write_file":
                return self.write_file(arguments["path"], arguments["content"])
            if name == "append_file":
                return self.append_file(arguments["path"], arguments["content"])
            raise ToolError(f"unknown tool: {name!r}")
        except ToolError as exc:
            return f"ERROR: {exc}"
        except KeyError as exc:
            return f"ERROR: missing required argument {exc} for tool {name!r}"


#: OpenAI-compatible function/tool schemas describing the WikiTools methods.
TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files (recursively) under a repo subdirectory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subdir": {
                        "type": "string",
                        "description": "Repo-relative directory, e.g. 'wiki' or "
                        "'.' for the whole repo.",
                    }
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a repo-relative text file and return its contents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Repo-relative file path.",
                    }
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or overwrite a repo-relative text file. Cannot "
            "write to the raw sources directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repo-relative path."},
                    "content": {"type": "string", "description": "Full file contents."},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "append_file",
            "description": "Append text to a repo-relative file (creates it if "
            "absent). Use for the append-only log.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Repo-relative path."},
                    "content": {"type": "string", "description": "Text to append."},
                },
                "required": ["path", "content"],
            },
        },
    },
]


def parse_arguments(raw: str | dict) -> dict:
    """Parse a tool call's ``arguments`` (JSON string or already-decoded dict)."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ToolError(f"could not parse tool arguments as JSON: {exc}") from exc
