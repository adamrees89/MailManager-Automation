"""
scanner.py

Reads parent directories from CONFIG.ini, lists immediate subdirectories
(non-recursive), stores them in a SQLite `locations` table in `projects.sqlite`,
and ensures a `projects` table entry exists for each location.

Usage:
    python scanner.py --config CONFIG.ini --db projects.sqlite
"""
import argparse
import configparser
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone


def parse_parents(value):
    """Parse the `parents` value from CONFIG.ini.

    Supports:
    - Multiple lines (one parent per line)
    - Semicolon- or comma-separated values on the same line
    Keeps order and removes duplicates.
    """
    if not value:
        return []
    parts = []
    for line in value.splitlines():
        line = line.strip()
        if not line:
            continue
        # split any ; or , on the same line
        for p in re.split(r"[;,]", line):
            p = p.strip()
            if p:
                parts.append(p)

    # deduplicate while preserving order
    parents = []
    for p in parts:
        expanded = os.path.expanduser(p)
        if expanded not in parents:
            parents.append(expanded)
    return parents


def ensure_schema(conn):
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS locations (
      id INTEGER PRIMARY KEY,
      parent TEXT NOT NULL,
      path TEXT NOT NULL UNIQUE,
      name TEXT,
      created_at TEXT
    );
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS projects (
      id INTEGER PRIMARY KEY,
      name TEXT NOT NULL,
      location_id INTEGER,
      path TEXT NOT NULL UNIQUE,
      FOREIGN KEY(location_id) REFERENCES locations(id)
    );
    """)
    conn.commit()


def scan_parents(parents, conn, verbose=False):
    cur = conn.cursor()
    found = []
    for parent in parents:
        if not os.path.isdir(parent):
            if verbose:
                print(f"Parent path does not exist or is not a directory: {parent}")
            continue
        try:
            with os.scandir(parent) as it:
                for entry in it:
                    if entry.is_dir(follow_symlinks=False):
                        path = os.path.abspath(entry.path)
                        name = entry.name
                        try:
                            created_ts = entry.stat(follow_symlinks=False).st_ctime
                        except Exception:
                            created_ts = os.path.getctime(path)
                        created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()

                        # insert or update location
                        cur.execute(
                            "INSERT OR IGNORE INTO locations (parent, path, name, created_at) VALUES (?,?,?,?)",
                            (parent, path, name, created_at),
                        )
                        cur.execute(
                            "UPDATE locations SET parent=?, name=?, created_at=? WHERE path=?",
                            (parent, name, created_at, path),
                        )
                        conn.commit()
                        found.append((parent, path, name, created_at))
                        if verbose:
                            print(f"Recorded location: {path}")
        except PermissionError:
            if verbose:
                print(f"Permission denied scanning: {parent}")
    return found


def populate_projects_from_locations(conn, verbose=False):
    cur = conn.cursor()
    cur.execute("SELECT id, path, name FROM locations")
    rows = cur.fetchall()
    created = 0
    updated = 0
    for loc_id, path, name in rows:
        cur.execute("SELECT id, location_id FROM projects WHERE path=?", (path,))
        proj = cur.fetchone()
        if proj is None:
            cur.execute(
                "INSERT INTO projects (name, location_id, path) VALUES (?,?,?)",
                (name or os.path.basename(path), loc_id, path),
            )
            created += 1
            if verbose:
                print(f"Created project for {path}")
        else:
            proj_id, proj_loc_id = proj
            if proj_loc_id != loc_id:
                cur.execute("UPDATE projects SET location_id=?, name=? WHERE id=?", (loc_id, name or os.path.basename(path), proj_id))
                updated += 1
                if verbose:
                    print(f"Updated project {proj_id} -> location {loc_id}")
    conn.commit()
    return created, updated


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="CONFIG.ini", help="Path to CONFIG.ini")
    parser.add_argument("--db", default="projects.sqlite", help="Path to sqlite database file")
    args = parser.parse_args(argv)

    cfg = configparser.ConfigParser()
    read = cfg.read(args.config)
    if not read:
        print(f"Warning: could not read config file: {args.config} (continuing with defaults)")
    parents_raw = ""
    verbose = False
    if cfg.has_section("scanner"):
        parents_raw = cfg.get("scanner", "parents", fallback="")
        verbose = cfg.getboolean("scanner", "verbose", fallback=False)

    parents = parse_parents(parents_raw)
    if not parents:
        print("No parent directories configured. Edit CONFIG.ini or pass parents in the file.")
        return 1

    conn = sqlite3.connect(args.db)
    ensure_schema(conn)

    found = scan_parents(parents, conn, verbose=verbose)
    created, updated = populate_projects_from_locations(conn, verbose=verbose)

    print(f"Scan complete. Locations recorded: {len(found)}. Projects created: {created}, updated: {updated}.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
