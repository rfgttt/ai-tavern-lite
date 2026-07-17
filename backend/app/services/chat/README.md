# Chat service architecture

The chat API is intentionally kept thin. Responsibilities are split as follows:

- `app/api/chat.py`: HTTP/SSE boundary and error mapping.
- `orchestrator.py`: public facade for stream, stop, regenerate, and preview actions.
- `preparation.py`: loads session data, validates provider settings, builds prompts, and creates pending messages.
- `stream_runner.py`: consumes the model stream, filters hidden runtime blocks, finalizes durable state, records diagnostics, and cleans active streams.
- `context.py`: immutable data passed from preparation to the independent stream transaction.
- `helpers.py`: serialization, SSE, identity, and redaction helpers.
- `errors.py`: user-facing service errors mapped to HTTP by the API layer.

Provider configuration is validated before pending user/assistant messages are written. Missing or unsafe configuration returns HTTP 422; unexpected provider initialization failures return HTTP 503. Once SSE streaming has started, upstream failures remain structured SSE `error` and `done` events with HTTP 200, because the response headers have already been sent.
