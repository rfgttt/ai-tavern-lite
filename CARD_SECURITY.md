# Character Card Security Gate V1

Character Card Security Gate V1 adds a static, fail-safe review step before a JSON or PNG character card is imported.

## Threat model

The scanner treats every card field as untrusted data. It checks:

- JavaScript tags, HTML event handlers, dangerous URL schemes, iframe/object/embed/form elements;
- script/plugin/Tavern Helper extensions and active Regex replacement rules;
- remote images, fonts, audio/video and CSS imports;
- CSS overlays and legacy executable CSS constructs;
- suspiciously expensive regular expressions;
- prompt injection that asks the model to ignore platform rules, reveal hidden prompts, obtain API keys or headers, execute commands/tools, or transmit data to a URL;
- roleplay "highest priority" or "iron rule" declarations, which are reported as warnings rather than automatically labelled malware.

The scanner never resolves DNS, opens a socket, downloads an image/font, or fetches a card-provided URL.

## Import decisions

The UI always scans before import and offers:

- **Safe import (recommended):** removes executable extensions and card Regex replacements, strips dangerous HTML/CSS/resource loading, clears high-risk system/post-history instructions, and disables lorebook entries containing high-risk prompt injection.
- **Quarantine:** preserves the original card for inspection/export but blocks session creation.
- **Original import:** available only when there are no high-risk or blocked findings and no prompt-injection findings. Card scripts still remain non-executable in AI Tavern Lite.
- **Cancel:** stores nothing.

Imported cards record a small `extensions.ai_tavern_security` audit marker with the source SHA-256, selected mode and remediation summary.

## Existing cards

The character action menu includes **Security check**. It rescans the stored card and can create a separate `（安全副本）` character. The original character and its sessions are not modified.

## API and prompt isolation

API keys and custom authorization headers are not added to model messages. They are applied only by the provider client when making the outbound API request.

Prompt construction also adds platform security rules and neutralizes high-risk injection lines from legacy cards at runtime. This runtime guard protects cards imported before Security Gate V1, but it does not claim that static scanning can identify every future jailbreak technique.

## Risk labels

- `safe`: no active content or injection indicators found;
- `notice`: external resources, custom style, Regex replacement or narrative priority declarations require review;
- `high`: risky extensions, expensive Regex, prompt override, secret request, hidden-prompt leak or tool execution request;
- `blocked`: executable HTML/JavaScript, dangerous protocols or explicit data exfiltration instructions.

## Known limitations

- Static analysis cannot prove that a card author is benign or malicious.
- Plain text URLs are reported but are not removed unless they are used as active resources or exfiltration targets.
- V1 does not execute or render card-provided HTML/CSS/JavaScript. Future immersive rendering must continue to use native, allowlisted components.
- Prompt injection detection is deliberately conservative around ordinary roleplay rules to avoid destroying legitimate card behavior.
