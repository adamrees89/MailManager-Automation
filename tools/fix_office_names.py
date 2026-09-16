import configparser, sqlite3, os, re

root = os.path.normpath(r"c:\Users\Adam.Rees\OneDrive - Services Design Solution Ltd\Documents\HelperScripts")
config_path = os.path.join(root, 'Dev', 'MailManager-Automation-main', 'CONFIG.ini')
cfg = configparser.ConfigParser()
cfg.read(config_path)

# load mappings
OFFICE_MAP = {'BR':'Bristol','CA':'Cardiff'}
SINGLE_TO_DOUBLE = {'B':'BR','C':'CA'}
if cfg.has_section('mappings'):
    office_map_raw = cfg.get('mappings','office_map',fallback='')
    if office_map_raw:
        OFFICE_MAP.clear()
        for part in [p.strip() for p in re.split('[,\n]+', office_map_raw) if p.strip()]:
            if ':' in part:
                k,v = part.split(':',1)
                OFFICE_MAP[k.strip().upper()] = v.strip()
    single_map_raw = cfg.get('mappings','single_letter_map',fallback='')
    if single_map_raw:
        SINGLE_TO_DOUBLE.clear()
        for part in [p.strip() for p in re.split('[,\n]+', single_map_raw) if p.strip()]:
            if ':' in part:
                k,v = part.split(':',1)
                SINGLE_TO_DOUBLE[k.strip().upper()] = v.strip().upper()

DB = os.path.join(root, 'projects.sqlite')
DB = os.path.normpath(DB)
print('DB:',DB)
conn = sqlite3.connect(DB)
cur = conn.cursor()
# get projects with missing office_name
cur.execute("SELECT p.id, p.name, p.office, p.location_id, l.path FROM projects p LEFT JOIN locations l ON p.location_id=l.id WHERE p.office_name IS NULL OR p.office_name='' LIMIT 1000")
rows = cur.fetchall()
updated = 0
for pid, name, office, loc_id, path in rows:
    office_abbr = office.strip().upper() if office else None
    if office_abbr and len(office_abbr)==1:
        office_abbr = SINGLE_TO_DOUBLE.get(office_abbr, office_abbr)
    office_name = None
    if office_abbr:
        office_name = OFFICE_MAP.get(office_abbr)
    if not office_name and path:
        parts = [p for p in re.split(r"[\\/]+", path) if p]
        for p in parts:
            if len(p)==2 and p.isalpha():
                office_name = OFFICE_MAP.get(p.upper())
                if office_name:
                    break
    if office_name:
        cur.execute("UPDATE projects SET office_name=? WHERE id=?", (office_name, pid))
        updated += 1
conn.commit()
print('Updated office_name for', updated, 'projects')
conn.close()
