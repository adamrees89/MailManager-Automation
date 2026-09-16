import sqlite3
import os
candidates = [
    r"c:\Users\Adam.Rees\OneDrive - Services Design Solution Ltd\Documents\HelperScripts\projects.sqlite",
    r"c:\Users\Adam.Rees\OneDrive - Services Design Solution Ltd\Documents\HelperScripts\Dev\MailManager-Automation-main\projects.sqlite",
]
for db in candidates:
    dbp = os.path.normpath(db)
    print('DB:', dbp)
    if not os.path.exists(dbp):
        print('  (not found)')
        continue
    try:
        conn = sqlite3.connect(dbp)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        print('  tables:', tables)
        if 'projects' in tables:
            cur.execute("SELECT COUNT(*) FROM projects")
            print('  projects:', cur.fetchone()[0])
            cur.execute("SELECT COUNT(*) FROM projects WHERE office_name IS NULL OR office_name=''")
            print('  projects missing office_name:', cur.fetchone()[0])
        conn.close()
    except Exception as e:
        print('  error:', e)
