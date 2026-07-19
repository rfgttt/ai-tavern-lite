# API Key Secure Storage V1

AI Tavern Lite stores model API keys differently by runtime platform.

## Windows

On Windows, a saved API key is encrypted with Windows DPAPI under the current Windows user profile. The encrypted file is stored at:

```text
%LOCALAPPDATA%\AI-Tavern-Lite\secrets\api-key.dpapi
```

The active SQLite database does not retain the API key row. The settings API returns only whether a key is configured, a last-four-character mask, the storage backend, and any recoverable storage error.

A key encrypted by one Windows user cannot normally be decrypted by a different Windows user account. Moving only the encrypted file to another computer or account is not a supported migration path.

## Legacy migration

At startup, before creating the normal SQLite startup backup, AI Tavern Lite checks for the legacy `app_settings.api_key` row. When found on Windows it:

1. encrypts the key with the current user's DPAPI profile;
2. reads it back and verifies the exact value;
3. removes the SQLite row with SQLite secure deletion enabled;
4. checkpoints/truncates SQLite WAL data and runs `VACUUM`;
5. only then creates the normal startup database backup.

If a different DPAPI key already exists, startup refuses to overwrite either value.

Historical database backup files created before this feature are not rewritten automatically. They should be treated as sensitive local files and deleted manually when no longer needed.

## Settings behavior

- Leaving the API Key field empty preserves the existing key.
- Saving a new non-empty value replaces the DPAPI value.
- The trash button explicitly deletes the encrypted key file.
- A corrupt or user-mismatched encrypted file is reported in the settings page and can be cleared without decrypting it.
- `AI_TAVERN_API_KEY` remains an environment-managed override and cannot be changed from the web page.

## Backup and restore

Portable AI Tavern backup ZIP files never include the DPAPI file or an API key database row. Restoring a portable backup leaves the current machine's DPAPI key unchanged.

## Non-Windows compatibility

Non-Windows runtimes retain the existing database-based compatibility behavior. Windows DPAPI protection is deliberately not simulated with a weak cross-platform encryption fallback.
