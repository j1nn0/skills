# Security Policy

## Supported Versions

Only the latest version of each package is supported with security updates.
Please always use the latest release.

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Since both extensions share a monorepo, GitHub advisories are repository-level and cannot be scoped to one package. Report vulnerabilities through the repository's security advisory feature: https://github.com/j1nn0/skills/security/advisories/new.

You can expect an initial response within a few days. If for some reason you do not, please follow up with a comment on the advisory to ensure we received your original report.

## pi-footer specific concerns

This extension reads provider credentials to query subscription quota endpoints. Reports about credential exposure, credentials being sent to unintended endpoints, or credentials appearing in footer output are especially welcome.
