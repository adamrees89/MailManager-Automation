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

# defaults that can be overridden from CONFIG.ini [mappings]
OFFICE_MAP = {
    'BR': 'Bristol',
    'CA': 'Cardiff',
}
SINGLE_TO_DOUBLE = {
    'B': 'BR',
    'C': 'CA',
}
BID_SUFFIXES = ['BID LOST', 'NO BID']
STRICT_PARENT_PREFIXES = []


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
            location_id INTEGER UNIQUE,
            project_number TEXT,
            office TEXT,
            client_abbr TEXT,
            office_name TEXT,
            FOREIGN KEY(location_id) REFERENCES locations(id)
        );
        """)
        conn.commit()
        # Ensure any missing columns are added for older DBs
        cur.execute("PRAGMA table_info(projects)")
        cols = {row[1] for row in cur.fetchall()}
        if 'office_name' not in cols:
                cur.execute("ALTER TABLE projects ADD COLUMN office_name TEXT")
                conn.commit()
        # Create bids table
        cur.execute("""
        CREATE TABLE IF NOT EXISTS bids (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            location_id INTEGER,
            project_id INTEGER,
            status TEXT,
            created_at TEXT,
            FOREIGN KEY(location_id) REFERENCES locations(id),
            FOREIGN KEY(project_id) REFERENCES projects(id)
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


def normalize_bid_name(raw_name, folder_type):
    """Normalize bid folder names from pending/submitted.

    - pending: names may start with 'D1234' prefix and end with 1-2 initials; strip both.
    - submitted: may have had prefixes removed already but may include 'BID LOST' or 'NO BID' suffix.
    Returns (clean_name, status)
    """
    name = raw_name.strip()
    status = None
    # Detect BID LOST / NO BID suffix (submitted)
    # detect configured bid suffixes
    for sfx in BID_SUFFIXES:
        m_suffix = re.search(r"\b" + re.escape(sfx) + r"\b", name, flags=re.IGNORECASE)
        if m_suffix:
            status = sfx.upper()
            # remove the suffix
            name = re.sub(re.escape(sfx), "", name, flags=re.IGNORECASE).strip()
            break

    # Remove leading D#### or D##### prefix
    name = re.sub(r"^D\d{4,5}[-_ ]?", "", name, flags=re.IGNORECASE)
    # Remove trailing 1-2 letter initials
    name = re.sub(r"[-_ ]?[A-Za-z]{1,2}$", "", name).strip()

    # Normalize spaces
    name = re.sub(r"\s+", " ", name)

    # Determine default status for pending/submitted when not explicit
    if folder_type == 'pending':
        status = 'Pending'
    elif folder_type == 'submitted' and not status:
        status = 'Submitted'

    return name, status


def scan_bids(bids_parents, conn, verbose=False):
    """Scan bids parent directories which contain `pending` and `submitted` subfolders.
    Inserts locations, projects, and bids rows accordingly.
    Returns counts (locations, projects, bids)
    """
    cur = conn.cursor()
    loc_count = proj_count = bid_count = 0
    for parent in bids_parents:
        # allow the user to specify either the bids root (which contains
        # 'pending' and 'submitted' subfolders) or the subfolder paths
        # themselves (e.g. ...\Pending). Normalize to (root, [folders]).
        if os.path.basename(parent).lower() in ('pending', 'submitted'):
            root_parent = os.path.dirname(parent)
            folders_to_scan = [os.path.basename(parent).lower()]
        else:
            root_parent = parent
            folders_to_scan = ('pending', 'submitted')

        if not os.path.isdir(root_parent):
            if verbose:
                print(f"Bids parent path does not exist or is not a directory: {root_parent}")
            continue

        for folder in folders_to_scan:
            folder_path = os.path.join(root_parent, folder)
            if not os.path.isdir(folder_path):
                continue
            try:
                with os.scandir(folder_path) as it:
                    for entry in it:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                        path = os.path.abspath(entry.path)
                        raw_name = entry.name
                        try:
                            created_ts = entry.stat(follow_symlinks=False).st_ctime
                        except Exception:
                            created_ts = os.path.getctime(path)
                        created_at = datetime.fromtimestamp(created_ts, tz=timezone.utc).isoformat()

                        clean_name, status = normalize_bid_name(raw_name, folder)

                        # insert or update location
                        cur.execute(
                            "INSERT OR IGNORE INTO locations (parent, path, name, created_at) VALUES (?,?,?,?)",
                            (parent, path, raw_name, created_at),
                        )
                        cur.execute(
                            "UPDATE locations SET parent=?, name=?, created_at=? WHERE path=?",
                            (parent, raw_name, created_at, path),
                        )
                        conn.commit()
                        loc_count += 1

                        # ensure project for this location using cleaned name
                        project_name = clean_name or os.path.basename(path)
                        proj_num, office, client = parse_project_meta(project_name, path)
                        office_name = resolve_office_name(office, path)

                        # try to find by location path: get location id
                        cur.execute("SELECT id FROM locations WHERE path=?", (path,))
                        loc_row = cur.fetchone()
                        loc_id = loc_row[0] if loc_row else None

                        cur.execute("SELECT id FROM projects WHERE location_id=?", (loc_id,))
                        proj = cur.fetchone()
                        if proj is None:
                            cur.execute(
                                "INSERT INTO projects (name, location_id, project_number, office, client_abbr, office_name) VALUES (?,?,?,?,?,?)",
                                (project_name, loc_id, proj_num, office, client, office_name),
                            )
                            proj_id = cur.lastrowid
                            proj_count += 1
                        else:
                            proj_id = proj[0]
                            cur.execute(
                                "UPDATE projects SET name=?, project_number=?, office=?, client_abbr=?, office_name=? WHERE id=?",
                                (project_name, proj_num, office, client, office_name, proj_id),
                            )
                        conn.commit()

                        # insert bid record
                        cur.execute(
                            "INSERT INTO bids (name, location_id, project_id, status, created_at) VALUES (?,?,?,?,?)",
                            (raw_name, loc_id, proj_id, status, created_at),
                        )
                        bid_count += 1
                        conn.commit()
                        if verbose:
                            print(f"Recorded bid: {path} -> status {status}")
            except PermissionError:
                if verbose:
                    print(f"Permission denied scanning bids folder: {folder_path}")
    return loc_count, proj_count, bid_count


def populate_projects_from_locations(conn, verbose=False):
    cur = conn.cursor()
    cur.execute("SELECT id, path, name FROM locations")
    rows = cur.fetchall()
    created = 0
    updated = 0
    for loc_id, path, name in rows:
        # derive metadata from the location name/path
        project_name = name or os.path.basename(path)
        proj_num, office, client = parse_project_meta(project_name, path)
        # resolve office name (may infer from path if office is None)
        office_name = resolve_office_name(office, path)

        cur.execute("SELECT id, location_id FROM projects WHERE location_id=?", (loc_id,))
        proj = cur.fetchone()
        if proj is None:
            cur.execute(
                "INSERT INTO projects (name, location_id, project_number, office, client_abbr, office_name) VALUES (?,?,?,?,?,?)",
                (project_name, loc_id, proj_num, office, client, office_name),
            )
            created += 1
            if verbose:
                print(f"Created project for location {path}")
        else:
            proj_id, proj_loc_id = proj
            # update metadata if changed
            cur.execute(
                "UPDATE projects SET name=?, project_number=?, office=?, client_abbr=?, office_name=? WHERE id=?",
                (project_name, proj_num, office, client, office_name, proj_id),
            )
            updated += 1
            if verbose:
                print(f"Updated project {proj_id} -> location {loc_id}")
    conn.commit()
    return created, updated


def parse_project_meta(name, path=None):
    """Extract project_number (first 5 digits), office (two letters after),
    and client_abbr (next text block) from a project name or path.

    Returns (project_number, office, client_abbr) — values may be None if not found.
    """
    if not name and path:
        name = os.path.basename(path)
    if not name:
        return None, None, None

    s = name.strip()
    # If path is under a strict parent, apply strict parsing rules:
    # - project number is 5 digits
    # - office code (1-2 letters) must immediately follow the digits (no space)
    # - if there's a space after the number, office is considered missing
    if path and STRICT_PARENT_PREFIXES:
        pnorm = os.path.normpath(path).lower()
        for sp in STRICT_PARENT_PREFIXES:
            spnorm = os.path.normpath(sp).lower()
            if pnorm.startswith(spnorm):
                # strict parsing
                m_space = re.search(r"(\d{5})\s", s)
                if m_space:
                    proj_num = m_space.group(1)
                    return proj_num, None, None
                m = re.search(r"(\d{5})([A-Za-z]{1,2})(?:\b|\W)(.*)", s)
                if m:
                    proj_num = m.group(1)
                    office = m.group(2).upper()
                    client = (m.group(3) or '').strip().split()[0].upper() if m.group(3) else None
                    # expand single-letter office if mapping exists
                    if office and len(office) == 1:
                        office = SINGLE_TO_DOUBLE.get(office, office)
                    return proj_num, office, client
                # fallthrough to general parsing if strict patterns not found
    # Try to match patterns like: 12345ABClient, 12345 AB Client, 12345-AB_Client
    # Accept 4 or 5 digit project numbers and 1-2 letter office codes
    m = re.search(r"(\d{4,5})\s*[-_ ]?\s*([A-Za-z]{1,2})\s*[-_ ]?\s*([A-Za-z0-9]+)", s)
    if m:
        proj_num = m.group(1)
        office = m.group(2).upper()
        client = m.group(3).upper()
        # expand single-letter office codes using configured mapping
        if office and len(office) == 1:
            office = SINGLE_TO_DOUBLE.get(office, office)
        return proj_num, office, client

    # fallback: find first 5-digit sequence, then next two letters, then next token
    m2 = re.search(r"(\d{4,5})", s)
    if m2:
        proj_num = m2.group(1)
        rest = s[m2.end():]
        m3 = re.search(r"([A-Za-z]{1,2})", rest)
        office = m3.group(1).upper() if m3 else None
        # expand single-letter office codes using configured mapping
        if office and len(office) == 1:
            office = SINGLE_TO_DOUBLE.get(office, office)
        # client: next alnum token
        m4 = re.search(r"[A-Za-z0-9]+", rest[m3.end():] if m3 else rest)
        client = m4.group(0).upper() if m4 else None
        return proj_num, office, client

    return None, None, None


def resolve_office_name(abbr, path=None):
    """Map an office abbreviation to a full office name. If `abbr` is missing or unknown,
    attempt to infer from the path by looking for a two-letter folder name.
    """
    if abbr:
        name = OFFICE_MAP.get(abbr.upper())
        if name:
            return name
    # try to infer from path: look for a path component that's two letters
    if path:
        parts = re.split(r"[\\/]+", path)
        for p in parts:
            if len(p) == 2 and p.isalpha():
                inferred = OFFICE_MAP.get(p.upper())
                if inferred:
                    return inferred
    return None


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default=None, help="Path to CONFIG.ini (defaults to CONFIG.ini next to scanner.py)")
    args = parser.parse_args(argv)

    # Determine config path: if not provided, expect CONFIG.ini next to this script
    cfg = configparser.ConfigParser()
    config_path = args.config
    if not config_path:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "CONFIG.ini")
    read = cfg.read(config_path)
    if not read:
        print(
            f"Warning: could not read config file: {config_path} (continuing with defaults)\n"
            f"Tip: pass --config <path> to specify a config file, or place CONFIG.ini next to scanner.py"
        )
    parents_raw = ""
    verbose = False
    if cfg.has_section("scanner"):
        parents_raw = cfg.get("scanner", "parents", fallback="")
        verbose = cfg.getboolean("scanner", "verbose", fallback=False)

    parents = parse_parents(parents_raw)
    if not parents:
        print("No parent directories configured. Edit CONFIG.ini or pass parents in the file.")
        return 1

    # Load configurable mappings from [mappings]
    if cfg.has_section('mappings'):
        # office_map: format like BR:Bristol,CA:Cardiff or multiline
        office_map_raw = cfg.get('mappings', 'office_map', fallback='')
        if office_map_raw:
            OFFICE_MAP.clear()
            for part in re.split(r"[,\n]+", office_map_raw):
                part = part.strip()
                if not part:
                    continue
                if ':' in part:
                    k, v = part.split(':', 1)
                elif '=' in part:
                    k, v = part.split('=', 1)
                else:
                    continue
                OFFICE_MAP[k.strip().upper()] = v.strip()

        single_map_raw = cfg.get('mappings', 'single_letter_map', fallback='')
        if single_map_raw:
            SINGLE_TO_DOUBLE.clear()
            for part in re.split(r"[,\n]+", single_map_raw):
                part = part.strip()
                if not part:
                    continue
                if ':' in part:
                    k, v = part.split(':', 1)
                elif '=' in part:
                    k, v = part.split('=', 1)
                else:
                    continue
                SINGLE_TO_DOUBLE[k.strip().upper()] = v.strip().upper()

        bid_suffixes_raw = cfg.get('mappings', 'bid_suffixes', fallback='')
        if bid_suffixes_raw:
            BID_SUFFIXES.clear()
            for part in re.split(r"[,\n]+", bid_suffixes_raw):
                part = part.strip()
                if part:
                    BID_SUFFIXES.append(part.upper())
            # parsing section
            if cfg.has_section('parsing'):
                strict_raw = cfg.get('parsing', 'strict_parents', fallback='')
                if strict_raw:
                    # reuse parse_parents semantics to split lines/commas
                    STRICT_PARENT_PREFIXES.clear()
                    for line in strict_raw.splitlines():
                        for p in re.split(r"[,;]", line):
                            p = p.strip()
                            if p:
                                STRICT_PARENT_PREFIXES.append(os.path.expanduser(p))

    # Determine project DB path from config (scanner.db or scanner.project_db),
    # otherwise default to projects.sqlite next to this script.
    db_path = None
    if cfg.has_section("scanner"):
        # support both 'db' and 'project_db' keys for backward compatibility
        db_path = cfg.get("scanner", "db", fallback="").strip()
        if not db_path:
            db_path = cfg.get("scanner", "project_db", fallback="").strip()
    if not db_path:
        db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects.sqlite")
    if verbose:
        print(f"Using project DB: {db_path}")
    conn = sqlite3.connect(db_path)
    ensure_schema(conn)

    found = scan_parents(parents, conn, verbose=verbose)
    created, updated = populate_projects_from_locations(conn, verbose=verbose)
    # handle bids if configured
    if cfg.has_section("bids"):
        bids_raw = cfg.get("bids", "parents", fallback="")
        bids_parents = parse_parents(bids_raw)
        if bids_parents:
            b_locs, b_projs, b_bids = scan_bids(bids_parents, conn, verbose=verbose)
            print(f"Bids scanned. Bids locations: {b_locs}, projects: {b_projs}, bids: {b_bids}")

    # Print project statistics
    cur = conn.cursor()
    try:
        cur.execute("SELECT COUNT(*) FROM projects")
        total_projects = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM projects WHERE office_name IS NULL OR office_name=''")
        null_office = cur.fetchone()[0]
        print(f"Projects total: {total_projects}. Projects missing office_name: {null_office}.")
    except Exception:
        # ignore if projects table missing for some reason
        pass

    print(f"Scan complete. Locations recorded: {len(found)}. Projects created: {created}, updated: {updated}.")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
