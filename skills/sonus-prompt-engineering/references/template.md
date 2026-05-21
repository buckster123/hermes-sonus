# Suno v[N.N] — Version Addon Template

> **How to use this template:**
>
> 1. Copy this file to `references/versions/v<N>.md` (e.g., `v6.md`) or `v<N_N>.md` for point releases (e.g., `v6_5.md`). Underscore not period — matches the API enum convention (`V5_5`).
> 2. Document only what's *different* from the prior version. Don't restate unchanged behavior — the core skill files cover that.
> 3. Walk the **Release checklist** at the bottom when done.
> 4. Delete this header and the meta-comments below before committing.

---

# Suno v[N.N] ([Month Year])

[One- or two-sentence summary of what this release does. Frame it as the *delta* from the prior version. Example: "v6 introduces real-time generation streaming and a redesigned vocal engine with adversarial training. The core prompting model is unchanged; v6 layers new capabilities on top of v5.5's foundation."]

[If applicable, add a one-line context about how users describe it — e.g., "v6 is described by users as 'studio-quality on first try'" or similar.]

This document covers what's *new for prompt engineering* in v[N.N] versus [prior version]. The general Suno prompting techniques from `advanced-hacks.md`, `song-structure.md`, and `model-internals.md` all still apply — v[N.N] is a [refinement / breakthrough / expansion], not a replacement of the prompting model.

## API model identifier

`V[N_N]` (the sunoapi.org enum string). [Note any aliases or version-specific deprecations.]

## Character limits

| Field | Prior version | v[N.N] |
|---|---|---|
| Style | [prior] chars | [new] chars |
| Lyrics (custom mode `prompt`) | [prior] chars | [new] chars |
| Title | [prior] chars | [new] chars |
| Non-custom mode prompt | [prior] chars | [new] chars |

[State whether limits changed or stayed the same. If unchanged: "No change from v[prior]. The stability target guidance from prior versions still applies."]

## What v[N.N] changes architecturally

[Bullet list of major architectural shifts. Each bullet: name the change, then explain the prompting implication.]

- **[Change name]:** [What changed]. [Why it matters for prompts.]
- **[Change name]:** [What changed]. [Why it matters for prompts.]

[Examples of what this section might contain:]
- New generation engine or model architecture
- Changed handling of negative prompts
- New persistent memory features (voice/instrument/style across project)
- New workflow primitives (streaming, real-time, etc.)
- Studio or post-production tooling changes

## v[N.N]-specific prompt engineering deltas

[The meat of the doc. What should the AI do differently when targeting this version? Organize as subsections.]

### [Delta category 1, e.g., "Vocal control vocabulary"]

[Describe what's new. Give concrete examples. Cite community findings if applicable.]

**[Sub-category]:**
- `term1`, `term2`, `term3`

**[Sub-category]:**
- `term1`, `term2`, `term3`

[Practical guidance: how many to stack, what compounds, what conflicts.]

### [Delta category 2, e.g., "Lyric phrasing"]

[Describe new phrasing rules / sweet spots / community-discovered patterns.]

### [Delta category 3, e.g., "Structure handling"]

[Describe section tag behavior changes, new section types if any.]

[Add more subsections as needed. Aim for 2-5 substantive deltas. If there's only one delta, the version probably doesn't warrant its own addon — fold into version-history.md instead.]

## What stays the same

[Reassures the AI that prior techniques still work. Short bullet list:]

- All section tags (`[Verse]`, `[Chorus]`, etc.) — same behavior
- Symbol/kaomoji/binary hacks — still work for instrumental texture
- The styles field reads the same vocabulary
- Punctuation conventions for vocal control (`::`, `( )`, `{ }`, `--`, etc.) — unchanged
- BPM, time signature, alt tuning, fractional BPM — all parsed
- Cross-cultural symbols — still effective
- Bracketed pseudocode (`[Infinite Loop: ...]`, `[EmotionMap: ...]`) — still parsed as directives

[Adjust this list based on what actually changed in v[N.N]. If something *did* change, remove it from this list and document it under "deltas" above.]

## API parameters introduced/refined for v[N.N]

[Document new or changed API parameters exposed by sunoapi.org or similar wrappers.]

- `[paramName]` ([type], [range]): [What it does]. [Default value if known].
- `[paramName]` ([type], enum): [What it does]. [Version-availability note].

[If no new API params, write: "No new API parameters. The v[prior] parameter set still applies in full."]

## [Optional: tooling/feature sections specific to this version]

[Add subsections for major non-prompting features that an AI using this skill should know about — e.g., new web UI features, Studio improvements, mobile-only additions, etc. Keep brief; this is reference, not marketing.]

[Examples of section headings used in prior addons:]
- ### Suno Studio integration
- ### Voice cloning workflow
- ### Custom fine-tuning

## Practical implications

[Synthesizes the deltas into actionable guidance. Bullet list of "when to use v[N.N] vs older" or "what changes in your default workflow."]

- For [use case]: [what to do differently on v[N.N]]
- For [use case]: [what to do differently on v[N.N]]
- For app integration: [API-level implications]

## Known quirks and trade-offs

[Anything that's regressed or has unexpected behavior. Don't sugarcoat — the AI needs this to set user expectations.]

- [Quirk or trade-off]
- [Quirk or trade-off]

## When to recommend v[N.N] over [prior version]

- Reach for v[N.N] when:
  - [Trigger condition 1]
  - [Trigger condition 2]
- Default to [prior version] when:
  - [Trigger condition 1]

---

## Release checklist (delete this section before committing)

When you finish writing the version addon, walk these steps:

- [ ] **Add row to `references/version-history.md` quick-reference table.** Include API enum, char limits, release date, key features, and a link to this file.
- [ ] **Update `references/version-history.md` "Newer versions" pointer list** to include this version.
- [ ] **Update `scripts/build_payload.py`'s `MODEL_LIMITS` dict** if char limits changed. Add a new entry keyed by the API enum string (e.g., `"V6"`).
- [ ] **Update `scripts/build_payload.py`'s default `--model` argument** if this becomes the new production default (default is set on the `argparse.add_argument("--model", ...)` line near the bottom of the file).
- [ ] **Update `SKILL.md` version-awareness section** if this becomes the new default. Specifically: the "Quick start workflow" step 1, and the "Version awareness" section.
- [ ] **Update `SKILL.md` field-section subtitles** if char limits changed (e.g., `### Title (100 chars on v4.5+/v5/v5.5; 80 on v4.0)`).
- [ ] **Update `SKILL.md` frontmatter metadata version** (bump the skill's own version, not Suno's) to reflect the addition.
- [ ] **If new API params were introduced:** update `references/api-integration.md` field-mapping table and document the new params under "What's new in v[N.N]" or similar.
- [ ] **If new MCP tools would be useful:** consider adding them to the MCP server wrapper in `mcp_server/` (if present).
- [ ] **Run a sanity test:** `python scripts/build_payload.py` with a minimal input and `--model V[N_N]` to confirm the new model enum is accepted and validation passes.
- [ ] **Delete this checklist section and the template-usage header at the top of the file.**

## Sources to cite

When researching a new version, prioritize:

1. Suno's official blog: `https://suno.com/blog/`
2. Suno's help center: `https://help.suno.com/`
3. sunoapi.org docs: `https://docs.sunoapi.org/`
4. Community findings from r/SunoAI, Discord, X — useful for *empirical* prompt-engineering deltas not in official docs
5. Independent reviews and walk-throughs (Medium, blog posts) — useful for vocabulary that works in practice

Don't rely on training-data knowledge for current versions — Suno's release cadence is faster than model cutoffs. Web-search before writing the addon.
