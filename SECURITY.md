# Security Policy

## Supported Versions

Security fixes are applied to the **latest stable release** only. Older versions do not receive backported patches.

| Version | Supported |
|---------|-----------|
| 1.5.x (latest) | ✅ |
| < 1.5 | ❌ |

## Reporting a Vulnerability

**Please do not file a public GitHub issue for security vulnerabilities.**

Use GitHub's private vulnerability reporting instead:

1. Go to the [Security tab](../../security) of this repository.
2. Click **"Report a vulnerability"**.
3. Fill in the details and submit.

This opens a private advisory thread visible only to you and the maintainers. We will acknowledge your report within **48 hours** and aim to release a fix within **14 days** for confirmed critical issues.

If you are unsure whether something qualifies as a security issue, err on the side of reporting it privately.

## Scope

The following are **in scope**:

- `synthadoc` CLI (install, serve, ingest, query, lint, uninstall, …)
- The built-in HTTP server (`synthadoc serve`)
- The MCP server
- The Obsidian plugin bundled with Synthadoc
- Docker image (`chenp/synthadoc`)

The following are **out of scope**:

- Vulnerabilities in third-party LLM providers (OpenAI, Anthropic, etc.)
- Issues that require physical access to the machine
- Social engineering attacks

## Disclosure Policy

Once a fix is released, we will publish a GitHub Security Advisory describing the vulnerability and the affected versions.
