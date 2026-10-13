# Security and privacy

This is a local prototype with no guaranteed security updates or monitored disclosure channel. The Android demo has no INTERNET permission, including merged dependencies, and starts with a generic local profile. Native check-ins persist in ordinary application SQLite/preferences; the app is not an encrypted vault. Local exports can reveal their contents.

Hosted developer/deploy/account services are excluded. Python includes experimental account/crypto/integration modules for contract tests, but the demonstrated command starts no HTTP server, external command or service. cryptography is declared and pinned; a passing tamper/envelope test is not a cryptographic security audit or a claim that Android storage is encrypted.

Garmin, AI/Codex diary extraction, S3 and PostgreSQL paths are optional/unverified. The default demonstrations require no credentials or external services. Do not add real provider keys or re-enable network permissions without reviewing data flows and security. Contact examples are non-contactable placeholders. Medical/clinical efficacy has not been established.
