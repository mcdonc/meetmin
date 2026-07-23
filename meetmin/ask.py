"""Answer questions against the compiled wiki (retrieve-then-read).

``meetmin-ask`` reads ``wiki/index.md`` as a router, asks the model which pages
are relevant to the question, reads only those pages, and answers from them with
citations. It does not re-read the raw transcripts — that's the whole point of
the compiled wiki.

Usage::

    meetmin-ask --repo customer-acme "when did punk come up and who raised it?"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from openai import OpenAI

from .chat import chat_completion
from .summarize import DEFAULT_MAX_TOKENS, DEFAULT_MODEL, DEFAULT_TEMPERATURE
from .wikitools import ToolError, WikiTools

SELECT_SYSTEM_PROMPT = """\
You are a router for a wiki of meeting knowledge. You are given the wiki's
index (one line per page) and a user question. Choose the pages most likely to
contain the answer.

Reply with ONLY a JSON array of the page paths (exactly as they appear in the
index, e.g. "topics/led-zeppelin.md"). Pick at most {k} pages; return [] if none
look relevant."""

ANSWER_SYSTEM_PROMPT = """\
You answer questions using ONLY the provided wiki pages. Cite the page path(s)
you used inline, e.g. (topics/led-zeppelin.md). If the pages do not contain the
answer, say so plainly — do not speculate or use outside knowledge."""


def select_pages(
    client: OpenAI, model: str, index_text: str, question: str, k: int,
    temperature: float, max_tokens: int,
) -> list[str]:
    """Ask the model which index pages are relevant; return their paths."""
    response = chat_completion(
        client,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": SELECT_SYSTEM_PROMPT.format(k=k)},
            {
                "role": "user",
                "content": f"Wiki index:\n\n{index_text}\n\nQuestion: {question}",
            },
        ],
    )
    return _parse_paths((response.choices[0].message.content or "").strip())


def _parse_paths(text: str) -> list[str]:
    """Extract a JSON array of paths from the model's reply, tolerantly."""
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return []
    return [str(p) for p in data if isinstance(p, (str,))]


def answer_question(
    client: OpenAI, model: str, question: str, pages: dict[str, str],
    temperature: float, max_tokens: int,
) -> str:
    """Answer the question from the given ``{path: content}`` pages."""
    context = "\n\n".join(
        f"=== {path} ===\n{content}" for path, content in pages.items()
    )
    response = chat_completion(
        client,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Wiki pages:\n\n{context}\n\nQuestion: {question}",
            },
        ],
    )
    return (response.choices[0].message.content or "").strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Answer a question against the compiled wiki (index-routed "
        "retrieve-then-read).",
    )
    parser.add_argument("question", help="The question to answer")
    parser.add_argument(
        "--repo", type=Path, default=Path.cwd(),
        help="Path to the customer repo working copy (default: current directory)",
    )
    parser.add_argument(
        "--wiki-dir", default="wiki", help="Wiki subdirectory (default: wiki)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=5,
        help="Max wiki pages to read for the answer (default: 5)",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Model (default: {DEFAULT_MODEL})")
    parser.add_argument(
        "--base-url", default=os.environ.get("OPENAI_BASE_URL"),
        help="OpenAI-compatible endpoint base URL (default: OPENAI_BASE_URL env / OpenAI)",
    )
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    parser.add_argument(
        "--show-sources", action="store_true",
        help="Print which pages were selected before the answer",
    )
    args = parser.parse_args()

    wiki_dir = args.repo / args.wiki_dir
    index_path = wiki_dir / "index.md"
    if not index_path.exists():
        print(
            f"error: no wiki index at {index_path} — run meetmin-ingest first",
            file=sys.stderr,
        )
        return 1

    tools = WikiTools(args.repo)
    client = OpenAI(base_url=args.base_url) if args.base_url else OpenAI()

    index_text = index_path.read_text()
    selected = select_pages(
        client, args.model, index_text, args.question, args.max_pages,
        args.temperature, args.max_tokens,
    )
    if not selected:
        print("No relevant wiki pages found for that question.")
        return 0

    pages: dict[str, str] = {}
    for rel in selected:
        # Paths in the index are relative to the wiki dir.
        full = f"{args.wiki_dir}/{rel}"
        try:
            pages[rel] = tools.read_file(full)
        except ToolError:
            # Index referenced a page that no longer exists; skip it.
            continue

    if not pages:
        print("Selected pages could not be read.")
        return 0

    if args.show_sources:
        print("Sources: " + ", ".join(pages) + "\n")

    print(answer_question(
        client, args.model, args.question, pages, args.temperature, args.max_tokens
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
