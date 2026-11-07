"""In-memory catalog, slots, appointments, and consult sessions."""

from __future__ import annotations

import copy
import threading
from datetime import datetime, timedelta
from typing import Any, Optional
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Shanghai")

_counter = {"session": 0, "appt": 0, "slot": 0, "patient": 0, "preconsult": 0, "lab": 0, "queue": 0, "message": 0, "vital": 0, "chronic_alert": 0}


def _now_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M:%S")


def _today() -> datetime:
    return datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)


def _next_id(prefix: str, key: str) -> str:
    _counter[key] += 1
    return f"{prefix}{_counter[key]}"


# ---------- Departments ----------
DEPARTMENTS: list[dict[str, str]] = [
    {"id": "dept-gi", "name": "消化内科", "intro": "胃肠、肝胆胰疾病诊治", "location": "门诊楼3F 东区", "tips": "空腹检查请先到1F抽血处；胃肠镜预约在诊室旁登记"},
    {"id": "dept-resp", "name": "呼吸内科", "intro": "咳嗽、肺炎、哮喘等呼吸道疾病", "location": "门诊楼3F 西区", "tips": "发热患者请先测体温；肺功能检查在同层3F-西侧"},
    {"id": "dept-cardio", "name": "心内科", "intro": "胸痛、高血压、心律不齐等", "location": "门诊楼4F 东区", "tips": "胸痛请优先急诊；心电图室在4F东侧走廊"},
    {"id": "dept-neuro", "name": "神经内科", "intro": "头晕、头痛、脑血管病等", "location": "门诊楼4F 西区", "tips": "头晕伴肢体无力请走急诊绿色通道"},
    {"id": "dept-uro", "name": "泌尿外科", "intro": "尿路感染、结石、前列腺等", "location": "门诊楼2F 东区", "tips": "尿常规采样杯在门口自取；B超预约同层2F"},
    {"id": "dept-gyn", "name": "妇科", "intro": "妇科炎症、月经相关、盆腔疾病", "location": "妇儿楼2F", "tips": "请勿空腹妇科超声以外的检查；更衣室在诊区入口"},
    {"id": "dept-ortho", "name": "骨科", "intro": "关节、脊柱、外伤相关", "location": "门诊楼5F", "tips": "拍片请先到放射科（医技楼1F）取号"},
    {"id": "dept-er", "name": "急诊科", "intro": "急危重症优先处置", "location": "急诊楼1F", "tips": "分诊台先挂号分诊；红区直入抢救"},
    {"id": "dept-gp", "name": "全科医学", "intro": "常见病初诊与健康管理", "location": "门诊楼1F 中区", "tips": "适合常见病初诊；慢病续方可咨询护士站"},
    {"id": "dept-ent", "name": "耳鼻喉科", "intro": "鼻塞、咽痛、耳鸣听力等", "location": "门诊楼2F 西区", "tips": "听力检查需提前预约；请勿佩戴耳机进入检查室"},
    {"id": "dept-derm", "name": "皮肤科", "intro": "皮疹、过敏、皮肤感染等", "location": "门诊楼1F 西区", "tips": "皮疹请勿自行涂抹药膏后再就诊，便于医生观察"},
]

DEPARTMENT_BY_ID = {d["id"]: d for d in DEPARTMENTS}


# ---------- Doctors ----------
DOCTORS: list[dict[str, str]] = [
    {"id": "doc-gi-1", "departmentId": "dept-gi", "name": "张明", "title": "主任医师", "intro": "擅长消化性溃疡、胃炎、幽门螺杆菌相关疾病"},
    {"id": "doc-gi-2", "departmentId": "dept-gi", "name": "李华", "title": "副主任医师", "intro": "擅长肝胆胰疾病与消化内镜"},
    {"id": "doc-resp-1", "departmentId": "dept-resp", "name": "王强", "title": "主任医师", "intro": "擅长慢阻肺、肺炎、哮喘"},
    {"id": "doc-resp-2", "departmentId": "dept-resp", "name": "陈静", "title": "主治医师", "intro": "擅长呼吸道感染与过敏相关咳嗽"},
    {"id": "doc-cardio-1", "departmentId": "dept-cardio", "name": "赵磊", "title": "主任医师", "intro": "擅长冠心病、高血压、心律失常"},
    {"id": "doc-cardio-2", "departmentId": "dept-cardio", "name": "刘芳", "title": "副主任医师", "intro": "擅长心力衰竭与血脂管理"},
    {"id": "doc-neuro-1", "departmentId": "dept-neuro", "name": "周伟", "title": "主任医师", "intro": "擅长脑血管病、头晕头痛"},
    {"id": "doc-neuro-2", "departmentId": "dept-neuro", "name": "吴婷", "title": "主治医师", "intro": "擅长偏头痛与周围神经病"},
    {"id": "doc-uro-1", "departmentId": "dept-uro", "name": "郑凯", "title": "副主任医师", "intro": "擅长尿路感染、结石、前列腺疾病"},
    {"id": "doc-gyn-1", "departmentId": "dept-gyn", "name": "孙丽", "title": "主任医师", "intro": "擅长妇科炎症与月经相关疾病"},
    {"id": "doc-ortho-1", "departmentId": "dept-ortho", "name": "马超", "title": "主任医师", "intro": "擅长颈肩腰腿痛与关节退变"},
    {"id": "doc-er-1", "departmentId": "dept-er", "name": "黄勇", "title": "主任医师", "intro": "急危重症抢救与分诊"},
    {"id": "doc-gp-1", "departmentId": "dept-gp", "name": "徐倩", "title": "副主任医师", "intro": "常见病初诊与慢病管理"},
    {"id": "doc-ent-1", "departmentId": "dept-ent", "name": "何敏", "title": "主治医师", "intro": "鼻炎、咽炎、中耳炎"},
    {"id": "doc-derm-1", "departmentId": "dept-derm", "name": "林雪", "title": "主治医师", "intro": "湿疹、荨麻疹、皮肤感染"},
]

DOCTOR_BY_ID = {d["id"]: d for d in DOCTORS}


# ---------- Slots (generated for next 7 days) ----------
_SLOTS: dict[str, dict[str, Any]] = {}


_SLOT_TIMES = ["08:30", "09:00", "09:30", "10:00", "10:30", "14:00", "14:30", "15:00", "15:30", "16:00"]
# S2: slots must always cover today .. today+SLOT_WINDOW_DAYS-1 (Asia/Shanghai)
SLOT_WINDOW_DAYS = 8  # today + 7


def _unique_id(prefix: str, key: str, mapping: dict[str, Any]) -> str:
    sid = _next_id(prefix, key)
    while sid in mapping:  # defensive: counters restored lower than existing ids
        sid = _next_id(prefix, key)
    return sid


def _make_doctor_slots_for_day(doc: dict[str, Any], day: datetime, day_offset: int) -> None:
    date_str = day.strftime("%Y-%m-%d")
    # fewer slots for ER / specialty variety
    doc_times = _SLOT_TIMES[:6] if doc["id"].endswith("-2") else _SLOT_TIMES
    for t in doc_times:
        sid = _unique_id("slot-", "slot", _SLOTS)
        remaining = 3 if day_offset < 2 else 5
        # make some fully booked
        if day_offset == 0 and t in ("09:00", "14:00"):
            remaining = 0
        _SLOTS[sid] = {
            "id": sid,
            "doctorId": doc["id"],
            "date": date_str,
            "time": t,
            "remaining": remaining,
            "available": remaining > 0,
        }


def _seed_slots() -> None:
    if _SLOTS:
        return
    base = _today()
    for day_offset in range(SLOT_WINDOW_DAYS):
        day = base + timedelta(days=day_offset)
        for doc in DOCTORS:
            _make_doctor_slots_for_day(doc, day, day_offset)


_seed_slots()


def list_departments() -> list[dict[str, str]]:
    return copy.deepcopy(DEPARTMENTS)


def get_department(dept_id: str) -> Optional[dict[str, str]]:
    d = DEPARTMENT_BY_ID.get(dept_id)
    return copy.deepcopy(d) if d else None


def list_doctors(dept_id: str) -> list[dict[str, str]]:
    return copy.deepcopy([d for d in DOCTORS if d["departmentId"] == dept_id])


def get_doctor(doctor_id: str) -> Optional[dict[str, str]]:
    d = DOCTOR_BY_ID.get(doctor_id)
    return copy.deepcopy(d) if d else None


def list_slots(doctor_id: str, date: str) -> list[dict[str, Any]]:
    _maybe_roll_slots()
    return copy.deepcopy(
        [
            s
            for s in _SLOTS.values()
            if s["doctorId"] == doctor_id and s["date"] == date
        ]
    )


def get_slot(slot_id: str) -> Optional[dict[str, Any]]:
    s = _SLOTS.get(slot_id)
    return copy.deepcopy(s) if s else None


def consume_slot(slot_id: str) -> Optional[dict[str, Any]]:
    s = _SLOTS.get(slot_id)
    if not s:
        return None
    if s["remaining"] <= 0:
        return None
    s["remaining"] -= 1
    s["available"] = s["remaining"] > 0
    return copy.deepcopy(s)


def restore_slot(slot_id: str) -> None:
    s = _SLOTS.get(slot_id)
    if not s:
        return
    s["remaining"] += 1
    s["available"] = True


# ---------- Appointments ----------
_APPOINTMENTS: dict[str, dict[str, Any]] = {}


def create_appointment(data: dict[str, Any], *, notify: bool = True) -> dict[str, Any]:
    aid = _next_id("appt-", "appt")
    appt = {
        "id": aid,
        **data,
        "status": data.get("status") or "confirmed",
        "createdAt": _now_str(),
    }
    _APPOINTMENTS[aid] = appt
    if notify:
        dept = appt.get("departmentName") or "门诊"
        doc = appt.get("doctorName") or "医师"
        when = ""
        if appt.get("date") or appt.get("time"):
            when = f"（{appt.get('date') or ''} {appt.get('time') or ''}）".replace(" ）", "）")
        create_message(
            {
                "title": "预约提醒",
                "body": f"您已预约{dept}{doc}{when}，请提前30分钟到院报到。",
                "type": "appointment_reminder",
                "read": False,
                "link": f"/appointments/{aid}",
                "patientId": appt.get("patientId"),
            }
        )
    return copy.deepcopy(appt)


def list_appointments() -> list[dict[str, Any]]:
    items = sorted(_APPOINTMENTS.values(), key=lambda x: x["createdAt"], reverse=True)
    return copy.deepcopy(items)


def get_appointment(appt_id: str) -> Optional[dict[str, Any]]:
    a = _APPOINTMENTS.get(appt_id)
    return copy.deepcopy(a) if a else None


def update_appointment(appt_id: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    a = _APPOINTMENTS.get(appt_id)
    if not a:
        return None
    old_status = a.get("status")
    new_status = patch.get("status")
    if new_status:
        a["status"] = new_status
        # restore inventory when cancelling a previously active booking
        if new_status == "cancelled" and old_status != "cancelled":
            restore_slot(a["slotId"])
    return copy.deepcopy(a)


# ---------- Consult sessions ----------
_SESSIONS: dict[str, dict[str, Any]] = {}


def create_session() -> dict[str, Any]:
    sid = _next_id("sess-", "session")
    greeting = {
        "role": "assistant",
        "content": "您好，我是导诊助手。请简单描述您哪里不舒服、持续多久，以及有无发热、胸痛等不适。",
        "createdAt": _now_str(),
    }
    sess = {
        "id": sid,
        "messages": [greeting],
        "status": "active",
        "triage": None,
        "turns": 0,  # user turns
        "facts": {},  # collected fields
        "createdAt": _now_str(),
    }
    _SESSIONS[sid] = sess
    return copy.deepcopy(sess)


def get_session(sid: str) -> Optional[dict[str, Any]]:
    s = _SESSIONS.get(sid)
    return copy.deepcopy(s) if s else None


def save_session(sess: dict[str, Any]) -> dict[str, Any]:
    _SESSIONS[sess["id"]] = sess
    return copy.deepcopy(sess)


# ---------- Patients (就诊人) ----------
_PATIENTS: dict[str, dict[str, Any]] = {}
_PROFILES: dict[str, dict[str, Any]] = {}


def _empty_profile() -> dict[str, Any]:
    return {
        "allergies": [],
        "chronicDiseases": [],
        "medications": [],
        "bloodType": "",
        "notes": "",
    }


def _seed_patients() -> None:
    if _PATIENTS:
        return
    seeds = [
        {
            "id": "pat-1",
            "name": "演示本人",
            "gender": "男",
            "age": 32,
            "relation": "self",
            "profile": {
                "allergies": ["青霉素"],
                "chronicDiseases": [],
                "medications": [],
                "bloodType": "A",
                "notes": "演示账号本人",
            },
        },
        {
            "id": "pat-2",
            "name": "演示父亲",
            "gender": "男",
            "age": 58,
            "relation": "父",
            "profile": {
                "allergies": [],
                "chronicDiseases": ["高血压"],
                "medications": ["氨氯地平"],
                "bloodType": "O",
                "notes": "",
            },
        },
        {
            "id": "pat-3",
            "name": "演示母亲",
            "gender": "女",
            "age": 55,
            "relation": "母",
            "profile": {
                "allergies": ["磺胺"],
                "chronicDiseases": ["2型糖尿病"],
                "medications": ["二甲双胍"],
                "bloodType": "B",
                "notes": "",
            },
        },
    ]
    for s in seeds:
        pid = s["id"]
        _PATIENTS[pid] = {
            "id": pid,
            "name": s["name"],
            "gender": s["gender"],
            "age": s["age"],
            "relation": s["relation"],
            "createdAt": _now_str(),
            "updatedAt": _now_str(),
            "deleted": False,
        }
        _PROFILES[pid] = {**_empty_profile(), **s["profile"]}
    # keep counters ahead of seeds
    _counter["patient"] = 3


_seed_patients()


def create_patient(data: dict[str, Any]) -> dict[str, Any]:
    pid = _next_id("pat-", "patient")
    now = _now_str()
    pat = {
        "id": pid,
        "name": data["name"],
        "gender": data.get("gender") or "未知",
        "age": int(data.get("age") or 0),
        "relation": data.get("relation") or "self",
        "createdAt": now,
        "updatedAt": now,
        "deleted": False,
    }
    _PATIENTS[pid] = pat
    _PROFILES[pid] = _empty_profile()
    return copy.deepcopy(pat)


def list_patients(*, include_deleted: bool = False) -> list[dict[str, Any]]:
    items = [
        p
        for p in _PATIENTS.values()
        if include_deleted or not p.get("deleted")
    ]
    items = sorted(items, key=lambda x: x["createdAt"])
    return copy.deepcopy(items)


def get_patient(pid: str, *, include_deleted: bool = False) -> Optional[dict[str, Any]]:
    p = _PATIENTS.get(pid)
    if not p:
        return None
    if p.get("deleted") and not include_deleted:
        return None
    return copy.deepcopy(p)


def update_patient(pid: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    p = _PATIENTS.get(pid)
    if not p or p.get("deleted"):
        return None
    for key in ("name", "gender", "age", "relation"):
        if key in patch and patch[key] is not None:
            p[key] = patch[key]
    p["updatedAt"] = _now_str()
    return copy.deepcopy(p)


def delete_patient(pid: str, *, hard: bool = False) -> bool:
    p = _PATIENTS.get(pid)
    if not p:
        return False
    if hard:
        _PATIENTS.pop(pid, None)
        _PROFILES.pop(pid, None)
        return True
    if p.get("deleted"):
        return True
    p["deleted"] = True
    p["updatedAt"] = _now_str()
    return True


def get_profile(pid: str) -> Optional[dict[str, Any]]:
    if not get_patient(pid):
        return None
    prof = _PROFILES.get(pid) or _empty_profile()
    return copy.deepcopy(prof)


def update_profile(pid: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not get_patient(pid):
        return None
    prof = _PROFILES.setdefault(pid, _empty_profile())
    for key in ("allergies", "chronicDiseases", "medications", "bloodType", "notes"):
        if key in patch and patch[key] is not None:
            prof[key] = patch[key]
    return copy.deepcopy(prof)


# ---------- Pre-consult reports ----------
_PRECONSULT: dict[str, dict[str, Any]] = {}


def create_preconsult_report(data: dict[str, Any]) -> dict[str, Any]:
    rid = _next_id("pcr-", "preconsult")
    report = {
        "id": rid,
        **data,
        "createdAt": data.get("createdAt") or _now_str(),
    }
    _PRECONSULT[rid] = report
    return copy.deepcopy(report)


def get_preconsult_report(rid: str) -> Optional[dict[str, Any]]:
    r = _PRECONSULT.get(rid)
    return copy.deepcopy(r) if r else None


def list_preconsult_reports(
    *,
    patient_id: Optional[str] = None,
    patient_name: Optional[str] = None,
) -> list[dict[str, Any]]:
    items = list(_PRECONSULT.values())
    if patient_id:
        items = [r for r in items if r.get("patientId") == patient_id]
    if patient_name:
        needle = patient_name.strip()
        items = [r for r in items if (r.get("patientName") or "") == needle]
    items = sorted(items, key=lambda x: x.get("createdAt") or "", reverse=True)
    return copy.deepcopy(items)


def find_preconsult_by_session(session_id: str) -> Optional[dict[str, Any]]:
    for r in _PRECONSULT.values():
        if r.get("sessionId") == session_id:
            return copy.deepcopy(r)
    return None


# Fixed-id demo preconsult report linked by doctor-side seed visit v1 (王小明).
# Fixed id (not the pcr-N counter) so the doctor reset can reference it
# regardless of which side is reset first.
SEED_PRECONSULT_ID = "pcr-seed-1"


def _seed_preconsult_reports() -> None:
    """Idempotent: ensure pcr-seed-1 exists (does not touch the pcr-N counter)."""
    if SEED_PRECONSULT_ID in _PRECONSULT:
        return
    chief = "反复上腹痛 3 天"
    summary = (
        "【预问诊摘要】主诉：反复上腹痛 3 天；紧急程度：routine；建议科室：消化内科。"
        "现病史要点：餐后上腹隐痛、伴反酸嗳气，无黑便呕血，无发热。"
    )
    depts = [{"id": "dept-gi", "name": "消化内科", "reason": "上腹痛伴反酸，需消化内科评估", "rank": 1}]
    structured = {
        "chiefComplaint": chief,
        "presentIllness": "近 3 天反复上腹隐痛，多于餐后出现，伴反酸、嗳气；无黑便、呕血，无发热。",
        "accompanying": ["反酸", "嗳气"],
        "relevantHistory": "否认药物过敏；偶服布洛芬止痛（演示数据）。",
        "urgency": "routine",
        "suggestedDepartments": depts,
        "patientNarrative": "最近三天吃完饭胃这块就隐隐作痛，还反酸。",
        "redFlags": [],
        "doctorHints": ["询问 NSAIDs 用药史与幽门螺杆菌检查史", "关注黑便/呕血等报警症状"],
        "summaryText": summary,
        "departments": depts,
        "suggestOnline": False,
        "nextSteps": [],
        "facts": {},
    }
    _PRECONSULT[SEED_PRECONSULT_ID] = {
        "id": SEED_PRECONSULT_ID,
        "patientId": None,
        "patientName": "王小明",
        "sessionId": None,
        "chief": chief,
        "summary": summary,
        "structuredSummary": structured,
        "triage": {"departments": depts, "urgency": "routine", "chiefComplaint": chief, "source": "mock"},
        "aiReport": None,
        "sessionStatus": "completed",
        "disclaimer": "本预问诊报告为演示种子数据，仅供接诊医生参考，不构成诊断或治疗建议。",
        "source": "seed",
        "createdAt": "2026-10-02 08:50:00",
    }


_seed_preconsult_reports()


# ---------- Lab / imaging report center (Mock) ----------
_LAB_REPORTS: dict[str, dict[str, Any]] = {}


def _seed_lab_reports() -> None:
    if _LAB_REPORTS:
        return
    seeds = [
        {
            "id": "lab-1",
            "type": "lab",
            "name": "血常规",
            "category": "检验",
            "patientId": "pat-1",
            "patientName": "演示本人",
            "status": "ready",
            "reportedAt": _now_str(),
            "summary": "白细胞轻度升高，余大致正常",
            "items": [
                {"name": "白细胞(WBC)", "value": "11.2", "unit": "10^9/L", "ref": "3.5-9.5", "flag": "H"},
                {"name": "血红蛋白(Hb)", "value": "142", "unit": "g/L", "ref": "130-175", "flag": ""},
                {"name": "血小板(PLT)", "value": "210", "unit": "10^9/L", "ref": "125-350", "flag": ""},
            ],
        },
        {
            "id": "lab-2",
            "type": "lab",
            "name": "肝功能",
            "category": "检验",
            "patientId": "pat-2",
            "patientName": "演示父亲",
            "status": "ready",
            "reportedAt": _now_str(),
            "summary": "ALT 轻度升高",
            "items": [
                {"name": "ALT", "value": "68", "unit": "U/L", "ref": "9-50", "flag": "H"},
                {"name": "AST", "value": "42", "unit": "U/L", "ref": "15-40", "flag": "H"},
                {"name": "总胆红素", "value": "14.2", "unit": "μmol/L", "ref": "3.4-20.5", "flag": ""},
            ],
        },
        {
            "id": "img-1",
            "type": "imaging",
            "name": "胸部正位片",
            "category": "检查",
            "patientId": "pat-1",
            "patientName": "演示本人",
            "status": "ready",
            "reportedAt": _now_str(),
            "summary": "双肺纹理增多，未见明显实变",
            "items": [
                {"name": "影像所见", "value": "双肺纹理增多、紊乱，心影大小正常，膈面光滑。", "unit": "", "ref": "", "flag": ""},
                {"name": "印象", "value": "支气管炎待排，建议结合临床。", "unit": "", "ref": "", "flag": ""},
            ],
        },
        {
            "id": "lab-3",
            "type": "lab",
            "name": "尿常规",
            "category": "检验",
            "patientId": "pat-3",
            "patientName": "演示母亲",
            "status": "ready",
            "reportedAt": _now_str(),
            "summary": "尿糖阳性",
            "items": [
                {"name": "尿糖", "value": "2+", "unit": "", "ref": "阴性", "flag": "H"},
                {"name": "尿蛋白", "value": "阴性", "unit": "", "ref": "阴性", "flag": ""},
                {"name": "隐血", "value": "阴性", "unit": "", "ref": "阴性", "flag": ""},
            ],
        },
    ]
    for s in seeds:
        _LAB_REPORTS[s["id"]] = s
    _counter["lab"] = 3


_seed_lab_reports()


def list_lab_reports(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_LAB_REPORTS.values())
    if patient_id:
        items = [r for r in items if r.get("patientId") == patient_id]
    # list view without full items detail optional — keep summary fields
    out = []
    for r in sorted(items, key=lambda x: x.get("reportedAt") or "", reverse=True):
        out.append(
            {
                "id": r["id"],
                "type": r.get("type"),
                "name": r.get("name"),
                "category": r.get("category"),
                "patientId": r.get("patientId"),
                "patientName": r.get("patientName"),
                "status": r.get("status"),
                "reportedAt": r.get("reportedAt"),
                "summary": r.get("summary"),
            }
        )
    return copy.deepcopy(out)


def get_lab_report(rid: str) -> Optional[dict[str, Any]]:
    r = _LAB_REPORTS.get(rid)
    return copy.deepcopy(r) if r else None




# ---------- M2: Waiting queue / check-in ----------
_QUEUES: dict[str, dict[str, Any]] = {}


def _queue_from_appointment(appt: dict[str, Any], *, status: str = "waiting") -> dict[str, Any]:
    qid = _next_id("queue-", "queue")
    # Mock queue number from appointment id digits / counter
    queue_no = _counter["queue"]
    item = {
        "id": qid,
        "appointmentId": appt["id"],
        "patientName": appt.get("patientName") or "",
        "departmentId": appt.get("departmentId") or "",
        "departmentName": appt.get("departmentName") or "",
        "doctorId": appt.get("doctorId") or "",
        "doctorName": appt.get("doctorName") or "",
        "date": appt.get("date") or "",
        "time": appt.get("time") or "",
        "status": status,  # not_checked_in | waiting | called | done
        "queueNo": queue_no,
        "aheadCount": max(0, 3 - (queue_no % 4)),  # mock people ahead
        "checkedInAt": None,
        "calledAt": None,
        "doneAt": None,
        "updatedAt": _now_str(),
        "createdAt": _now_str(),
        "location": (DEPARTMENT_BY_ID.get(appt.get("departmentId") or "") or {}).get("location") or "",
        "tips": (DEPARTMENT_BY_ID.get(appt.get("departmentId") or "") or {}).get("tips") or "",
        "disclaimer": "候诊信息为演示 Mock，以医院现场叫号为准。",
    }
    _QUEUES[qid] = item
    return copy.deepcopy(item)


def get_queue_by_appointment(appointment_id: str) -> Optional[dict[str, Any]]:
    for q in _QUEUES.values():
        if q.get("appointmentId") == appointment_id:
            return copy.deepcopy(q)
    return None


def list_queues(*, active_only: bool = False) -> list[dict[str, Any]]:
    items = list(_QUEUES.values())
    if active_only:
        items = [q for q in items if q.get("status") in ("not_checked_in", "waiting", "called")]
    items = sorted(items, key=lambda x: (x.get("date") or "", x.get("time") or "", x.get("queueNo") or 0))
    return copy.deepcopy(items)


def get_or_create_queue_for_appointment(appointment_id: str) -> dict[str, Any]:
    """Return existing queue, or auto-create from confirmed appointment."""
    existing = get_queue_by_appointment(appointment_id)
    if existing:
        return existing
    appt = get_appointment(appointment_id)
    if not appt:
        raise KeyError("appointment_not_found")
    status = appt.get("status") or ""
    if status != "confirmed":
        raise ValueError(f"appointment_not_confirmed:{status}")
    # Before check-in: not_checked_in; demo seed may set waiting directly
    return _queue_from_appointment(appt, status="not_checked_in")


def check_in_queue(appointment_id: str) -> dict[str, Any]:
    """Check-in: ensure queue exists, move not_checked_in/waiting → waiting (or called as mock progress)."""
    q = get_queue_by_appointment(appointment_id)
    if not q:
        # auto-create then check in
        q = get_or_create_queue_for_appointment(appointment_id)
    raw = _QUEUES.get(q["id"])
    if not raw:
        raise KeyError("queue_not_found")
    st = raw.get("status")
    if st == "done":
        raise ValueError("already_done")
    if st == "called":
        # already called — idempotent return
        return copy.deepcopy(raw)
    # Mock: first check-in → waiting; if already waiting, second action can mock-call
    now = _now_str()
    if st in (None, "not_checked_in"):
        raw["status"] = "waiting"
        raw["checkedInAt"] = now
        raw["aheadCount"] = max(0, int(raw.get("aheadCount") or 0))
    elif st == "waiting":
        # allow demo transition waiting → called on repeated check-in POST
        raw["status"] = "called"
        raw["calledAt"] = now
        raw["aheadCount"] = 0
    raw["updatedAt"] = now
    return copy.deepcopy(raw)


def advance_queue_status(appointment_id: str, status: str) -> Optional[dict[str, Any]]:
    q = get_queue_by_appointment(appointment_id)
    if not q:
        return None
    raw = _QUEUES.get(q["id"])
    if not raw:
        return None
    now = _now_str()
    raw["status"] = status
    if status == "waiting" and not raw.get("checkedInAt"):
        raw["checkedInAt"] = now
    if status == "called":
        raw["calledAt"] = now
        raw["aheadCount"] = 0
    if status == "done":
        raw["doneAt"] = now
        raw["aheadCount"] = 0
    raw["updatedAt"] = now
    return copy.deepcopy(raw)


# ---------- M2: Message center ----------
_MESSAGES: dict[str, dict[str, Any]] = {}


def create_message(data: dict[str, Any]) -> dict[str, Any]:
    mid = data.get("id") or _next_id("msg-", "message")
    msg = {
        "id": mid,
        "title": data.get("title") or "",
        "body": data.get("body") or "",
        "type": data.get("type") or "system",
        "read": bool(data.get("read", False)),
        "createdAt": data.get("createdAt") or _now_str(),
        "link": data.get("link"),
        "patientId": data.get("patientId"),
    }
    # drop None patientId for cleaner payloads? keep for consistency with optional field
    _MESSAGES[mid] = msg
    return copy.deepcopy(msg)


def list_messages(
    *, type: Optional[str] = None, unread_only: bool = False
) -> list[dict[str, Any]]:
    items = list(_MESSAGES.values())
    if type:
        items = [m for m in items if m.get("type") == type]
    if unread_only:
        items = [m for m in items if not m.get("read")]
    items = sorted(items, key=lambda x: x.get("createdAt") or "", reverse=True)
    return copy.deepcopy(items)


def unread_message_count(*, type: Optional[str] = None) -> int:
    items = _MESSAGES.values()
    if type:
        items = [m for m in items if m.get("type") == type]
    return sum(1 for m in items if not m.get("read"))


def get_message(mid: str) -> Optional[dict[str, Any]]:
    m = _MESSAGES.get(mid)
    return copy.deepcopy(m) if m else None


def mark_message_read(mid: str) -> Optional[dict[str, Any]]:
    m = _MESSAGES.get(mid)
    if not m:
        return None
    m["read"] = True
    return copy.deepcopy(m)


def notify_report_interpreted(report: dict[str, Any]) -> dict[str, Any]:
    """Push inbox message after successful report interpret."""
    rid = report.get("id") or ""
    name = report.get("name") or "检查/检验"
    return create_message(
        {
            "title": "报告解读已完成",
            "body": f"您的「{name}」报告解读参考已生成，可在报告中心查看（辅助参考，不替代面诊）。",
            "type": "report_ready",
            "read": False,
            "link": f"/reports/{rid}" if rid else "/reports",
            "patientId": report.get("patientId"),
        }
    )


def list_navigation_departments() -> list[dict[str, str]]:
    """Departments with location/tips for院内导航."""
    out = []
    for d in DEPARTMENTS:
        out.append(
            {
                "id": d["id"],
                "name": d["name"],
                "intro": d.get("intro") or "",
                "location": d.get("location") or "",
                "tips": d.get("tips") or "",
            }
        )
    return copy.deepcopy(out)


def get_navigation(dept_id: str) -> Optional[dict[str, str]]:
    d = DEPARTMENT_BY_ID.get(dept_id)
    if not d:
        return None
    return copy.deepcopy(
        {
            "id": d["id"],
            "name": d["name"],
            "intro": d.get("intro") or "",
            "location": d.get("location") or "",
            "tips": d.get("tips") or "",
        }
    )


# ---------- M2 seed: demo appointment + queue + messages ----------
def _seed_m2_clinic() -> None:
    if _MESSAGES:
        return
    # Ensure slots exist
    _seed_slots()
    # Pick a confirmed demo appointment for today or next available slot
    demo_doc = DOCTOR_BY_ID.get("doc-resp-1") or DOCTORS[0]
    demo_dept = DEPARTMENT_BY_ID.get(demo_doc["departmentId"]) or DEPARTMENTS[0]
    # Prefer today's available slot for this doctor
    today = _today().strftime("%Y-%m-%d")
    slot = None
    for s in _SLOTS.values():
        if s["doctorId"] == demo_doc["id"] and s["date"] == today and s.get("remaining", 0) > 0:
            slot = s
            break
    if not slot:
        for s in _SLOTS.values():
            if s["doctorId"] == demo_doc["id"] and s.get("remaining", 0) > 0:
                slot = s
                break
    if not slot:
        # fallback any available
        for s in _SLOTS.values():
            if s.get("remaining", 0) > 0:
                slot = s
                demo_doc = DOCTOR_BY_ID[s["doctorId"]]
                demo_dept = DEPARTMENT_BY_ID[demo_doc["departmentId"]]
                break

    appt = None
    if slot and not _APPOINTMENTS:
        consumed = consume_slot(slot["id"])
        if consumed:
            appt = create_appointment(
                {
                    "departmentId": demo_dept["id"],
                    "departmentName": demo_dept["name"],
                    "doctorId": demo_doc["id"],
                    "doctorName": demo_doc["name"],
                    "slotId": consumed["id"],
                    "date": consumed["date"],
                    "time": consumed["time"],
                    "patientName": "演示本人",
                    "phone": "13800000000",
                    "chief": "咳嗽发热",
                    "status": "confirmed",
                },
                notify=False,
            )
            # Queue already waiting (seeded as checked-in for demo convenience)
            _queue_from_appointment(appt, status="waiting")
            # Second demo: not checked in yet (another appointment if possible)
            slot2 = None
            for s in _SLOTS.values():
                if s["doctorId"] == "doc-gi-1" and s.get("remaining", 0) > 0:
                    slot2 = s
                    break
            if slot2:
                c2 = consume_slot(slot2["id"])
                if c2:
                    dept2 = DEPARTMENT_BY_ID["dept-gi"]
                    doc2 = DOCTOR_BY_ID["doc-gi-1"]
                    appt2 = create_appointment(
                        {
                            "departmentId": dept2["id"],
                            "departmentName": dept2["name"],
                            "doctorId": doc2["id"],
                            "doctorName": doc2["name"],
                            "slotId": c2["id"],
                            "date": c2["date"],
                            "time": c2["time"],
                            "patientName": "演示父亲",
                            "phone": "13900000000",
                            "chief": "上腹痛",
                            "status": "confirmed",
                        },
                        notify=False,
                    )
                    _queue_from_appointment(appt2, status="not_checked_in")

    # Seed messages
    appt_id = appt["id"] if appt else None
    link_appt = f"/appointments/{appt_id}" if appt_id else "/appointments"
    create_message(
        {
            "id": "msg-1",
            "title": "预约提醒",
            "body": (
                f"您已预约{demo_dept['name']}{demo_doc['name']}医师"
                + (f"（{appt['date']} {appt['time']}）" if appt else "")
                + "，请提前30分钟到院报到。"
            ),
            "type": "appointment_reminder",
            "read": False,
            "link": link_appt,
            "createdAt": _now_str(),
        }
    )
    create_message(
        {
            "id": "msg-2",
            "title": "报告已出",
            "body": "您的「血常规」报告已出，可在报告中心查看并获取解读参考。",
            "type": "report_ready",
            "read": False,
            "link": "/reports/lab-1",
            "createdAt": _now_str(),
        }
    )
    create_message(
        {
            "id": "msg-3",
            "title": "候诊提示",
            "body": "请关注候诊状态；叫号后请及时前往诊室，过号需重新报到。",
            "type": "system",
            "read": False,
            "link": "/waiting",
            "createdAt": _now_str(),
        }
    )
    create_message(
        {
            "id": "msg-4",
            "title": "院内导航",
            "body": f"{demo_dept['name']}位于{demo_dept.get('location') or '门诊楼'}，可打开科室导航查看路线提示。",
            "type": "system",
            "read": True,
            "link": f"/navigation/{demo_dept['id']}",
            "createdAt": _now_str(),
        }
    )
    _counter["message"] = max(_counter["message"], 4)


_seed_m2_clinic()

# Patch create_session to accept optional patientId
_orig_create_session = create_session


def create_session(patient_id: Optional[str] = None) -> dict[str, Any]:
    sess = _orig_create_session()
    # write back patientId on the stored session
    raw = _SESSIONS.get(sess["id"])
    if raw is not None:
        raw["patientId"] = patient_id
        sess["patientId"] = patient_id
    return copy.deepcopy(sess)


# ---------- M3: Refills (复诊续方) ----------
_REFILLS: dict[str, dict[str, Any]] = {}
_counter["refill"] = 0

REFILL_DISCLAIMER = "演示申请不构成真实处方，不替代医师开方与审方；实际续方请以医院处方流程为准。"


def create_refill(data: dict[str, Any]) -> dict[str, Any]:
    rid = _next_id("refill-", "refill")
    dept_id = data.get("departmentId") or ""
    dept = DEPARTMENT_BY_ID.get(dept_id) if dept_id else None
    item = {
        "id": rid,
        "patientId": data.get("patientId") or "pat-1",
        "medicationName": data.get("medicationName") or "",
        "dosage": data.get("dosage") or "",
        "quantity": data.get("quantity") or "",
        "reason": data.get("reason") or "",
        "departmentId": dept_id,
        "departmentName": (dept or {}).get("name") or "",
        "status": "pending",
        "reviewNote": "",
        "createdAt": _now_str(),
        "updatedAt": _now_str(),
        "disclaimer": REFILL_DISCLAIMER,
    }
    _REFILLS[rid] = item
    return copy.deepcopy(item)


def list_refills(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_REFILLS.values())
    if patient_id:
        items = [r for r in items if r.get("patientId") == patient_id]
    items = sorted(items, key=lambda x: x.get("createdAt") or "", reverse=True)
    return copy.deepcopy(items)


def get_refill(rid: str) -> Optional[dict[str, Any]]:
    r = _REFILLS.get(rid)
    return copy.deepcopy(r) if r else None


def update_refill(rid: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    r = _REFILLS.get(rid)
    if not r:
        return None
    if "status" in patch and patch["status"] is not None:
        r["status"] = patch["status"]
    if "reviewNote" in patch and patch["reviewNote"] is not None:
        r["reviewNote"] = patch["reviewNote"]
    r["updatedAt"] = _now_str()
    r["disclaimer"] = REFILL_DISCLAIMER
    return copy.deepcopy(r)


def _seed_refills() -> None:
    if _REFILLS:
        return
    seeds = [
        {
            "patientId": "pat-2",
            "medicationName": "氨氯地平",
            "dosage": "5mg 每日一次",
            "quantity": "30片",
            "reason": "高血压长期用药，原方将尽",
            "departmentId": "dept-cardio",
            "status": "pending",
        },
        {
            "patientId": "pat-3",
            "medicationName": "二甲双胍",
            "dosage": "0.5g 每日两次",
            "quantity": "60片",
            "reason": "2型糖尿病复诊续方",
            "departmentId": "dept-gp",
            "status": "approved",
            "reviewNote": "演示：已模拟通过，非正式处方。",
        },
    ]
    for s in seeds:
        item = create_refill(s)
        raw = _REFILLS[item["id"]]
        if s.get("status") and s["status"] != "pending":
            raw["status"] = s["status"]
        if s.get("reviewNote"):
            raw["reviewNote"] = s["reviewNote"]


_seed_refills()


# ---------- M3: Medication reminders ----------
_REMINDERS: dict[str, dict[str, Any]] = {}
_counter["reminder"] = 0

MED_DISCLAIMER = "用药提醒为演示辅助，不构成用药指导；请遵医嘱与药品说明书，勿自行加减药。"


def create_medication_reminder(data: dict[str, Any]) -> dict[str, Any]:
    mid = _next_id("med-", "reminder")
    today = _today().strftime("%Y-%m-%d")
    times = list(data.get("times") or [])
    item = {
        "id": mid,
        "patientId": data.get("patientId") or "pat-1",
        "drugName": data.get("drugName") or "",
        "dose": data.get("dose") or "",
        "frequency": data.get("frequency") or "",
        "times": times,
        "startDate": data.get("startDate") or today,
        "endDate": data.get("endDate") or "",
        "enabled": bool(data["enabled"]) if data.get("enabled") is not None else True,
        # { "YYYY-MM-DD": ["08:00", ...] }
        "takenLog": {},
        "createdAt": _now_str(),
        "updatedAt": _now_str(),
        "disclaimer": MED_DISCLAIMER,
    }
    _REMINDERS[mid] = item
    return copy.deepcopy(item)


def list_medication_reminders(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_REMINDERS.values())
    if patient_id:
        items = [r for r in items if r.get("patientId") == patient_id]
    items = sorted(items, key=lambda x: x.get("createdAt") or "", reverse=True)
    return copy.deepcopy(items)


def get_medication_reminder(mid: str) -> Optional[dict[str, Any]]:
    r = _REMINDERS.get(mid)
    return copy.deepcopy(r) if r else None


def update_medication_reminder(mid: str, patch: dict[str, Any]) -> Optional[dict[str, Any]]:
    r = _REMINDERS.get(mid)
    if not r:
        return None
    for key in ("patientId", "drugName", "dose", "frequency", "times", "startDate", "endDate", "enabled"):
        if key in patch and patch[key] is not None:
            r[key] = patch[key]
    today = _today().strftime("%Y-%m-%d")
    taken_time = patch.get("takenTime")
    if taken_time:
        log = r.setdefault("takenLog", {})
        day_list = list(log.get(today) or [])
        if taken_time not in day_list:
            day_list.append(taken_time)
            day_list.sort()
        log[today] = day_list
    untaken = patch.get("untakenTime")
    if untaken:
        log = r.setdefault("takenLog", {})
        day_list = [t for t in (log.get(today) or []) if t != untaken]
        log[today] = day_list
    r["updatedAt"] = _now_str()
    r["disclaimer"] = MED_DISCLAIMER
    return copy.deepcopy(r)


def delete_medication_reminder(mid: str) -> bool:
    if mid not in _REMINDERS:
        return False
    _REMINDERS.pop(mid, None)
    return True


def list_today_doses(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    today = _today().strftime("%Y-%m-%d")
    items: list[dict[str, Any]] = []
    for r in _REMINDERS.values():
        if not r.get("enabled", True):
            continue
        if patient_id and r.get("patientId") != patient_id:
            continue
        start = r.get("startDate") or ""
        end = r.get("endDate") or ""
        if start and today < start:
            continue
        if end and today > end:
            continue
        taken_today = set((r.get("takenLog") or {}).get(today) or [])
        for t in r.get("times") or []:
            items.append(
                {
                    "reminderId": r["id"],
                    "drugName": r.get("drugName") or "",
                    "dose": r.get("dose") or "",
                    "time": t,
                    "taken": t in taken_today,
                    "patientId": r.get("patientId"),
                }
            )
    items.sort(key=lambda x: (x.get("time") or "", x.get("drugName") or ""))
    return copy.deepcopy(items)


def _seed_medication_reminders() -> None:
    if _REMINDERS:
        return
    create_medication_reminder(
        {
            "patientId": "pat-2",
            "drugName": "氨氯地平",
            "dose": "5mg",
            "frequency": "每日一次",
            "times": ["08:00"],
            "enabled": True,
        }
    )
    create_medication_reminder(
        {
            "patientId": "pat-3",
            "drugName": "二甲双胍",
            "dose": "0.5g",
            "frequency": "每日两次",
            "times": ["08:00", "20:00"],
            "enabled": True,
        }
    )
    create_medication_reminder(
        {
            "patientId": "pat-1",
            "drugName": "维生素C",
            "dose": "0.1g",
            "frequency": "每日一次",
            "times": ["09:00"],
            "enabled": True,
        }
    )


_seed_medication_reminders()


# ---------- M3: Follow-up surveys ----------
_SURVEYS: dict[str, dict[str, Any]] = {}
_FOLLOWUP_RESPONSES: dict[str, dict[str, Any]] = {}
_counter["survey"] = 0
_counter["followup"] = 0

FOLLOWUP_DISCLAIMER = "随访问卷为演示采集，结果仅供参考，不构成诊疗结论；如有不适请及时就医。"


def list_followup_surveys() -> list[dict[str, Any]]:
    return copy.deepcopy(list(_SURVEYS.values()))


def get_followup_survey(sid: str) -> Optional[dict[str, Any]]:
    s = _SURVEYS.get(sid)
    return copy.deepcopy(s) if s else None


_HIGH_RISK_HINTS = (
    "经常漏服",
    "已停药",
    "明显加重",
    "胸痛",
    "气促",
    "很高",
    "失控",
    "明显感染征象",
    "9-10",
)
_MEDIUM_RISK_HINTS = (
    "偶尔漏服",
    "控制不佳",
    "偶有波动",
    "轻微红肿",
    "有渗液",
    "6-8",
    "漏约",
)


def _answer_blob(answers: Any) -> str:
    if isinstance(answers, dict):
        parts = [str(v) for v in answers.values() if v is not None]
    elif isinstance(answers, list):
        parts = [str(v) for v in answers]
    else:
        parts = [str(answers)] if answers is not None else []
    return " ".join(parts)


def assess_followup_risk(answers: Any) -> dict[str, Any]:
    """Rule-based risk placeholder from free-text / option answers."""
    blob = _answer_blob(answers)
    level = "none"
    note = "未见明显风险占位"
    if any(h in blob for h in _HIGH_RISK_HINTS):
        level = "high"
        if any(h in blob for h in ("经常漏服", "已停药")):
            note = "依从性风险占位"
        elif any(h in blob for h in ("胸痛", "气促", "明显加重")):
            note = "症状加重风险占位"
        else:
            note = "高风险占位，建议医生复核"
    elif any(h in blob for h in _MEDIUM_RISK_HINTS):
        level = "medium"
        note = "需关注占位（波动/依从性）"
    elif blob.strip():
        level = "low"
        note = "低风险占位"
    return {
        "riskLevel": level,
        "riskFlag": level in ("high", "medium"),
        "riskNote": note,
    }


def _enrich_followup_response(item: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(item)
    pid = out.get("patientId") or ""
    patient = get_patient(pid, include_deleted=True) if pid else None
    out["patientName"] = (
        (patient or {}).get("name")
        or out.get("patientName")
        or pid
        or "未知患者"
    )
    survey_id = out.get("surveyId") or ""
    survey = _SURVEYS.get(survey_id) if survey_id else None
    if survey and not out.get("surveyTitle"):
        out["surveyTitle"] = survey.get("title") or ""
    out.setdefault("surveyTitle", "")
    submitted = out.get("submittedAt") or out.get("createdAt") or _now_str()
    out["submittedAt"] = submitted
    out["createdAt"] = out.get("createdAt") or submitted
    if "riskLevel" not in out:
        risk = assess_followup_risk(out.get("answers") or {})
        out.update(risk)
    else:
        out.setdefault("riskFlag", out.get("riskLevel") in ("high", "medium"))
        out.setdefault("riskNote", "")
    out["disclaimer"] = FOLLOWUP_DISCLAIMER
    return out


def submit_followup_response(survey_id: str, data: dict[str, Any]) -> dict[str, Any]:
    survey = _SURVEYS.get(survey_id)
    if not survey:
        raise KeyError("survey_not_found")
    rid = _next_id("fu-", "followup")
    answers = data.get("answers") or {}
    risk = assess_followup_risk(answers)
    patient_id = data.get("patientId") or "pat-1"
    patient = get_patient(patient_id, include_deleted=True)
    now = _now_str()
    item = {
        "id": rid,
        "surveyId": survey_id,
        "surveyTitle": survey.get("title") or "",
        "patientId": patient_id,
        "patientName": (patient or {}).get("name") or patient_id,
        "answers": answers,
        "createdAt": now,
        "submittedAt": now,
        "disclaimer": FOLLOWUP_DISCLAIMER,
        **risk,
    }
    _FOLLOWUP_RESPONSES[rid] = item
    return _enrich_followup_response(item)


def get_followup_response(rid: str) -> Optional[dict[str, Any]]:
    item = _FOLLOWUP_RESPONSES.get(rid)
    if not item:
        return None
    return _enrich_followup_response(item)


def list_followup_responses(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_FOLLOWUP_RESPONSES.values())
    if patient_id:
        items = [r for r in items if r.get("patientId") == patient_id]
    items = sorted(
        items,
        key=lambda x: x.get("submittedAt") or x.get("createdAt") or "",
        reverse=True,
    )
    return [_enrich_followup_response(r) for r in items]


def list_doctor_followups() -> list[dict[str, Any]]:
    """All follow-up responses for doctor inbox, newest first."""
    return list_followup_responses()


def _seed_followup_surveys() -> None:
    if _SURVEYS:
        return
    _SURVEYS["survey-1"] = {
        "id": "survey-1",
        "title": "慢病随访（高血压/糖尿病）",
        "description": "了解近期血压/血糖控制与用药依从性",
        "questions": [
            {
                "id": "q1",
                "type": "single",
                "label": "近一周是否按时服药？",
                "options": ["是", "偶尔漏服", "经常漏服", "已停药"],
            },
            {
                "id": "q2",
                "type": "single",
                "label": "近期血压/血糖控制感觉如何？",
                "options": ["稳定", "偶有波动", "控制不佳", "不清楚"],
            },
            {
                "id": "q3",
                "type": "number",
                "label": "今日晨起收缩压（mmHg，可填0表示未测）",
            },
            {
                "id": "q4",
                "type": "text",
                "label": "其他不适或想告诉医生的话",
            },
        ],
    }
    _SURVEYS["survey-2"] = {
        "id": "survey-2",
        "title": "术后随访（1周）",
        "description": "了解伤口愈合与疼痛情况",
        "questions": [
            {
                "id": "q1",
                "type": "single",
                "label": "伤口有无红肿渗液？",
                "options": ["无", "轻微红肿", "有渗液", "明显感染征象"],
            },
            {
                "id": "q2",
                "type": "single",
                "label": "疼痛评分（0无痛–10剧痛）大致范围",
                "options": ["0-2", "3-5", "6-8", "9-10"],
            },
            {
                "id": "q3",
                "type": "single",
                "label": "是否按医嘱复诊/换药？",
                "options": ["是", "未到时间", "漏约", "不清楚"],
            },
            {
                "id": "q4",
                "type": "text",
                "label": "补充说明",
            },
        ],
    }
    _counter["survey"] = 2


_seed_followup_surveys()


def _seed_followup_responses() -> None:
    """Demo inbox rows with mixed risk levels (idempotent)."""
    if _FOLLOWUP_RESPONSES:
        return
    demos = [
        {
            "id": "fu-seed-1",
            "surveyId": "survey-1",
            "patientId": "pat-2",
            "answers": {
                "q1": "经常漏服",
                "q2": "控制不佳",
                "q3": 168,
                "q4": "偶有头晕",
            },
            "createdAt": "2026-10-08 09:15:00",
        },
        {
            "id": "fu-seed-2",
            "surveyId": "survey-1",
            "patientId": "pat-3",
            "answers": {
                "q1": "偶尔漏服",
                "q2": "偶有波动",
                "q3": 142,
                "q4": "",
            },
            "createdAt": "2026-10-08 14:30:00",
        },
        {
            "id": "fu-seed-3",
            "surveyId": "survey-2",
            "patientId": "pat-1",
            "answers": {
                "q1": "无",
                "q2": "0-2",
                "q3": "是",
                "q4": "恢复良好",
            },
            "createdAt": "2026-10-09 08:00:00",
        },
    ]
    for d in demos:
        survey = _SURVEYS.get(d["surveyId"]) or {}
        answers = d["answers"]
        risk = assess_followup_risk(answers)
        patient = get_patient(d["patientId"], include_deleted=True)
        item = {
            "id": d["id"],
            "surveyId": d["surveyId"],
            "surveyTitle": survey.get("title") or "",
            "patientId": d["patientId"],
            "patientName": (patient or {}).get("name") or d["patientId"],
            "answers": answers,
            "createdAt": d["createdAt"],
            "submittedAt": d["createdAt"],
            "disclaimer": FOLLOWUP_DISCLAIMER,
            **risk,
        }
        _FOLLOWUP_RESPONSES[item["id"]] = item
    _counter["followup"] = max(_counter.get("followup", 0), 3)


_seed_followup_responses()


# ---------- M4: Bills (缴费 Mock) ----------
_BILLS: dict[str, dict[str, Any]] = {}
_counter["bill"] = 0

BILL_DISCLAIMER = "演示缴费，不发生真实扣款"


def _public_bill(b: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(b)
    out["disclaimer"] = BILL_DISCLAIMER
    return out


def list_bills(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_BILLS.values())
    if patient_id:
        items = [b for b in items if b.get("patientId") == patient_id]
    items = sorted(items, key=lambda x: x.get("createdAt") or "", reverse=True)
    return [_public_bill(b) for b in items]


def get_bill(bill_id: str) -> Optional[dict[str, Any]]:
    b = _BILLS.get(bill_id)
    return _public_bill(b) if b else None


def pay_bill(bill_id: str) -> Optional[dict[str, Any]]:
    b = _BILLS.get(bill_id)
    if not b:
        return None
    if b.get("status") == "paid":
        # idempotent
        return _public_bill(b)
    b["status"] = "paid"
    b["paidAt"] = _now_str()
    append_audit(
        action="bill.pay",
        resource_type="bill",
        resource_id=bill_id,
        detail=f"模拟缴费成功 amount={b.get('amount')} title={b.get('title')}",
    )
    return _public_bill(b)


def _seed_bills() -> None:
    if _BILLS:
        return
    seeds = [
        {
            "id": "bill-1",
            "title": "门诊诊查费 + 血常规",
            "amount": 86.5,
            "status": "unpaid",
            "patientId": "pat-1",
            "createdAt": _now_str(),
            "paidAt": None,
            "items": [
                {"name": "门诊诊查费", "amount": 28.0},
                {"name": "血常规", "amount": 58.5},
            ],
        },
        {
            "id": "bill-2",
            "title": "胸部CT（平扫）",
            "amount": 320.0,
            "status": "unpaid",
            "patientId": "pat-1",
            "createdAt": _now_str(),
            "paidAt": None,
            "items": [{"name": "胸部CT平扫", "amount": 320.0}],
        },
        {
            "id": "bill-3",
            "title": "西药处方（演示已缴）",
            "amount": 45.8,
            "status": "paid",
            "patientId": "pat-2",
            "createdAt": _now_str(),
            "paidAt": _now_str(),
            "items": [
                {"name": "氨氯地平片", "amount": 32.0},
                {"name": "药事服务费", "amount": 13.8},
            ],
        },
    ]
    for s in seeds:
        _BILLS[s["id"]] = s
    _counter["bill"] = 3


_seed_bills()


# ---------- M4: Identity / 就诊卡绑定（占位） ----------
IDENTITY_DISCLAIMER = "演示占位，未对接公安/医保实名"

# Internal full values; API responses never echo these.
_IDENTITY: dict[str, Any] = {
    "realName": "",
    "idNumber": "",
    "visitCardNo": "",
    "bound": False,
    "updatedAt": None,
}


def _mask_real_name(name: str) -> str:
    from app.privacy import mask_name
    return mask_name(name)


def _mask_id_number(id_number: str) -> str:
    from app.privacy import mask_id_card
    return mask_id_card(id_number)


def _visit_card_last4(card: str) -> str:
    s = (card or "").strip()
    if not s:
        return ""
    return s[-4:] if len(s) >= 4 else s


def get_identity_public() -> dict[str, Any]:
    from app import settings as _settings
    name = _IDENTITY.get("realName") or ""
    idn = _IDENTITY.get("idNumber") or ""
    card = _IDENTITY.get("visitCardNo") or ""
    bound = bool(_IDENTITY.get("bound")) and bool(name or idn or card)
    # Always expose masked forms when policy on (default); never omit masks
    out: dict[str, Any] = {
        "realNameMasked": _mask_real_name(name) if name else "",
        "idCardMasked": _mask_id_number(idn) if idn else "",
        "visitCardLast4": _visit_card_last4(card) if card else "",
        "bound": bound,
        "updatedAt": _IDENTITY.get("updatedAt"),
        "disclaimer": IDENTITY_DISCLAIMER,
        "maskingApplied": _settings.should_mask_sensitive(),
    }
    # Dangerous non-prod only: also include plaintext when ALLOW_FULL_SENSITIVE=1
    if not _settings.should_mask_sensitive():
        out["realName"] = name
        out["idNumber"] = idn
        out["visitCardNo"] = card
    return out


def update_identity(data: dict[str, Any]) -> dict[str, Any]:
    changed: list[str] = []
    if "realName" in data and data["realName"] is not None:
        _IDENTITY["realName"] = str(data["realName"]).strip()
        changed.append("realName")
    if "idNumber" in data and data["idNumber"] is not None:
        _IDENTITY["idNumber"] = str(data["idNumber"]).strip()
        changed.append("idNumber")
    if "visitCardNo" in data and data["visitCardNo"] is not None:
        _IDENTITY["visitCardNo"] = str(data["visitCardNo"]).strip()
        changed.append("visitCardNo")
    _IDENTITY["updatedAt"] = _now_str()
    # bound if we have name + (id or card)
    name = _IDENTITY.get("realName") or ""
    idn = _IDENTITY.get("idNumber") or ""
    card = _IDENTITY.get("visitCardNo") or ""
    _IDENTITY["bound"] = bool(name) and bool(idn or card)
    # audit without sensitive plaintext
    parts = []
    if "realName" in changed:
        parts.append(f"realNameMasked={_mask_real_name(name)}")
    if "idNumber" in changed:
        parts.append(f"idCardMasked={_mask_id_number(idn)}")
    if "visitCardNo" in changed:
        parts.append(f"visitCardLast4={_visit_card_last4(card)}")
    append_audit(
        action="identity.put",
        resource_type="identity",
        resource_id="demo",
        detail="更新实名/就诊卡绑定 " + (", ".join(parts) if parts else "无字段变更"),
    )
    return get_identity_public()


def _seed_identity() -> None:
    # lightly bound demo: name + card last4, no full id by default → still show masks
    if _IDENTITY.get("updatedAt"):
        return
    _IDENTITY["realName"] = "张伟"
    _IDENTITY["idNumber"] = "110101199001011234"
    _IDENTITY["visitCardNo"] = "VC2024006688"
    _IDENTITY["bound"] = True
    _IDENTITY["updatedAt"] = _now_str()


_seed_identity()


# ---------- M4: Audit log ----------
_AUDIT: list[dict[str, Any]] = []
_counter["audit"] = 0

AUDIT_DISCLAIMER = "演示审计日志，无敏感明文；非正式合规审计系统。"


def append_audit(
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    detail: str = "",
    actor: str = "demo",
) -> dict[str, Any]:
    from app.privacy import scrub_audit_detail
    aid = _next_id("aud-", "audit")
    entry = {
        "id": aid,
        "action": action,
        "resourceType": resource_type,
        "resourceId": resource_id,
        "actor": actor,
        "detail": scrub_audit_detail(detail or ""),
        "createdAt": _now_str(),
    }
    _AUDIT.append(entry)
    return copy.deepcopy(entry)


def list_audit(*, limit: int = 50) -> list[dict[str, Any]]:
    from app.privacy import scrub_audit_entry
    lim = max(1, min(int(limit or 50), 500))
    # newest first; id as tie-breaker within the same second
    items = sorted(
        _AUDIT,
        key=lambda x: (x.get("createdAt") or "", x.get("id") or ""),
        reverse=True,
    )
    return [scrub_audit_entry(copy.deepcopy(x)) for x in items[:lim]]


def export_audit_items(*, limit: int = 500) -> list[dict[str, Any]]:
    """All recent audit rows, scrubbed for export (no sensitive plaintext)."""
    return list_audit(limit=limit)


# ---------- M5: 图文/视频接诊 (distinct from AI /api/consult/sessions) ----------
# Primary contract: /api/doctor-consult/sessions (产品 UI)
# Compat alias: /api/consultations* (需求整理)
_CONSULTATIONS: dict[str, dict[str, Any]] = {}
_counter["consultation"] = 0
_counter["consult_msg"] = 0

CONSULTATION_DISCLAIMER = (
    "演示接诊，非真实诊疗；视频仅为状态占位，无音视频能力。"
)

# waiting statuses treated as "in queue"
_QUEUE_STATUSES = frozenset({"queued", "waiting_doctor"})


def _queue_position(consultation_id: str) -> int:
    """1-based position among waiting sessions ordered by createdAt."""
    waiting = sorted(
        [c for c in _CONSULTATIONS.values() if c.get("status") in _QUEUE_STATUSES],
        key=lambda x: (x.get("createdAt") or "", x.get("id") or ""),
    )
    for i, c in enumerate(waiting, start=1):
        if c["id"] == consultation_id:
            return i
    return 0


def _normalize_mode(data: dict[str, Any]) -> str:
    mode = data.get("mode") or data.get("type") or "text"
    if mode not in ("text", "video"):
        raise ValueError("mode/type must be text or video")
    return mode


def _resolve_department_name(name: Optional[str], dept_id: Optional[str]) -> tuple[Optional[str], str]:
    if dept_id and dept_id in DEPARTMENT_BY_ID:
        return dept_id, DEPARTMENT_BY_ID[dept_id]["name"]
    if name:
        for d in DEPARTMENTS:
            if d["name"] == name:
                return d["id"], d["name"]
        return None, name
    return dept_id, ""


def _public_doctor_consult(
    c: dict[str, Any], *, include_messages: bool = False, recent: int = 50
) -> dict[str, Any]:
    """产品 UI /api/doctor-consult/sessions 响应形状."""
    status = c.get("status") or "waiting_doctor"
    qpos = _queue_position(c["id"]) if status in _QUEUE_STATUSES else 0
    out: dict[str, Any] = {
        "id": c["id"],
        "mode": c.get("mode") or c.get("type") or "text",
        "status": status,
        "patientId": c.get("patientId"),
        "patientName": c.get("patientName") or "",
        "doctorId": c.get("doctorId"),
        "doctorName": c.get("doctorName") or "",
        "departmentId": c.get("departmentId"),
        "departmentName": c.get("departmentName") or "",
        "chiefComplaint": c.get("chiefComplaint") or c.get("chief") or "",
        "queuePosition": qpos,
        "createdAt": c.get("createdAt"),
        "acceptedAt": c.get("acceptedAt") or c.get("claimedAt"),
        "endedAt": c.get("endedAt"),
        "summary": c.get("summary") or "",
        "videoState": c.get("videoState") or "idle",
        "disclaimer": CONSULTATION_DISCLAIMER,
    }
    if (c.get("mode") or c.get("type")) == "video":
        out["roomId"] = c.get("roomId")
    if include_messages:
        msgs = list(c.get("messages") or [])
        if recent and recent > 0:
            msgs = msgs[-recent:]
        # normalize message role field for UI
        norm = []
        for m in msgs:
            norm.append(
                {
                    "id": m.get("id"),
                    "role": m.get("role") or m.get("senderRole") or "patient",
                    "content": m.get("content") or "",
                    "createdAt": m.get("createdAt"),
                }
            )
        out["messages"] = norm
        out["messageCount"] = len(c.get("messages") or [])
    else:
        out["messageCount"] = len(c.get("messages") or [])
    return out


def _public_consultation(
    c: dict[str, Any], *, include_messages: bool = False, recent: int = 20
) -> dict[str, Any]:
    """兼容 /api/consultations*：type + queued 别名."""
    status = c.get("status") or "waiting_doctor"
    # alias: waiting_doctor → queued
    alias_status = "queued" if status in _QUEUE_STATUSES else status
    mode = c.get("mode") or c.get("type") or "text"
    out: dict[str, Any] = {
        "id": c["id"],
        "type": mode,
        "mode": mode,
        "status": alias_status,
        "patientId": c.get("patientId"),
        "patientName": c.get("patientName") or "",
        "departmentId": c.get("departmentId"),
        "departmentName": c.get("departmentName") or "",
        "doctorId": c.get("doctorId"),
        "doctorName": c.get("doctorName") or "",
        "chief": c.get("chiefComplaint") or c.get("chief") or "",
        "chiefComplaint": c.get("chiefComplaint") or c.get("chief") or "",
        "reason": c.get("reason") or "",
        "roomId": c.get("roomId") if mode == "video" else None,
        "videoState": c.get("videoState") or "idle",
        "queuePosition": _queue_position(c["id"]) if status in _QUEUE_STATUSES else 0,
        "createdAt": c.get("createdAt"),
        "claimedAt": c.get("acceptedAt") or c.get("claimedAt"),
        "acceptedAt": c.get("acceptedAt") or c.get("claimedAt"),
        "endedAt": c.get("endedAt"),
        "summary": c.get("summary") or "",
        "disclaimer": CONSULTATION_DISCLAIMER,
    }
    if include_messages:
        msgs = list(c.get("messages") or [])
        if recent and recent > 0:
            msgs = msgs[-recent:]
        out["messages"] = copy.deepcopy(msgs)
        out["messageCount"] = len(c.get("messages") or [])
    else:
        out["messageCount"] = len(c.get("messages") or [])
    return out


def create_consultation(data: dict[str, Any], *, shape: str = "doctor") -> dict[str, Any]:
    mode = _normalize_mode(data)
    cid = _next_id("cons-", "consultation")
    patient_id = data.get("patientId") or "pat-1"
    patient = get_patient(patient_id) if patient_id else None
    patient_name = data.get("patientName") or (patient or {}).get("name") or "演示患者"

    dept_id = data.get("departmentId")
    dept_name_in = data.get("departmentName")
    dept_id, dept_name = _resolve_department_name(dept_name_in, dept_id)

    doctor_id = data.get("doctorId")
    doctor = get_doctor(doctor_id) if doctor_id else None
    if doctor and not dept_id:
        dept_id = doctor.get("departmentId")
        d = DEPARTMENT_BY_ID.get(dept_id or "")
        if d:
            dept_name = d["name"]

    chief = (
        data.get("chiefComplaint")
        or data.get("chief")
        or data.get("reason")
        or ""
    ).strip()

    room_id = f"room-{cid}" if mode == "video" else None
    video_state = "idle" if mode == "video" else "idle"

    item = {
        "id": cid,
        "mode": mode,
        "type": mode,
        "status": "waiting_doctor",
        "patientId": patient_id,
        "patientName": patient_name,
        "departmentId": dept_id,
        "departmentName": dept_name or "",
        "doctorId": None,
        "doctorName": "",
        "preferredDoctorId": doctor_id,
        "chief": chief,
        "chiefComplaint": chief,
        "reason": (data.get("reason") or "").strip(),
        "roomId": room_id,
        "videoState": video_state,
        "summary": "",
        "createdAt": _now_str(),
        "acceptedAt": None,
        "claimedAt": None,
        "endedAt": None,
        "messages": [],
    }
    _CONSULTATIONS[cid] = item
    append_audit(
        action="consultation.create",
        resource_type="consultation",
        resource_id=cid,
        detail=f"新建接诊 mode={mode} patientId={patient_id}",
        actor="patient",
    )
    if shape == "alias":
        return _public_consultation(item, include_messages=True)
    return _public_doctor_consult(item, include_messages=True)


def list_consultations(
    *,
    patient_id: Optional[str] = None,
    status: Optional[str] = None,
    ctype: Optional[str] = None,
    role: Optional[str] = None,
    shape: str = "doctor",
) -> list[dict[str, Any]]:
    items = list(_CONSULTATIONS.values())
    if patient_id:
        items = [c for c in items if c.get("patientId") == patient_id]
    if status:
        if status in _QUEUE_STATUSES:
            items = [c for c in items if c.get("status") in _QUEUE_STATUSES]
        else:
            items = [c for c in items if c.get("status") == status]
    if ctype:
        items = [c for c in items if (c.get("mode") or c.get("type")) == ctype]
    # role=doctor → typically waiting queue; role=patient → all (already filtered by patientId if given)
    if role == "doctor" and not status:
        # default doctor list: waiting + in_progress
        items = [
            c
            for c in items
            if c.get("status") in _QUEUE_STATUSES or c.get("status") == "in_progress"
        ]
    items = sorted(items, key=lambda x: x.get("createdAt") or "", reverse=True)
    pub = _public_consultation if shape == "alias" else _public_doctor_consult
    return [pub(c) for c in items]


def get_consultation(
    consultation_id: str, *, include_messages: bool = True, shape: str = "doctor"
) -> Optional[dict[str, Any]]:
    c = _CONSULTATIONS.get(consultation_id)
    if not c:
        return None
    if shape == "alias":
        return _public_consultation(c, include_messages=include_messages)
    return _public_doctor_consult(c, include_messages=include_messages)


def end_consultation(
    consultation_id: str,
    *,
    actor: str = "patient",
    summary: Optional[str] = None,
    shape: str = "doctor",
) -> Optional[dict[str, Any]]:
    c = _CONSULTATIONS.get(consultation_id)
    if not c:
        return None
    if c["status"] != "ended":
        c["status"] = "ended"
        c["endedAt"] = _now_str()
        if c.get("mode") == "video" or c.get("type") == "video":
            c["videoState"] = "ended"
        if summary is not None:
            c["summary"] = str(summary).strip()
        append_audit(
            action="consultation.end",
            resource_type="consultation",
            resource_id=consultation_id,
            detail=f"结束接诊 by={actor}",
            actor=actor,
        )
    elif summary is not None and not c.get("summary"):
        c["summary"] = str(summary).strip()
    pub = _public_consultation if shape == "alias" else _public_doctor_consult
    return pub(c, include_messages=True)


def list_consultation_messages(consultation_id: str) -> Optional[list[dict[str, Any]]]:
    c = _CONSULTATIONS.get(consultation_id)
    if not c:
        return None
    out = []
    for m in c.get("messages") or []:
        out.append(
            {
                "id": m.get("id"),
                "role": m.get("role") or m.get("senderRole") or "patient",
                "senderRole": m.get("senderRole") or m.get("role") or "patient",
                "content": m.get("content") or "",
                "createdAt": m.get("createdAt"),
                "consultationId": consultation_id,
            }
        )
    return out


def add_consultation_message(
    consultation_id: str,
    *,
    content: str,
    sender_role: str = "patient",
    allow_queued: bool = True,
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    c = _CONSULTATIONS.get(consultation_id)
    if not c:
        return None, "not_found"
    if c["status"] == "ended":
        return None, "ended"
    status = c["status"]
    if status in _QUEUE_STATUSES:
        if not allow_queued or sender_role not in ("patient", "system"):
            return None, "not_in_progress"
    elif status != "in_progress":
        return None, "not_in_progress"
    if sender_role not in ("patient", "doctor", "system"):
        sender_role = "patient"
    text = (content or "").strip()
    if not text:
        return None, "empty"
    mid = _next_id("cmsg-", "consult_msg")
    msg = {
        "id": mid,
        "consultationId": consultation_id,
        "role": sender_role,
        "senderRole": sender_role,
        "content": text,
        "createdAt": _now_str(),
    }
    c.setdefault("messages", []).append(msg)
    append_audit(
        action="consultation.message",
        resource_type="consultation",
        resource_id=consultation_id,
        detail=f"消息 sender={sender_role} len={len(text)}",
        actor=sender_role,
    )
    return {
        "id": mid,
        "role": sender_role,
        "senderRole": sender_role,
        "content": text,
        "createdAt": msg["createdAt"],
        "consultationId": consultation_id,
    }, None


def claim_consultation(
    consultation_id: str,
    *,
    doctor_id: Optional[str] = None,
    doctor_name: Optional[str] = None,
    shape: str = "doctor",
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    """accept / claim: waiting → in_progress."""
    c = _CONSULTATIONS.get(consultation_id)
    if not c:
        return None, "not_found"
    if c["status"] == "ended":
        return None, "ended"
    if c["status"] == "in_progress":
        pub = _public_consultation if shape == "alias" else _public_doctor_consult
        return pub(c, include_messages=True), None
    if c["status"] not in _QUEUE_STATUSES:
        return None, "invalid_status"

    preferred = c.get("preferredDoctorId")
    doc_id = doctor_id or preferred
    if not doc_id and c.get("departmentId"):
        for d in DOCTORS:
            if d.get("departmentId") == c.get("departmentId"):
                doc_id = d["id"]
                break
    doc_id = doc_id or "doc-gp-1"
    doc = get_doctor(doc_id) or DOCTOR_BY_ID.get(doc_id)
    name = doctor_name or (doc or {}).get("name") or "演示医生"
    c["doctorId"] = doc_id
    c["doctorName"] = name
    if not c.get("departmentId") and doc:
        c["departmentId"] = doc.get("departmentId")
        d = DEPARTMENT_BY_ID.get(c["departmentId"] or "")
        if d:
            c["departmentName"] = d["name"]
    c["status"] = "in_progress"
    now = _now_str()
    c["acceptedAt"] = now
    c["claimedAt"] = now
    if (c.get("mode") or c.get("type")) == "video":
        # placeholder state machine: connecting on accept (no WebRTC)
        c["videoState"] = "connecting"
        if not c.get("roomId"):
            c["roomId"] = f"room-{consultation_id}"
    mid = _next_id("cmsg-", "consult_msg")
    c.setdefault("messages", []).append(
        {
            "id": mid,
            "consultationId": consultation_id,
            "role": "system",
            "senderRole": "system",
            "content": f"医生 {name} 已接诊",
            "createdAt": now,
        }
    )
    append_audit(
        action="consultation.claim",
        resource_type="consultation",
        resource_id=consultation_id,
        detail=f"医生接诊 doctorId={doc_id} name={name}",
        actor="doctor",
    )
    pub = _public_consultation if shape == "alias" else _public_doctor_consult
    return pub(c, include_messages=True), None


def doctor_reply_consultation(
    consultation_id: str, content: str, *, shape: str = "doctor"
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    msg, err = add_consultation_message(
        consultation_id,
        content=content,
        sender_role="doctor",
        allow_queued=False,
    )
    if err:
        return None, err
    c = _CONSULTATIONS.get(consultation_id)
    if not c:
        return None, "not_found"
    pub = _public_consultation if shape == "alias" else _public_doctor_consult
    return pub(c, include_messages=True), None


def patch_consultation_status(
    consultation_id: str,
    status: str,
    *,
    actor: str = "doctor",
    doctor_id: Optional[str] = None,
    shape: str = "alias",
) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    allowed = {"queued", "waiting_doctor", "in_progress", "ended"}
    if status not in allowed:
        return None, "invalid_status"
    c = _CONSULTATIONS.get(consultation_id)
    if not c:
        return None, "not_found"
    if status in ("in_progress",) and c["status"] in _QUEUE_STATUSES:
        return claim_consultation(consultation_id, doctor_id=doctor_id, shape=shape)
    if status == "ended":
        return end_consultation(consultation_id, actor=actor, shape=shape), None
    if status in _QUEUE_STATUSES:
        return None, "cannot_requeue"
    pub = _public_consultation if shape == "alias" else _public_doctor_consult
    return pub(c, include_messages=True), None


def set_video_state(consultation_id: str, video_state: str) -> Optional[dict[str, Any]]:
    allowed = {"idle", "connecting", "connected", "ended"}
    if video_state not in allowed:
        return None
    c = _CONSULTATIONS.get(consultation_id)
    if not c:
        return None
    c["videoState"] = video_state
    return _public_doctor_consult(c, include_messages=True)


def _seed_consultations() -> None:
    if _CONSULTATIONS:
        return
    t_id = "cons-1"
    _CONSULTATIONS[t_id] = {
        "id": t_id,
        "mode": "text",
        "type": "text",
        "status": "waiting_doctor",
        "patientId": "pat-1",
        "patientName": "演示本人",
        "departmentId": "dept-resp",
        "departmentName": "呼吸内科",
        "doctorId": None,
        "doctorName": "",
        "preferredDoctorId": "doc-resp-1",
        "chief": "咳嗽发热三天",
        "chiefComplaint": "咳嗽发热三天",
        "reason": "希望图文咨询是否需要拍胸片",
        "roomId": None,
        "videoState": "idle",
        "summary": "",
        "createdAt": _now_str(),
        "acceptedAt": None,
        "claimedAt": None,
        "endedAt": None,
        "messages": [
            {
                "id": "cmsg-1",
                "consultationId": t_id,
                "role": "patient",
                "senderRole": "patient",
                "content": "医生您好，咳嗽伴低热三天，想咨询一下。",
                "createdAt": _now_str(),
            }
        ],
    }
    v_id = "cons-2"
    _CONSULTATIONS[v_id] = {
        "id": v_id,
        "mode": "video",
        "type": "video",
        "status": "waiting_doctor",
        "patientId": "pat-2",
        "patientName": "演示父亲",
        "departmentId": "dept-cardio",
        "departmentName": "心内科",
        "doctorId": None,
        "doctorName": "",
        "preferredDoctorId": "doc-cardio-1",
        "chief": "胸闷不适",
        "chiefComplaint": "胸闷不适",
        "reason": "血压偏高，想视频问诊",
        "roomId": f"room-{v_id}",
        "videoState": "idle",
        "summary": "",
        "createdAt": _now_str(),
        "acceptedAt": None,
        "claimedAt": None,
        "endedAt": None,
        "messages": [],
    }
    _counter["consultation"] = 2
    _counter["consult_msg"] = 1


_seed_consultations()


# ---------- M6: 检查检验预约（独立于门诊 /api/appointments 与医生号源） ----------
_LAB_EXAMS: dict[str, dict[str, Any]] = {}
_LAB_EXAM_SLOTS: dict[str, dict[str, Any]] = {}
_LAB_EXAM_BOOKINGS: dict[str, dict[str, Any]] = {}
_counter["lab_exam"] = 0
_counter["lab_exam_slot"] = 0
_counter["lab_exam_booking"] = 0

LAB_EXAM_DISCLAIMER = "演示预约，以医院实际开单与告知为准。"
LAB_EXAM_RESCHEDULE_LIMIT = 3

_LAB_EXAM_SEED: list[dict[str, Any]] = [
    {
        "id": "exam-cbc",
        "name": "血常规",
        "category": "lab",
        "durationMinutes": 15,
        "price": 25.0,
        "location": "医技楼1F 抽血窗口",
        "prepNotes": "建议空腹或不严格空腹均可；采血前勿剧烈运动；请携带就诊卡排队取号。",
    },
    {
        "id": "exam-lft-rft",
        "name": "肝肾功能",
        "category": "lab",
        "durationMinutes": 20,
        "price": 68.0,
        "location": "医技楼1F 抽血窗口",
        "prepNotes": "需空腹8–12小时（可少量清水）；采血前停用影响肝酶的保健品请遵医嘱；憋尿非必须。",
    },
    {
        "id": "exam-abd-us",
        "name": "腹部超声",
        "category": "imaging",
        "durationMinutes": 30,
        "price": 120.0,
        "location": "医技楼2F 超声科",
        "prepNotes": "需空腹8小时以上；胆囊检查前勿进油腻食物；请穿着宽松上衣便于暴露上腹。",
    },
    {
        "id": "exam-chest-ct",
        "name": "胸部CT",
        "category": "imaging",
        "durationMinutes": 25,
        "price": 320.0,
        "location": "医技楼1F 放射科CT室",
        "prepNotes": "检查前摘除项链、金属扣、文胸钢圈等金属物件；告知是否怀孕或备孕；增强CT需另开对比剂知情同意。",
    },
    {
        "id": "exam-ecg",
        "name": "心电图",
        "category": "other",
        "durationMinutes": 10,
        "price": 30.0,
        "location": "门诊楼4F 心电室",
        "prepNotes": "检查前安静休息5–10分钟；避免剧烈运动与饮用浓茶咖啡；保持胸部皮肤清洁干燥。",
    },
    {
        "id": "exam-gastroscopy",
        "name": "胃镜",
        "category": "other",
        "durationMinutes": 45,
        "price": 480.0,
        "location": "医技楼3F 内镜中心",
        "prepNotes": "检查前至少空腹8小时、禁水4小时；无痛胃镜需陪同家属；高血压/糖尿病患者用药请遵麻醉评估医嘱；摘除活动假牙与金属饰品。",
    },
    {
        "id": "exam-ua",
        "name": "尿常规",
        "category": "lab",
        "durationMinutes": 10,
        "price": 15.0,
        "location": "医技楼1F 检验采样处",
        "prepNotes": "采集中段尿；女性避开月经期；采样前清洁外阴；憋尿约1–2小时更利于取样。",
    },
    {
        "id": "exam-thyroid",
        "name": "甲状腺功能",
        "category": "lab",
        "durationMinutes": 15,
        "price": 95.0,
        "location": "医技楼1F 抽血窗口",
        "prepNotes": "建议晨起空腹采血；正在服用甲状腺激素者请遵医嘱是否停药后再采；无需憋尿。",
    },
]


def _seed_lab_exams() -> None:
    if _LAB_EXAMS:
        return
    for item in _LAB_EXAM_SEED:
        _LAB_EXAMS[item["id"]] = dict(item)
    _counter["lab_exam"] = len(_LAB_EXAM_SEED)


def _seed_lab_exam_slots() -> None:
    if _LAB_EXAM_SLOTS:
        return
    _seed_lab_exams()
    # morning / afternoon windows; vary by category (see _LAB_BASE_TIMES)
    base = _today()
    for day_offset in range(LAB_SLOT_WINDOW_DAYS):  # today .. today+7 (Asia/Shanghai)
        day = base + timedelta(days=day_offset)
        for exam in _LAB_EXAMS.values():
            _make_lab_exam_slots_for_day(exam, day, day_offset)


LAB_SLOT_WINDOW_DAYS = 8
_LAB_BASE_TIMES = {
    "lab": ["07:30", "08:00", "08:30", "09:00", "09:30", "10:00"],
    "imaging": ["08:30", "09:30", "10:30", "14:00", "15:00", "16:00"],
    "other": ["08:00", "09:00", "10:00", "14:30", "15:30"],
}


def _make_lab_exam_slots_for_day(exam: dict[str, Any], day: datetime, day_offset: int) -> None:
    date_str = day.strftime("%Y-%m-%d")
    times = _LAB_BASE_TIMES.get(exam.get("category") or "other", _LAB_BASE_TIMES["other"])
    for t in times:
        sid = _unique_id("leslot-", "lab_exam_slot", _LAB_EXAM_SLOTS)
        remaining = 4 if day_offset > 0 else 2
        # seed a few full slots for realism
        if day_offset == 0 and t in ("08:00", "14:00"):
            remaining = 0
        _LAB_EXAM_SLOTS[sid] = {
            "id": sid,
            "examId": exam["id"],
            "date": date_str,
            "time": t,
            "remaining": remaining,
            "available": remaining > 0,
        }


_seed_lab_exams()
_seed_lab_exam_slots()


def _public_lab_exam(exam: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(exam)
    # alias for Chinese clients
    out["注意事项"] = out.get("prepNotes") or ""
    out["disclaimer"] = LAB_EXAM_DISCLAIMER
    return out


def list_lab_exams(*, category: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_LAB_EXAMS.values())
    if category:
        items = [e for e in items if e.get("category") == category]
    return [_public_lab_exam(e) for e in items]


def get_lab_exam(exam_id: str) -> Optional[dict[str, Any]]:
    e = _LAB_EXAMS.get(exam_id)
    return _public_lab_exam(e) if e else None


def list_lab_exam_slots(exam_id: str, *, date: Optional[str] = None) -> list[dict[str, Any]]:
    _maybe_roll_slots()
    if exam_id not in _LAB_EXAMS:
        return []
    items = [s for s in _LAB_EXAM_SLOTS.values() if s.get("examId") == exam_id]
    if date:
        items = [s for s in items if s.get("date") == date]
    items.sort(key=lambda x: (x.get("date") or "", x.get("time") or "", x.get("id") or ""))
    return copy.deepcopy(items)


def get_lab_exam_slot(slot_id: str) -> Optional[dict[str, Any]]:
    s = _LAB_EXAM_SLOTS.get(slot_id)
    return copy.deepcopy(s) if s else None


def consume_lab_exam_slot(slot_id: str) -> Optional[dict[str, Any]]:
    s = _LAB_EXAM_SLOTS.get(slot_id)
    if not s:
        return None
    if not s.get("available") or int(s.get("remaining") or 0) <= 0:
        return None
    s["remaining"] = int(s["remaining"]) - 1
    s["available"] = s["remaining"] > 0
    return copy.deepcopy(s)


def release_lab_exam_slot(slot_id: str) -> Optional[dict[str, Any]]:
    s = _LAB_EXAM_SLOTS.get(slot_id)
    if not s:
        return None
    s["remaining"] = int(s.get("remaining") or 0) + 1
    s["available"] = True
    return copy.deepcopy(s)


def _find_lab_exam_slot_by_datetime(exam_id: str, date: str, time: str) -> Optional[dict[str, Any]]:
    for s in _LAB_EXAM_SLOTS.values():
        if s.get("examId") == exam_id and s.get("date") == date and s.get("time") == time:
            return s
    return None


def _enrich_lab_exam_booking(booking: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(booking)
    exam = _LAB_EXAMS.get(out.get("examId") or "")
    if exam:
        out["examName"] = exam.get("name")
        out["category"] = exam.get("category")
        out["location"] = exam.get("location")
        out["prepNotes"] = exam.get("prepNotes")
        out["注意事项"] = exam.get("prepNotes")
        out["price"] = exam.get("price")
        out["durationMinutes"] = exam.get("durationMinutes")
    out["disclaimer"] = LAB_EXAM_DISCLAIMER
    return out


def list_lab_exam_bookings(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_LAB_EXAM_BOOKINGS.values())
    if patient_id:
        items = [b for b in items if b.get("patientId") == patient_id]
    items.sort(key=lambda x: (x.get("createdAt") or "", x.get("id") or ""), reverse=True)
    return [_enrich_lab_exam_booking(b) for b in items]


def get_lab_exam_booking(booking_id: str) -> Optional[dict[str, Any]]:
    b = _LAB_EXAM_BOOKINGS.get(booking_id)
    return _enrich_lab_exam_booking(b) if b else None


def create_lab_exam_booking(
    *,
    exam_id: str,
    slot_id: str,
    patient_id: Optional[str] = None,
    patient_name: Optional[str] = None,
    note: Optional[str] = None,
) -> dict[str, Any]:
    exam = _LAB_EXAMS.get(exam_id)
    if not exam:
        raise ValueError("exam_not_found")
    slot = _LAB_EXAM_SLOTS.get(slot_id)
    if not slot:
        raise ValueError("slot_not_found")
    if slot.get("examId") != exam_id:
        raise ValueError("slot_exam_mismatch")
    consumed = consume_lab_exam_slot(slot_id)
    if not consumed:
        raise ValueError("slot_full")

    bid = _next_id("leb-", "lab_exam_booking")
    name = (patient_name or "").strip() or "演示患者"
    booking = {
        "id": bid,
        "examId": exam_id,
        "slotId": slot_id,
        "date": consumed["date"],
        "time": consumed["time"],
        "patientId": patient_id,
        "patientName": name,
        "note": (note or "").strip() or None,
        "status": "confirmed",
        "rescheduleCount": 0,
        "createdAt": _now_str(),
        "updatedAt": _now_str(),
        "cancelledAt": None,
        "cancelReason": None,
    }
    _LAB_EXAM_BOOKINGS[bid] = booking
    exam_name = exam.get("name") or "检查检验"
    create_message(
        {
            "title": "检查预约成功",
            "body": (
                f"您已预约「{exam_name}」"
                f"（{booking.get('date')} {booking.get('time')}），"
                f"请按注意事项准备并按时到检。"
            ),
            "type": "exam_booking",
            "read": False,
            "link": f"/exam-bookings/{bid}",
            "patientId": patient_id,
        }
    )
    return _enrich_lab_exam_booking(booking)


def reschedule_lab_exam_booking(
    booking_id: str,
    *,
    slot_id: Optional[str] = None,
    date: Optional[str] = None,
    time: Optional[str] = None,
) -> dict[str, Any]:
    b = _LAB_EXAM_BOOKINGS.get(booking_id)
    if not b:
        raise ValueError("booking_not_found")
    if b.get("status") == "cancelled":
        raise ValueError("booking_cancelled")
    if int(b.get("rescheduleCount") or 0) >= LAB_EXAM_RESCHEDULE_LIMIT:
        raise ValueError("reschedule_limit")

    exam_id = b["examId"]
    new_slot: Optional[dict[str, Any]] = None
    if slot_id:
        new_slot = _LAB_EXAM_SLOTS.get(slot_id)
        if not new_slot:
            raise ValueError("slot_not_found")
        if new_slot.get("examId") != exam_id:
            raise ValueError("slot_exam_mismatch")
    elif date and time:
        new_slot = _find_lab_exam_slot_by_datetime(exam_id, date, time)
        if not new_slot:
            raise ValueError("slot_not_found")
        slot_id = new_slot["id"]
    else:
        raise ValueError("missing_slot")

    if slot_id == b.get("slotId"):
        raise ValueError("same_slot")

    consumed = consume_lab_exam_slot(slot_id)
    if not consumed:
        raise ValueError("slot_full")

    # release old slot after new one secured
    old_slot_id = b.get("slotId")
    if old_slot_id:
        release_lab_exam_slot(old_slot_id)

    b["slotId"] = slot_id
    b["date"] = consumed["date"]
    b["time"] = consumed["time"]
    b["rescheduleCount"] = int(b.get("rescheduleCount") or 0) + 1
    b["updatedAt"] = _now_str()
    exam = _LAB_EXAMS.get(exam_id) or {}
    exam_name = exam.get("name") or "检查检验"
    create_message(
        {
            "title": "检查改约成功",
            "body": (
                f"您的「{exam_name}」已改约至"
                f"{b.get('date')} {b.get('time')}（第 {b['rescheduleCount']} 次改约）。"
            ),
            "type": "exam_reschedule",
            "read": False,
            "link": f"/exam-bookings/{booking_id}",
            "patientId": b.get("patientId"),
        }
    )
    return _enrich_lab_exam_booking(b)


def cancel_lab_exam_booking(booking_id: str, *, reason: Optional[str] = None) -> dict[str, Any]:
    b = _LAB_EXAM_BOOKINGS.get(booking_id)
    if not b:
        raise ValueError("booking_not_found")
    if b.get("status") == "cancelled":
        return _enrich_lab_exam_booking(b)
    old_slot_id = b.get("slotId")
    if old_slot_id:
        release_lab_exam_slot(old_slot_id)
    b["status"] = "cancelled"
    b["cancelReason"] = (reason or "").strip() or None
    b["cancelledAt"] = _now_str()
    b["updatedAt"] = _now_str()
    return _enrich_lab_exam_booking(b)


# ---------- M7: Pharmacy / 药品配送 Mock ----------
_PHARMACY_ORDERS: dict[str, dict[str, Any]] = {}
_PHARMACY_ADDRESSES: dict[str, dict[str, Any]] = {}
_PHARMACY_DELIVERIES: dict[str, dict[str, Any]] = {}
_counter["pharm_order"] = 0
_counter["pharm_addr"] = 0
_counter["pharm_delivery"] = 0
_counter["pharm_track"] = 0

PHARMACY_DISCLAIMER = "演示配送，非真实处方与物流履约。"

# Canonical status <-> UI alias
_STATUS_TO_UI = {
    "pending": "pending_shipment",
    "shipped": "in_transit",
    "delivered": "delivered",
    "cancelled": "cancelled",
}
_UI_TO_STATUS = {
    "pending_shipment": "pending",
    "in_transit": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
    # also accept canonical as input
    "pending": "pending",
    "shipped": "shipped",
}


def _normalize_delivery_status(raw: Optional[str]) -> Optional[str]:
    if raw is None:
        return None
    s = str(raw).strip().lower()
    if s in _STATUS_TO_UI:
        return s
    if s in _UI_TO_STATUS:
        return _UI_TO_STATUS[s]
    return None


def _public_pharmacy_order(o: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(o)
    out["disclaimer"] = PHARMACY_DISCLAIMER
    return out


def _public_pharmacy_address(a: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(a)
    out["disclaimer"] = PHARMACY_DISCLAIMER
    return out


def _public_pharmacy_delivery(d: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(d)
    status = out.get("status") or "pending"
    out["status"] = status
    out["uiStatus"] = _STATUS_TO_UI.get(status, status)
    out["disclaimer"] = PHARMACY_DISCLAIMER
    return out


def list_pharmacy_orders(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_PHARMACY_ORDERS.values())
    if patient_id:
        items = [o for o in items if o.get("patientId") == patient_id]
    items = sorted(items, key=lambda x: x.get("createdAt") or "", reverse=True)
    return [_public_pharmacy_order(o) for o in items]


def get_pharmacy_order(order_id: str) -> Optional[dict[str, Any]]:
    o = _PHARMACY_ORDERS.get(order_id)
    return _public_pharmacy_order(o) if o else None


def _clear_default_addresses(*, patient_id: Optional[str] = None) -> None:
    for a in _PHARMACY_ADDRESSES.values():
        if patient_id and a.get("patientId") != patient_id:
            continue
        a["isDefault"] = False


def list_pharmacy_addresses(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_PHARMACY_ADDRESSES.values())
    if patient_id:
        items = [a for a in items if a.get("patientId") == patient_id]
    items = sorted(
        items,
        key=lambda x: (0 if x.get("isDefault") else 1, x.get("createdAt") or ""),
    )
    return [_public_pharmacy_address(a) for a in items]


def get_pharmacy_address(address_id: str) -> Optional[dict[str, Any]]:
    a = _PHARMACY_ADDRESSES.get(address_id)
    return _public_pharmacy_address(a) if a else None


def create_pharmacy_address(data: dict[str, Any]) -> dict[str, Any]:
    aid = _next_id("addr-", "pharm_addr")
    patient_id = data.get("patientId")
    is_default = bool(data.get("isDefault"))
    if is_default or not _PHARMACY_ADDRESSES:
        # first address becomes default; or explicit default
        _clear_default_addresses(patient_id=patient_id)
        is_default = True
    addr = {
        "id": aid,
        "name": str(data.get("name") or "").strip(),
        "phone": str(data.get("phone") or "").strip(),
        "province": str(data.get("province") or "").strip(),
        "city": str(data.get("city") or "").strip(),
        "district": str(data.get("district") or "").strip(),
        "detail": str(data.get("detail") or "").strip(),
        "isDefault": is_default,
        "patientId": patient_id,
        "createdAt": _now_str(),
        "updatedAt": _now_str(),
    }
    if not addr["name"] or not addr["phone"] or not addr["detail"]:
        raise ValueError("missing_required")
    _PHARMACY_ADDRESSES[aid] = addr
    return _public_pharmacy_address(addr)


def update_pharmacy_address(address_id: str, data: dict[str, Any]) -> dict[str, Any]:
    a = _PHARMACY_ADDRESSES.get(address_id)
    if not a:
        raise ValueError("address_not_found")
    for key in ("name", "phone", "province", "city", "district", "detail", "patientId"):
        if key in data and data[key] is not None:
            a[key] = str(data[key]).strip() if key != "patientId" else data[key]
    if "isDefault" in data and data["isDefault"] is not None:
        if bool(data["isDefault"]):
            _clear_default_addresses(patient_id=a.get("patientId"))
            a["isDefault"] = True
        else:
            a["isDefault"] = False
    a["updatedAt"] = _now_str()
    return _public_pharmacy_address(a)


def delete_pharmacy_address(address_id: str) -> bool:
    a = _PHARMACY_ADDRESSES.pop(address_id, None)
    if not a:
        raise ValueError("address_not_found")
    # if deleted was default, promote another
    if a.get("isDefault"):
        remaining = [
            x
            for x in _PHARMACY_ADDRESSES.values()
            if x.get("patientId") == a.get("patientId")
        ]
        if remaining:
            remaining[0]["isDefault"] = True
            remaining[0]["updatedAt"] = _now_str()
    return True


def list_pharmacy_deliveries(*, patient_id: Optional[str] = None) -> list[dict[str, Any]]:
    items = list(_PHARMACY_DELIVERIES.values())
    if patient_id:
        items = [d for d in items if d.get("patientId") == patient_id]
    items = sorted(items, key=lambda x: x.get("createdAt") or "", reverse=True)
    return [_public_pharmacy_delivery(d) for d in items]


def get_pharmacy_delivery(delivery_id: str) -> Optional[dict[str, Any]]:
    d = _PHARMACY_DELIVERIES.get(delivery_id)
    return _public_pharmacy_delivery(d) if d else None


def create_pharmacy_delivery(
    *, order_id: str, address_id: str, patient_id: Optional[str] = None
) -> dict[str, Any]:
    order = _PHARMACY_ORDERS.get(order_id)
    if not order:
        raise ValueError("order_not_found")
    addr = _PHARMACY_ADDRESSES.get(address_id)
    if not addr:
        raise ValueError("address_not_found")
    # prevent duplicate active delivery for same order
    for d in _PHARMACY_DELIVERIES.values():
        if d.get("orderId") == order_id and d.get("status") in ("pending", "shipped"):
            raise ValueError("delivery_exists")
    did = _next_id("del-", "pharm_delivery")
    now = _now_str()
    pid = patient_id or order.get("patientId") or addr.get("patientId")
    address_snapshot = {
        "id": addr["id"],
        "name": addr.get("name"),
        "phone": addr.get("phone"),
        "province": addr.get("province"),
        "city": addr.get("city"),
        "district": addr.get("district"),
        "detail": addr.get("detail"),
    }
    delivery = {
        "id": did,
        "orderId": order_id,
        "orderTitle": order.get("title") or "",
        "status": "pending",
        "uiStatus": "pending_shipment",
        "addressSnapshot": address_snapshot,
        "trackingNo": None,
        "trackingEvents": [
            {
                "at": now,
                "status": "pending",
                "desc": "配送单已创建，待发货（演示）",
            }
        ],
        "patientId": pid,
        "createdAt": now,
        "updatedAt": now,
    }
    _PHARMACY_DELIVERIES[did] = delivery
    # mark order as delivery_pending-ish without breaking simple seed status
    if order.get("status") in ("ready", "available", None, ""):
        order["status"] = "delivering"
        order["updatedAt"] = now
    return _public_pharmacy_delivery(delivery)


def advance_pharmacy_delivery(
    delivery_id: str, *, target: Optional[str] = None
) -> dict[str, Any]:
    d = _PHARMACY_DELIVERIES.get(delivery_id)
    if not d:
        raise ValueError("delivery_not_found")
    cur = d.get("status") or "pending"
    if cur == "cancelled":
        raise ValueError("delivery_cancelled")
    if cur == "delivered":
        return _public_pharmacy_delivery(d)

    chain = ["pending", "shipped", "delivered"]
    if target:
        norm = _normalize_delivery_status(target)
        if not norm:
            raise ValueError("invalid_status")
        if norm == cur:
            return _public_pharmacy_delivery(d)
        if norm not in chain:
            raise ValueError("invalid_status")
        # only allow forward one step or to delivered from pending via multi-advance
        cur_idx = chain.index(cur)
        tgt_idx = chain.index(norm)
        if tgt_idx <= cur_idx:
            raise ValueError("invalid_status")
        # advance step by step
        result = None
        for step in chain[cur_idx + 1 : tgt_idx + 1]:
            result = _advance_one_step(d, step)
        return result or _public_pharmacy_delivery(d)

    # default: one step forward
    idx = chain.index(cur)
    if idx >= len(chain) - 1:
        return _public_pharmacy_delivery(d)
    return _advance_one_step(d, chain[idx + 1])


def _advance_one_step(d: dict[str, Any], new_status: str) -> dict[str, Any]:
    now = _now_str()
    if new_status == "shipped":
        if not d.get("trackingNo"):
            _counter["pharm_track"] = int(_counter.get("pharm_track") or 0) + 1
            d["trackingNo"] = f"MOCK{880000000 + _counter['pharm_track']}"
        desc = f"已发货，运单号 {d['trackingNo']}（演示）"
    elif new_status == "delivered":
        desc = "已签收送达（演示）"
        order = _PHARMACY_ORDERS.get(d.get("orderId") or "")
        if order:
            order["status"] = "delivered"
            order["updatedAt"] = now
    else:
        desc = f"状态更新为 {new_status}"
    d["status"] = new_status
    d["uiStatus"] = _STATUS_TO_UI.get(new_status, new_status)
    d["updatedAt"] = now
    d.setdefault("trackingEvents", []).append(
        {"at": now, "status": new_status, "desc": desc}
    )
    status_label = {
        "pending": "待发货",
        "shipped": "已发货",
        "delivered": "已送达",
    }.get(new_status, new_status)
    title_map = {
        "pending": "药品配送已创建",
        "shipped": "药品已发货",
        "delivered": "药品已送达",
    }
    order_title = d.get("orderTitle") or ""
    if not order_title:
        order = _PHARMACY_ORDERS.get(d.get("orderId") or "") or {}
        order_title = order.get("title") or "处方药品"
    create_message(
        {
            "title": title_map.get(new_status, "配送状态更新"),
            "body": f"「{order_title}」配送状态：{status_label}。{desc}",
            "type": "delivery_status",
            "read": False,
            "link": f"/pharmacy/deliveries/{d.get('id')}",
            "patientId": d.get("patientId"),
        }
    )
    return _public_pharmacy_delivery(d)


def cancel_pharmacy_delivery(
    delivery_id: str, *, reason: Optional[str] = None
) -> dict[str, Any]:
    d = _PHARMACY_DELIVERIES.get(delivery_id)
    if not d:
        raise ValueError("delivery_not_found")
    if d.get("status") == "delivered":
        raise ValueError("already_delivered")
    if d.get("status") == "cancelled":
        return _public_pharmacy_delivery(d)
    now = _now_str()
    d["status"] = "cancelled"
    d["uiStatus"] = "cancelled"
    d["cancelReason"] = (reason or "").strip() or None
    d["updatedAt"] = now
    d.setdefault("trackingEvents", []).append(
        {
            "at": now,
            "status": "cancelled",
            "desc": f"配送已取消（演示）{('：' + reason) if reason else ''}",
        }
    )
    order = _PHARMACY_ORDERS.get(d.get("orderId") or "")
    if order and order.get("status") == "delivering":
        order["status"] = "ready"
        order["updatedAt"] = now
    return _public_pharmacy_delivery(d)


def _seed_pharmacy() -> None:
    if _PHARMACY_ORDERS:
        return
    now = _now_str()
    orders = [
        {
            "id": "rx-1",
            "title": "氨氯地平续方",
            "items": [
                {"name": "苯磺酸氨氯地平片", "spec": "5mg*28片", "qty": 1},
            ],
            "status": "ready",
            "createdAt": now,
            "patientId": "pat-1",
        },
        {
            "id": "rx-2",
            "title": "感冒药购药单",
            "items": [
                {"name": "复方氨酚烷胺胶囊", "spec": "10粒", "qty": 1},
                {"name": "连花清瘟胶囊", "spec": "24粒", "qty": 1},
            ],
            "status": "ready",
            "createdAt": now,
            "patientId": "pat-1",
        },
        {
            "id": "rx-3",
            "title": "胃黏膜保护剂",
            "items": [
                {"name": "铝碳酸镁咀嚼片", "spec": "0.5g*20片", "qty": 2},
            ],
            "status": "ready",
            "createdAt": now,
            "patientId": "pat-2",
        },
    ]
    for o in orders:
        _PHARMACY_ORDERS[o["id"]] = o
    _counter["pharm_order"] = 3

    addrs = [
        {
            "id": "addr-1",
            "name": "张三",
            "phone": "13800001111",
            "province": "上海市",
            "city": "上海市",
            "district": "浦东新区",
            "detail": "张江路100号 演示小区 3栋201",
            "isDefault": True,
            "patientId": "pat-1",
            "createdAt": now,
            "updatedAt": now,
        },
        {
            "id": "addr-2",
            "name": "李四",
            "phone": "13900002222",
            "province": "上海市",
            "city": "上海市",
            "district": "徐汇区",
            "detail": "漕溪北路88号",
            "isDefault": False,
            "patientId": "pat-1",
            "createdAt": now,
            "updatedAt": now,
        },
    ]
    for a in addrs:
        _PHARMACY_ADDRESSES[a["id"]] = a
    _counter["pharm_addr"] = 2

    # one pending delivery for demo
    did = "del-1"
    _PHARMACY_DELIVERIES[did] = {
        "id": did,
        "orderId": "rx-1",
        "orderTitle": "氨氯地平续方",
        "status": "pending",
        "uiStatus": "pending_shipment",
        "addressSnapshot": {
            "id": "addr-1",
            "name": "张三",
            "phone": "13800001111",
            "province": "上海市",
            "city": "上海市",
            "district": "浦东新区",
            "detail": "张江路100号 演示小区 3栋201",
        },
        "trackingNo": None,
        "trackingEvents": [
            {
                "at": now,
                "status": "pending",
                "desc": "配送单已创建，待发货（演示）",
            }
        ],
        "patientId": "pat-1",
        "createdAt": now,
        "updatedAt": now,
    }
    _PHARMACY_ORDERS["rx-1"]["status"] = "delivering"
    _counter["pharm_delivery"] = 1


_seed_pharmacy()


# =============================================================================
# SQLite durable snapshot (dict API unchanged; HTTP contracts unchanged)
# =============================================================================
import functools
import os
from typing import Callable


# ---------- M10: Chronic vitals & doctor alerts ----------
CHRONIC_DISCLAIMER = "演示数据，非真实慢病管理；异常规则为演示阈值，不构成诊疗建议。"

_VITALS: dict[str, dict[str, Any]] = {}
_CHRONIC_ALERTS: dict[str, dict[str, Any]] = {}
if "vital" not in _counter:
    _counter["vital"] = 0
if "chronic_alert" not in _counter:
    _counter["chronic_alert"] = 0


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    for fmt, n in (("%Y-%m-%d %H:%M:%S", 19), ("%Y-%m-%dT%H:%M:%S", 19), ("%Y-%m-%d", 10)):
        try:
            dt = datetime.strptime(s[:n], fmt)
            return dt.replace(tzinfo=TZ)
        except ValueError:
            continue
    try:
        raw = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=TZ)
        return dt.astimezone(TZ)
    except ValueError:
        return None


def _vital_abnormal(
    vtype: str,
    *,
    systolic: Optional[float] = None,
    diastolic: Optional[float] = None,
    glucose: Optional[float] = None,
) -> tuple[bool, str]:
    if vtype == "bp":
        notes = []
        if systolic is not None and float(systolic) >= 140:
            notes.append(f"收缩压≥140（{systolic}）")
        if diastolic is not None and float(diastolic) >= 90:
            notes.append(f"舒张压≥90（{diastolic}）")
        if notes:
            return True, "；".join(notes)
        return False, ""
    if vtype == "glucose":
        if glucose is not None and float(glucose) >= 7.0:
            return True, f"血糖≥7.0 mmol/L（{glucose}）"
        return False, ""
    return False, ""


def create_vital(data: dict[str, Any]) -> dict[str, Any]:
    """Create a BP/glucose check-in; abnormal → message + chronic_alerts inbox."""
    patient_id = (data.get("patientId") or "").strip()
    if not patient_id:
        raise ValueError("patientId_required")
    if not get_patient(patient_id):
        raise ValueError("patient_not_found")

    vtype = (data.get("type") or "").strip().lower()
    if vtype not in ("bp", "glucose"):
        raise ValueError("invalid_type")

    systolic = data.get("systolic")
    diastolic = data.get("diastolic")
    glucose = data.get("glucose")

    if vtype == "bp":
        if systolic is None or diastolic is None:
            raise ValueError("bp_requires_systolic_diastolic")
        try:
            systolic = float(systolic)
            diastolic = float(diastolic)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_bp_values") from exc
        glucose = None
        unit = data.get("unit") or "mmHg"
    else:
        if glucose is None:
            raise ValueError("glucose_required")
        try:
            glucose = float(glucose)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_glucose") from exc
        systolic = None
        diastolic = None
        unit = data.get("unit") or "mmol/L"

    abnormal, risk_note = _vital_abnormal(
        vtype, systolic=systolic, diastolic=diastolic, glucose=glucose
    )
    measured_at = data.get("measuredAt") or _now_str()
    vid = data.get("id") or _next_id("vital-", "vital")
    patient = get_patient(patient_id) or {}
    record = {
        "id": vid,
        "patientId": patient_id,
        "patientName": patient.get("name") or "",
        "type": vtype,
        "systolic": systolic,
        "diastolic": diastolic,
        "glucose": glucose,
        "unit": unit,
        "measuredAt": measured_at,
        "note": data.get("note") or "",
        "abnormal": abnormal,
        "riskNote": risk_note if abnormal else "",
        "createdAt": _now_str(),
        "disclaimer": CHRONIC_DISCLAIMER,
    }
    _VITALS[vid] = record

    append_audit(
        action="vital.create",
        resource_type="chronic_vital",
        resource_id=vid,
        detail=f"type={vtype} abnormal={abnormal} patientId={patient_id}",
        actor=str(data.get("actor") or "patient"),
    )

    alert = None
    if abnormal:
        aid = _next_id("calert-", "chronic_alert")
        alert = {
            "id": aid,
            "vitalId": vid,
            "patientId": patient_id,
            "patientName": patient.get("name") or "",
            "type": vtype,
            "systolic": systolic,
            "diastolic": diastolic,
            "glucose": glucose,
            "unit": unit,
            "measuredAt": measured_at,
            "abnormal": True,
            "riskNote": risk_note,
            "read": False,
            "createdAt": _now_str(),
            "disclaimer": CHRONIC_DISCLAIMER,
        }
        _CHRONIC_ALERTS[aid] = alert
        create_message(
            {
                "title": "慢病打卡异常提醒",
                "body": f"{patient.get('name') or '就诊人'}的{('血压' if vtype == 'bp' else '血糖')}打卡异常：{risk_note}（演示规则，请结合面诊判断）。",
                "type": "chronic_alert",
                "read": False,
                "link": "/chronic",
                "patientId": patient_id,
            }
        )

    out = copy.deepcopy(record)
    if alert:
        out["alertId"] = alert["id"]
    return out


def list_vitals(
    *,
    patient_id: Optional[str] = None,
    vtype: Optional[str] = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    items = list(_VITALS.values())
    if patient_id:
        items = [v for v in items if v.get("patientId") == patient_id]
    if vtype:
        items = [v for v in items if v.get("type") == vtype]
    items = sorted(
        items,
        key=lambda x: (x.get("measuredAt") or "", x.get("createdAt") or "", x.get("id") or ""),
        reverse=True,
    )
    lim = max(1, min(int(limit or 50), 500))
    return copy.deepcopy(items[:lim])


def get_vital(vid: str) -> Optional[dict[str, Any]]:
    v = _VITALS.get(vid)
    return copy.deepcopy(v) if v else None


def _avg(nums: list[float]) -> Optional[float]:
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def vitals_summary(patient_id: str) -> dict[str, Any]:
    if not get_patient(patient_id):
        raise ValueError("patient_not_found")
    now = datetime.now(TZ)
    items = list_vitals(patient_id=patient_id, limit=500)

    def in_days(v: dict[str, Any], days: int) -> bool:
        dt = _parse_dt(v.get("measuredAt") or v.get("createdAt"))
        if not dt:
            return False
        return (now - dt) <= timedelta(days=days)

    def collect(window_days: Optional[int]) -> dict[str, Any]:
        subset = items if window_days is None else [v for v in items if in_days(v, window_days)]
        bp_sys = [float(v["systolic"]) for v in subset if v.get("type") == "bp" and v.get("systolic") is not None]
        bp_dia = [float(v["diastolic"]) for v in subset if v.get("type") == "bp" and v.get("diastolic") is not None]
        glu = [float(v["glucose"]) for v in subset if v.get("type") == "glucose" and v.get("glucose") is not None]
        return {
            "count": len(subset),
            "bpSystolicAvg": _avg(bp_sys),
            "bpDiastolicAvg": _avg(bp_dia),
            "glucoseAvg": _avg(glu),
            "bpCount": len(bp_sys),
            "glucoseCount": len(glu),
        }

    latest_bp = next((v for v in items if v.get("type") == "bp"), None)
    latest_glu = next((v for v in items if v.get("type") == "glucose"), None)
    abnormal_30 = sum(1 for v in items if v.get("abnormal") and in_days(v, 30))

    patient = get_patient(patient_id) or {}
    return {
        "patientId": patient_id,
        "patientName": patient.get("name") or "",
        "last7": collect(7),
        "last30": collect(30),
        "latest": {
            "bp": latest_bp,
            "glucose": latest_glu,
        },
        "abnormalCount": abnormal_30,
        "abnormalWindowDays": 30,
        "disclaimer": CHRONIC_DISCLAIMER,
    }


def list_chronic_alerts(*, unread_only: bool = False, limit: int = 100) -> list[dict[str, Any]]:
    items = list(_CHRONIC_ALERTS.values())
    if unread_only:
        items = [a for a in items if not a.get("read")]
    items = sorted(
        items,
        key=lambda x: (x.get("createdAt") or "", x.get("id") or ""),
        reverse=True,
    )
    lim = max(1, min(int(limit or 100), 500))
    return copy.deepcopy(items[:lim])


def unread_chronic_alert_count() -> int:
    return sum(1 for a in _CHRONIC_ALERTS.values() if not a.get("read"))


def mark_chronic_alert_read(alert_id: str) -> Optional[dict[str, Any]]:
    a = _CHRONIC_ALERTS.get(alert_id)
    if not a:
        return None
    a["read"] = True
    append_audit(
        action="chronic_alert.read",
        resource_type="chronic_alert",
        resource_id=alert_id,
        detail=f"patientId={a.get('patientId')}",
        actor="doctor",
    )
    return copy.deepcopy(a)


def list_chronic_patients() -> list[dict[str, Any]]:
    """Patients with chronicDiseases tag OR any vitals history."""
    vital_pids = {v.get("patientId") for v in _VITALS.values() if v.get("patientId")}
    out: list[dict[str, Any]] = []
    for p in list_patients():
        pid = p.get("id")
        if not pid:
            continue
        prof = get_profile(pid) or _empty_profile()
        diseases = list(prof.get("chronicDiseases") or [])
        if not diseases and pid not in vital_pids:
            continue
        vitals = list_vitals(patient_id=pid, limit=5)
        latest = vitals[0] if vitals else None
        abnormal_recent = sum(1 for v in list_vitals(patient_id=pid, limit=100) if v.get("abnormal"))
        out.append(
            {
                "patientId": pid,
                "patientName": p.get("name") or "",
                "age": p.get("age"),
                "gender": p.get("gender"),
                "chronicDiseases": diseases,
                "vitalCount": len(list_vitals(patient_id=pid, limit=500)),
                "abnormalCount": abnormal_recent,
                "latestVital": latest,
                "disclaimer": CHRONIC_DISCLAIMER,
            }
        )
    out.sort(key=lambda x: (x.get("abnormalCount") or 0, x.get("patientName") or ""), reverse=True)
    return out


def _seed_chronic_vitals() -> None:
    """M10 demo: 5–7 vitals for 演示本人, including ≥1 abnormal."""
    if _VITALS:
        return
    if not get_patient("pat-1"):
        _seed_patients()
    base = datetime.now(TZ)
    seeds = [
        # older → newer; one abnormal BP near the end
        {"patientId": "pat-1", "type": "bp", "systolic": 128, "diastolic": 82, "days_ago": 6, "note": "晨起"},
        {"patientId": "pat-1", "type": "glucose", "glucose": 5.6, "days_ago": 5, "note": "空腹"},
        {"patientId": "pat-1", "type": "bp", "systolic": 132, "diastolic": 84, "days_ago": 4, "note": ""},
        {"patientId": "pat-1", "type": "glucose", "glucose": 5.9, "days_ago": 3, "note": "空腹"},
        {"patientId": "pat-1", "type": "bp", "systolic": 126, "diastolic": 80, "days_ago": 2, "note": ""},
        {"patientId": "pat-1", "type": "bp", "systolic": 148, "diastolic": 92, "days_ago": 1, "note": "演示异常"},
        {"patientId": "pat-2", "type": "bp", "systolic": 136, "diastolic": 88, "days_ago": 1, "note": "父亲常规"},
    ]
    # Use internal write without going through create_vital's ValueError path for seed,
    # but still want alerts for abnormal — call create_vital.
    for s in seeds:
        measured = (base - timedelta(days=int(s["days_ago"]))).strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "patientId": s["patientId"],
            "type": s["type"],
            "measuredAt": measured,
            "note": s.get("note") or "",
            "actor": "seed",
        }
        if s["type"] == "bp":
            payload["systolic"] = s["systolic"]
            payload["diastolic"] = s["diastolic"]
        else:
            payload["glucose"] = s["glucose"]
        create_vital(payload)



_seed_chronic_vitals()


from app.persistence import (
    SqliteStore,
    reset_requested,
    store_backend,
)

_PERSIST: SqliteStore | None = None
_PERSIST_ENABLED = False

# kind -> module-level dict that holds entities
_ENTITY_KINDS: dict[str, dict[str, Any]] = {}


def _register_entity_kinds() -> None:
    global _ENTITY_KINDS
    _ENTITY_KINDS = {
        "slots": _SLOTS,
        "appointments": _APPOINTMENTS,
        "sessions": _SESSIONS,
        "patients": _PATIENTS,
        "profiles": _PROFILES,
        "preconsult": _PRECONSULT,
        "lab_reports": _LAB_REPORTS,
        "queues": _QUEUES,
        "messages": _MESSAGES,
        "refills": _REFILLS,
        "reminders": _REMINDERS,
        "surveys": _SURVEYS,
        "followup_responses": _FOLLOWUP_RESPONSES,
        "bills": _BILLS,
        "consultations": _CONSULTATIONS,
        "lab_exams": _LAB_EXAMS,
        "lab_exam_slots": _LAB_EXAM_SLOTS,
        "lab_exam_bookings": _LAB_EXAM_BOOKINGS,
        "pharmacy_orders": _PHARMACY_ORDERS,
        "pharmacy_addresses": _PHARMACY_ADDRESSES,
        "pharmacy_deliveries": _PHARMACY_DELIVERIES,
        "chronic_vitals": _VITALS,
        "chronic_alerts": _CHRONIC_ALERTS,
    }


_FLUSH_LOCK = threading.RLock()


def _flush_store() -> None:
    """Replace-all snapshot of every registered kind + identity + audit + counters."""
    if not _PERSIST_ENABLED or _PERSIST is None:
        return
    with _FLUSH_LOCK:  # serialize snapshots across threadpool requests
        kinds = {kind: dict(mapping) for kind, mapping in _ENTITY_KINDS.items()}
        kinds["identity"] = {"default": dict(_IDENTITY)}
        kinds["audit"] = {str(a.get("id") or i): a for i, a in enumerate(list(_AUDIT))}
        _PERSIST.snapshot(kinds, counters=dict(_counter))


def _load_into_dicts(loaded: dict[str, dict[str, Any]]) -> None:
    for kind, mapping in _ENTITY_KINDS.items():
        mapping.clear()
        src = loaded.get(kind) or {}
        for eid, data in src.items():
            if isinstance(data, dict):
                mapping[eid] = data
    # identity singleton
    ident = (loaded.get("identity") or {}).get("default")
    if isinstance(ident, dict):
        _IDENTITY.clear()
        _IDENTITY.update(ident)
    # audit list
    _AUDIT.clear()
    audit_items = list((loaded.get("audit") or {}).values())
    audit_items.sort(key=lambda x: x.get("createdAt") or x.get("id") or "")
    _AUDIT.extend(audit_items)
    # counters
    saved = _PERSIST.load_counters() if _PERSIST else {}
    if saved:
        for k, v in saved.items():
            try:
                _counter[k] = int(v)
            except (TypeError, ValueError):
                continue


def _ensure_catalogs_after_load() -> None:
    """Catalogs are code constants; reseed slots/exams only if DB had none."""
    if not _SLOTS:
        _seed_slots()
    if not _LAB_EXAMS:
        _seed_lab_exams()
    if not _LAB_EXAM_SLOTS:
        _seed_lab_exam_slots()
    if not _SURVEYS:
        _seed_followup_surveys()
    if not _VITALS:
        _seed_chronic_vitals()


def _with_flush(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        result = fn(*args, **kwargs)
        _flush_store()
        return result

    return wrapper


_MUTATOR_NAMES = [
    "consume_slot",
    "restore_slot",
    "create_appointment",
    "update_appointment",
    "create_session",
    "save_session",
    "create_patient",
    "update_patient",
    "delete_patient",
    "update_profile",
    "create_preconsult_report",
    "get_or_create_queue_for_appointment",
    "check_in_queue",
    "advance_queue_status",
    "create_message",
    "mark_message_read",
    "notify_report_interpreted",
    "create_refill",
    "update_refill",
    "create_medication_reminder",
    "update_medication_reminder",
    "delete_medication_reminder",
    "submit_followup_response",
    "pay_bill",
    "update_identity",
    "append_audit",
    "create_consultation",
    "claim_consultation",
    "add_consultation_message",
    "end_consultation",
    "consume_lab_exam_slot",
    "release_lab_exam_slot",
    "create_lab_exam_booking",
    "reschedule_lab_exam_booking",
    "cancel_lab_exam_booking",
    "create_pharmacy_address",
    "update_pharmacy_address",
    "delete_pharmacy_address",
    "create_pharmacy_delivery",
    "advance_pharmacy_delivery",
    "create_vital",
    "mark_chronic_alert_read",
]


def _wrap_mutators() -> None:
    g = globals()
    for name in _MUTATOR_NAMES:
        fn = g.get(name)
        if callable(fn):
            g[name] = _with_flush(fn)
    # cancel_pharmacy_delivery if present
    for extra in ("cancel_pharmacy_delivery", "accept_consultation", "doctor_reply_consultation"):
        fn = g.get(extra)
        if callable(fn):
            g[extra] = _with_flush(fn)



# ---------- S2: rolling slot window (号源滚动) ----------
_LAST_SLOT_ROLL: dict[str, str] = {"date": ""}


def _referenced_slot_ids() -> tuple[set[str], set[str]]:
    doc_refs = {str(a.get("slotId")) for a in _APPOINTMENTS.values() if a.get("slotId")}
    lab_refs = {str(b.get("slotId")) for b in _LAB_EXAM_BOOKINGS.values() if b.get("slotId")}
    return doc_refs, lab_refs


def roll_slots_window(*, persist: bool = True) -> dict[str, Any]:
    """Ensure bookable slots exist for today..today+N (Asia/Shanghai). Idempotent.

    - Past-dated slots referenced by an appointment/booking are kept as history.
    - Past-dated, unreferenced slots are pruned (they could never be booked).
    - Every (doctor|exam, day) in the window that has no slot gets a fresh set.
    Existing in-window slots (and their remaining counts) are never touched.
    """
    today_dt = _today()
    today = today_dt.strftime("%Y-%m-%d")
    doc_refs, lab_refs = _referenced_slot_ids()
    stats = {"today": today, "prunedSlots": 0, "addedSlots": 0, "prunedLabSlots": 0, "addedLabSlots": 0}

    for sid in [k for k, v in _SLOTS.items() if str(v.get("date") or "") < today and k not in doc_refs]:
        del _SLOTS[sid]
        stats["prunedSlots"] += 1
    have = {(v.get("doctorId"), v.get("date")) for v in _SLOTS.values()}
    before = len(_SLOTS)
    for off in range(SLOT_WINDOW_DAYS):
        day = today_dt + timedelta(days=off)
        ds = day.strftime("%Y-%m-%d")
        for doc in DOCTORS:
            if (doc["id"], ds) not in have:
                _make_doctor_slots_for_day(doc, day, off)
    stats["addedSlots"] = len(_SLOTS) - before

    if _LAB_EXAMS:
        for sid in [k for k, v in _LAB_EXAM_SLOTS.items() if str(v.get("date") or "") < today and k not in lab_refs]:
            del _LAB_EXAM_SLOTS[sid]
            stats["prunedLabSlots"] += 1
        have_lab = {(v.get("examId"), v.get("date")) for v in _LAB_EXAM_SLOTS.values()}
        before = len(_LAB_EXAM_SLOTS)
        for off in range(LAB_SLOT_WINDOW_DAYS):
            day = today_dt + timedelta(days=off)
            ds = day.strftime("%Y-%m-%d")
            for exam in _LAB_EXAMS.values():
                if (exam["id"], ds) not in have_lab:
                    _make_lab_exam_slots_for_day(exam, day, off)
        stats["addedLabSlots"] = len(_LAB_EXAM_SLOTS) - before

    _LAST_SLOT_ROLL["date"] = today
    changed = any(stats[k] for k in ("prunedSlots", "addedSlots", "prunedLabSlots", "addedLabSlots"))
    if changed and persist:
        _flush_store()
    return {**stats, "changed": changed}


def _maybe_roll_slots() -> None:
    """Cheap guard for long-running processes that cross midnight."""
    if _LAST_SLOT_ROLL["date"] != _today().strftime("%Y-%m-%d"):
        try:
            roll_slots_window()
        except Exception:  # never break slot reads
            pass



SEED_VERSION = "m9-golden-1"
DEMO_RESET_DISCLAIMER = "演示重置，非真实就医数据。"


def reset_demo_seed(*, actor: str = "demo") -> dict[str, Any]:
    """Wipe mutable demo entities and re-seed M9 golden path; persist if sqlite."""
    _register_entity_kinds()
    for mapping in _ENTITY_KINDS.values():
        mapping.clear()
    _IDENTITY.clear()
    _AUDIT.clear()
    for k in list(_counter.keys()):
        _counter[k] = 0

    _seed_slots()
    _seed_patients()
    _seed_lab_reports()
    _seed_m2_clinic()
    _seed_refills()
    _seed_medication_reminders()
    _seed_followup_surveys()
    _seed_followup_responses()
    _seed_bills()
    _seed_identity()
    _seed_consultations()
    _seed_preconsult_reports()
    _seed_lab_exams()
    _seed_lab_exam_slots()
    _seed_pharmacy()
    _seed_chronic_vitals()
    roll_slots_window(persist=False)

    # Audit after reseed so it is not wiped; detail has no sensitive plaintext
    append_audit(
        action="demo.reset",
        resource_type="demo",
        resource_id=SEED_VERSION,
        detail="黄金路径演示数据已重置",
        actor=actor or "demo",
    )
    _flush_store()
    return {
        "ok": True,
        "seedVersion": SEED_VERSION,
        "disclaimer": DEMO_RESET_DISCLAIMER,
    }


def bootstrap_persistence() -> None:
    """Call once at import end: memory keeps seeds; sqlite loads or seeds then persists."""
    global _PERSIST, _PERSIST_ENABLED
    _register_entity_kinds()
    backend = store_backend()
    if backend == "memory":
        _PERSIST = None
        _PERSIST_ENABLED = False
        roll_slots_window(persist=False)
        return

    _PERSIST = SqliteStore()
    if reset_requested():
        _PERSIST.wipe()

    if _PERSIST.has_data():
        loaded = _PERSIST.load_all()
        _load_into_dicts(loaded)
        _ensure_catalogs_after_load()
        _seed_preconsult_reports()  # demo v1 link target; idempotent
        roll_slots_window(persist=False)  # S2: stale DB → shift window to today
        _PERSIST_ENABLED = True
        # catalogs may have been re-seeded into empty kinds — persist again
        _flush_store()
    else:
        # First run: keep in-memory seeds, snapshot to disk
        roll_slots_window(persist=False)
        _PERSIST_ENABLED = True
        _flush_store()

    _wrap_mutators()


bootstrap_persistence()
