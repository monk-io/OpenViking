# Case Study: OpenViking Context Architecture Blog Post

This case study records the second OpenViking blog workflow: converting the Lark document `OpenViking Context Database Architecture` into `/post/openviking-context-database-architecture/`.

## Source And Outputs

- Source: Lark wiki document about OpenViking context database architecture.
- Human page: `/post/openviking-context-database-architecture/`.
- Agent page: `/post/openviking-context-database-architecture/llm.txt`.
- Cover asset: `public/assets/covers/openviking-context-database-architecture.png`.
- Author: `maojia`, GitHub `MaojiaSheng`.
- Published date: `2026-05-12`.

## Method That Worked

1. Scaffold first: create the slug, metadata, route registration, source provenance, `llm.txt`, initial cover, and article section order before trying to polish every block.
2. Use a second pass with parallel agents after the skeleton exists:
   - content-gap review against the source and `llm.txt`;
   - frontend block implementation in a separate file;
   - terminology and translation QA.
3. Integrate the agents' output centrally. The final article should feel authored, not assembled from unrelated widgets.
4. Translate after structure and components stabilize. Custom component labels, buttons, tables, and active states need the same bilingual treatment as paragraphs.
5. Verify generated static output, not only source JSX. Check page HTML, index card, OG/Twitter image, JSON-LD, `/llms.txt`, and post-level `llm.txt`.

## Content Lessons

- The first draft was too summary-like. The useful second pass added connective tissue: why `TYPE_PATH` differs from scalar filtering, how uploads become L0/L1/L2 context objects, where consistency breaks, why identity is a privacy model, and which evaluation question each benchmark answers.
- `llm.txt` must remain agent-clean. Even a Chinese `Source title` violates an English-only requirement, so translate metadata-like lines too.
- Keep `sourceTitle` in post metadata for provenance when useful, but do not surface rendering instructions or agent routing notes in the human article.

## Frontend Lessons

- Do not duplicate navigation. A sticky chip rail is useful only when there is no better navigation surface; if the left TOC already works, extra sticky buttons create noise.
- Interactive blocks must still be understandable by scrolling. The dashboard can focus attention, but the table above it should carry the architectural meaning.
- Validate visual states inside custom components. The evaluation progress bars failed because the fill element was an inline `span` with `width`, so the width did not render; set it to `display: block`.
- Remove unclear microcopy. The sentence about `find`, `read`, `overview`, and policy enforcement confused the reader and crowded the dashboard, so it was better deleted.
- Use `H4 toc={false}` inside cards and panels to avoid polluting the left TOC.

## Cover Lessons

- The best cover was not the most branded version. A large OV logo overwhelmed the composition; a small OV sail/crescent hint inside an airy watercolor system map worked better.
- Preferred style for similar posts: watercolor on cream paper, generous negative space, warm gold, muted sage, graphite, light umber, and only minimal indigo depth.
- Avoid literal keys, locks, oversized logos, dense diagrams, dark backgrounds, and blue/purple-dominant brand art.
- When using generated assets in the repo, copy the chosen file from the Codex generated-images directory into `public/assets/covers/`, keep the source file intact, and remove unreferenced temporary assets from the workspace.

## Verification Used

- `npm run build`.
- Search generated HTML for the new cover path and metadata.
- Search `llm.txt` for non-English characters when English-only was required.
- Check the generated post HTML for removed duplicate sticky navigation.
- Check generated dashboard markup for progress-bar fill elements and CSS.
