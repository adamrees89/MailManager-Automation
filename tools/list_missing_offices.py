import sqlite3, os
DB = os.path.normpath(r"c:\Users\Adam.Rees\OneDrive - Services Design Solution Ltd\Documents\HelperScripts\projects.sqlite")
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("SELECT office, COUNT(*) FROM projects WHERE office_name IS NULL OR office_name='' GROUP BY office ORDER BY COUNT(*) DESC")
for office, cnt in cur.fetchall():
    print(f"{office!r}: {cnt}")
conn.close()
