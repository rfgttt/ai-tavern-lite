# Tavern-Compatible Runtime UX Design

## Goal

Replace AI Tavern's platform-invented fixed dashboards with a SillyTavern-compatible, card-driven runtime UI. A panel appears only when a card or conversation contains real data. Technical state remains available behind a developer disclosure instead of being presented as gameplay.

## Product behavior

### Session management

Each session row has an explicit menu with rename, export, and delete. Delete uses a confirmation dialog and immediately clears the active cache when the current session is removed.

### Card-driven panels

The right rail is assembled from real data and card capabilities:

- Scene: show the card scenario or runtime scene facts. Never invent `环境平稳`, `周围平静`, or `未命名场景`. When no scene exists, show one concise uninitialized notice.
- Relationship: show only when the card declares relationship state or a runtime patch has changed relationship data. Display card-native field names, latest change, source, and turns since last change.
- Tasks, clues, inventory, combat, and character status: show only when non-empty. Recognize common Chinese and English aliases.
- Card data: hide framework metadata (`runtime`, `model`, schema/version fields). Group meaningful unknown data under friendly categories; expose raw paths only in developer details.
- Timeline: rename to `剧情时间线`, explain its purpose, and display concrete events, state changes, lore triggers, and rollback action.
- Lorebook: show title, trigger keys, insertion position, content preview, and whether it was injected. Do not render anonymous `设定 1/2/3` labels.
- Compatibility report: translate capability names, show counts and usable/partial/isolated status, and explain what will actually render.

### Runtime protocol

Card-native variables take priority. Generic variable blocks are normalized using safe aliases (`scene`, `relationship`, `quests`, `inventory`, `combat`, and common Chinese equivalents). Unknown fields are retained under `custom`. Platform defaults are never treated as active gameplay data until changed.

The model contract requires natural narrative first and a hidden runtime block after it. It must not invent arbitrary relationship scores. It records scene facts, events, and existing card variables when the narrative establishes a real change. An empty patch is valid and is surfaced as `本轮无结构化变化`.

## Data flow

1. Character adapter creates capability metadata and preserves unknown extensions.
2. Session state retains the existing safe canonical namespaces for compatibility.
3. Output parser maps known aliases to canonical paths and retains unknown variables.
4. Turn snapshots remain the source of change activity, recency, lore activation, and rollback.
5. Frontend derives panel visibility from current data, initial state, card capabilities, and snapshot patches.

## Safety

No arbitrary card JavaScript executes in the main page. Regex and helper scripts remain analyzed or safely converted. Raw runtime paths and unsupported code are shown only in developer details.

## Compatibility

Existing databases and branches remain readable. Existing platform default state may still exist in stored sessions, but unchanged defaults are hidden. Any later real patch makes the relevant panel visible.

## Testing

- Unit tests for alias normalization and capability classification.
- API tests for session deletion cascade and lore payload detail.
- Runtime tests that unchanged platform defaults are distinguishable from real changes.
- Frontend production build.
- Existing backend regression suite.
- One-click self-test extended to cover session menu and conditional runtime panel markers.
