# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest  | ✅ |
| older   | ❌ |

SOC-DB follows continuous delivery — only the latest release receives security updates.

## Reporting a Vulnerability

**Do not open a public issue.** Send details to **vitkuz573@gmail.com**.

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We aim to respond within 72 hours and will coordinate disclosure once a fix is released.

## Scope

- The Python package (`src/soc_db/`)
- The FastAPI server (`api/`)
- The GitHub Pages frontend (`index.html`)
- Dependencies listed in `pyproject.toml` and `api/requirements.txt`

## Out of Scope

- Data accuracy (chip specs) — these are [data issues](https://github.com/vitkuz573/soc-db/issues/new?template=03_data_issue.yml)
- Wikipedia availability (upstream dependency)
