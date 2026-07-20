# Tavern Safe Native Emulation 2.4.3 R2 Hotfix 3

Hotfix 3 replaces the previous all-or-nothing treatment of executable Tavern card extensions with a two-layer compatibility model:

1. **Executable source stays blocked.** Card JavaScript, remote imports, HTML event handlers and arbitrary Regex replacement output are never executed.
2. **Recognizable intent is restored natively.** The importer converts known display, filtering and button intents into a small declarative manifest consumed by AI Tavern Lite's own backend and React components.

No database migration is required.

## Safe native equivalents

For compatible cards, the platform can now restore these purposes without running card code:

- status placeholder → native inline status panel;
- night-sky / moon status styling → local CSS theme;
- relationship meters → native 0–100 progress meters;
- injury chips → native injury tags;
- important-memory paging → local previous/next controls, one item per page when requested;
- hide status placeholder from AI → prompt-history sanitation;
- hide `<UpdateVariable>` and `<Analysis>` protocol blocks from AI history → prompt-history sanitation;
- “重新处理变量” → automatic missing-state recovery on every complete turn;
- “重新读取初始变量” → confirmed native reset button;
- snapshot/replay intent → durable turn snapshots and timeline rollback.

The compatibility manifest stores capability names and presentation hints only. It never stores the original JavaScript body, remote URL, executable HTML or event handler.

## Card-declared state policy

Hotfix 3 extracts supported relationship rules from the card's enabled variable/controller entries and enforces them before the generic state engine, regardless of whether an operation came from the primary response or the fallback extractor.

For the reviewed 穗秋生 card this includes:

- relationship change per turn: absolute maximum 2 points per field;
- relationship change per story date: absolute maximum 5 points per field;
- numeric bounds: 0–100;
- terminal lock at affection 100, fear 0, dependence 100;
- native stage projection for base, 02, 03, 04, 05 and terminal 06;
- duplicate exact memory append and same-value replacement filtering.

When the engine adjusts an operation, the turn snapshot records a policy-adjustment event. Empty/no-op updates do not increment state revision.

## Safe controller and prompt behavior

The read-only controller interpreter remains limited to:

- `getvar` reads;
- numeric/boolean conditions;
- `getwi` lookup of card-owned lore entries;
- safe card/user/variable macros.

It does not evaluate general EJS or JavaScript. Controller-selected character-stage lore is treated as high-priority character context and may borrow genuinely unused optional prompt budget without taking the planned recent-history floor.

Status placeholders and historical variable protocol blocks are removed before chat history is sent to the model.

## Context recommendation

The runtime profile reports a per-card context recommendation derived from controller-referenced stage content. The reviewed card reports 16384. The 8192 setting remains usable for short conversations because optional budget is reallocated to controller output, but 16384 is recommended for sustained play with more history.

## Remaining boundary

This is semantic/native emulation, not a browser sandbox for arbitrary SillyTavern extensions. Unknown scripts, network calls, arbitrary DOM manipulation and custom third-party buttons remain disabled. Unsupported intent is reported rather than guessed or executed.
