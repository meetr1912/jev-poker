# Security

This is a local demo. It does not ship credentials and does not call any paid
API in CI.

- **No secrets in the repo.** `.env` is gitignored; `.env.example` holds empty
  placeholders only. CI runs the `--offline` path, which never reads
  `TYPESAFE_API_KEY`.
- **No real-money gambling.** The engine is local. Do not point this at
  real-money poker sites; automating them violates their terms of service.
- **Model output is constrained.** The engine generates the legal action names;
  the model only picks among them. It cannot produce selectors or sizes.

If you believe you found a security issue, open a private security advisory on
the repository rather than a public issue.
