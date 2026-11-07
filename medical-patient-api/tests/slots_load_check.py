import os, sys, json
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
sys.path.insert(0, "/workspace/medical-patient-api")
from app import store
today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
win = {(today + timedelta(days=i)).isoformat() for i in range(8)}
docs = {s["doctorId"] for s in store._SLOTS.values()}
dates = sorted({s["date"] for s in store._SLOTS.values()})
future = {s["date"] for s in store._SLOTS.values() if s["date"] >= today.isoformat()}
missing = [(dc, dt) for dc in docs for dt in win if not any(s["doctorId"] == dc and s["date"] == dt for s in store._SLOTS.values())]
avail = sum(1 for s in store._SLOTS.values() if s["date"] >= today.isoformat() and s.get("available", True) and not s.get("booked"))
refs = {a.get("slotId") for a in store._APPOINTMENTS.values()}
kept_hist = [sid for sid in refs if sid in store._SLOTS and store._SLOTS[sid]["date"] < today.isoformat()]
dangling = [sid for sid in refs if sid and sid not in store._SLOTS]
lab_dates = sorted({s["date"] for s in store._LAB_EXAM_SLOTS.values() if s["date"] >= today.isoformat()})
print(json.dumps({"today": today.isoformat(), "doctorSlotDates": [dates[0], dates[-1]], "futureDates": len(future),
  "missingDoctorDayPairs": len(missing), "futureAvailable": avail, "pastBookedKept": len(kept_hist),
  "danglingApptSlotRefs": len(dangling), "labFutureDates": [lab_dates[0], lab_dates[-1]] if lab_dates else None,
  "lastRoll": store._LAST_SLOT_ROLL, "slotCount": len(store._SLOTS), "labSlotCount": len(store._LAB_EXAM_SLOTS)}, ensure_ascii=False))
r = store.roll_slots_window(persist=True)
print("second roll (idempotency):", r)
