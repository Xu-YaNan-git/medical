"""Visit store: in-memory dicts with optional SQLite durable snapshot."""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Optional
from zoneinfo import ZoneInfo

from app.persistence import SqliteStore, reset_requested, store_backend

TZ = ZoneInfo("Asia/Shanghai")

# Seed chart data aligned with frontend openVisit() prefill
_SEED_CHART: dict[str, dict[str, str]] = {
    "v1": {
        "chief": "反复上腹痛 3 天",
        "hpi": "反复上腹痛3天，多为餐后隐痛，伴反酸烧心，无放射痛。偶有恶心，无呕吐、黑便。",
        "pmh": "慢性胃炎病史2年，否认手术史。",
        "allergy": "对青霉素过敏（皮疹）",
        "pe": "T 36.6℃，P 78次/分，BP 128/82 mmHg。腹软，上腹轻压痛，无反跳痛及肌紧张，Murphy征阴性。",
        "labs": "近期未行胃镜检查",
        "rawText": "",
    },
    "v2": {
        "chief": "咳嗽、发热 2 天",
        "hpi": "咳嗽、发热2天，体温最高38.2℃，有黄白痰，无胸痛咯血。",
        "pmh": "既往体健",
        "allergy": "否认药物过敏",
        "pe": "T 37.8℃，咽充血，双肺呼吸音粗，未闻及明显干湿啰音。",
        "labs": "",
        "rawText": "",
    },
    "v3": {
        "chief": "头晕、血压升高 1 周",
        "hpi": "",
        "pmh": "",
        "allergy": "",
        "pe": "",
        "labs": "",
        "rawText": "",
    },
    "v4": {
        "chief": "尿频尿急 1 天",
        "hpi": "尿频尿急1天，伴尿痛，无发热腰痛，无肉眼血尿。",
        "pmh": "否认泌尿系结石及手术史",
        "allergy": "否认药物过敏",
        "pe": "腹软，无压痛，肾区无叩痛。",
        "labs": "",
        "rawText": "",
    },
}


def _now_str() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%d %H:%M")


def _empty_chart() -> dict[str, str]:
    return {
        "chief": "",
        "hpi": "",
        "pmh": "",
        "allergy": "",
        "pe": "",
        "labs": "",
        "rawText": "",
    }


def _make_visit(
    vid: str,
    name: str,
    gender: str,
    age: int,
    chief: str,
    time: str,
    status: str,
    chart: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    c = chart or _empty_chart()
    if not c.get("chief"):
        c["chief"] = chief
    return {
        "id": vid,
        "name": name,
        "gender": gender,
        "age": age,
        "chief": chief,
        "time": time,
        "status": status,
        "hpi": c.get("hpi", ""),
        "pmh": c.get("pmh", ""),
        "allergy": c.get("allergy", ""),
        "pe": c.get("pe", ""),
        "labs": c.get("labs", ""),
        "rawText": c.get("rawText", ""),
        "diagnosis": c.get("diagnosis", ""),
        "assessment": c.get("assessment", ""),
        "specialty": c.get("specialty", ""),
        "differential": [],  # list of dicts
        "orders": [],  # list of {type, text, ...}
        "note": "",
        "preconsultReportId": None,
    }


SEED_PRECONSULT_ID = "pcr-seed-1"  # must match medical-patient-api store.SEED_PRECONSULT_ID


def seed_visits() -> dict[str, dict[str, Any]]:
    specs = [
        ("v1", "王小明", "男", 42, "反复上腹痛 3 天", "2026-10-02 09:15", "waiting"),
        ("v2", "李秀英", "女", 58, "咳嗽、发热 2 天", "2026-10-02 09:40", "waiting"),
        ("v3", "陈建国", "男", 67, "头晕、血压升高 1 周", "2026-10-02 10:05", "done"),
        ("v4", "赵丽华", "女", 35, "尿频尿急 1 天", "2026-10-02 10:30", "waiting"),
    ]
    out: dict[str, dict[str, Any]] = {}
    for vid, name, gender, age, chief, time, status in specs:
        chart = copy.deepcopy(_SEED_CHART.get(vid, _empty_chart()))
        out[vid] = _make_visit(vid, name, gender, age, chief, time, status, chart)
    # Demo: v1 links the patient-side fixed seed report (8001 seeds pcr-seed-1 on boot
    # and on every demo reset, so reset order between the two services doesn't matter).
    out["v1"]["preconsultReportId"] = SEED_PRECONSULT_ID
    return out


AUDIT_DISCLAIMER = "演示审计日志，无敏感明文；非正式合规审计系统。"
SEED_VERSION = "m9-golden-1"
DEMO_RESET_DISCLAIMER = "演示重置，非真实就医数据。"


class VisitStore:
    def __init__(self) -> None:
        self._visits = seed_visits()
        self._counter = 100
        self._audit: list[dict[str, Any]] = []
        self._audit_counter = 0
        self._db: SqliteStore | None = None
        self._persist_enabled = False
        self._bootstrap()

    def _bootstrap(self) -> None:
        backend = store_backend()
        if backend == "memory":
            self._seed_audit_if_empty()
            return
        self._db = SqliteStore()
        if reset_requested():
            self._db.wipe()
        if self._db.has_data():
            loaded = self._db.load_kind("visits")
            if loaded:
                # Re-key by data["id"] so list summaries and GET /visits/{id} never diverge
                # (dict key vs embedded id mismatch → list shows an id that detail 404s).
                fixed: dict[str, dict[str, Any]] = {}
                for eid, data in loaded.items():
                    if not isinstance(data, dict):
                        continue
                    vid = str(data.get("id") or eid)
                    data = dict(data)
                    data["id"] = vid
                    fixed[vid] = data
                self._visits = fixed
            audit_map = self._db.load_kind("audit")
            if audit_map:
                items = list(audit_map.values())
                items.sort(key=lambda x: x.get("createdAt") or x.get("id") or "")
                self._audit = [x for x in items if isinstance(x, dict)]
            counters = self._db.load_counters()
            if "visit" in counters:
                try:
                    self._counter = int(counters["visit"])
                except (TypeError, ValueError):
                    pass
            else:
                # derive counter from max numeric suffix of vN ids
                max_n = 100
                for vid in self._visits:
                    if vid.startswith("v"):
                        try:
                            max_n = max(max_n, int(vid[1:]))
                        except ValueError:
                            pass
                self._counter = max_n
            if "audit" in counters:
                try:
                    self._audit_counter = int(counters["audit"])
                except (TypeError, ValueError):
                    pass
            else:
                max_a = self._audit_counter
                for a in self._audit:
                    aid = str(a.get("id") or "")
                    if aid.startswith("aud-"):
                        try:
                            max_a = max(max_a, int(aid[4:]))
                        except ValueError:
                            pass
                self._audit_counter = max_a
            self._persist_enabled = True
            self._seed_audit_if_empty()
            self._flush()
        else:
            self._persist_enabled = True
            self._seed_audit_if_empty()
            self._flush()

    def _flush(self) -> None:
        if not self._persist_enabled or self._db is None:
            return
        # shallow copies: other threadpool requests may mutate while we serialize
        audit_map = {str(a.get("id") or i): a for i, a in enumerate(list(self._audit))}
        self._db.snapshot(
            {"visits": dict(self._visits), "audit": audit_map},
            counters={"visit": self._counter, "audit": self._audit_counter},
        )

    def _seed_audit_if_empty(self) -> None:
        if self._audit:
            return
        now = _now_str()
        seeds = [
            {
                "id": "aud-1",
                "action": "system.seed",
                "resourceType": "system",
                "resourceId": "boot",
                "actor": "system",
                "detail": "医生端审计种子初始化",
                "createdAt": now,
            },
            {
                "id": "aud-2",
                "action": "visit.seed",
                "resourceType": "visit",
                "resourceId": "v1",
                "actor": "system",
                "detail": "种子就诊王小明（演示）",
                "createdAt": now,
            },
            {
                "id": "aud-3",
                "action": "visit.seed",
                "resourceType": "visit",
                "resourceId": "v2",
                "actor": "system",
                "detail": "种子就诊李秀英（演示）",
                "createdAt": now,
            },
        ]
        self._audit.extend(seeds)
        self._audit_counter = max(self._audit_counter, 3)

    def append_audit(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        detail: str = "",
        actor: str = "doctor",
    ) -> dict[str, Any]:
        from app.privacy import scrub_audit_detail

        self._audit_counter += 1
        aid = f"aud-{self._audit_counter}"
        entry = {
            "id": aid,
            "action": action,
            "resourceType": resource_type,
            "resourceId": resource_id,
            "actor": actor,
            "detail": scrub_audit_detail(detail or ""),
            "createdAt": _now_str(),
        }
        self._audit.append(entry)
        self._flush()
        return copy.deepcopy(entry)

    def list_audit(self, *, limit: int = 50) -> list[dict[str, Any]]:
        from app.privacy import scrub_audit_entry

        lim = max(1, min(int(limit or 50), 500))
        items = sorted(
            self._audit,
            key=lambda x: (x.get("createdAt") or "", x.get("id") or ""),
            reverse=True,
        )
        return [scrub_audit_entry(copy.deepcopy(x)) for x in items[:lim]]


    def reset_demo_seed(self, *, actor: str = "doctor") -> dict[str, Any]:
        """Wipe visits/audit demo data and re-seed golden-path waiting visits."""
        self._visits = seed_visits()
        self._counter = 100
        self._audit = []
        self._audit_counter = 0
        self._seed_audit_if_empty()
        self.append_audit(
            action="demo.reset",
            resource_type="demo",
            resource_id=SEED_VERSION,
            detail="黄金路径演示就诊数据已重置",
            actor=actor or "doctor",
        )
        self._flush()
        return {
            "ok": True,
            "seedVersion": SEED_VERSION,
            "disclaimer": DEMO_RESET_DISCLAIMER,
        }

    def list_visits(self) -> list[dict[str, Any]]:
        # Stable display order: by time ascending like demo list
        return sorted(self._visits.values(), key=lambda v: v["time"])

    def get(self, visit_id: str) -> Optional[dict[str, Any]]:
        return self._visits.get(visit_id)

    def create(
        self,
        name: str = "新患者",
        gender: str = "男",
        age: int = 40,
        chief: str = "（待填写）",
        status: str = "waiting",
        preconsultReportId: str | None = None,
    ) -> dict[str, Any]:
        self._counter += 1
        vid = f"v{self._counter}"
        visit = _make_visit(vid, name, gender, age, chief, _now_str(), status)
        visit["preconsultReportId"] = preconsultReportId
        self._visits[vid] = visit
        self._flush()
        self.append_audit(
            action="visit.create",
            resource_type="visit",
            resource_id=vid,
            detail=f"新建就诊 name={name} chief={chief}",
            actor="doctor",
        )
        return visit

    def update(self, visit_id: str, fields: dict[str, Any]) -> Optional[dict[str, Any]]:
        visit = self._visits.get(visit_id)
        if not visit:
            return None
        allowed = {
            "name",
            "gender",
            "age",
            "chief",
            "status",
            "hpi",
            "pmh",
            "allergy",
            "pe",
            "labs",
            "rawText",
            "diagnosis",
            "assessment",
            "specialty",
            "differential",
            "orders",
            "note",
            "preconsultReportId",
        }
        for k, v in fields.items():
            if k in allowed and v is not None:
                visit[k] = v
        # Keep list chief in sync with chart chief when chart chief updated
        if "chief" in fields and fields["chief"] is not None:
            visit["chief"] = fields["chief"]
        self._flush()
        changed = ",".join(sorted(k for k in fields if k in allowed and fields[k] is not None))
        self.append_audit(
            action="visit.update",
            resource_type="visit",
            resource_id=visit_id,
            detail=f"更新就诊字段 {changed or '无'}",
            actor="doctor",
        )
        return visit

    def summary(self, visit: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": visit["id"],
            "name": visit["name"],
            "gender": visit["gender"],
            "age": visit["age"],
            "chief": visit["chief"],
            "time": visit["time"],
            "status": visit["status"],
        }

    def detail(self, visit: dict[str, Any]) -> dict[str, Any]:
        out = copy.deepcopy(visit)
        out.setdefault("diagnosis", "")
        out.setdefault("assessment", "")
        out.setdefault("specialty", "")
        # normalize order entries
        orders = out.get("orders") or []
        for o in orders:
            if isinstance(o, dict):
                o.setdefault("source", None)
        return out


store = VisitStore()
