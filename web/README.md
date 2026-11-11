# The page

A React page that shows one `findings.json`. It is a shell today: header, logo, light and dark themes, the design
system, and the data arriving. The real screen is James's to build.

## See it
From the repo root, with nothing installed but Python:

```bash
./run.sh
```

That serves the built page (`web/dist`, committed) and the example findings at http://localhost:8010.

## Work on it
```bash
cd web
npm install
npm run dev          # the page with live reload, on http://localhost:5173
```
Keep `./run.sh serve --no-open` running beside it so the page has a server to ask. Or open
`http://localhost:5173/?example=1` to use the hand-written example with no server.

After a change: `npm run build`, and commit `web/dist` so nobody needs Node to run the tool.

## What is here
| File | What it is |
|---|---|
| `src/App.tsx` | The shell. A comment marks where the screen goes and lists the six things it must show. |
| `src/findings.ts` | TypeScript types for `findings.json`. The rules for each field are in `docs/OUTPUT-CONTRACT.md`. |
| `src/api.ts` | The only place that talks to the server. |
| `src/theme.ts` | Light and dark, remembered. |
| `src/Panel.tsx` | A side drawer: focus stays inside it, Escape closes it. |
| `src/index.css` | The design tokens: colours for both themes, the three typefaces. Use the tokens, never a literal colour. |
| `src/App.css` | The design system's classes: verdict word, check strip, meters, tables, drawers, buttons. |
| `public/brand/` | The mark for light and dark, and the icons. |

## The design, in four rules
- **Indigo is the brand colour. Pink means one thing: "this is the cell being pointed at."** Nothing else is pink.
- **Verdict colours carry meaning** (ready green, conditional amber, insufficient grey, blocked red). Never use them
  for decoration, and never as the only signal: pair them with the word or a mark.
- **Red Hat Display** for the verdict and headings, **Red Hat Text** for everything read, **Red Hat Mono** for ids,
  cells and hashes. Sentence case. No capital-letter labels.
- **The page computes nothing.** Every number on screen is read from `findings.json`. If the screen needs something
  the file lacks, ask Ahmed to add a field.

## Parts to reuse
`parts-from-readyset/` holds the components from the earlier ReadySet page. They are not compiled and will not run as
they are, because they talk to the old API. Lift what is useful:

| File | Worth taking |
|---|---|
| `VerdictColumn.tsx` | The check strip (one cell per item, coloured and marked by status), the findings list ordered worst first, the report menu with keyboard support. |
| `EvidencePanel.tsx` | A data grid with a sticky header, a pinned id column and the pointed-at cells marked in pink. |
| `BarPanel.tsx` | Meters that show a value against a limit; quoted sources with links. |
| `App.tsx` | Drag-and-drop upload with a visible drop state; loading skeletons. |
| `DraftPanel.tsx`, `api.ts` | Reference only. |
