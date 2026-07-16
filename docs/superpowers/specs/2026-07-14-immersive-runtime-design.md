# AI Tavern Immersive Runtime Design

## Goal

Turn AI Tavern Lite from a themed character chat client into a safe, stateful role-playing runtime that can play modern V2/V3 character cards with visible consequences, persistent world state, native status panels, dice and battle snapshots, dynamic choices, and reversible turns.

## Product principles

1. Character-card text remains the creative source of truth, but card-provided HTML and JavaScript are never executed.
2. The runtime stores machine-readable state separately from narrative text.
3. Every completed assistant turn records state-before, patch, state-after, events, choices, dice, battle, and triggered lorebook entries.
4. State changes feed back into the next prompt and are visible to the player.
5. The runtime is card-agnostic, with adapters for recognizable conventions such as MVU JSON patches, `<dice>`, `<battlecheck>`, and `<battle>`.
6. Disabled worldbook entries are excluded from capability analysis and runtime adaptation.
7. No arbitrary card script, remote iframe, or raw replacement HTML is executed.

## Runtime profile

Each imported card receives a computed runtime profile stored inside normalized card JSON under `ai_tavern_runtime`:

- card spec and version
- suggested experience mode: relationship, adventure, or general
- capability flags: worldbook, alternate greetings, MVU state, dice, battle, battle checks, status placeholder
- counts of lorebook entries and regex scripts
- external-resource warning count
- safe renderer list
- default state schema and initial state

The profile is descriptive. It does not enable card scripts.

## State model

A `session_states` row stores the current and initial JSON state for each chat session. The default state has stable top-level areas:

- `scene`: location, time, weather, atmosphere, objective
- `character`: mood, expression, energy, condition
- `relationship`: affection, trust, tension, stage, recent_reason
- `player`: name, level, hp, max_hp, ac, conditions, resources
- `party`: actors visible in the current scene
- `quests`: active objectives
- `inventory`: lightweight items
- `combat`: active, round, turn, units, terrain, events
- `custom`: card-specific state, including imported MVU paths

Cards recognized as D&D-like start in adventure mode and expose RPG fields prominently. Other cards start with relationship and scene fields.

## Turn protocol

The prompt asks the model to append a hidden block after the narrative:

```xml
<tavern_state>
{"patch":[],"events":[],"choices":[],"dice":[],"battle":null,"expression":""}
</tavern_state>
```

The backend strips this block from visible text, validates patches, applies them, and stores a turn snapshot. It also reads safe legacy blocks:

- `<UpdateVariable>` / `<update_variable>` JSONPatch data
- `<dice>` six-line check result
- `<battlecheck>` seven-line combat result
- `<battle>` pipe-delimited tactical snapshot

Legacy blocks are converted to native metadata and removed from narrative. No HTML replacement strings are used.

## Patch safety

Supported operations are `replace`, `add`, `insert`, `increment`, `delta`, and `remove`. Limits:

- at most 64 operations per turn
- maximum path depth 16
- no keys beginning with `_`
- no prototype-pollution keys
- maximum serialized state size 512 KiB
- numeric clamps for affection/trust/tension/energy and D&D level/HP fields

Invalid individual operations are rejected without discarding the narrative. Rejection details are stored in turn metadata for diagnostics.

## Rollback

Every completed assistant message gets a `turn_snapshots` row. Regeneration restores `state_before`, removes the old snapshot and assistant message, then generates a replacement. An explicit rollback endpoint deletes messages after a selected message and restores the nearest retained state. This gives state-safe branching and save-point behavior.

## API

- `GET /api/characters/{id}/runtime-profile`
- `GET /api/sessions/{id}/runtime`
- `PUT /api/sessions/{id}/runtime/state`
- `GET /api/sessions/{id}/timeline`
- `POST /api/sessions/{id}/rollback`

Chat SSE adds:

- initial `runtime` event with state and triggered lorebook
- final `done` event with runtime metadata and updated state

## Frontend

The chat page becomes a three-zone stage:

- left: characters and sessions
- center: narrative, native dice/combat cards, dynamic choices, turn actions
- right: live scene, relationship/RPG status, events, active lorebook, quests, party, and timeline

The right panel is entirely data-driven. The old fake “初识 25%”, fake worldbook entries, and fake token counts are removed.

A compact mobile runtime drawer provides the same information below desktop width.

## Testing

Backend tests cover card profiling, state initialization, patches, legacy tag parsing, chat metadata storage, regeneration rollback, timeline rollback, and API responses. Frontend compilation verifies type and component integration. A D&D fixture derived only from non-optional runtime conventions verifies battle, dice, and MVU compatibility.
