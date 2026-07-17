"""Summarize raw meeting transcripts into minutes using the Claude API.

Scans ``<repo>/raw/*.txt`` and, for each transcript that does not yet have a
matching ``<repo>/minutes/<stem>.md``, generates a structured minutes summary
with Claude and writes it. Existing minutes are left untouched unless
``--force`` is given.

Auth: set ``ANTHROPIC_API_KEY``, or run ``ant auth login`` — the SDK picks up
the resulting profile automatically.

Usage::

    meetmin-summarize --repo /path/to/customer-acme
    # or, without installing the console script:
    uv run python -m meetmin.summarize --repo /path/to/customer-acme
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anthropic

MODEL = "claude-opus-4-8"

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
    client: anthropic.Anthropic,
    model: str,
    transcript: str,
    raw_relpath: str,
    raw_link: str,
) -> str:
    """Return the Markdown minutes for a single transcript."""
    user_message = (
        f"RAW_RELPATH = {raw_relpath}\n"
        f"RAW_LINK = {raw_link}\n\n"
        f"Transcript:\n\n{transcript}"
    )
    response = client.messages.create(
        model=model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize raw/*.txt transcripts into minutes/*.md with Claude.",
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
    parser.add_argument("--model", default=MODEL, help=f"Claude model (default: {MODEL})")
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

    client = anthropic.Anthropic()
    minutes_dir.mkdir(parents=True, exist_ok=True)
    for transcript, out in pending:
        raw_relpath = f"{args.raw_dir}/{transcript.name}"
        raw_link = f"../{args.raw_dir}/{transcript.name}"
        print(f"summarizing {transcript.name} ...", flush=True)
        minutes = summarize_transcript(
            client, args.model, transcript.read_text(), raw_relpath, raw_link
        )
        out.write_text(minutes)
        print(f"wrote  {out.relative_to(args.repo)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
