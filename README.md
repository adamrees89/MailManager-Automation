# MailManager-Automation

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Contributions Welcome](https://img.shields.io/badge/contributions-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![CI](https://github.com/adamrees89/MailManager-Automation/workflows/tests/badge.svg)](https://github.com/adamrees89/MailManager-Automation/actions)

A small utility to scan a directory tree, record file paths and creation dates into a SQLite database, and reconcile those records against MailManager XML location files.

## Features
- Walk a target directory and capture file paths and created timestamps
- Store records in a SQLite table for fast lookups and reconciliation
- Parse MailManager XML files and compare expected locations to actual filesystem records
- Produce reconciliation reports (missing, orphaned, or mismatched files)

## Quickstart

Requirements:
- Python 3.8+
- Uses the standard `sqlite3` library and `xml` modules (no external deps required for core features)

Install (optional virtualenv):

```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\\Scripts\\activate
pip install -r requirements.txt  # optional, if adding extras
```

Run (example CLI idea):

```bash
python -m mailmanager_automation scan --root /path/to/scan --db data/locations.db
python -m mailmanager_automation reconcile --db data/locations.db --mailman-xml /path/to/mailmanager.xml
```

## Database schema

Example SQLite table schema used by the scanner:

```sql
CREATE TABLE IF NOT EXISTS files (
  id INTEGER PRIMARY KEY,
  path TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL
);
```

Timestamps are stored as ISO 8601 strings (UTC recommended).

## Reconciliation overview

- Parse MailManager XML files to extract the expected file locations
- Compare extracted locations against `files.path` entries in the SQLite DB
- Produce three sets: `missing` (in XML but not on disk), `orphaned` (on disk but not in XML), and `mismatched` (exists but timestamp differs if relevant)

## Configuration

- Database path: path to SQLite DB file
- Root scan path: filesystem root folder to walk
- XML source: path(s) to MailManager XML exports

## Logging & reports

- The tool should write reconciliation reports to stdout and optionally to JSON/CSV files for later analysis.

## Todo

- [ ] Implement directory scanner and SQLite writer
- [ ] Implement MailManager XML parser
- [ ] Implement reconciliation logic and reporting
- [ ] Add CLI entrypoint and configuration file support
- [ ] Add tests and CI

## Contributing

See CONTRIBUTING.md for contribution guidelines and CODE_OF_CONDUCT.md for behavior expectations.

## License

This repository uses the license in the LICENSE file.
