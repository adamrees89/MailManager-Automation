import sqlite3, os
DB = os.path.normpath(r"c:\Users\Adam.Rees\OneDrive - Services Design Solution Ltd\Documents\HelperScripts\projects.sqlite")
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT p.id,p.name,p.project_number,p.office,p.client_abbr,l.path FROM projects p JOIN locations l ON p.location_id=l.id WHERE p.office_name IS NULL OR p.office_name='' LIMIT 100")
for r in cur.fetchall():
    print(r)
conn.close()
