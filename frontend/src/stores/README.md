# Frontend store architecture

`appStore.ts` is only the public composition entry. Domain behavior lives in slices:

- `characterSlice.ts`: character list, selection, create/update/import/delete.
- `sessionSlice.ts`: sessions, messages/runtime loading, cache, drafts and scroll positions.
- `chatSlice.ts`: streaming send/stop/regenerate and message mutations.
- `settingsSlice.ts`: model and application settings.
- `uiSlice.ts`: sidebar, runtime drawer and immersive error presentation state.

Shared state contracts live in `types.ts`; initial state, request guards and streaming helpers are separate modules.

## Rules for future changes

1. Keep `useAppStore` as the stable public API. Add behavior to the owning slice instead of growing `appStore.ts`.
2. Components should subscribe with field selectors, for example `useAppStore((state) => state.messages)`. Do not subscribe to the whole store.
3. Cross-domain actions may call `get()` methods from another slice, but each state field must have one clear owning slice.
4. Tests should call `resetStore()` through `resetAppStore()` so request guards and active streams are reset together.
5. Add request guards for asynchronous list/detail loads that can become stale after user navigation.

## Reliability controls

- `sessionReliability.ts` deduplicates concurrent message/runtime/timeline requests for the same session load generation.
- The session cache keeps at most six recently used sessions so long histories do not grow browser memory without bound.
- A cache entry is considered fresh only after messages, runtime state and timeline have all completed recently.
- `requestGuards.ts` invalidates both stale session loads and stale chat-stream callbacks when the user changes sessions or stops generation.
