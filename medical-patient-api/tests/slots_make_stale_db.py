import json, os, sqlite3, sys
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
src, dst = "/workspace/medical-patient-api/data/app.db", "/tmp/s2/slots/stale.db"
s = sqlite3.connect(src); d = sqlite3.connect(dst); s.backup(d); s.close()
SHIFT = 40
def shift(v):
    return (date.fromisoformat(v) - timedelta(days=SHIFT)).isoformat()
n = 0
for kind in ("slots", "lab_exam_slots"):
    for (i, data) in d.execute("SELECT id, data FROM entities WHERE kind=?", (kind,)).fetchall():
        o = json.loads(data); o["date"] = shift(o["date"]); n += 1
        d.execute("UPDATE entities SET data=? WHERE kind=? AND id=?", (json.dumps(o, ensure_ascii=False), kind, i))
# make one booked appointment's slot point into the past (history must survive)
row = d.execute("SELECT id, data FROM entities WHERE kind='appointments' LIMIT 1").fetchone()
appt_slot = json.loads(row[1]).get("slotId") if row else None
d.commit()
print("stale DB: shifted", n, "slots by -%d days; sample appointment slot" % SHIFT, appt_slot)
dates = sorted({json.loads(x)["date"] for (x,) in d.execute("SELECT data FROM entities WHERE kind='slots'")})
print("stale doctor-slot dates:", dates[0], "..", dates[-1]); d.close()
