"""Summarize raw meeting transcripts into minutes via an OpenAI-compatible API.

Scans ``<repo>/raw/*.txt`` and, for each transcript that does not yet have a
matching ``<repo>/minutes/<stem>.md``, generates a structured minutes summary
and writes it. Existing minutes are left untouched unless ``--force`` is given.

This talks to the generic OpenAI **Chat Completions** API, so it works with
OpenAI itself or any OpenAI-compatible server (vLLM, Ollama, LM Studio,
llama.cpp, a gateway, ...). Point it at one with ``--base-url`` or the
``OPENAI_BASE_URL`` environment variable.

Auth / config (env vars, all overridable by flags):
    OPENAI_API_KEY      API key. Required by the client; for a local server
                        with no auth, set it to any non-empty placeholder.
    OPENAI_BASE_URL     Endpoint, e.g. http://localhost:8000/v1 (default: OpenAI).
    OPENAI_MODEL        Model name (default: gpt-4o-mini).
    OPENAI_TEMPERATURE  Sampling temperature (default: 0.2).
    OPENAI_MAX_TOKENS   Max output tokens (default: 8000).

Usage::

    meetmin-summarize --repo /path/to/customer-acme
    # against a local OpenAI-compatible server:
    meetmin-summarize --repo customer-acme \\
        --base-url http://localhost:8000/v1 --model my-local-model
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from openai import OpenAI

DEFAULT_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
DEFAULT_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.2"))
DEFAULT_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", "8000"))

SYSTEM_PROMPT = """\
You are a meeting-minutes writer. You are given the raw, auto-transcribed text
of a short business meeting. Produce clean, structured minutes in
GitHub-flavored Markdown.

Output ONLY the Markdown document — no code fences, no preamble, no commentary.

Use exactly this structure:

# <Meeting Title> — Minutes

- **Date:** <YYYY-MM-DD>
- **Duration:** <e.g. 2 min>
- **Attendees:** <names with roles>
- **Source:** [<RAW_RELPATH>](<RAW_LINK>)

## Summary

<One tight paragraph: what the meeting was about and what came out of it.>

## Decisions

<Bulleted list of concrete decisions. Omit this section entirely if there were none.>

## Action Items

| Owner | Task | Due |
|-------|------|-----|
<one row per action item; use an em dash when a field is unknown>

## Upcoming

<Bulleted list of upcoming dates/events mentioned. Omit this section if none.>

Extract the title, date, duration, and attendees from the transcript header.
Substitute the provided RAW_RELPATH and RAW_LINK values into the Source line.
Be faithful to the transcript: do not invent decisions, owners, or dates that
were not stated. Keep it concise."""


def summarize_transcript(
    client: OpenAI,
    model: str,
    transcript: str,
    raw_relpath: str,
    raw_link: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> str:
    """Return the Markdown minutes for a single transcript."""
    user_message = (
        f"RAW_RELPATH = {raw_relpath}\n"
        f"RAW_LINK = {raw_link}\n\n"
        f"Transcript:\n\n{transcript}"
    )
    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
    )
    text = (response.choices[0].message.content or "").strip()
    return text + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize raw/*.txt transcripts into minutes/*.md via an "
        "OpenAI-compatible Chat Completions API.",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path.cwd(),
        help="Path to the customer repo working copy (default: current directory)",
    )
    parser.add_argument(
        "--raw-dir", default="raw", help="Transcript subdirectory (default: raw)"
    )
    parser.add_argument(
        "--minutes-dir", default="minutes", help="Output subdirectory (default: minutes)"
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
        "--temperature",
        type=float,
        default=DEFAULT_TEMPERATURE,
        help=f"Sampling temperature (default: {DEFAULT_TEMPERATURE}, env OPENAI_TEMPERATURE)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help=f"Max output tokens (default: {DEFAULT_MAX_TOKENS}, env OPENAI_MAX_TOKENS)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate minutes even if the output file already exists",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List what would be summarized without calling the API",
    )
    args = parser.parse_args()

    raw_dir = args.repo / args.raw_dir
    minutes_dir = args.repo / args.minutes_dir

    if not raw_dir.is_dir():
        print(f"error: no raw directory at {raw_dir}", file=sys.stderr)
        return 1

    transcripts = sorted(raw_dir.glob("*.txt"))
    if not transcripts:
        print(f"No .txt transcripts found in {raw_dir}")
        return 0

    pending: list[tuple[Path, Path]] = []
    for transcript in transcripts:
        out = minutes_dir / (transcript.stem + ".md")
        if out.exists() and not args.force:
            print(f"skip   {transcript.name} (minutes already exist)")
            continue
        pending.append((transcript, out))

    if not pending:
        print("Nothing to do — every transcript already has minutes.")
        return 0

    if args.dry_run:
        for transcript, out in pending:
            print(f"would  {transcript.name} -> {out.relative_to(args.repo)}")
        return 0

    # OpenAI() reads OPENAI_API_KEY / OPENAI_BASE_URL from the environment;
    # --base-url overrides the latter when given.
    client = OpenAI(base_url=args.base_url) if args.base_url else OpenAI()
    minutes_dir.mkdir(parents=True, exist_ok=True)
    for transcript, out in pending:
        raw_relpath = f"{args.raw_dir}/{transcript.name}"
        raw_link = f"../{args.raw_dir}/{transcript.name}"
        print(f"summarizing {transcript.name} ...", flush=True)
        minutes = summarize_transcript(
            client,
            args.model,
            transcript.read_text(),
            raw_relpath,
            raw_link,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
        )
        out.write_text(minutes)
        print(f"wrote  {out.relative_to(args.repo)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
