# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |

## Reporting a Vulnerability

We take the security of Swarmind seriously. If you discover a security vulnerability, please do **not** open a public issue.

Instead, report it privately by emailing the maintainers at the address listed in the repository's `pyproject.toml` author metadata, or by opening a draft security advisory on GitHub via the **Security** tab of the repository.

Please include:
- A description of the vulnerability
- Steps to reproduce it
- Potential impact
- Any suggested fix (if known)

You should receive a response within 5 business days. We will keep you informed of the progress toward a fix and release.

## Disclosure Policy

When a vulnerability is reported:
1. We will acknowledge receipt within 5 business days.
2. We will investigate and develop a fix.
3. A security release will be published as soon as possible.
4. The vulnerability will be disclosed after the fix is released.

## Hardcoded Secrets

Swarmind includes automated secret scanning in the pre-commit hook. Never commit API keys, tokens, passwords, or other credentials to the repository. Use environment variables or a `.env` file (excluded via `.gitignore`) for local development.

## Branch Protection & Code Owners

The `main` branch is protected by GitHub branch protection rules. To contribute, you must open a Pull Request; direct pushes to `main` are rejected.

### Required Status Checks

Every PR must pass these CI jobs before merge:

| Job | What it checks |
|---|---|
| `lint` | ruff + mypy |
| `test` | pytest with coverage |
| `security` | bandit + pip-audit |

### Code Owners

`CODEOWNERS` (at the repo root) defines the review policy. The owner of each area is automatically requested as a reviewer on any PR that touches it. Areas with stricter review:

- `/scripts/`, `/.github/` — deployment & CI changes (high blast radius)
- `/harness/security/`, `/harness/qa/` — security & quality gates
- `/harness/tests/` — test contracts
- Root config: `pyproject.toml`, `uv.lock`, `Dockerfile`, `.env.example`

To add co-maintainers or team-based ownership, use the GitHub UI under **Settings → Code owners** or edit `CODEOWNERS` directly. Note: GitHub usernames are case-sensitive; the file uses `@MauricioFCC` (correct casing) and GitHub will silently ignore mismatched handles.
