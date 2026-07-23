# WIKI.md — schema for the meetmin LLM Wiki

This file is the **schema** for the compiled wiki: it tells the ingest agent how
to structure, name, and cross-link pages. It is loaded into the ingest agent's
system prompt. Keep it short and prescriptive.

## Layers

1. **Raw sources** — `meeting_dialog/*.md`. Original meeting transcripts. The
   agent **reads these but never edits them.**
2. **Minutes** — `minutes/<transcript-stem>.md`. One structured page per meeting
   (the per-meeting layer). Format is fixed (see "Minutes format" below).
3. **Wiki** — `wiki/`. Agent-owned, cross-linked knowledge that accretes across
   meetings:
   - `wiki/index.md` — the catalog / router. One line per wiki page.
   - `wiki/log.md` — append-only ingest log. One entry per ingested meeting.
   - `wiki/topics/*.md` — topic and entity pages (see "Topic pages").

## Minutes format

Each `minutes/<stem>.md` page uses exactly the shared minutes structure
(title, Date/Duration/Attendees/Source, Summary, Decisions, Action Items table,
Upcoming). The `Source` link points back at the raw transcript
(`../meeting_dialog/<stem>.md`).

## Topic pages

Topic/entity pages live in `wiki/topics/`. You decide which pages a meeting
warrants — infer them from the content. For this discussion group the natural
entities are things like **bands/artists**, **albums**, **subgenres/eras**,
**people** (recurring attendees), and **recurring debates/themes**.

Naming:

- Kebab-case filename derived from the entity, e.g.
  `wiki/topics/led-zeppelin.md`, `wiki/topics/prog-rock.md`,
  `wiki/topics/dark-side-of-the-moon.md`, `wiki/topics/person-dana.md`.
- Prefix person pages with `person-` to avoid clashes.

Each topic page should have:

- An `# <Title>` heading.
- A short prose summary of what the wiki knows about this entity.
- A `## Mentions` section: one bullet per meeting that referenced it, each
  linking back to that meeting's minutes page and summarizing what was said,
  e.g. `- [2026-07-01](../../minutes/2026-07-01-70s-rock-discussion.md): first
  cited as an example of massive early-70s production.`
- Cross-links to related topic pages using relative Markdown links, e.g.
  `[Led Zeppelin](led-zeppelin.md)`.

When a later meeting adds information, **update the existing page** (append a new
Mentions bullet, refine the summary) rather than creating a duplicate.

## index.md

`wiki/index.md` is the router used at query time. Format: a Markdown list, one
line per wiki page, each an entry of the form:

```
- [<Title>](topics/<file>.md) — <one-line description of what the page covers>
```

Keep it current: add a line when you create a page, refine the description as a
page grows. Do not list `index.md` or `log.md` themselves.

## log.md

`wiki/log.md` is append-only. For each meeting you ingest, append one entry:

```
## <YYYY-MM-DD> — <meeting title>
Ingested <transcript relpath>. Pages touched: <comma-separated wiki page files>.
```

Never rewrite or delete earlier log entries.

## Workflow (per meeting)

1. Read the raw transcript.
2. Read `wiki/index.md` (if it exists) to see what pages already exist.
3. Write/refresh `minutes/<stem>.md`.
4. For each entity/topic the meeting touches: read the existing topic page (if
   any), then create it or update it — add a Mentions bullet and cross-links.
5. Update `wiki/index.md` for any new/changed pages.
6. Append an entry to `wiki/log.md`.

## Consistency rules

- Never edit files under `meeting_dialog/`.
- Prefer updating an existing page over creating a near-duplicate; reuse the
  established filename for an entity.
- All links between wiki pages are relative.
- Be faithful to the transcripts — do not invent facts, quotes, or dates.
