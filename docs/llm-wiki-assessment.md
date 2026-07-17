# LLM Wiki — assessment for meetmin

_Research note: is the "LLM Wiki" pattern a good fit for querying meeting minutes?_

**Verdict:** Strong conceptual fit — essentially the productized version of the
retrieve-then-read / index-routing approach, and it slots onto meetmin's
existing rails (Git repos of markdown, a summarizer, an OpenAI-compatible
endpoint).

## What "LLM Wiki" is

A **pattern** Andrej Karpathy published (April 2026), not a single product. The
core idea directly targets the "don't stuff all minutes into context" concern:
instead of re-reading raw sources on every query (classic RAG), the LLM
**compiles sources once into a persistent, cross-linked wiki of markdown pages
and maintains it over time**. Queries then read the *compiled wiki*, not the raw
pile.

Three layers:

1. **Raw sources** — original docs; the LLM reads, never edits.
2. **The wiki** — agent-generated, cross-linked markdown pages the LLM fully
   owns (creates, updates, keeps consistent). Anchored by an `index.md` catalog
   (one line per page) and an append-only `log.md`.
3. **The schema** — a `CLAUDE.md` / `AGENTS.md`-style config defining structure,
   naming, and workflows that turns the LLM into a "disciplined wiki maintainer."

Operations:

- **Ingest** — read source → create/update pages + cross-refs + log entry.
- **Query** — search the wiki, answer with citations, optionally file good
  answers back as new pages.
- **Lint** — flag contradictions, stale claims superseded by newer sources,
  orphaned pages.

At moderate scale (~100 sources / hundreds of pages) the `index.md` does the
routing — **no embeddings needed**.

## Why it fits meetmin unusually well

meetmin already *is* most of this:

| LLM Wiki layer | meetmin already has |
|---|---|
| Raw sources | `raw/*.txt` transcripts (immutable) |
| The wiki | `minutes/*.md` — a **proto-wiki** (per-meeting pages, not yet cross-linked topic/entity pages) |
| The schema | `AGENTS.md` |
| index.md router | exactly the "Tier 2 index routing" idea |
| Ingest step | `meetmin-summarize` (already reads → summarizes) |

Properties line up with the project's constraints:

- **Bounds context** — read a compiled, structured layer instead of all raw
  minutes → solves the speed / cost / unbounded-growth problem.
- **Markdown-in-Git** — native to Gitea, diffable, human-readable, **on-prem**
  (compliance-friendly). No new database / vector infra.
- **Not RAG** — matches "we don't have RAG and don't necessarily want it."
- **Compounds** — cross-meeting knowledge accretes into topic/entity pages
  (e.g. an "Export feature" page aggregating every mention across meetings, or
  an "ACME account" page), so answers get richer over time instead of being
  re-derived each query.

## Caveats to weigh

- **Bigger than the current tool.** The ingest/maintain step is *agentic*
  (read/write/edit/glob over the repo, cross-ref updates, linting) — a step up
  from the one-shot `chat.completions` summarizer. Reference implementations
  lean on an agent with file tools (e.g. Claude via MCP).
- **Depends on the model's bookkeeping discipline.** Karpathy flags it needs an
  LLM reliable at maintaining schema + cross-references. Worth testing whether
  the self-hosted `MiniMax-M2.7` holds up; if not, the maintenance step is where
  it would show.
- **Superseding decisions.** Meeting decisions change over time
  (toast → modal → …). The lint step is designed for exactly this, but requires
  discipline to keep pages non-contradictory.
- **Still has a scale ceiling.** The index-only approach is great to ~hundreds
  of pages per customer; well beyond that you'd eventually add retrieval. For
  per-customer meeting minutes, that's far off.
- **Keep it per-customer.** One wiki per customer repo preserves data
  segregation; cross-customer topic pages would mix data — avoid, per the
  compliance stance.

## Recommendation

Adopt the pattern **incrementally** — a natural evolution of what's merged, not
a wholesale new system:

1. Keep `raw/` as sources; add `index.md` + `log.md` and a `WIKI.md` schema
   (or extend `AGENTS.md`).
2. Evolve `minutes/` into a real wiki layer: keep per-meeting pages **and**
   start emitting cross-linked **topic/entity pages**.
3. Grow `meetmin-summarize` into an **ingest** command that updates the
   index/log and relevant topic pages (agentic, with file tools) rather than
   writing one isolated file.
4. `meetmin-ask` reads `index.md` → selects pages → answers from the compiled
   wiki (retrieve-then-read, with the index as router).

Pilot on the ACME repo first and stress-test the maintenance step with the
self-hosted model before committing.

## Sources

- [Karpathy's original LLM Wiki gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [lucasastorian/llmwiki — open-source implementation (docs + Claude via MCP)](https://github.com/lucasastorian/llmwiki)
- [nashsu/llm_wiki — desktop app implementation](https://github.com/nashsu/llm_wiki) ([DeepWiki overview](https://deepwiki.com/nashsu/llm_wiki))
- [tonbistudio/llm-wiki — open-source template](https://github.com/tonbistudio/llm-wiki)
- ["I built Karpathy's LLM Wiki twice — code vs .md" (Towards AI)](https://pub.towardsai.net/i-built-karpathys-llm-wiki-twice-once-as-code-once-as-a-md-heres-what-each-one-gives-up-08b31170999a)
- [Retrieval-augmented generation (Wikipedia), for the RAG contrast](https://en.wikipedia.org/wiki/Retrieval-augmented_generation)
