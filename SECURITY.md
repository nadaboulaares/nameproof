# Security Policy

nameproof is used to decide whether a payment goes to the intended payee, so matching flaws can
enable fraud. We treat the following as security issues:

- inputs that produce a false `MATCH` for a clearly different person or company,
- ways to extract an account holder's real name outside a `CLOSE_MATCH` result,
- crashes or pathological slowdowns triggered by crafted input.

## Reporting

Please **do not open a public issue.** Report privately via
[GitHub Security Advisories](https://github.com/nadaboulaares/nameproof/security/advisories/new).
Do not include real customer data in reports — reproduce with synthetic names.

You should receive an acknowledgement within 72 hours.

## Supported versions

Until 1.0, only the latest release receives fixes.
