import sqlite3
import os
DB = os.path.normpath(r"c:\Users\Adam.Rees\OneDrive - Services Design Solution Ltd\Documents\HelperScripts\projects.sqlite")
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT id,name,project_number,office,client_abbr,location_id FROM projects WHERE office_name IS NULL OR office_name='' LIMIT 50")
rows = cur.fetchall()
for r in rows:
    print(r)
conn.close()
