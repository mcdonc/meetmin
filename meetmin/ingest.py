"""Agentically compile raw transcripts into a cross-linked markdown wiki.

``meetmin-ingest`` is the LLM-Wiki ingest step. For each raw transcript under
``meeting_dialog/`` it runs a tool-calling loop: the model reads the transcript
and the existing wiki, then uses file tools (see :mod:`meetmin.wikitools`) to
write a per-meeting ``minutes/`` page and create/update cross-linked
``wiki/topics/`` pages, the ``wiki/index.md`` router, and the append-only
``wiki/log.md``. The structure/naming rules come from the repo's ``WIKI.md``.

Like :mod:`meetmin.summarize`, it talks to the generic OpenAI Chat Completions
API, so it works against OpenAI or any OpenAI-compatible server via ``--base-url``
/ ``OPENAI_BASE_URL``. The model must support tool calling; if a model ignores
the tools entirely, ingest falls back to writing just the per-meeting minutes
page (reusing the summarizer) and warns that wiki maintenance was skipped.

Usage::

    meetmin-ingest --repo /path/to/customer-acme
    meetmin-ingest --repo customer-acme --base-url http://localhost:8000/v1 \\
        --model my-local-model
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from openai import OpenAI

from .summarize import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_MODEL,
    DEFAULT_TEMPERATURE,
    summarize_transcript,
)
from .wikitools import TOOL_SCHEMAS, WikiTools, parse_arguments

DEFAULT_MAX_STEPS = 20

# Built-in fallback schema, used only when the repo has no WIKI.md.
FALLBACK_SCHEMA = """\
Structure the wiki as: minutes/<stem>.md per meeting; wiki/index.md (a one-line
catalog per wiki page); wiki/log.md (append-only ingest log); wiki/topics/*.md
(cross-linked topic/entity pages). Link between pages with relative Markdown
links. Never edit files under the raw sources directory."""


def build_system_prompt(schema: str, dialog_dir: str, minutes_dir: str, wiki_dir: str) -> str:
    return f"""\
You are the maintainer of an "LLM Wiki": a compiled, cross-linked set of
markdown pages built from raw meeting transcripts. You maintain it with the
provided file tools. Work carefully and keep the wiki internally consistent.

Directories in this repo:
- {dialog_dir}/  — raw transcripts. READ ONLY. Never write here.
- {minutes_dir}/ — one structured page per meeting.
- {wiki_dir}/    — index.md, log.md, and topics/ (topic & entity pages).

Follow this schema exactly:

--- WIKI SCHEMA ---
{schema}
--- END SCHEMA ---

You will be given one transcript to ingest. Do the full workflow with tool
calls: read the existing wiki index if present, write the per-meeting minutes
page, create or update the relevant topic/entity pages (updating existing pages
rather than duplicating them), refresh index.md, and append a log.md entry.
When everything is written and consistent, stop and reply with a one-line
summary of what you did. Do not claim to have written a file you did not write
with a tool call."""


def ingest_transcript(
    client: OpenAI,
    model: str,
    tools: WikiTools,
    *,
    system_prompt: str,
    transcript_relpath: str,
    transcript_text: str,
    minutes_relpath: str,
    temperature: float,
    max_tokens: int,
    max_steps: int,
) -> tuple[bool, list[str]]:
    """Run the agentic ingest loop for one transcript.

    Returns ``(used_tools, notes)`` where ``used_tools`` is whether the model
    drove any tool call, and ``notes`` collects human-readable step lines.
    """
    user_message = (
        f"Ingest this transcript.\n\n"
        f"Raw source path: {transcript_relpath}\n"
        f"Write its per-meeting minutes to: {minutes_relpath}\n\n"
        f"Transcript:\n\n{transcript_text}"
    )
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]

    used_tools = False
    notes: list[str] = []
    for _ in range(max_steps):
        response = client.chat.completions.create(
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
        )
        message = response.choices[0].message
        tool_calls = getattr(message, "tool_calls", None) or []

        assistant_msg: dict = {"role": "assistant", "content": message.content or ""}
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        if not tool_calls:
            # Model produced a final answer.
            if message.content:
                notes.append(message.content.strip())
            break

        used_tools = True
        for tc in tool_calls:
            args = parse_arguments(tc.function.arguments)
            result = tools.dispatch(tc.function.name, args)
            notes.append(f"{tc.function.name}({_brief(args)}) -> {result.splitlines()[0] if result else ''}")
            messages.append(
                {"role": "tool", "tool_call_id": tc.id, "content": result}
            )
    else:
        notes.append(f"(stopped after {max_steps} steps without a final reply)")

    return used_tools, notes


def _brief(args: dict) -> str:
    """Compact one-line rendering of tool args for progress output."""
    parts = []
    for k, v in args.items():
        s = str(v)
        parts.append(f"{k}={s[:40] + '…' if len(s) > 40 else s}")
    return ", ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Agentically compile raw transcripts into a cross-linked "
        "markdown wiki via an OpenAI-compatible Chat Completions API.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Path to the customer repo working copy (default: current directory)",
    )
    parser.add_argument(
        "--dialog-dir",
        default="meeting_dialog",
        help="Raw transcript subdirectory (default: meeting_dialog)",
    )
    parser.add_argument(
        "--minutes-dir",
        default="minutes",
        help="Per-meeting minutes subdirectory (default: minutes)",
    )
    parser.add_argument(
        "--wiki-dir", default="wiki", help="Wiki subdirectory (default: wiki)"
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, help=f"Model name (default: {DEFAULT_MODEL})"
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("OPENAI_BASE_URL"),
        help="OpenAI-compatible endpoint base URL (default: OPENAI_BASE_URL env / OpenAI)",
    )
    parser.add_argument(
        "--temperature", type=float, default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature (default: {DEFAULT_TEMPERATURE})",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=DEFAULT_MAX_TOKENS,
        help=f"Max output tokens per step (default: {DEFAULT_MAX_TOKENS})",
    )
    parser.add_argument(
        "--max-steps", type=int, default=DEFAULT_MAX_STEPS,
        help=f"Max tool-call steps per transcript (default: {DEFAULT_MAX_STEPS})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-ingest even if a minutes page already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be ingested without calling the API",
    )
    args = parser.parse_args()

    dialog_dir = args.repo / args.dialog_dir
    minutes_dir = args.repo / args.minutes_dir

    if not dialog_dir.is_dir():
        print(f"error: no dialog directory at {dialog_dir}", file=sys.stderr)
        return 1

    transcripts = sorted(dialog_dir.glob("*.md"))
    if not transcripts:
        print(f"No .md transcripts found in {dialog_dir}")
        return 0

    pending: list[Path] = []
    for transcript in transcripts:
        out = minutes_dir / (transcript.stem + ".md")
        if out.exists() and not args.force:
            print(f"skip   {transcript.name} (already ingested)")
            continue
        pending.append(transcript)

    if not pending:
        print("Nothing to do — every transcript is already ingested.")
        return 0

    if args.dry_run:
        for transcript in pending:
            print(f"would ingest  {transcript.name}")
        return 0

    # Load the wiki schema from WIKI.md if present, else use the fallback.
    wiki_md = args.repo / "WIKI.md"
    schema = wiki_md.read_text() if wiki_md.exists() else FALLBACK_SCHEMA
    system_prompt = build_system_prompt(
        schema, args.dialog_dir, args.minutes_dir, args.wiki_dir
    )

    tools = WikiTools(args.repo, read_only_dirs=(args.dialog_dir,))
    client = OpenAI(base_url=args.base_url) if args.base_url else OpenAI()

    for transcript in pending:
        transcript_relpath = f"{args.dialog_dir}/{transcript.name}"
        minutes_relpath = f"{args.minutes_dir}/{transcript.stem}.md"
        print(f"ingesting {transcript.name} ...", flush=True)
        used_tools, notes = ingest_transcript(
            client,
            args.model,
            tools,
            system_prompt=system_prompt,
            transcript_relpath=transcript_relpath,
            transcript_text=transcript.read_text(),
            minutes_relpath=minutes_relpath,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            max_steps=args.max_steps,
        )
        for note in notes:
            print(f"  {note}")

        if not used_tools:
            # Graceful degradation: the model never called a tool. Fall back to
            # writing just the per-meeting minutes so ingest still produces
            # something, and warn that wiki maintenance was skipped.
            print(
                "  warning: model did not use tools; falling back to minutes-only",
                file=sys.stderr,
            )
            raw_link = f"../{args.dialog_dir}/{transcript.name}"
            minutes = summarize_transcript(
                client, args.model, transcript.read_text(),
                transcript_relpath, raw_link,
                temperature=args.temperature, max_tokens=args.max_tokens,
            )
            out = minutes_dir / f"{transcript.stem}.md"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(minutes)
            print(f"  wrote {minutes_relpath} (minutes only)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
