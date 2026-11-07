/**
 * 导诊台 · 患者端 MVP
 * API_BASE 优先真实接口，失败静默降级 Mock；预约成功后镜像 localStorage。
 */
const API_BASE = String((window.APP_CONFIG && window.APP_CONFIG.patientApiBase) || 'http://127.0.0.1:8001').replace(/\/+$/, '');
const STORAGE_KEY = 'triage_appointments_v1';
const PATIENTS_KEY = 'triage_patients_v1';
const ACTIVE_PATIENT_KEY = 'triage_active_patient_v1';
const PROFILES_KEY = 'triage_profiles_v1';
const PRECONSULT_KEY = 'triage_preconsult_v1';
const REPORTS_CACHE_KEY = 'triage_reports_cache_v1';
const REFILLS_KEY = 'triage_refills_v1';
const MED_REMINDERS_KEY = 'triage_med_reminders_v1';
const MED_TODAY_KEY = 'triage_med_today_v1';
const FOLLOWUP_RESP_KEY = 'triage_followup_responses_v1';
const BILLS_KEY = 'triage_bills_v1';
const IDENTITY_KEY = 'triage_identity_binding_v1';
const DC_SESSIONS_KEY = 'doctor_consult_sessions_v1';
const EXAM_BOOKINGS_KEY = 'exam_bookings_v1';
const EXAM_SLOTS_KEY = 'exam_slots_v1';
const PHARMACY_ORDERS_KEY = 'pharmacy_orders_v1';
const PHARMACY_ADDRESSES_KEY = 'pharmacy_addresses_v1';
const PHARMACY_DELIVERIES_KEY = 'pharmacy_deliveries_v1';
const CHRONIC_VITALS_KEY = 'triage_chronic_vitals_v1';
const APP_VERSION = 'v16-s2-guardrail-020';
const API_TIMEOUT_MS = 15000;
/** 真实 LLM 约 10s/次：AI 端点超时放宽到 60s（≥25s），避免前端提前中断 */
const AI_TIMEOUT_MS = 60000;
const AI_PATH_RE = /^\/api\/(triage|consult|reports\/interpret|preconsult|chat|ai)\b/;

const RELATIONS = ['本人', '父母', '配偶', '子女', '其他'];

const RELATION_TO_API = { '本人': 'self', '父母': '父母', '配偶': '配偶', '子女': '子女', '其他': '其他' };
const RELATION_FROM_API = {
  self: '本人', '本人': '本人',
  '父': '父母', '母': '父母', '父母': '父母', father: '父母', mother: '父母', parent: '父母',
  '配偶': '配偶', spouse: '配偶',
  '子女': '子女', child: '子女',
  '其他': '其他', other: '其他'
};

function relationToApi(r) {
  return RELATION_TO_API[r] || r || 'self';
}
function relationFromApi(r) {
  if (!r) return '其他';
  return RELATION_FROM_API[r] || RELATION_FROM_API[String(r).toLowerCase()] || r;
}

function normalizePatient(p, source) {
  if (!p) return null;
  return {
    id: p.id,
    name: p.name,
    relation: relationFromApi(p.relation),
    gender: p.gender || '',
    age: p.age ?? null,
    phone: p.phone || '',
    source: source || p.source || 'api'
  };
}

function normalizeLabReport(r, source) {
  if (!r) return null;
  const status = r.status || '';
  const statusLabel = r.statusLabel || (
    status === 'ready' || status === '已出' ? '已出'
    : status === 'reading' || status === '解读中' ? '解读中'
    : (status || '已出')
  );
  return {
    ...r,
    title: r.title || r.name || '报告',
    typeLabel: r.typeLabel || r.category || (r.type === 'imaging' ? '检查' : '检验'),
    status,
    statusLabel,
    date: r.date || (r.reportedAt ? String(r.reportedAt).slice(0, 10) : ''),
    patientName: r.patientName || '',
    hospitalName: r.hospitalName || '演示院区',
    summary: r.summary || '',
    items: r.items || [],
    findings: r.findings || '',
    impression: r.impression || '',
    disclaimer: r.disclaimer || '仅供参考，不能替代面诊',
    source: source || r.source || 'api'
  };
}

function mapUrgencyLabel(u, fallback) {
  if (u === 'emergency' || u === 'urgent') return '建议急诊';
  if (u === 'routine' || u === 'normal') return '门诊';
  if (typeof u === 'string' && u) {
    if (u.includes('急诊') || u.includes('紧急')) return u;
    if (u.includes('门诊') || u.includes('线上')) return u;
  }
  return fallback || '门诊';
}

function normalizePreconsultApi(data, fallbackResult, patient, sessionId) {
  const ss = data.structuredSummary || {};
  const triage = data.triage || {};
  const depts = ss.departments || data.departments || triage.departments
    || data.suggestedDepartments || fallbackResult?.departments || [];
  const mappedDepts = (depts || []).map((d) => typeof d === 'string' ? { name: d, reason: '' } : {
    id: d.id, name: d.name, reason: d.reason || ''
  });
  const rawUrgency = ss.urgency || data.urgency || triage.urgency || data.level
    || data.emergencyLevel || fallbackResult?.urgency || fallbackResult?.level || 'routine';
  // Prefer triage.urgency for display level when structuredSummary marks emergency as red-flag template
  const displayUrgencySrc = triage.urgency || data.urgency || ss.urgency || rawUrgency;
  const urgency = mapUrgencyLabel(displayUrgencySrc, fallbackResult?.level || '门诊');
  const urgent = !!(data.urgent || displayUrgencySrc === 'emergency' || displayUrgencySrc === 'urgent'
    || String(urgency).includes('急诊') || fallbackResult?.urgent);
  const nextSteps = Array.isArray(ss.nextSteps) ? ss.nextSteps
    : (Array.isArray(data.nextSteps) ? data.nextSteps
      : (Array.isArray(triage.nextSteps) ? triage.nextSteps
        : (Array.isArray(data.advice) ? data.advice
          : (data.advice ? [data.advice] : (fallbackResult?.advice ? [fallbackResult.advice] : [])))));
  const patientObj = data.patient || (patient ? {
    id: patient.id, name: patient.name, relation: patient.relation,
    gender: patient.gender, age: patient.age, phone: patient.phone
  } : null);
  const hpi = ss.presentIllness || data.hpi || data.history || data.presentIllness
    || data.summaryText || data.summary || '';
  const chief = data.chief || ss.chiefComplaint || data.chiefComplaint
    || fallbackResult?.summary?.chief || '';
  return {
    id: data.id || data.reportId || ('pc-' + Date.now()),
    sessionId: sessionId || data.sessionId || null,
    createdAt: data.createdAt || data.generatedAt || new Date().toISOString(),
    patient: patientObj || (data.patientName ? {
      id: data.patientId || '', name: data.patientName, relation: '', gender: '', age: null, phone: ''
    } : null),
    chief,
    hpi,
    chatSummary: data.chatSummary || ss.patientNarrative || fallbackResult?.chatSummary || '',
    departments: mappedDepts,
    urgency,
    urgent,
    nextSteps,
    advice: typeof data.advice === 'string' ? data.advice : (nextSteps[0] || fallbackResult?.advice || ''),
    redFlags: ss.redFlags || data.redFlags || [],
    doctorHints: ss.doctorHints || data.doctorHints || [],
    disclaimer: data.disclaimer || triage.disclaimer || '仅供参考，不能替代面诊',
    source: 'api',
    raw: data
  };
}

const SEED_PATIENTS = [
  { id: 'p-self', name: '演示患者', relation: '本人', gender: '男', age: 32, phone: '' },
  { id: 'p-mom', name: '王秀英', relation: '父母', gender: '女', age: 58, phone: '' }
];

const SEED_PROFILES = {
  'p-self': {
    allergies: ['青霉素'],
    chronicDiseases: [],
    medications: [],
    updatedAt: new Date().toISOString()
  },
  'p-mom': {
    allergies: ['磺胺类'],
    chronicDiseases: ['高血压', '2型糖尿病'],
    medications: ['氨氯地平', '二甲双胍'],
    updatedAt: new Date().toISOString()
  }
};

const MOCK_LAB_REPORTS = [
  {
    id: 'r-cbc-1',
    title: '血常规',
    type: 'lab',
    typeLabel: '检验',
    status: 'ready',
    statusLabel: '已出',
    patientName: '演示患者',
    date: '2026-10-06',
    hospitalName: '演示院区',
    summary: '白细胞轻度升高，其余大致正常',
    items: [
      { name: '白细胞 WBC', value: '11.2', unit: '×10⁹/L', ref: '3.5–9.5', flag: 'H' },
      { name: '红细胞 RBC', value: '4.6', unit: '×10¹²/L', ref: '4.3–5.8', flag: '' },
      { name: '血红蛋白 Hb', value: '142', unit: 'g/L', ref: '130–175', flag: '' },
      { name: '血小板 PLT', value: '210', unit: '×10⁹/L', ref: '125–350', flag: '' }
    ],
    disclaimer: '仅供参考，不能替代面诊'
  },
  {
    id: 'r-liver-1',
    title: '肝功能',
    type: 'lab',
    typeLabel: '检验',
    status: 'ready',
    statusLabel: '已出',
    patientName: '演示患者',
    date: '2026-10-05',
    hospitalName: '演示院区',
    summary: '转氨酶轻度升高',
    items: [
      { name: 'ALT', value: '68', unit: 'U/L', ref: '9–50', flag: 'H' },
      { name: 'AST', value: '52', unit: 'U/L', ref: '15–40', flag: 'H' },
      { name: '总胆红素', value: '14', unit: 'μmol/L', ref: '3.4–20.5', flag: '' }
    ],
    disclaimer: '仅供参考，不能替代面诊'
  },
  {
    id: 'r-ct-1',
    title: '胸部 CT 平扫',
    type: 'imaging',
    typeLabel: '检查',
    status: 'reading',
    statusLabel: '解读中',
    patientName: '王秀英',
    date: '2026-10-07',
    hospitalName: '演示院区',
    summary: '双肺未见明显实质性病变（演示）',
    findings: '双肺纹理清晰，未见明显实质性病变；纵隔未见明显肿大淋巴结。',
    impression: '胸部 CT 未见明显异常（演示报告）。',
    disclaimer: '仅供参考，不能替代面诊'
  },
  {
    id: 'r-ua-1',
    title: '尿常规',
    type: 'lab',
    typeLabel: '检验',
    status: 'ready',
    statusLabel: '已出',
    patientName: '演示患者',
    date: '2026-09-28',
    hospitalName: '演示院区',
    summary: '大致正常',
    items: [
      { name: '尿蛋白', value: '阴性', unit: '', ref: '阴性', flag: '' },
      { name: '尿隐血', value: '阴性', unit: '', ref: '阴性', flag: '' },
      { name: '白细胞酯酶', value: '阴性', unit: '', ref: '阴性', flag: '' }
    ],
    disclaimer: '仅供参考，不能替代面诊'
  }
];

const URGENT_KEYWORDS = [
  '胸痛', '胸口痛', '心绞痛', '大出血', '出血不止', '意识不清', '昏迷',
  '呼吸困难', '喘不上气', '抽搐', '中风', '偏瘫', '剧烈头痛', '呕血',
  '便血量大', '高热惊厥', '自杀', '休克'
];

const MOCK_DEPARTMENTS = [
  { id: 'd1', name: '呼吸内科', desc: '咳嗽、发热、哮喘等', intro: '咳嗽、发热、哮喘等' },
  { id: 'd2', name: '全科医学', desc: '常见病初诊与转诊', intro: '常见病初诊与转诊' },
  { id: 'd3', name: '急诊科', desc: '急危重症优先', intro: '急危重症优先' },
  { id: 'd4', name: '心内科', desc: '胸闷、胸痛、高血压', intro: '胸闷、胸痛、高血压' },
  { id: 'd5', name: '消化内科', desc: '腹痛、胃炎、消化不良', intro: '腹痛、胃炎、消化不良' },
  { id: 'd6', name: '神经内科', desc: '头痛、眩晕、麻木', intro: '头痛、眩晕、麻木' },
  { id: 'd7', name: '皮肤科', desc: '皮疹、过敏、瘙痒', intro: '皮疹、过敏、瘙痒' },
  { id: 'd8', name: '骨科', desc: '关节、外伤、腰痛', intro: '关节、外伤、腰痛' },
  { id: 'd9', name: '耳鼻喉科', desc: '咽痛、鼻塞、耳鸣', intro: '咽痛、鼻塞、耳鸣' }
];

const MOCK_DOCTORS = [
  { id: 'doc1', name: '王晓明', title: '主任医师', deptId: 'd1', departmentId: 'd1', intro: '呼吸专科' },
  { id: 'doc2', name: '李芳', title: '副主任医师', deptId: 'd1', departmentId: 'd1', intro: '哮喘与慢阻肺' },
  { id: 'doc3', name: '陈志远', title: '主治医师', deptId: 'd2', departmentId: 'd2', intro: '全科初诊' },
  { id: 'doc4', name: '赵倩', title: '主任医师', deptId: 'd3', departmentId: 'd3', intro: '急诊抢救' },
  { id: 'doc5', name: '刘洋', title: '副主任医师', deptId: 'd4', departmentId: 'd4', intro: '冠心病' },
  { id: 'doc6', name: '周敏', title: '主治医师', deptId: 'd5', departmentId: 'd5', intro: '胃炎消化不良' },
  { id: 'doc7', name: '孙磊', title: '主任医师', deptId: 'd6', departmentId: 'd6', intro: '头痛眩晕' },
  { id: 'doc8', name: '吴佳', title: '主治医师', deptId: 'd7', departmentId: 'd7', intro: '过敏皮疹' },
  { id: 'doc9', name: '郑凯', title: '副主任医师', deptId: 'd8', departmentId: 'd8', intro: '关节外伤' },
  { id: 'doc10', name: '黄丽', title: '主任医师', deptId: 'd9', departmentId: 'd9', intro: '咽喉鼻部' }
];

function todayPlus(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const w = ['日', '一', '二', '三', '四', '五', '六'][d.getDay()];
  return `${d.getMonth() + 1}月${d.getDate()}日 周${w}`;
}

function isoDatePlus(days) {
  const d = new Date();
  d.setDate(d.getDate() + days);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function dateLabelFromIso(iso) {
  if (!iso) return '';
  const [y, m, d] = iso.split('-').map(Number);
  const dt = new Date(y, m - 1, d);
  const w = ['日', '一', '二', '三', '四', '五', '六'][dt.getDay()];
  return `${m}月${d}日 周${w}`;
}

function mockSlots(doctorId) {
  const times = ['08:30', '09:00', '09:30', '10:00', '10:30', '14:00', '14:30', '15:00', '15:30', '16:00'];
  const slots = [];
  for (let day = 1; day <= 3; day++) {
    const date = isoDatePlus(day);
    times.forEach((t, i) => {
      const available = !((day + i) % 5 === 0);
      slots.push({
        id: `${doctorId}-${day}-${t}`,
        doctorId,
        date,
        dateLabel: dateLabelFromIso(date),
        time: t,
        remaining: available ? 3 : 0,
        available
      });
    });
  }
  return slots;
}

/* ---------- API helpers ---------- */
async function apiFetch(path, options = {}) {
  const ctrl = new AbortController();
  const timeoutMs = options.timeoutMs || (AI_PATH_RE.test(path) ? AI_TIMEOUT_MS : API_TIMEOUT_MS);
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: ctrl.signal,
      headers: {
        'Content-Type': 'application/json',
        ...(options.headers || {})
      }
    });
    clearTimeout(timer);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (e) {
    clearTimeout(timer);
    throw e;
  }
}

function isUrgentText(...parts) {
  const text = parts.filter(Boolean).join(' ');
  return URGENT_KEYWORDS.some((k) => text.includes(k));
}

function sourceLabel(source) {
  if (!source || source === 'mock' || source === 'seed') return '本地 Mock';
  if (source === 'guardrail') return '安全护栏';
  if (source === 'mock_fallback') return '服务端（AI 校验未通过，已回落）';
  return '服务端 API';
}

function isApiSource(source) {
  return source && source !== 'mock' && source !== 'seed';
}

/** Normalize TriageResult → UI shape expected by renderResult */
function normalizeTriage(data, requestPayload = {}) {
  if (!data) return null;
  const urgency = data.urgency || '';
  const urgent = urgency === 'emergency' || urgency === 'urgent' || !!data.urgent;
  let level = data.level;
  if (!level) {
    if (urgency === 'emergency') level = '建议急诊';
    else if (urgency === 'urgent') level = '建议急诊';
    else if (data.suggestOnline) level = '可线上问诊 / 门诊';
    else level = '门诊';
  }
  const nextSteps = Array.isArray(data.nextSteps) ? data.nextSteps : [];
  const advice = data.advice || (nextSteps.length ? nextSteps.slice(0, 3).join('；') : '');
  let summary = data.summary;
  if (!summary || typeof summary === 'string') {
    const companions = requestPayload.companions
      || (requestPayload.extra ? String(requestPayload.extra).split(/[、,，]/).map((s) => s.trim()).filter(Boolean) : []);
    summary = {
      chief: requestPayload.chief || (typeof data.summary === 'string' ? data.summary : '') || '',
      duration: requestPayload.duration || '',
      location: requestPayload.location || requestPayload.bodyPart || '',
      severity: requestPayload.severity || '',
      companions,
      narrative: typeof data.summary === 'string' ? data.summary : ''
    };
  }
  const departments = (data.departments || []).map((d) => ({
    id: d.id,
    name: d.name,
    reason: d.reason || '',
    score: d.score ?? d.rank
  }));
  return {
    ...data,
    urgent,
    urgency,
    level,
    advice,
    departments,
    summary,
    disclaimer: data.disclaimer || '仅供参考，不能替代面诊',
    source: data.source || 'api'
  };
}

function mockTriageSymptom(payload) {
  const { chief = '', duration = '', location = '', severity = '', companions = [] } = payload;
  const all = [chief, location, severity, ...(companions || [])].join(' ');
  const urgent = isUrgentText(all) || (severity === '重' && /胸|呼吸|意识|出血/.test(all));

  let departments = [];
  let level = '门诊';
  let advice = '';

  if (urgent) {
    departments = [
      { name: '急诊科', reason: '存在急危重症相关表现，建议优先急诊评估', score: 98 },
      { name: '心内科', reason: '胸痛/呼吸相关需排除心源性疾病', score: 80 },
      { name: '呼吸内科', reason: '若以呼吸症状为主可同步评估', score: 70 }
    ];
    level = '建议急诊';
    advice = '请立即前往就近医院急诊科，或拨打 120。不要自行驾驶车辆，保持同伴陪同。';
  } else if (/咳|痰|咽|发烧|发热|感冒|流感/.test(all) || location === '咽喉' || (location === '胸部' && /咳/.test(all))) {
    departments = [
      { name: '呼吸内科', reason: '呼吸道症状为主，适合专科门诊', score: 92 },
      { name: '全科医学', reason: '症状较轻时可先全科评估', score: 78 },
      { name: '耳鼻喉科', reason: '若以咽痛、鼻塞为主可考虑', score: 65 }
    ];
    level = companions.includes('发热') && severity !== '轻' ? '可线上问诊 / 门诊' : '门诊';
    advice = '注意休息与补液；若持续高热、气促加重请及时复诊。';
  } else if (/腹|胃|吐|泻|消化/.test(all) || location === '腹部') {
    departments = [
      { name: '消化内科', reason: '消化道症状为主', score: 90 },
      { name: '全科医学', reason: '轻症可先全科处理', score: 75 }
    ];
    level = '门诊';
    advice = '清淡饮食，观察腹痛位置与大便性状变化。';
  } else if (/头|晕|麻木|失眠/.test(all) || location === '头部') {
    departments = [
      { name: '神经内科', reason: '头痛/神经系统相关症状', score: 88 },
      { name: '全科医学', reason: '排除常见诱因', score: 72 }
    ];
    level = '门诊';
    advice = '记录发作频率与诱因，就医时一并告知医生。';
  } else if (/皮疹|痒|过敏|皮肤/.test(all) || location === '皮肤') {
    departments = [
      { name: '皮肤科', reason: '皮肤相关症状', score: 90 },
      { name: '全科医学', reason: '可先初步评估过敏史', score: 70 }
    ];
    level = '可线上问诊 / 门诊';
    advice = '避免搔抓与自行乱用激素药膏。';
  } else if (/关节|腰|腿|骨折|扭伤/.test(all) || location === '四肢') {
    departments = [
      { name: '骨科', reason: '骨骼关节相关不适', score: 88 },
      { name: '全科医学', reason: '轻伤可先评估', score: 68 }
    ];
    level = '门诊';
    advice = '制动休息，冰敷消肿；畸形或无法负重请急诊。';
  } else {
    departments = [
      { name: '全科医学', reason: '症状较笼统，建议全科初诊分流', score: 85 },
      { name: '呼吸内科', reason: '若伴呼吸道症状可转诊', score: 60 }
    ];
    level = '门诊';
    advice = '建议完善主诉细节后就诊，便于医生快速判断。';
  }

  return {
    urgent,
    level,
    departments: departments.slice(0, 3),
    advice,
    summary: {
      chief, duration, location: location || '未注明', severity, companions: companions || []
    },
    source: 'mock',
    disclaimer: '仅供参考，不能替代面诊'
  };
}

const chatSessions = new Map();

function mockChat(sessionId, message) {
  let state = chatSessions.get(sessionId);
  if (!state) {
    state = { turn: 0, facts: {}, messages: [] };
    chatSessions.set(sessionId, state);
  }
  state.turn += 1;
  state.messages.push({ role: 'user', content: message });

  const lower = message;
  if (/胸痛|呼吸困难|意识不清|大出血|昏迷/.test(lower)) {
    state.facts.urgentHint = true;
    state.facts.chief = (state.facts.chief || '') + ' ' + message;
  }
  if (!state.facts.chief && state.turn === 1) state.facts.chief = message;
  if (/天|周|小时|月/.test(lower)) state.facts.duration = message;
  if (/头|胸|腹|喉|腿|手|皮肤/.test(lower)) state.facts.location = message;
  if (/轻|中|重|能忍|不能忍|很痛/.test(lower)) state.facts.severity = message;
  if (/发烧|发热|咳|吐|晕|乏力/.test(lower)) state.facts.companions = message;

  let reply = '';
  let done = false;
  let result = null;

  if (state.facts.urgentHint && state.turn >= 1) {
    reply = '您描述的情况可能涉及急危重症。请立刻停止在线问诊，尽快前往急诊或拨打 120。\n\n我仍会给出导诊建议供参考。';
    done = true;
  } else if (state.turn === 1) {
    reply = '已收到。请问不适大概持续多久了？（例如：2 天、1 周）';
  } else if (state.turn === 2) {
    reply = '主要不适在哪个部位？有没有发热、咳嗽、恶心等伴随症状？';
  } else if (state.turn === 3) {
    reply = '严重程度您觉得是轻、中、还是重？日常活动是否明显受影响？';
  } else {
    reply = '感谢配合。下面是根据对话整理的导诊小结（仅供参考，不能替代面诊）。';
    done = true;
  }

  if (done) {
    const payload = {
      chief: (state.facts.chief || message).trim(),
      duration: state.facts.duration || '未明确',
      location: state.facts.location || '',
      severity: /重|不能忍|很痛/.test(state.facts.severity || '') ? '重'
        : /中/.test(state.facts.severity || '') ? '中' : (state.facts.urgentHint ? '重' : '轻'),
      companions: state.facts.companions ? [state.facts.companions] : []
    };
    result = mockTriageSymptom(payload);
    result.fromChat = true;
    result.chatSummary = [
      `主诉：${payload.chief}`,
      `时长：${payload.duration}`,
      `部位：${payload.location || '未注明'}`,
      `程度：${payload.severity}`,
      state.facts.companions ? `伴随：${state.facts.companions}` : null
    ].filter(Boolean).join('\n');
  }

  state.messages.push({ role: 'assistant', content: reply });
  return { sessionId, reply, done, result, turn: state.turn, source: 'mock' };
}

function mapAppointmentStatus(status) {
  const s = String(status || '');
  if (s === 'cancelled' || s.includes('取消')) return '已取消';
  if (s === 'pending' || s === 'confirmed' || s === '待就诊') return '待就诊';
  if (s.includes('完成') || s.includes('已就诊') || s === 'done' || s === 'completed') return '已完成';
  return s || '待就诊';
}

function normalizeAppointment(a) {
  if (!a) return a;
  const slotLabel = a.slotLabel
    || [a.date ? dateLabelFromIso(a.date) : '', a.time].filter(Boolean).join(' ')
    || '';
  return {
    ...a,
    departmentName: a.departmentName || a.department?.name || '',
    doctorName: a.doctorName || a.doctor?.name || '',
    hospitalName: a.hospitalName || '演示院区',
    slotLabel,
    status: mapAppointmentStatus(a.status),
    rawStatus: a.status,
    source: a.source || 'api'
  };
}

/* ---------- Public API wrappers ---------- */
async function triageSymptom(payload) {
  const body = {
    chief: payload.chief,
    duration: payload.duration || '',
    bodyPart: payload.location || payload.bodyPart || '',
    severity: payload.severity || null,
    extra: Array.isArray(payload.companions) && payload.companions.length
      ? payload.companions.join('、')
      : (payload.extra || null)
  };
  try {
    const data = await apiFetch('/api/triage/recommend', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    const norm = normalizeTriage(data, {
      chief: payload.chief,
      duration: payload.duration,
      location: payload.location || body.bodyPart,
      severity: payload.severity,
      companions: payload.companions || [],
      extra: body.extra
    });
    norm.guardrail = resolveGuardrail(data, [payload.chief, ...(payload.companions || [])].join(' '));
    return norm;
  } catch {
    const m = mockTriageSymptom(payload);
    m.guardrail = localGuardrailCheck([payload.chief, ...(payload.companions || [])].join(' '));
    return m;
  }
}

async function createConsultSession() {
  const data = await apiFetch('/api/consult/sessions', { method: 'POST' });
  return data;
}

/** consult 会话响应（非流式 JSON 或流式 final 事件）→ 聊天结果 */
function chatResultFromData(data, sessionId, message) {
  const replyText = (data.reply && data.reply.content) || (typeof data.reply === 'string' ? data.reply : '') || data.message || '';
  const done = data.status === 'completed' || !!data.triage;
  let result = null;
  if (data.triage) {
    result = normalizeTriage(data.triage, { chief: message });
    result.fromChat = true;
  }
  return {
    sessionId: data.id || sessionId,
    reply: replyText,
    done,
    result,
    status: data.status,
    disclaimer: data.disclaimer,
    source: data.source || 'api',
    guardrail: resolveGuardrail(data, message)
  };
}

/**
 * 流式问诊：POST …/messages?stream=true（SSE：token / final / done / error）
 * onToken(text, full) 逐段回调；final 携带完整会话 + guardrail。
 * 不支持流式（非 event-stream）时按 JSON 解析；出错抛异常由调用方回落非流式。
 */
async function consultStream(sessionId, message, onToken) {
  const ctrl = new AbortController();
  let timer = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}/api/consult/sessions/${encodeURIComponent(sessionId)}/messages?stream=true`, {
      method: 'POST',
      signal: ctrl.signal,
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      body: JSON.stringify({ content: message })
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const ct = res.headers.get('Content-Type') || '';
    if (!ct.includes('text/event-stream') || !res.body || !res.body.getReader) {
      if (ct.includes('application/json')) return chatResultFromData(await res.json(), sessionId, message);
      throw new Error('stream unsupported');
    }
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = '';
    let full = '';
    let finalData = null;
    const handle = (evt, raw) => {
      let d = null;
      try { d = raw ? JSON.parse(raw) : null; } catch (_) { d = raw; }
      if (evt === 'token') {
        const t = d && typeof d === 'object' ? (d.text || d.token || d.content || '') : String(d || '');
        if (t) { full += t; onToken && onToken(t, full); }
      } else if (evt === 'final') {
        finalData = d && typeof d === 'object' ? d : null;
      } else if (evt === 'error') {
        const msg = d && typeof d === 'object' ? (d.message || d.error || 'stream error') : String(d || 'stream error');
        throw new Error(msg);
      }
    };
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      clearTimeout(timer);
      timer = setTimeout(() => ctrl.abort(), AI_TIMEOUT_MS);
      buf += dec.decode(value, { stream: true }).replace(/\r\n/g, '\n');
      let idx;
      while ((idx = buf.indexOf('\n\n')) >= 0) {
        const block = buf.slice(0, idx);
        buf = buf.slice(idx + 2);
        let evt = 'message';
        const dataLines = [];
        block.split('\n').forEach((line) => {
          if (line.startsWith('event:')) evt = line.slice(6).trim();
          else if (line.startsWith('data:')) dataLines.push(line.slice(5).replace(/^ /, ''));
        });
        handle(evt, dataLines.join('\n'));
      }
    }
    if (!finalData) throw new Error('stream ended without final');
    const out = chatResultFromData(finalData, sessionId, message);
    if (!out.reply && full) out.reply = full;
    out.streamed = true;
    return out;
  } finally {
    clearTimeout(timer);
  }
}

async function triageChat(sessionId, message, onToken) {
  // Prefer real consult session messaging
  if (sessionId && !String(sessionId).startsWith('local-')) {
    if (onToken && typeof ReadableStream !== 'undefined') {
      try {
        return await consultStream(sessionId, message, onToken);
      } catch (e) {
        console.warn('[consult] stream failed, fallback to non-stream:', e && e.message);
        onToken && onToken(null, null); // 通知 UI 清空部分 token
      }
    }
    try {
      const data = await apiFetch(`/api/consult/sessions/${encodeURIComponent(sessionId)}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content: message })
      });
      return chatResultFromData(data, sessionId, message);
    } catch {
      /* fall through to mock */
    }
  }
  const sid = sessionId || ('local-' + Date.now());
  const mres = mockChat(sid, message);
  mres.guardrail = resolveGuardrail({}, message);
  return mres;
}

async function getDepartments() {
  try {
    const list = await apiFetch('/api/departments');
    return (list || []).map((d) => ({
      ...d,
      desc: d.intro || d.desc || ''
    }));
  } catch {
    return MOCK_DEPARTMENTS.map((d) => ({ ...d, desc: d.intro || d.desc }));
  }
}

async function getDoctors(deptId) {
  try {
    if (!deptId) throw new Error('no dept');
    const list = await apiFetch(`/api/departments/${encodeURIComponent(deptId)}/doctors`);
    return (list || []).map((d) => ({
      ...d,
      deptId: d.departmentId || d.deptId,
      rating: d.rating
    }));
  } catch {
    return MOCK_DOCTORS.filter((d) => !deptId || d.deptId === deptId || d.departmentId === deptId);
  }
}

async function getSlots(doctorId) {
  try {
    if (!doctorId) throw new Error('no doctor');
    const dates = [1, 2, 3].map(isoDatePlus);
    const batches = await Promise.all(
      dates.map((date) =>
        apiFetch(`/api/doctors/${encodeURIComponent(doctorId)}/slots?date=${encodeURIComponent(date)}`)
          .catch(() => [])
      )
    );
    const slots = batches.flat().map((s) => ({
      ...s,
      dateLabel: dateLabelFromIso(s.date),
      available: s.available !== false && s.remaining !== 0
    }));
    if (!slots.length) throw new Error('empty slots');
    return slots;
  } catch {
    return mockSlots(doctorId);
  }
}

function loadAppointments() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
  } catch {
    return [];
  }
}

function saveAppointments(list) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(list));
}

async function createAppointment(payload) {
  const apiBody = {
    departmentId: payload.departmentId,
    doctorId: payload.doctorId,
    slotId: payload.slotId,
    patientName: payload.patientName || getActivePatient()?.name || '演示患者',
    patientId: payload.patientId || getActivePatientId() || null,
    phone: payload.phone || null,
    chief: payload.chief || null,
    triageSessionId: payload.triageSessionId || null
  };
  try {
    const data = await apiFetch('/api/appointments', {
      method: 'POST',
      body: JSON.stringify(apiBody)
    });
    const item = normalizeAppointment({
      ...data,
      hospitalName: payload.hospitalName || '演示院区',
      departmentName: data.departmentName || payload.departmentName,
      doctorName: data.doctorName || payload.doctorName,
      slotLabel: payload.slotLabel || [data.date ? dateLabelFromIso(data.date) : '', data.time].filter(Boolean).join(' '),
      source: 'api'
    });
    const list = loadAppointments();
    list.unshift(item);
    saveAppointments(list);
    return item;
  } catch {
    const item = normalizeAppointment({
      id: 'apt-' + Date.now(),
      ...payload,
      patientName: apiBody.patientName,
      status: '待就诊',
      createdAt: new Date().toISOString(),
      source: 'mock'
    });
    const list = loadAppointments();
    list.unshift(item);
    saveAppointments(list);
    return item;
  }
}

async function fetchAppointments() {
  try {
    const data = await apiFetch('/api/appointments');
    if (Array.isArray(data)) {
      const remote = data.map((a) => normalizeAppointment({ ...a, source: a.source || 'api' }));
      const local = loadAppointments();
      const map = new Map();
      [...remote, ...local].forEach((a) => {
        const prev = map.get(a.id);
        if (!prev || isApiSource(a.source)) map.set(a.id, a);
      });
      const merged = [...map.values()].sort((a, b) => String(b.createdAt || '').localeCompare(String(a.createdAt || '')));
      saveAppointments(merged);
      return merged;
    }
  } catch { /* mock */ }
  const local = loadAppointments();
  if (!local.length) {
    const seed = [
      normalizeAppointment({
        id: 'demo-1',
        hospitalName: '演示院区',
        departmentName: '呼吸内科',
        doctorName: '王晓明',
        slotLabel: `${todayPlus(2)} 09:00`,
        status: '待就诊',
        createdAt: new Date(Date.now() - 86400000).toISOString(),
        source: 'seed'
      })
    ];
    saveAppointments(seed);
    return seed;
  }
  return local.map(normalizeAppointment);
}

async function cancelAppointment(id) {
  try {
    await apiFetch(`/api/appointments/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify({ status: 'cancelled' })
    });
  } catch { /* local mirror still updated */ }
  const list = loadAppointments().map((a) =>
    a.id === id ? { ...a, status: '已取消', rawStatus: 'cancelled' } : a
  );
  saveAppointments(list);
  return list;
}


/* ---------- M1: Patients / Profile / Preconsult / Reports ---------- */
function loadLocalPatients() {
  try {
    const list = JSON.parse(localStorage.getItem(PATIENTS_KEY) || 'null');
    if (Array.isArray(list) && list.length) return list;
  } catch { /* ignore */ }
  localStorage.setItem(PATIENTS_KEY, JSON.stringify(SEED_PATIENTS));
  return SEED_PATIENTS.map((p) => ({ ...p }));
}

function saveLocalPatients(list) {
  localStorage.setItem(PATIENTS_KEY, JSON.stringify(list));
}

function getActivePatientId() {
  let id = localStorage.getItem(ACTIVE_PATIENT_KEY);
  const list = loadLocalPatients();
  if (!id || !list.some((p) => p.id === id)) {
    id = list[0]?.id || 'p-self';
    localStorage.setItem(ACTIVE_PATIENT_KEY, id);
  }
  return id;
}

function setActivePatientId(id) {
  localStorage.setItem(ACTIVE_PATIENT_KEY, id);
}

function getActivePatient() {
  const id = getActivePatientId();
  return loadLocalPatients().find((p) => p.id === id) || SEED_PATIENTS[0];
}

function loadLocalProfiles() {
  try {
    const obj = JSON.parse(localStorage.getItem(PROFILES_KEY) || 'null');
    if (obj && typeof obj === 'object') return obj;
  } catch { /* ignore */ }
  localStorage.setItem(PROFILES_KEY, JSON.stringify(SEED_PROFILES));
  return { ...SEED_PROFILES };
}

function saveLocalProfiles(obj) {
  localStorage.setItem(PROFILES_KEY, JSON.stringify(obj));
}

function emptyProfile() {
  return { allergies: [], chronicDiseases: [], medications: [], updatedAt: new Date().toISOString() };
}

async function fetchPatients() {
  try {
    const data = await apiFetch('/api/patients');
    if (Array.isArray(data) && data.length) {
      const list = data.filter((p) => !p.deleted).map((p) => normalizePatient(p, 'api'));
      saveLocalPatients(list);
      return list;
    }
  } catch { /* mock */ }
  return loadLocalPatients().map((p) => ({ ...p, source: p.source || 'mock' }));
}

async function createPatient(payload) {
  const body = {
    name: payload.name,
    relation: relationToApi(payload.relation),
    gender: payload.gender || '未知',
    age: payload.age != null && payload.age !== '' ? Number(payload.age) : 0
  };
  try {
    const data = await apiFetch('/api/patients', { method: 'POST', body: JSON.stringify(body) });
    const item = normalizePatient({ ...data, phone: payload.phone || data.phone || '' }, 'api');
    // keep UI relation preference if API stores self/父/母
    if (payload.relation) item.relation = payload.relation;
    const list = loadLocalPatients();
    list.push(item);
    saveLocalPatients(list);
    return item;
  } catch {
    const item = {
      id: 'p-' + Date.now(),
      name: payload.name,
      relation: payload.relation,
      gender: payload.gender || '',
      age: payload.age != null && payload.age !== '' ? Number(payload.age) : null,
      phone: payload.phone || '',
      source: 'mock'
    };
    const list = loadLocalPatients();
    list.push(item);
    saveLocalPatients(list);
    return item;
  }
}

async function updatePatient(id, payload) {
  const body = {
    name: payload.name,
    relation: relationToApi(payload.relation),
    gender: payload.gender || null,
    age: payload.age != null && payload.age !== '' ? Number(payload.age) : null
  };
  try {
    const data = await apiFetch(`/api/patients/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body)
    });
    const item = normalizePatient({ ...data, id, phone: payload.phone || data.phone || '' }, 'api');
    if (payload.relation) item.relation = payload.relation;
    const list = loadLocalPatients().map((p) => (p.id === id ? item : p));
    saveLocalPatients(list);
    return item;
  } catch {
    const item = {
      id,
      name: payload.name,
      relation: payload.relation,
      gender: payload.gender || '',
      age: payload.age != null && payload.age !== '' ? Number(payload.age) : null,
      phone: payload.phone || '',
      source: 'mock'
    };
    const list = loadLocalPatients().map((p) => (p.id === id ? item : p));
    saveLocalPatients(list);
    return item;
  }
}

async function fetchPatientProfile(patientId) {
  try {
    const data = await apiFetch(`/api/patients/${encodeURIComponent(patientId)}/profile`);
    if (data && typeof data === 'object') {
      const profile = {
        allergies: Array.isArray(data.allergies) ? data.allergies : [],
        chronicDiseases: Array.isArray(data.chronicDiseases) ? data.chronicDiseases : [],
        medications: Array.isArray(data.medications) ? data.medications : [],
        updatedAt: data.updatedAt || new Date().toISOString(),
        source: 'api'
      };
      const all = loadLocalProfiles();
      all[patientId] = profile;
      saveLocalProfiles(all);
      return profile;
    }
  } catch { /* mock */ }
  const all = loadLocalProfiles();
  return { ...(all[patientId] || emptyProfile()), source: 'mock' };
}

async function savePatientProfile(patientId, profile) {
  const body = {
    allergies: profile.allergies || [],
    chronicDiseases: profile.chronicDiseases || [],
    medications: profile.medications || []
  };
  try {
    const data = await apiFetch(`/api/patients/${encodeURIComponent(patientId)}/profile`, {
      method: 'PUT',
      body: JSON.stringify(body)
    });
    const saved = {
      allergies: Array.isArray(data.allergies) ? data.allergies : body.allergies,
      chronicDiseases: Array.isArray(data.chronicDiseases) ? data.chronicDiseases : body.chronicDiseases,
      medications: Array.isArray(data.medications) ? data.medications : body.medications,
      updatedAt: data.updatedAt || new Date().toISOString(),
      source: 'api'
    };
    const all = loadLocalProfiles();
    all[patientId] = saved;
    saveLocalProfiles(all);
    return saved;
  } catch {
    const saved = { ...body, updatedAt: new Date().toISOString(), source: 'mock' };
    const all = loadLocalProfiles();
    all[patientId] = saved;
    saveLocalProfiles(all);
    return saved;
  }
}

function loadPreconsultReports() {
  try {
    return JSON.parse(localStorage.getItem(PRECONSULT_KEY) || '[]');
  } catch {
    return [];
  }
}

function savePreconsultReports(list) {
  localStorage.setItem(PRECONSULT_KEY, JSON.stringify(list));
}

function buildClientPreconsultReport(result, patient, sessionId) {
  const summary = result?.summary || {};
  const depts = result?.departments || [];
  const companions = Array.isArray(summary.companions)
    ? summary.companions.join('、')
    : (summary.companions || '');
  const hpiParts = [
    summary.chief || (result?.chatSummary ? String(result.chatSummary).split('\n')[0] : '') || '（未记录主诉）',
    summary.duration ? `病程：${summary.duration}` : '',
    summary.location ? `部位：${summary.location}` : '',
    summary.severity ? `程度：${summary.severity}` : '',
    companions ? `伴随：${companions}` : '',
    summary.narrative || ''
  ].filter(Boolean);
  const urgency = result?.urgent || result?.urgency === 'emergency' || result?.urgency === 'urgent'
    ? '建议急诊'
    : (result?.level || '门诊');
  const nextSteps = Array.isArray(result?.nextSteps) && result.nextSteps.length
    ? result.nextSteps
    : (result?.advice ? [result.advice] : ['建议按推荐科室预约面诊', '携带既往病历与用药清单']);
  return {
    id: 'pc-' + Date.now(),
    sessionId: sessionId || null,
    createdAt: new Date().toISOString(),
    patient: patient ? {
      id: patient.id,
      name: patient.name,
      relation: patient.relation,
      gender: patient.gender,
      age: patient.age,
      phone: patient.phone
    } : null,
    chief: summary.chief || '',
    hpi: hpiParts.join('\n'),
    chatSummary: result?.chatSummary || '',
    departments: depts,
    urgency,
    urgent: !!(result?.urgent || result?.urgency === 'emergency' || result?.urgency === 'urgent'),
    nextSteps,
    advice: result?.advice || '',
    disclaimer: '仅供参考，不能替代面诊',
    source: result?.source === 'api' ? 'client+api-triage' : 'mock'
  };
}

async function generatePreconsultReport(result, sessionId) {
  const patient = getActivePatient();
  // Prefer session preconsult-report; fall back to /api/previsit/report; then client compose
  if (sessionId && !String(sessionId).startsWith('local-')) {
    try {
      const data = await apiFetch(`/api/consult/sessions/${encodeURIComponent(sessionId)}/preconsult-report`, {
        method: 'POST',
        body: JSON.stringify({ patientId: patient?.id || null })
      });
      const report = normalizePreconsultApi(data, result, patient, sessionId);
      // enrich HPI from triage if API summary thin
      if (!report.hpi || report.hpi.length < 8) {
        const built = buildClientPreconsultReport(result, patient, sessionId);
        report.hpi = built.hpi;
        if (!report.chief) report.chief = built.chief;
        if (!report.departments?.length) report.departments = built.departments;
        if (!report.nextSteps?.length) report.nextSteps = built.nextSteps;
      }
      const list = loadPreconsultReports();
      list.unshift(report);
      savePreconsultReports(list.slice(0, 20));
      return report;
    } catch { /* try previsit */ }
    try {
      const summary = result?.summary || {};
      let allergies = [];
      try {
        const prof = await fetchPatientProfile(patient.id);
        allergies = prof.allergies || [];
      } catch { /* ignore */ }
      const data = await apiFetch('/api/previsit/report', {
        method: 'POST',
        body: JSON.stringify({
          sessionId,
          patientId: patient?.id || null,
          chiefComplaint: summary.chief || result?.chatSummary || '',
          duration: summary.duration || '',
          bodyPart: summary.location || '',
          accompanying: Array.isArray(summary.companions) ? summary.companions : [],
          allergies
        })
      });
      const report = normalizePreconsultApi(data, result, patient, sessionId);
      const list = loadPreconsultReports();
      list.unshift(report);
      savePreconsultReports(list.slice(0, 20));
      return report;
    } catch { /* client */ }
  }
  const report = buildClientPreconsultReport(result, patient, sessionId);
  const list = loadPreconsultReports();
  list.unshift(report);
  savePreconsultReports(list.slice(0, 20));
  return report;
}

async function fetchLabReports() {
  try {
    const data = await apiFetch('/api/reports');
    if (Array.isArray(data) && data.length) {
      const list = data.map((r) => normalizeLabReport(r, 'api'));
      localStorage.setItem(REPORTS_CACHE_KEY, JSON.stringify(list));
      return list;
    }
  } catch { /* mock */ }
  try {
    const cached = JSON.parse(localStorage.getItem(REPORTS_CACHE_KEY) || 'null');
    if (Array.isArray(cached) && cached.length) return cached.map((r) => normalizeLabReport(r, r.source || 'mock'));
  } catch { /* ignore */ }
  return MOCK_LAB_REPORTS.map((r) => normalizeLabReport(r, 'mock'));
}

async function fetchReportDetail(id) {
  try {
    const data = await apiFetch(`/api/reports/${encodeURIComponent(id)}`);
    if (data && data.id) return normalizeLabReport(data, 'api');
  } catch { /* mock */ }
  const list = await fetchLabReports();
  return list.find((r) => r.id === id) || null;
}

function mockInterpret(report) {
  const flags = (report.items || []).filter((i) => i.flag);
  const lines = [];
  if (report.type === 'imaging') {
    lines.push(report.impression || report.summary || '影像所见大致正常（演示解读）。');
    lines.push('建议结合临床症状由影像科/临床医师综合判断。');
  } else if (flags.length) {
    lines.push(`发现 ${flags.length} 项指标偏离参考范围：` + flags.map((f) => f.name).join('、') + '。');
    lines.push('轻度异常常见于感染、炎症或一过性波动，需结合症状与复查。');
  } else {
    lines.push(report.summary || '主要指标大致在参考范围内（演示解读）。');
  }
  lines.push('本解读不能替代执业医师面诊与正式报告说明。');
  return {
    summary: lines[0],
    points: lines.slice(1),
    risk: flags.length ? '关注' : '低',
    disclaimer: '仅供参考，不能替代面诊',
    source: 'mock'
  };
}

async function interpretReport(id, report) {
  try {
    const data = await apiFetch('/api/reports/interpret', {
      method: 'POST',
      body: JSON.stringify({
        reportId: id,
        reportType: report?.type === 'imaging' ? 'imaging' : 'lab',
        text: ''
      })
    });
    const abn = Array.isArray(data.abnormalities)
      ? data.abnormalities.map((a) => `${a.item || ''}：${a.finding || ''}`.trim()).filter(Boolean)
      : [];
    const advice = Array.isArray(data.advice) ? data.advice : (data.advice ? [data.advice] : []);
    const points = [...abn, ...advice, ...(Array.isArray(data.points) ? data.points : [])];
    return {
      summary: data.summary || data.interpretation || '',
      points,
      risk: data.risk || '',
      disclaimer: data.disclaimer || '仅供参考，不能替代面诊',
      source: data.source === 'llm' || data.source === 'api' ? 'api' : (data.source || 'api'),
      guardrail: extractGuardrail(data)
    };
  } catch {
    return mockInterpret(report || { id });
  }
}

function formatPreconsultText(report) {
  const p = report.patient || {};
  const depts = (report.departments || []).map((d, i) => `${i + 1}. ${d.name}${d.reason ? '（' + d.reason + '）' : ''}`).join('\n');
  const steps = (report.nextSteps || []).map((s, i) => `${i + 1}. ${s}`).join('\n');
  return [
    '【预问诊报告】',
    `就诊人：${p.name || '—'}（${p.relation || ''}）${p.gender ? ' · ' + p.gender : ''}${p.age != null ? ' · ' + p.age + '岁' : ''}`,
    `生成时间：${report.createdAt ? new Date(report.createdAt).toLocaleString('zh-CN') : '—'}`,
    '',
    '一、主诉与现病史',
    report.hpi || report.chief || report.chatSummary || '—',
    '',
    '二、紧急程度',
    report.urgency || '—',
    '',
    '三、建议科室',
    depts || '—',
    '',
    '四、下一步建议',
    steps || report.advice || '—',
    '',
    '免责声明：仅供参考，不能替代面诊。急危重症请立即急诊或拨打 120。'
  ].join('\n');
}


/* ---------- UI state ---------- */
const state = {
  view: 'home',
  history: [],
  lastResult: null,
  lastPreconsult: null,
  preferredDept: null,
  chatSessionId: null,
  chatStarted: false,
  chatUsingApi: false,
  chatTurn: 0,
  chatDone: false,
  chatUrgent: false,
  editingPatientId: null,
  reportsTab: 'lab',
  currentReportId: null,
  currentInterpret: null,
  profileDraft: null,
  appoint: {
    step: 1,
    department: null,
    doctor: null,
    slot: null
  },
  waitingAppointmentId: null,
  waitingStatus: null,
  waitingTimer: null,
  messagesCache: null,
  messagesUnreadApi: null,
  messagesUsingApi: false,
  messagesFilterServer: null,
  _msgFilterProbed: false,
  msgFilter: 'all',
  currentMessageId: null,
  navQuery: '',
  navDepts: null,
  currentNavDeptId: null,
  refillTab: 'list',
  medsTab: 'today',
  followupTab: 'surveys',
  chronicTab: 'bp',
  currentSurveyId: null,
  refillFormDraft: null,
  billsFilter: 'unpaid',
  currentBillId: null,
  lastPayReceipt: null,
  dcMode: 'text',
  dcSessionId: null,
  dcSession: null,
  dcListFilter: 'active',
  dcQueueTimer: null,
  dcPollTimer: null,
  dcVideoLocal: null,
  dcUsingApi: false,
  examCat: 'all',
  examMineFilter: 'booked',
  examItem: null,
  examBook: {
    step: 1,
    date: null,
    slot: null,
    mode: 'book', // book | reschedule
    bookingId: null
  },
  examLastBooking: null,
  examCurrentId: null,
  examUsingApi: false,
  pharmOrderFilter: 'deliverable',
  pharmDelivFilter: 'active',
  pharmOrderId: null,
  pharmOrder: null,
  pharmAddressId: null,
  pharmDeliveryId: null,
  pharmUsingApi: false,
  pharmAddrFormMode: 'add'
};

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.classList.remove('hidden');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add('hidden'), 2200);
}

function setLoading(on, text) {
  const mask = $('#loadingMask');
  mask.classList.toggle('hidden', !on);
  const p = mask.querySelector('p');
  if (p && text) p.textContent = text;
  else if (p && on) p.textContent = '正在分析…';
}

function setNavActive(view) {
  const map = {
    home: 'home', symptom: 'home', result: 'home', appoint: 'home',
    waiting: 'home', nav: 'home', 'nav-detail': 'home',
    patients: 'mine', 'patient-form': 'mine', profile: 'mine', chronic: 'mine',
    refills: 'mine', meds: 'mine', followups: 'mine', 'followup-form': 'mine',
    bills: 'mine', 'bill-pay': 'mine', identity: 'mine', settings: 'mine',
    pharmacy: 'mine', 'pharmacy-address': 'mine', 'pharmacy-address-form': 'mine',
    'pharmacy-deliveries': 'mine', 'pharmacy-delivery': 'mine',
    exam: 'home', 'exam-book': 'home', 'exam-success': 'home', 'exam-mine': 'home', 'exam-detail': 'home',
    chat: 'consult', consult: 'consult',
    'dc-start': 'consult', 'dc-queue': 'consult', 'dc-session': 'consult',
    'dc-summary': 'consult', 'dc-list': 'consult',
    reports: 'reports', 'report-detail': 'reports', preconsult: 'reports',
    messages: 'messages', 'message-detail': 'messages',
    mine: 'mine'
  };
  const key = map[view] || 'home';
  $$('.nav-item').forEach((b) => b.classList.toggle('active', b.dataset.nav === key));
}

function showView(view, { push = true } = {}) {
  if (push && state.view !== view) {
    state.history.push(state.view);
  }
  if (state.view === 'waiting' && view !== 'waiting') stopWaitingTicker();
  if ((state.view === 'dc-queue' || state.view === 'dc-session') && view !== 'dc-queue' && view !== 'dc-session') {
    stopDcTimers();
  }
  state.view = view;
  $$('.view').forEach((v) => v.classList.toggle('active', v.id === `view-${view}`));
  const sec = $(`#view-${view}`);
  $('#pageTitle').textContent = sec?.dataset.title || '导诊台';
  $('#pageSubtitle').textContent = sec?.dataset.sub || '';
  const showBack = view !== 'home';
  $('#btnBack').classList.toggle('hidden', !showBack);
  setNavActive(view);

  if (view === 'home') refreshHomePatient();
  if (view === 'chat') {
    if (!state.chatStarted) startChat();
  }
  if (view === 'appoint') renderAppoint();
  if (view === 'mine') renderMine();
  if (view === 'result' && state.lastResult) renderResult(state.lastResult);
  if (view === 'patients') renderPatients();
  if (view === 'patient-form') renderPatientForm();
  if (view === 'profile') renderProfile();
  if (view === 'chronic') renderChronic();
  if (view === 'preconsult') renderPreconsult(state.lastPreconsult);
  if (view === 'reports') renderReports();
  if (view === 'report-detail') renderReportDetail(state.currentReportId);
  if (view === 'waiting') renderWaiting(state.waitingAppointmentId);
  if (view === 'messages') renderMessages();
  if (view === 'message-detail') renderMessageDetail(state.currentMessageId);
  if (view === 'nav') renderNav();
  if (view === 'nav-detail') renderNavDetail(state.currentNavDeptId);
  if (view === 'refills') renderRefills();
  if (view === 'meds') renderMeds();
  if (view === 'followups') renderFollowups();
  if (view === 'followup-form') renderFollowupForm(state.currentSurveyId);
  if (view === 'bills') renderBills();
  if (view === 'bill-pay') renderBillPay(state.currentBillId);
  if (view === 'identity') renderIdentity();
  if (view === 'settings') renderSettings();
  if (view === 'consult') renderConsultHub();
  if (view === 'dc-start') renderDcStart();
  if (view === 'dc-queue') renderDcQueue();
  if (view === 'dc-session') renderDcSession();
  if (view === 'dc-summary') renderDcSummary();
  if (view === 'dc-list') renderDcList();
  if (view === 'exam') renderExamItems();
  if (view === 'exam-book') renderExamBook();
  if (view === 'exam-success') renderExamSuccess();
  if (view === 'exam-mine') renderExamMine();
  if (view === 'exam-detail') renderExamDetail();
  if (view === 'pharmacy') renderPharmacyOrders();
  if (view === 'pharmacy-address') renderPharmacyAddress();
  if (view === 'pharmacy-address-form') renderPharmacyAddressForm();
  if (view === 'pharmacy-deliveries') renderPharmacyDeliveries();
  if (view === 'pharmacy-delivery') renderPharmacyDelivery();
  if (typeof markDemoStepByView === 'function') markDemoStepByView(view);
}

function goBack() {
  const prev = state.history.pop() || 'home';
  showView(prev, { push: false });
}

/* ---------- Symptom ---------- */
function fillForm({ chief, duration, location, severity, companions }) {
  $('#chief').value = chief || '';
  $('#duration').value = duration || '';
  $('#location').value = location || '';
  $$(`input[name="severity"]`).forEach((r) => { r.checked = r.value === severity; });
  $$(`input[name="companions"]`).forEach((c) => {
    c.checked = (companions || []).includes(c.value);
  });
}

async function onSymptomSubmit(e) {
  e.preventDefault();
  const companions = $$('input[name="companions"]:checked').map((c) => c.value);
  const payload = {
    chief: $('#chief').value.trim(),
    duration: $('#duration').value,
    location: $('#location').value,
    severity: ($('input[name="severity"]:checked') || {}).value,
    companions
  };
  if (!payload.chief || !payload.duration || !payload.severity) {
    toast('请完整填写必填项');
    return;
  }
  setLoading(true, 'AI 思考中…（约 10 秒）');
  try {
    if (state.triageGuardLocked) { toast('当前问诊已暂停，请优先就医'); return; }
    const result = await triageSymptom(payload);
    state.lastResult = result;
    if (result.departments?.[0]) state.preferredDept = result.departments[0].name;
    showView('result');
    if (result.guardrail?.action === 'redflag') {
      showGuardrailRedflag(result.guardrail, result.nextSteps);
      lockSymptomFormByGuardrail(true);
    }
  } finally {
    setLoading(false);
  }
}

/* ---------- Chat ---------- */
const CHAT_TOTAL_STEPS = 4;

function formatMsgTime(d = new Date()) {
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  return `${h}:${m}`;
}

function updateChatProgress(turn, done) {
  const t = Math.max(0, Number(turn) || 0);
  const step = done ? CHAT_TOTAL_STEPS : Math.min(CHAT_TOTAL_STEPS, Math.max(1, t + 1));
  // turn 0 → 0%; turn 1 → 25%; … turn 4+/done → 100%
  let pct = done ? 100 : Math.min(95, Math.round((t / CHAT_TOTAL_STEPS) * 100));
  if (t === 0) pct = 0;
  const fill = $('#chatProgressFill');
  const bar = $('#chatProgressBar');
  const pctEl = $('#chatProgressPct');
  const label = $('#chatProgressLabel');
  if (fill) fill.style.width = pct + '%';
  if (bar) bar.setAttribute('aria-valuenow', String(pct));
  if (pctEl) pctEl.textContent = pct + '%';
  if (label) label.textContent = done ? '问诊已完成' : '问诊进度';
  $$('#chatSteps .chat-step').forEach((el) => {
    const sn = Number(el.dataset.step);
    el.classList.toggle('active', !done && sn === step);
    el.classList.toggle('done', done ? sn <= CHAT_TOTAL_STEPS : sn < step);
  });
}

function showChatUrgent(on) {
  state.chatUrgent = !!on;
  const el = $('#chatUrgent');
  if (el) el.classList.toggle('hidden', !on);
}

function detectUrgentFromText(text) {
  return isUrgentText(text);
}

function appendMsg(role, text, extra = '') {
  const box = $('#chatMessages');
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  const body = document.createElement('div');
  body.className = 'msg-body';
  body.textContent = text;
  div.appendChild(body);
  if (role === 'bot' && extra) extra = String(extra).replace(/^仅供参考，不能替代面诊\s*·\s*/, '');
  if (extra) {
    const tag = document.createElement('span');
    tag.className = 'ref-tag';
    tag.textContent = extra;
    div.appendChild(tag);
  }
  if (role === 'bot' && !hasAiDisclaimer(text)) {
    const disc = document.createElement('p');
    disc.className = 'ai-disclaimer';
    disc.setAttribute('role', 'note');
    disc.textContent = AI_DISCLAIMER;
    div.appendChild(disc);
  }
  const time = document.createElement('span');
  time.className = 'msg-time';
  time.textContent = formatMsgTime();
  div.appendChild(time);
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
  return div;
}

function renderChatSummary(result) {
  const card = $('#chatSummary');
  if (!card || !result) return;
  const allowCaution = isAllowCaution(result.guardrail);
  const urgent = !allowCaution && (!!result.urgent || result.level === '建议急诊'
    || result.urgency === 'emergency' || result.urgency === 'urgent');
  const depts = result.departments || [];
  if (depts[0]) state.preferredDept = depts[0].name;
  showChatUrgent(urgent);

  let levelBadge = '<span class="badge ok">建议门诊</span>';
  if (urgent) levelBadge = '<span class="badge er">建议急诊</span>';
  else if (String(result.level || '').includes('线上')) levelBadge = '<span class="badge online">可线上问诊</span>';

  card.classList.remove('hidden');
  card.innerHTML = `
    <h3><span>导诊小结</span>${levelBadge}</h3>
    <div class="sum-depts">
      ${depts.map((d) => `<span class="sum-dept-pill">${escapeHtml(d.name)}</span>`).join('') || '<span class="sum-advice">暂无科室建议</span>'}
    </div>
    ${result.advice ? `<p class="sum-advice">${escapeHtml(result.advice)}</p>` : ''}
    <div class="sum-actions">
      ${urgent ? `<a class="btn danger sm" href="tel:120">拨打 120</a>` : ''}
      <button type="button" class="btn primary" id="btnChatPreconsult">预问诊报告</button>
      <button type="button" class="btn primary" id="btnChatGoAppoint">去预约</button>
      <button type="button" class="btn ghost sm" id="btnChatViewResult">查看完整结果</button>
    </div>
    ${result.guardrail?.action === 'refuse' ? refuseNoticeHtml(result.guardrail) : ''}
    ${cautionNoticeHtml(result.guardrail)}
    <p class="sum-note">仅供参考，不能替代面诊 · ${sourceLabel(result.source)}</p>
    ${aiDisclaimerHtml(result.disclaimer, true)}
  `;
  $('#btnChatPreconsult')?.addEventListener('click', () => openPreconsultFromResult(result));
  $('#btnChatGoAppoint')?.addEventListener('click', () => {
    state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
    if (depts[0]) state.preferredDept = depts[0].name;
    showView('appoint');
  });
  $('#btnChatViewResult')?.addEventListener('click', () => showView('result'));
  // scroll summary into view inside messages area if needed
  card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

async function startChat() {
  state.chatStarted = true;
  state.chatUsingApi = false;
  state.chatSessionId = null;
  state.chatTurn = 0;
  state.chatDone = false;
  state.chatUrgent = false;
  $('#chatMessages').innerHTML = '';
  $('#chatSummary')?.classList.add('hidden');
  if ($('#chatSummary')) $('#chatSummary').innerHTML = '';
  showChatUrgent(false);
  updateChatProgress(0, false);
  setLoading(true, '正在连接问诊…');
  try {
    const sess = await createConsultSession();
    state.chatSessionId = sess.id;
    state.chatUsingApi = true;
    const welcome = (sess.messages && sess.messages[0] && sess.messages[0].content)
      || '你好，我是导诊助手。请用一两句话描述目前最不舒服的地方。\n若出现胸痛、大出血、意识不清、严重呼吸困难，请立即急诊或拨打 120。';
    appendMsg('bot', welcome, '仅供参考，不能替代面诊 · 服务端');
  } catch {
    state.chatSessionId = 'local-' + Date.now();
    state.chatUsingApi = false;
    appendMsg(
      'bot',
      '你好，我是导诊助手。请用一两句话描述目前最不舒服的地方。\n若出现胸痛、大出血、意识不清、严重呼吸困难，请立即急诊或拨打 120。',
      '仅供参考，不能替代面诊 · 本地 Mock'
    );
  } finally {
    setLoading(false);
  }
}

async function sendChat() {
  const input = $('#chatInput');
  const text = input.value.trim();
  if (!text || state.chatDone || state.chatGuardLocked || state.chatSending) return;
  input.value = '';
  appendMsg('user', text);

  if (detectUrgentFromText(text)) {
    showChatUrgent(true);
  }

  state.chatTurn += 1;
  updateChatProgress(state.chatTurn, false);

  // 不用全屏遮罩：气泡内「AI 思考中…」+ 流式逐字；发送中禁用按钮防重复提交
  state.chatSending = true;
  const sendBtnEl = $('#btnSendChat');
  if (sendBtnEl) { sendBtnEl.disabled = true; sendBtnEl.dataset.label = sendBtnEl.dataset.label || sendBtnEl.textContent; sendBtnEl.textContent = '思考中…'; }
  const pending = appendMsg('bot', 'AI 思考中…');
  pending.classList.add('msg-pending');
  pending.querySelector('.ai-disclaimer')?.remove();
  const pendingBody = pending.querySelector('.msg-body');
  const onToken = (t, full) => {
    if (t === null) { pendingBody.textContent = 'AI 思考中…'; pending.classList.remove('msg-streaming'); return; }
    pending.classList.add('msg-streaming');
    pendingBody.textContent = full;
    const box = $('#chatMessages');
    if (box) box.scrollTop = box.scrollHeight;
  };
  try {
    const res = await triageChat(state.chatSessionId, text, onToken);
    pending.remove();
    state.chatSessionId = res.sessionId || state.chatSessionId;
    if (typeof res.turn === 'number') state.chatTurn = res.turn;
    const src = sourceLabel(res.source) + (res.streamed ? ' · 流式' : '');
    const reply = res.reply || res.message || '…';
    appendMsg('bot', reply, `仅供参考，不能替代面诊 · ${src}`);
    if (res.guardrail && res.guardrail.caution) appendCautionNotice(res.guardrail);
    if (res.guardrail && res.guardrail.action !== 'allow') {
      applyChatGuardrail(res.guardrail);
      if (res.guardrail.action === 'redflag') {
        updateChatProgress(state.chatTurn, false);
        return;
      }
    }

    // v16：真实 LLM 回复常带「如有…请立即急诊/拨打120」安全话术，不再按关键词扫描后端回复（以 guardrail 为准）；仅本地 Mock 仍扫描
    const replyIsMock = !res.source || /mock/.test(String(res.source));
    if ((replyIsMock && detectUrgentFromText(reply)) || (res.result && (res.result.urgent || res.result.urgency === 'emergency' || res.result.urgency === 'urgent'))) {
      showChatUrgent(true);
    }

    if (res.done && res.result) {
      state.chatDone = true;
      state.lastResult = res.result;
      if (res.result.departments?.[0]) state.preferredDept = res.result.departments[0].name;
      updateChatProgress(CHAT_TOTAL_STEPS, true);
      renderChatSummary(res.result);
      // disable input softly
      input.placeholder = '问诊已完成，可去预约或查看结果';
      input.disabled = true;
      const sendBtn = $('#btnSendChat');
      if (sendBtn) sendBtn.disabled = true;
    } else {
      updateChatProgress(state.chatTurn, false);
    }
  } finally {
    if (pending.isConnected) pending.remove();
    state.chatSending = false;
    if (sendBtnEl) {
      sendBtnEl.textContent = sendBtnEl.dataset.label || '发送';
      if (!state.chatGuardLocked && !state.chatDone) sendBtnEl.disabled = false;
    }
  }
}

function resetChatSession() {
  state.chatStarted = false;
  state.chatDone = false;
  state.chatTurn = 0;
  state.chatUrgent = false;
  const input = $('#chatInput');
  if (input) {
    input.disabled = false;
    input.placeholder = '描述你的不适…';
  }
  const sendBtn = $('#btnSendChat');
  if (sendBtn) sendBtn.disabled = false;
  showChatUrgent(false);
  if (typeof unlockChatGuard === 'function') unlockChatGuard();
  $('#chatSummary')?.classList.add('hidden');
}

/* ---------- Result ---------- */
/** nextSteps 数组渲染为列表；无数组时回落 advice 单行 */
function nextStepsHtml(result) {
  let steps = Array.isArray(result.nextSteps) ? result.nextSteps.filter(Boolean) : [];
  // refuse 时后端 nextSteps 仅是 advice 原文（与护栏提示完全相同）→ 不重复列出
  const g = result.guardrail;
  if (g && g.action === 'refuse' && g.advice) steps = steps.filter((x) => String(x).trim() !== g.advice.trim());
  if (steps.length) {
    return `<div class="next-steps"><strong>下一步</strong><ol>${steps.map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ol></div>`;
  }
  if (g && g.action === 'refuse') return '';
  return result.advice ? `<p class="ref-note">下一步：${escapeHtml(result.advice)}</p>` : '';
}

function renderResult(result) {
  const el = $('#resultContent');
  const allowCaution = isAllowCaution(result.guardrail);
  // allow+caution：urgency 即使是 urgent/emergency 也只出琥珀提示，不抬急诊横幅 / 急诊徽章
  const urgent = !allowCaution && (!!result.urgent || result.level === '建议急诊' || result.urgency === 'emergency' || result.urgency === 'urgent');
  const depts = result.departments || [];
  const summary = result.summary || {};
  const companions = Array.isArray(summary.companions)
    ? summary.companions.join('、')
    : (summary.companions || '无');

  let levelBadge = '<span class="badge ok">建议门诊</span>';
  if (urgent) levelBadge = '<span class="badge er">建议急诊</span>';
  else if (allowCaution) levelBadge = '<span class="badge online">请留意 · 门诊评估</span>';
  else if (String(result.level || '').includes('线上')) levelBadge = '<span class="badge online">可线上问诊 / 门诊</span>';
  else if (String(result.level || '').includes('急诊')) levelBadge = '<span class="badge er">建议急诊</span>';
  if (result.guardrail?.action === 'refuse') levelBadge = '<span class="badge">🛡 安全护栏</span>';

  const narrative = summary.narrative ? `<p class="result-meta">${escapeHtml(summary.narrative)}</p>` : '';

  el.innerHTML = `
    ${result.guardrail?.action === 'redflag' ? `
      <div class="gr-lock" role="alert"><div class="gr-lock-text"><strong>🔒 当前问诊已暂停，请优先就医</strong><span>${escapeHtml(guardAdviceFor(result.guardrail))}</span></div>
        <div class="gr-lock-actions"><a class="btn danger sm" href="tel:120">拨打 120</a>${isSuicideCategory(result.guardrail.category) ? '<a class="btn danger sm" href="tel:12356">12356</a>' : ''}<button type="button" class="btn ghost sm" id="btnGuardResultNew">重新开始新问诊</button></div></div>` : ''}
    ${urgent && result.guardrail?.action !== 'redflag' ? `
      <div class="urgent-banner" role="alert">
        <div class="ub-icon">🚨</div>
        <div>
          <h3>建议立即急诊</h3>
          <p>您的描述可能与急危重症相关。请马上前往就近急诊或拨打 120，不要延误。</p>
        </div>
      </div>` : ''}

    <div class="result-card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap">
        <h3>推荐科室</h3>
        ${levelBadge}
      </div>
      <div class="result-meta">
        主诉：${escapeHtml(summary.chief || result.chatSummary || '—')}<br/>
        ${summary.duration ? `时长：${escapeHtml(summary.duration)} · ` : ''}
        ${summary.location ? `部位：${escapeHtml(summary.location)} · ` : ''}
        ${summary.severity ? `程度：${escapeHtml(summary.severity)}` : ''}
        ${summary.companions && (Array.isArray(summary.companions) ? summary.companions.length : summary.companions) ? `<br/>伴随：${escapeHtml(companions)}` : ''}
      </div>
      ${narrative}
      ${result.chatSummary && !summary.chief ? `<pre class="result-meta" style="white-space:pre-wrap;margin:0 0 12px;font-family:inherit">${escapeHtml(result.chatSummary)}</pre>` : ''}
      <div class="dept-list">
        ${depts.map((d, i) => `
          <div class="dept-item">
            <div class="dept-rank">${i + 1}</div>
            <div style="flex:1">
              <strong>${escapeHtml(d.name)}</strong>
              <small>${escapeHtml(d.reason || '')}</small>
            </div>
          </div>`).join('') || `<p class="result-meta">${result.guardrail?.action === 'redflag' ? '已触发安全护栏：请优先急诊就医，暂不提供科室分诊。' : result.guardrail?.action === 'refuse' ? '本次请求未生成科室建议，请描述具体症状后重新分诊。' : '暂无科室建议'}</p>`}
      </div>
      ${nextStepsHtml(result)}
      ${result.guardrail?.action === 'refuse' ? refuseNoticeHtml(result.guardrail) : ''}
      ${cautionNoticeHtml(result.guardrail)}
      <p class="ref-note">仅供参考，不能替代面诊 · 数据来源：${sourceLabel(result.source)}</p>
      ${aiDisclaimerHtml(result.disclaimer, true)}
      <div class="actions-row">
        ${urgent ? `<a class="btn danger" href="tel:120">拨打 120</a>` : ''}
        <button class="btn primary" id="btnGoPreconsult">生成预问诊报告</button>
        <button class="btn primary" id="btnGoAppoint">去预约挂号</button>
        <button class="btn ghost" id="btnRetrySymptom">重新填写</button>
      </div>
    </div>
  `;

  $('#btnGoPreconsult')?.addEventListener('click', () => openPreconsultFromResult(result));
  $('#btnGoAppoint')?.addEventListener('click', () => {
    state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
    showView('appoint');
  });
  $('#btnRetrySymptom')?.addEventListener('click', () => showView('symptom'));
  $('#btnGuardResultNew')?.addEventListener('click', () => {
    $('#symptomForm')?.reset();
    lockSymptomFormByGuardrail(false);
    showView('symptom');
  });
}

function escapeHtml(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ---------- Appoint flow: 科室 → 医生 → 时段 → 确认 ---------- */
function setAppointStep(n) {
  state.appoint.step = n;
  $$('#appointSteps .step').forEach((s) => {
    const sn = Number(s.dataset.step);
    s.classList.toggle('active', sn === n);
    s.classList.toggle('done', sn < n);
  });
}

async function renderAppoint() {
  const panel = $('#appointPanel');
  const a = state.appoint;
  setAppointStep(a.step);

  if (a.step === 1) {
    panel.innerHTML = `
      <p class="result-meta" style="margin-top:0">请选择科室
        ${state.preferredDept ? `<br/><span class="badge online">导诊推荐：${escapeHtml(state.preferredDept)}</span>` : ''}
      </p>
      <div class="option-list" id="listDepts"><div class="empty-state">加载中…</div></div>`;
    const list = await getDepartments();
    const box = $('#listDepts');
    if (!list.length) {
      box.innerHTML = `<div class="empty-state"><div class="big">🩺</div><p>暂无科室数据</p></div>`;
      return;
    }
    box.innerHTML = list.map((d) => {
      const preferred = state.preferredDept && (
        d.name === state.preferredDept
        || d.name.includes(state.preferredDept.replace(/科$/, ''))
        || state.preferredDept.includes(d.name.replace(/科$/, ''))
      );
      return `
      <button type="button" class="option-card ${preferred ? 'selected' : ''}" data-id="${d.id}">
        <div class="oc-icon">🩺</div>
        <div class="oc-body"><strong>${escapeHtml(d.name)}${preferred ? ' · 推荐' : ''}</strong><small>${escapeHtml(d.desc || d.intro || '')}</small></div>
      </button>`;
    }).join('');
    box.querySelectorAll('.option-card').forEach((btn) => {
      btn.addEventListener('click', () => {
        a.department = list.find((x) => x.id === btn.dataset.id);
        a.doctor = a.slot = null;
        a.step = 2;
        renderAppoint();
      });
    });
  } else if (a.step === 2) {
    panel.innerHTML = `
      <p class="result-meta" style="margin-top:0">${escapeHtml(a.department?.name)} · 请选择医生</p>
      <div class="option-list" id="listDocs"><div class="empty-state">加载中…</div></div>
      <button class="btn ghost block" style="margin-top:12px" id="backStep">上一步</button>`;
    $('#backStep').onclick = () => { a.step = 1; renderAppoint(); };
    const list = await getDoctors(a.department?.id);
    const box = $('#listDocs');
    box.innerHTML = list.map((d) => `
      <button type="button" class="option-card" data-id="${d.id}">
        <div class="oc-icon">👨‍⚕️</div>
        <div class="oc-body"><strong>${escapeHtml(d.name)}</strong><small>${escapeHtml(d.title || '')}${d.intro ? ' · ' + escapeHtml(d.intro) : ''}${d.rating != null ? ' · 评分 ' + d.rating : ''}</small></div>
      </button>`).join('') || `<div class="empty-state"><p>暂无出诊医生</p></div>`;
    box.querySelectorAll('.option-card').forEach((btn) => {
      btn.addEventListener('click', () => {
        a.doctor = list.find((x) => x.id === btn.dataset.id);
        a.slot = null;
        a.step = 3;
        renderAppoint();
      });
    });
  } else if (a.step === 3) {
    panel.innerHTML = `
      <p class="result-meta" style="margin-top:0">${escapeHtml(a.doctor?.name)} · 请选择时段</p>
      <div id="slotGroups"><div class="empty-state">加载中…</div></div>
      <button class="btn ghost block" style="margin-top:12px" id="backStep">上一步</button>`;
    $('#backStep').onclick = () => { a.step = 2; renderAppoint(); };
    const slots = await getSlots(a.doctor?.id);
    const byDate = {};
    slots.forEach((s) => {
      (byDate[s.dateLabel || dateLabelFromIso(s.date)] ||= []).push(s);
    });
    const wrap = $('#slotGroups');
    wrap.innerHTML = Object.entries(byDate).map(([date, arr]) => `
      <div style="margin-bottom:14px">
        <strong style="font-size:0.9rem">${escapeHtml(date)}</strong>
        <div class="slot-grid" style="margin-top:8px">
          ${arr.map((s) => {
            const disabled = s.available === false || s.remaining === 0;
            return `
            <button type="button" class="slot-btn" data-id="${s.id}" ${disabled ? 'disabled' : ''}>
              ${escapeHtml(s.time)}${disabled ? '<br/><small>已满</small>' : (s.remaining != null ? `<br/><small>余${s.remaining}</small>` : '')}
            </button>`;
          }).join('')}
        </div>
      </div>`).join('') || `<div class="empty-state"><p>暂无号源</p></div>`;
    wrap.querySelectorAll('.slot-btn:not(:disabled)').forEach((btn) => {
      btn.addEventListener('click', () => {
        a.slot = slots.find((x) => x.id === btn.dataset.id);
        a.step = 4;
        renderAppoint();
      });
    });
  } else if (a.step === 4) {
    if (a._success) {
      panel.innerHTML = `
        <div class="success-panel">
          <div class="big">✅</div>
          <h3>预约已提交</h3>
          <p>演示院区 · ${escapeHtml(a.department?.name)}<br/>
          ${escapeHtml(a.doctor?.name)} · ${escapeHtml(a.slot?.dateLabel || dateLabelFromIso(a.slot?.date))} ${escapeHtml(a.slot?.time)}</p>
          <div class="actions-row" style="justify-content:center">
            <button class="btn primary" id="goMine">查看我的预约</button>
            <button class="btn ghost" id="goHome">返回首页</button>
          </div>
        </div>`;
      $('#goMine').onclick = () => { a._success = false; showView('mine'); };
      $('#goHome').onclick = () => { a._success = false; showView('home'); };
      return;
    }
    const ap = getActivePatient();
    panel.innerHTML = `
      <div class="confirm-box">
        <h3 style="margin:0 0 12px">确认预约信息</h3>
        <dl>
          <dt>院区</dt><dd>演示院区</dd>
          <dt>科室</dt><dd>${escapeHtml(a.department?.name)}</dd>
          <dt>医生</dt><dd>${escapeHtml(a.doctor?.name)}（${escapeHtml(a.doctor?.title || '')}）</dd>
          <dt>时段</dt><dd>${escapeHtml(a.slot?.dateLabel || dateLabelFromIso(a.slot?.date))} ${escapeHtml(a.slot?.time)}</dd>
          <dt>当前就诊人</dt><dd>${escapeHtml(ap?.name || '演示患者')}（${escapeHtml(ap?.relation || '本人')}）</dd>
        </dl>
        <label class="field" style="margin:12px 0">
          <span>就诊人姓名 <em>*</em></span>
          <input type="text" id="patientName" value="${escapeHtml(ap?.name || '演示患者')}" required />
        </label>
        <label class="field" style="margin:0 0 12px">
          <span>手机号（可选）</span>
          <input type="tel" id="patientPhone" placeholder="用于医院回访演示" value="${escapeHtml(ap?.phone || '')}" />
        </label>
        <p class="ref-note" style="margin-top:0">演示预约，不产生真实就诊号；请以医院官方渠道为准。</p>
        <div class="actions-row">
          <button class="btn primary" id="btnConfirmApt">确认预约</button>
          <button class="btn ghost" id="backStep">返回改选</button>
        </div>
      </div>`;
    $('#backStep').onclick = () => { a.step = 3; renderAppoint(); };
    $('#btnConfirmApt').onclick = async () => {
      const patientName = ($('#patientName')?.value || '').trim() || '演示患者';
      const phone = ($('#patientPhone')?.value || '').trim() || null;
      setLoading(true, '提交预约…');
      try {
        await createAppointment({
          hospitalName: '演示院区',
          departmentId: a.department?.id,
          departmentName: a.department?.name,
          doctorId: a.doctor?.id,
          doctorName: a.doctor?.name,
          slotId: a.slot?.id,
          slotLabel: `${a.slot?.dateLabel || dateLabelFromIso(a.slot?.date)} ${a.slot?.time}`,
          patientName,
          phone,
          patientId: getActivePatientId(),
          chief: state.lastResult?.summary?.chief || null,
          triageSessionId: state.chatUsingApi ? state.chatSessionId : null
        });
        a._success = true;
        toast('预约成功');
        renderAppoint();
      } finally {
        setLoading(false);
      }
    };
  }
}

/* ---------- Mine + M1 UI ---------- */
async function refreshHomePatient() {
  const list = await fetchPatients();
  const active = list.find((p) => p.id === getActivePatientId()) || list[0];
  if (active) setActivePatientId(active.id);
  const nameEl = $('#homePatientName');
  const metaEl = $('#homePatientMeta');
  const avatar = $('#homePatientAvatar');
  if (nameEl) nameEl.textContent = active ? active.name : '未设置就诊人';
  if (metaEl) metaEl.textContent = active
    ? `${active.relation}${active.gender ? ' · ' + active.gender : ''}${active.age != null ? ' · ' + active.age + '岁' : ''} · 点击管理`
    : '点击添加就诊人';
  if (avatar) avatar.textContent = active ? String(active.name).slice(0, 1) : '?';

  const card = $('#homeProfileCard');
  const tags = $('#homeProfileTags');
  if (!card || !tags || !active) return;
  const profile = await fetchPatientProfile(active.id);
  const pills = [];
  (profile.allergies || []).forEach((t) => pills.push(`<span class="tag-pill allergy">过敏 · ${escapeHtml(t)}</span>`));
  (profile.chronicDiseases || []).forEach((t) => pills.push(`<span class="tag-pill chronic">慢病 · ${escapeHtml(t)}</span>`));
  (profile.medications || []).slice(0, 3).forEach((t) => pills.push(`<span class="tag-pill med">用药 · ${escapeHtml(t)}</span>`));
  if (!pills.length) pills.push('<span class="tag-pill muted">暂无档案，点击编辑完善</span>');
  tags.innerHTML = pills.join('');
  card.classList.remove('hidden');
}

async function renderPatients() {
  const box = $('#patientsList');
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchPatients();
  const activeId = getActivePatientId();
  if (!list.length) {
    box.innerHTML = `<div class="empty-state"><div class="big">👨‍👩‍👧</div><p>还没有就诊人</p></div>`;
    return;
  }
  box.innerHTML = list.map((p) => {
    const active = p.id === activeId;
    return `
      <div class="patient-card ${active ? 'active' : ''}" data-id="${escapeHtml(p.id)}">
        <div class="pc-avatar">${escapeHtml(String(p.name || '?').slice(0, 1))}</div>
        <div class="pc-body">
          <strong>${escapeHtml(p.name)}</strong>
          <small>${escapeHtml(p.relation)}${p.gender ? ' · ' + escapeHtml(p.gender) : ''}${p.age != null ? ' · ' + escapeHtml(p.age) + '岁' : ''}${p.phone ? ' · ' + escapeHtml(p.phone) : ''}</small>
        </div>
        ${active ? '<span class="pc-badge">当前</span>' : ''}
        <div class="pc-actions">
          ${!active ? `<button type="button" class="link-btn btn-switch" data-id="${escapeHtml(p.id)}">切换</button>` : ''}
          <button type="button" class="link-btn btn-edit-p" data-id="${escapeHtml(p.id)}">编辑</button>
        </div>
      </div>`;
  }).join('');
  box.querySelectorAll('.btn-switch').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      setActivePatientId(btn.dataset.id);
      toast('已切换就诊人');
      renderPatients();
      refreshHomePatient();
    });
  });
  box.querySelectorAll('.btn-edit-p').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      state.editingPatientId = btn.dataset.id;
      showView('patient-form');
    });
  });
  box.querySelectorAll('.patient-card').forEach((card) => {
    card.addEventListener('click', (e) => {
      if (e.target.closest('.pc-actions')) return;
      setActivePatientId(card.dataset.id);
      toast('已切换为当前就诊人');
      renderPatients();
      refreshHomePatient();
    });
  });
}

function renderPatientForm() {
  const id = state.editingPatientId;
  const p = id ? loadLocalPatients().find((x) => x.id === id) : null;
  $('#pageTitle').textContent = p ? '编辑就诊人' : '添加就诊人';
  $('#pfId').value = p?.id || '';
  $('#pfName').value = p?.name || '';
  $('#pfRelation').value = p?.relation || '本人';
  $('#pfGender').value = p?.gender || '';
  $('#pfAge').value = p?.age != null ? p.age : '';
  $('#pfPhone').value = p?.phone || '';
}

async function onPatientFormSubmit(e) {
  e.preventDefault();
  const name = $('#pfName').value.trim();
  const relation = $('#pfRelation').value;
  if (!name || !relation) {
    toast('请填写姓名与关系');
    return;
  }
  const payload = {
    name,
    relation,
    gender: $('#pfGender').value || '',
    age: $('#pfAge').value,
    phone: $('#pfPhone').value.trim()
  };
  setLoading(true, '保存中…');
  try {
    const id = $('#pfId').value;
    let item;
    if (id) item = await updatePatient(id, payload);
    else {
      item = await createPatient(payload);
      setActivePatientId(item.id);
    }
    toast('已保存');
    state.editingPatientId = null;
    showView('patients');
  } finally {
    setLoading(false);
  }
}

function renderTagEditor(containerId, items, kind) {
  const box = document.getElementById(containerId);
  if (!box) return;
  box.innerHTML = (items || []).map((t, i) => `
    <span class="tag-pill ${kind}">${escapeHtml(t)}
      <button type="button" data-kind="${kind}" data-i="${i}" aria-label="删除">×</button>
    </span>`).join('') || `<span class="tag-pill muted">暂无</span>`;
  box.querySelectorAll('button').forEach((btn) => {
    btn.addEventListener('click', () => {
      const k = btn.dataset.kind;
      const i = Number(btn.dataset.i);
      if (!state.profileDraft) return;
      if (k === 'allergy') state.profileDraft.allergies.splice(i, 1);
      if (k === 'chronic') state.profileDraft.chronicDiseases.splice(i, 1);
      if (k === 'med') state.profileDraft.medications.splice(i, 1);
      renderProfileEditors();
    });
  });
}

function renderProfileEditors() {
  const d = state.profileDraft || emptyProfile();
  renderTagEditor('tagAllergies', d.allergies, 'allergy');
  renderTagEditor('tagChronic', d.chronicDiseases, 'chronic');
  renderTagEditor('tagMeds', d.medications, 'med');
}

async function renderProfile() {
  const el = $('#profileContent');
  const patient = getActivePatient();
  el.innerHTML = `<div class="empty-state">加载中…</div>`;
  const profile = await fetchPatientProfile(patient.id);
  state.profileDraft = {
    allergies: [...(profile.allergies || [])],
    chronicDiseases: [...(profile.chronicDiseases || [])],
    medications: [...(profile.medications || [])]
  };
  el.innerHTML = `
    <div class="result-card" style="margin-bottom:12px">
      <p class="result-meta" style="margin:0">当前就诊人：<strong>${escapeHtml(patient.name)}</strong>（${escapeHtml(patient.relation)}）
        · <button type="button" class="link-btn" id="btnProfileSwitchPatient">切换</button>
      </p>
      <p class="ref-note" style="margin:6px 0 0">数据来源：${sourceLabel(profile.source)} · 仅供参考，不能替代面诊</p>
    </div>
    <div class="form-stack">
      <div class="field">
        <span>过敏史</span>
        <div class="tag-editor" id="tagAllergies"></div>
        <div class="tag-add-row">
          <input type="text" id="inputAllergy" placeholder="如：青霉素" maxlength="30" />
          <button type="button" class="btn ghost sm" id="addAllergy">添加</button>
        </div>
      </div>
      <div class="field">
        <span>慢性病</span>
        <div class="tag-editor" id="tagChronic"></div>
        <div class="tag-add-row">
          <input type="text" id="inputChronic" placeholder="如：高血压" maxlength="30" />
          <button type="button" class="btn ghost sm" id="addChronic">添加</button>
        </div>
      </div>
      <div class="field">
        <span>当前用药</span>
        <div class="tag-editor" id="tagMeds"></div>
        <div class="tag-add-row">
          <input type="text" id="inputMed" placeholder="如：氨氯地平" maxlength="30" />
          <button type="button" class="btn ghost sm" id="addMed">添加</button>
        </div>
      </div>
      <button type="button" class="btn primary block" id="btnSaveProfile">保存档案</button>
    </div>`;
  renderProfileEditors();
  $('#btnProfileSwitchPatient').onclick = () => showView('patients');
  const addOne = (inputId, key) => {
    const v = ($(inputId)?.value || '').trim();
    if (!v) return;
    if (!state.profileDraft[key].includes(v)) state.profileDraft[key].push(v);
    $(inputId).value = '';
    renderProfileEditors();
  };
  $('#addAllergy').onclick = () => addOne('#inputAllergy', 'allergies');
  $('#addChronic').onclick = () => addOne('#inputChronic', 'chronicDiseases');
  $('#addMed').onclick = () => addOne('#inputMed', 'medications');
  $('#btnSaveProfile').onclick = async () => {
    setLoading(true, '保存档案…');
    try {
      await savePatientProfile(patient.id, state.profileDraft);
      toast('档案已保存');
      refreshHomePatient();
    } finally {
      setLoading(false);
    }
  };
}

async function openPreconsultFromResult(result) {
  setLoading(true, 'AI 思考中…正在生成预问诊报告');
  try {
    const sessionId = state.chatUsingApi ? state.chatSessionId : null;
    const report = await generatePreconsultReport(result || state.lastResult, sessionId);
    state.lastPreconsult = report;
    showView('preconsult');
  } finally {
    setLoading(false);
  }
}

function renderPreconsult(report) {
  const el = $('#preconsultContent');
  if (!report) {
    const list = loadPreconsultReports();
    report = list[0] || null;
    state.lastPreconsult = report;
  }
  if (!report) {
    el.innerHTML = `
      <div class="empty-state">
        <div class="big">📄</div>
        <p>暂无预问诊报告</p>
        <p class="ref-note">完成智能问诊或症状导诊后可生成</p>
        <button class="btn primary" style="margin-top:12px" id="pcGoChat">去智能问诊</button>
      </div>`;
    $('#pcGoChat')?.addEventListener('click', () => {
      if (state.chatDone) resetChatSession();
      showView('chat');
    });
    return;
  }
  const p = report.patient || {};
  const depts = report.departments || [];
  const urgent = !!report.urgent || String(report.urgency || '').includes('急诊');
  el.innerHTML = `
    <div class="preconsult-card">
      <div class="preconsult-hero">
        <div class="pc-seal">预问诊报告 · 可分享给医生</div>
        <h2>${escapeHtml(p.name || '就诊人')}</h2>
        <p>${escapeHtml(p.relation || '')}${p.gender ? ' · ' + escapeHtml(p.gender) : ''}${p.age != null ? ' · ' + escapeHtml(p.age) + '岁' : ''}
          · ${escapeHtml(report.createdAt ? new Date(report.createdAt).toLocaleString('zh-CN') : '')}</p>
      </div>
      ${urgent ? `<div class="urgent-banner" role="alert" style="margin:12px 0"><div class="ub-icon">🚨</div><div><h3>紧急程度：${escapeHtml(report.urgency || '建议急诊')}</h3><p>如正在发作，请立即急诊或拨打 120。</p></div></div>` : ''}
      <div class="preconsult-section">
        <h4>主诉与现病史</h4>
        <p>${escapeHtml(report.hpi || report.chief || report.chatSummary || '—')}</p>
      </div>
      <div class="preconsult-section">
        <h4>紧急程度</h4>
        <p>${escapeHtml(report.urgency || '门诊')}</p>
      </div>
      <div class="preconsult-section">
        <h4>建议科室</h4>
        <div class="preconsult-depts">
          ${depts.map((d) => `<span class="sum-dept-pill">${escapeHtml(d.name)}</span>`).join('') || '<span class="tag-pill muted">暂无</span>'}
        </div>
        ${depts.map((d) => d.reason ? `<p class="result-meta" style="margin-top:8px">${escapeHtml(d.name)}：${escapeHtml(d.reason)}</p>` : '').join('')}
      </div>
      <div class="preconsult-section">
        <h4>下一步建议</h4>
        ${(report.nextSteps || []).map((s) => `<p>· ${escapeHtml(s)}</p>`).join('') || `<p>${escapeHtml(report.advice || '—')}</p>`}
      </div>
      ${(report.redFlags || []).length ? `<div class="preconsult-section"><h4>需警惕</h4>${report.redFlags.map((s) => `<p>· ${escapeHtml(s)}</p>`).join('')}</div>` : ''}
      <p class="ref-note" style="margin-top:14px">${escapeHtml(report.disclaimer || '仅供参考，不能替代面诊')} · ${sourceLabel(report.source)}</p>
      <div class="preconsult-actions">
        <button type="button" class="btn primary" id="btnCopyReport">复制全文</button>
        <button type="button" class="btn ghost" id="btnShareReport">分享</button>
        <button type="button" class="btn primary" id="btnPcAppoint">一键去预约</button>
      </div>
    </div>`;
  const text = formatPreconsultText(report);
  $('#btnCopyReport')?.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制预问诊报告');
    } catch {
      toast('复制失败，请长按选择文本');
    }
  });
  $('#btnShareReport')?.addEventListener('click', async () => {
    if (navigator.share) {
      try {
        await navigator.share({ title: '预问诊报告', text });
        return;
      } catch { /* fallthrough */ }
    }
    try {
      await navigator.clipboard.writeText(text);
      toast('已复制，可粘贴分享给医生');
    } catch {
      toast('请手动复制报告内容');
    }
  });
  $('#btnPcAppoint')?.addEventListener('click', () => {
    if (depts[0]) state.preferredDept = depts[0].name;
    state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
    showView('appoint');
  });
}

async function renderReports() {
  const box = $('#reportsList');
  $$('#reportsTabs .seg-tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === state.reportsTab));
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  if (state.reportsTab === 'preconsult') {
    const list = loadPreconsultReports();
    if (!list.length) {
      box.innerHTML = `
        <div class="empty-state">
          <div class="big">📄</div>
          <p>暂无预问诊报告</p>
          <button class="btn primary" style="margin-top:12px" id="emptyPc">去问诊生成</button>
        </div>`;
      $('#emptyPc')?.addEventListener('click', () => {
        if (state.chatDone) resetChatSession();
        showView('chat');
      });
      return;
    }
    box.innerHTML = list.map((r) => `
      <button type="button" class="report-card" data-pc="${escapeHtml(r.id)}">
        <div class="report-card-head">
          <h4>预问诊 · ${escapeHtml(r.patient?.name || '就诊人')}</h4>
          <span class="status-pill ready">可分享</span>
        </div>
        <p class="meta">${escapeHtml(r.createdAt ? new Date(r.createdAt).toLocaleString('zh-CN') : '')}
          · ${escapeHtml(r.urgency || '')}
          · ${(r.departments || []).map((d) => d.name).slice(0, 2).join('、')}</p>
      </button>`).join('');
    box.querySelectorAll('[data-pc]').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.lastPreconsult = list.find((x) => x.id === btn.dataset.pc);
        showView('preconsult');
      });
    });
    return;
  }
  const list = await fetchLabReports();
  if (!list.length) {
    box.innerHTML = `<div class="empty-state"><div class="big">🧪</div><p>暂无检验检查报告</p></div>`;
    return;
  }
  box.innerHTML = list.map((r) => {
    const st = r.statusLabel || r.status || '';
    const cls = (st.includes('解读') || r.status === 'reading') ? 'reading' : 'ready';
    return `
      <button type="button" class="report-card" data-rid="${escapeHtml(r.id)}">
        <div class="report-card-head">
          <h4>${escapeHtml(r.title)}</h4>
          <span class="status-pill ${cls}">${escapeHtml(st)}</span>
        </div>
        <p class="meta">${escapeHtml(r.typeLabel || '')} · ${escapeHtml(r.date || '')} · ${escapeHtml(r.patientName || '')}
          <br/>${escapeHtml(r.summary || '')}</p>
        <p class="ref-note" style="margin:6px 0 0">来源：${sourceLabel(r.source)}</p>
      </button>`;
  }).join('');
  box.querySelectorAll('[data-rid]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.currentReportId = btn.dataset.rid;
      state.currentInterpret = null;
      showView('report-detail');
    });
  });
}

async function renderReportDetail(id) {
  const el = $('#reportDetailContent');
  el.innerHTML = `<div class="empty-state">加载中…</div>`;
  const report = await fetchReportDetail(id);
  if (!report) {
    el.innerHTML = `<div class="empty-state"><p>未找到报告</p></div>`;
    return;
  }
  const itemsHtml = (report.items || []).length ? `
    <div class="preconsult-section">
      <h4>结果明细</h4>
      <div class="option-list">
        ${report.items.map((it) => `
          <div class="option-card" style="cursor:default">
            <div class="oc-body">
              <strong>${escapeHtml(it.name)} ${it.flag ? `<span class="badge er" style="font-size:0.7rem">${escapeHtml(it.flag)}</span>` : ''}</strong>
              <small>${escapeHtml(it.value)}${it.unit ? ' ' + escapeHtml(it.unit) : ''}　参考 ${escapeHtml(it.ref || '—')}</small>
            </div>
          </div>`).join('')}
      </div>
    </div>` : '';
  const imgHtml = report.findings || report.impression ? `
    <div class="preconsult-section">
      <h4>影像所见</h4>
      <p>${escapeHtml(report.findings || '')}</p>
      ${report.impression ? `<p><strong>印象：</strong>${escapeHtml(report.impression)}</p>` : ''}
    </div>` : '';
  const interp = state.currentInterpret;
  el.innerHTML = `
    <div class="report-detail-card">
      <h3>${escapeHtml(report.title)}</h3>
      <dl class="report-kv">
        <dt>类型</dt><dd>${escapeHtml(report.typeLabel || report.type || '')}</dd>
        <dt>状态</dt><dd>${escapeHtml(report.statusLabel || report.status || '')}</dd>
        <dt>日期</dt><dd>${escapeHtml(report.date || '')}</dd>
        <dt>就诊人</dt><dd>${escapeHtml(report.patientName || '')}</dd>
        <dt>院区</dt><dd>${escapeHtml(report.hospitalName || '演示院区')}</dd>
      </dl>
      ${report.summary ? `<p class="result-meta">${escapeHtml(report.summary)}</p>` : ''}
      ${itemsHtml}
      ${imgHtml}
      <div id="interpretArea">
        ${interp ? `
          <div class="interpret-box">
            <h4>AI 解读</h4>
            <p>${escapeHtml(interp.summary || '')}</p>
            <ul>${(interp.points || []).map((x) => `<li>${escapeHtml(x)}</li>`).join('')}</ul>
            ${interp.risk ? `<p>关注程度：${escapeHtml(interp.risk)}</p>` : ''}
            ${interp.guardrail?.action === 'refuse' ? refuseNoticeHtml(interp.guardrail) : ''}
            ${cautionNoticeHtml(interp.guardrail)}
            ${interp.guardrail?.action === 'redflag' ? `<div class="gr-lock" role="alert"><div class="gr-lock-text"><strong>🚨 请优先就医</strong><span>${escapeHtml(guardAdviceFor(interp.guardrail))}</span></div><div class="gr-lock-actions"><a class="btn danger sm" href="tel:120">拨打 120</a>${isSuicideCategory(interp.guardrail.category) ? '<a class="btn danger sm" href="tel:12356">12356</a>' : ''}</div></div>` : ''}
            <p class="ref-note">${escapeHtml(interp.disclaimer || '仅供参考，不能替代面诊')} · ${sourceLabel(interp.source)}</p>
            ${aiDisclaimerHtml(interp.disclaimer)}
          </div>` : ''}
      </div>
      <div class="actions-row" style="margin-top:12px">
        <button type="button" class="btn primary" id="btnInterpret">AI 解读</button>
        <button type="button" class="btn ghost" id="btnBackReports">返回列表</button>
      </div>
      <p class="ref-note">报告与解读仅供参考，不能替代面诊 · ${sourceLabel(report.source)}</p>
    </div>`;
  $('#btnBackReports')?.addEventListener('click', () => showView('reports'));
  $('#btnInterpret')?.addEventListener('click', async () => {
    setLoading(true, 'AI 思考中…正在解读报告');
    try {
      state.currentInterpret = await interpretReport(report.id, report);
      await renderReportDetail(report.id);
      if (state.currentInterpret?.guardrail?.action === 'redflag') showGuardrailRedflag(state.currentInterpret.guardrail);
    } finally {
      setLoading(false);
    }
  });
}

async function renderMine() {
  const hub = $('#mineHub');
  const ap = getActivePatient();
  if (hub) {
    hub.innerHTML = `
      <button type="button" class="hub-tile" data-nav="patients">
        <span class="hub-icon">👨‍👩‍👧</span><strong>就诊人</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="profile">
        <span class="hub-icon">🗂️</span><strong>健康档案</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="chronic">
        <span class="hub-icon">💓</span><strong>慢病打卡</strong>
        <small>血压血糖 · 趋势</small>
      </button>
      <button type="button" class="hub-tile" data-nav="refills">
        <span class="hub-icon">💊</span><strong>复诊续方</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="meds">
        <span class="hub-icon">⏰</span><strong>用药提醒</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="followups">
        <span class="hub-icon">📝</span><strong>随访问卷</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="waiting">
        <span class="hub-icon">🎫</span><strong>候诊报到</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="messages">
        <span class="hub-icon">🔔</span><strong>消息中心</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="nav">
        <span class="hub-icon">🗺️</span><strong>院内导航</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="dc-start" data-mode="text">
        <span class="hub-icon">📝</span><strong>图文问诊</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="dc-start" data-mode="video">
        <span class="hub-icon">📹</span><strong>视频问诊</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="dc-list">
        <span class="hub-icon">🗂️</span><strong>我的接诊</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="exam">
        <span class="hub-icon">🔬</span><strong>检查预约</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="exam-mine">
        <span class="hub-icon">📋</span><strong>我的检查</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="pharmacy">
        <span class="hub-icon">📦</span><strong>药品配送</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="pharmacy-deliveries">
        <span class="hub-icon">🚚</span><strong>我的配送</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="bills">
        <span class="hub-icon">💳</span><strong>在线缴费</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="identity">
        <span class="hub-icon">🪪</span><strong>实名绑定</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="settings">
        <span class="hub-icon">⚙️</span><strong>设置须知</strong>
      </button>
      <button type="button" class="hub-tile" data-nav="reports">
        <span class="hub-icon">🧪</span><strong>报告中心</strong>
      </button>`;
    hub.querySelectorAll('[data-nav]').forEach((b) => b.addEventListener('click', () => {
      if (b.dataset.mode) state.dcMode = b.dataset.mode;
      if (b.dataset.nav === 'chat' && state.chatDone) resetChatSession();
      showView(b.dataset.nav);
    }));
  }

  const box = $('#mineList');
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchAppointments();
  if (!list.length) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="big">🧾</div>
        <p>暂无预约记录</p>
        <p class="ref-note">当前就诊人：${escapeHtml(ap?.name || '—')}</p>
        <button class="btn primary" style="margin-top:12px" id="emptyGoApt">去预约挂号</button>
      </div>`;
    $('#emptyGoApt').onclick = () => {
      state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
      showView('appoint');
    };
    return;
  }
  box.innerHTML = list.map((a) => {
    const st = a.status || '待就诊';
    const cls = st.includes('取消') ? 'cancelled' : st.includes('完成') || st.includes('已就诊') ? 'done' : 'pending';
    return `
      <div class="appt-card" data-id="${a.id}">
        <div class="appt-card-head">
          <h4>${escapeHtml(a.departmentName || '科室')}</h4>
          <span class="status-pill ${cls}">${escapeHtml(st)}</span>
        </div>
        <p class="meta">
          ${escapeHtml(a.hospitalName || '演示院区')}<br/>
          ${escapeHtml(a.doctorName || '')} · ${escapeHtml(a.slotLabel || '')}
          ${a.patientName ? `<br/>就诊人：${escapeHtml(a.patientName)}` : ''}
        </p>
        <p class="ref-note" style="margin:4px 0 0">来源：${sourceLabel(a.source)}</p>
        <div class="appt-actions">
          ${st === '待就诊' ? `<button class="btn primary sm btn-checkin" data-id="${a.id}">去报到</button>` : ''}
          ${st === '待就诊' ? `<button class="btn ghost sm btn-cancel" data-id="${a.id}">取消预约</button>` : ''}
          <button class="btn ghost sm btn-nav-dept" data-dept="${escapeHtml(a.departmentName || '')}">找科室</button>
        </div>
      </div>`;
  }).join('');
  box.querySelectorAll('.btn-checkin').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.waitingAppointmentId = btn.dataset.id;
      showView('waiting');
    });
  });
  box.querySelectorAll('.btn-nav-dept').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const name = btn.dataset.dept;
      const list = await fetchNavDepartments();
      const hit = list.find((d) => d.name === name) || list[0];
      if (hit) {
        state.currentNavDeptId = hit.id;
        showView('nav-detail');
      } else {
        showView('nav');
      }
    });
  });
  box.querySelectorAll('.btn-cancel').forEach((btn) => {
    btn.addEventListener('click', async () => {
      setLoading(true, '取消中…');
      try {
        await cancelAppointment(btn.dataset.id);
        toast('已取消预约');
        await renderMine();
      } finally {
        setLoading(false);
      }
    });
  });
}

/* ---------- Wire ---------- */
function init() {
  // ensure seeds
  loadLocalPatients();
  loadLocalProfiles();
  getActivePatientId();
  if (typeof initDemoMode === 'function') initDemoMode();

  document.addEventListener('click', (e) => {
    const navEl = e.target.closest('[data-nav]');
    if (!navEl || navEl.classList.contains('nav-item')) return;
    if (!navEl.dataset.nav) return;
    // entry cards / chips / hub already handled below if they have listeners;
    // home patient chip & profile edit use data-nav
    if (navEl.id === 'homePatientChip' || navEl.closest('#homeProfileCard') || navEl.matches('.link-btn[data-nav]')) {
      e.preventDefault();
      const v = navEl.dataset.nav;
      if (v === 'chat' && state.chatDone) resetChatSession();
      if (v === 'appoint') state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
      showView(v);
    }
  });

  $$('.entry-card').forEach((b) => b.addEventListener('click', () => {
    if (b.dataset.nav === 'chat' && state.chatDone) resetChatSession();
    if (b.dataset.nav === 'appoint') state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
    if (b.dataset.nav === 'exam') resetExamBookState();
    if (b.dataset.mode) state.dcMode = b.dataset.mode;
    showView(b.dataset.nav);
  }));
  $$('.nav-item').forEach((b) => {
    b.addEventListener('click', () => {
      const v = b.dataset.nav;
      if (v === 'appoint') {
        state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
      }
      if (v === 'chat' && state.chatDone) {
        resetChatSession();
      }
      if (v === 'reports') state.reportsTab = 'lab';
      showView(v);
    });
  });
  $('#btnBack').addEventListener('click', goBack);
  $('#symptomForm').addEventListener('submit', onSymptomSubmit);
  $('#fillUrgent').addEventListener('click', () => fillForm({
    chief: '突发胸痛伴呼吸困难，出冷汗约 30 分钟',
    duration: '不到 24 小时',
    location: '胸部',
    severity: '重',
    companions: ['呼吸困难', '胸闷']
  }));
  $('#fillMild').addEventListener('click', () => fillForm({
    chief: '咳嗽伴低热三天，偶有咽痛',
    duration: '1–3 天',
    location: '咽喉',
    severity: '轻',
    companions: ['发热', '咳嗽']
  }));
  $('#btnSendChat').addEventListener('click', sendChat);
  $('#chatInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); sendChat(); }
  });
  $('#btnAddPatient')?.addEventListener('click', () => {
    state.editingPatientId = null;
    showView('patient-form');
  });
  $('#patientForm')?.addEventListener('submit', onPatientFormSubmit);
  $('#btnCancelPatientForm')?.addEventListener('click', () => {
    state.editingPatientId = null;
    showView('patients');
  });
  $$('#reportsTabs .seg-tab').forEach((t) => {
    t.addEventListener('click', () => {
      state.reportsTab = t.dataset.tab;
      renderReports();
    });
  });
  $$('#msgTabs .seg-tab').forEach((t) => {
    t.addEventListener('click', () => {
      state.msgFilter = t.dataset.filter || 'all';
      renderMessages();
    });
  });
  $('#btnMessages')?.addEventListener('click', () => showView('messages'));
  const navSearch = $('#navSearch');
  if (navSearch) {
    let t = null;
    navSearch.addEventListener('input', () => {
      clearTimeout(t);
      t = setTimeout(() => {
        state.navQuery = navSearch.value || '';
        renderNav();
      }, 180);
    });
  }

  $$('#refillTabs .seg-tab').forEach((t) => {
    t.addEventListener('click', () => {
      state.refillTab = t.dataset.tab || 'list';
      renderRefills();
    });
  });
  $$('#medsTabs .seg-tab').forEach((t) => {
    t.addEventListener('click', () => {
      state.medsTab = t.dataset.tab || 'today';
      renderMeds();
    });
  });
  $$('#followupTabs .seg-tab').forEach((t) => {
    t.addEventListener('click', () => {
      state.followupTab = t.dataset.tab || 'surveys';
      renderFollowups();
    });
  });
  $$('#billsTabs .seg-tab').forEach((t) => {
    t.addEventListener('click', () => {
      state.billsFilter = t.dataset.filter || 'all';
      renderBills();
    });
  });

  $$('#chronicTabs .seg-tab').forEach((t) => {
    t.addEventListener('click', () => {
      state.chronicTab = t.dataset.tab || 'bp';
      renderChronic();
    });
  });

  registerServiceWorker();
  updateMsgBadge();
  showView('home', { push: false });
}

function registerServiceWorker() {
  const proto = location.protocol;
  if (proto !== 'http:' && proto !== 'https:') return;
  if (!('serviceWorker' in navigator)) return;
  navigator.serviceWorker.register('./sw.js').catch(() => {
    /* silent: SW optional for demo */
  });
}

document.addEventListener('DOMContentLoaded', init);

/* ========== M2 · 诊中便利 ========== */
const WAITING_KEY = 'triage_waiting_v1';
const MESSAGES_KEY = 'triage_messages_v1';
const MESSAGES_READ_KEY = 'triage_messages_read_v1';

const WAITING_STATUS_MAP = {
  not_checked: { label: '未报到', cls: 'not_checked' },
  not_checked_in: { label: '未报到', cls: 'not_checked' },
  '未报到': { label: '未报到', cls: 'not_checked' },
  waiting: { label: '已报到候诊中', cls: 'waiting' },
  checked_in: { label: '已报到候诊中', cls: 'waiting' },
  '已报到候诊中': { label: '已报到候诊中', cls: 'waiting' },
  '已报到': { label: '已报到候诊中', cls: 'waiting' },
  soon: { label: '即将叫号', cls: 'soon' },
  called: { label: '即将叫号', cls: 'soon' },
  '即将叫号': { label: '即将叫号', cls: 'soon' },
  seeing: { label: '就诊中', cls: 'seeing' },
  in_progress: { label: '就诊中', cls: 'seeing' },
  '就诊中': { label: '就诊中', cls: 'seeing' },
  done: { label: '已完成', cls: 'done' },
  finished: { label: '已完成', cls: 'done' },
  completed: { label: '已完成', cls: 'done' },
  '已完成': { label: '已完成', cls: 'done' }
};

const WAITING_FLOW = ['未报到', '已报到候诊中', '即将叫号', '就诊中', '已完成'];

const MOCK_NAV_LOCATIONS = {
  'dept-gi': { floor: '3F', zone: 'A区', building: '门诊楼', gate: '1号门', elevator: '电梯A', tips: '1号门 → 电梯A → 3F 消化内科' },
  'dept-resp': { floor: '3F', zone: 'B区', building: '门诊楼', gate: '1号门', elevator: '电梯A', tips: '1号门 → 电梯A → 3F 呼吸内科' },
  'dept-cardio': { floor: '4F', zone: 'A区', building: '门诊楼', gate: '1号门', elevator: '电梯B', tips: '1号门 → 电梯B → 4F 心内科' },
  'dept-neuro': { floor: '4F', zone: 'B区', building: '门诊楼', gate: '1号门', elevator: '电梯B', tips: '1号门 → 电梯B → 4F 神经内科' },
  'dept-uro': { floor: '2F', zone: 'C区', building: '门诊楼', gate: '2号门', elevator: '电梯C', tips: '2号门 → 电梯C → 2F 泌尿外科' },
  'dept-gyn': { floor: '5F', zone: 'A区', building: '门诊楼', gate: '2号门', elevator: '电梯C', tips: '2号门 → 电梯C → 5F 妇科' },
  'dept-ortho': { floor: '2F', zone: 'A区', building: '门诊楼', gate: '1号门', elevator: '电梯A', tips: '1号门 → 电梯A → 2F 骨科' },
  'dept-er': { floor: '1F', zone: '急诊区', building: '急诊楼', gate: '急诊入口', elevator: '—', tips: '急诊入口直行 → 1F 急诊分诊台' },
  'dept-gp': { floor: '1F', zone: 'B区', building: '门诊楼', gate: '1号门', elevator: '—', tips: '1号门 → 直行大厅 → 1F 全科医学' },
  'dept-ent': { floor: '3F', zone: 'C区', building: '门诊楼', gate: '1号门', elevator: '电梯A', tips: '1号门 → 电梯A → 3F 耳鼻喉科' },
  d1: { floor: '3F', zone: 'B区', building: '门诊楼', gate: '1号门', elevator: '电梯A', tips: '1号门 → 电梯A → 3F 呼吸内科' },
  d2: { floor: '1F', zone: 'B区', building: '门诊楼', gate: '1号门', elevator: '—', tips: '1号门 → 直行大厅 → 1F 全科医学' },
  d3: { floor: '1F', zone: '急诊区', building: '急诊楼', gate: '急诊入口', elevator: '—', tips: '急诊入口直行 → 1F 急诊分诊台' },
  d4: { floor: '4F', zone: 'A区', building: '门诊楼', gate: '1号门', elevator: '电梯B', tips: '1号门 → 电梯B → 4F 心内科' },
  d5: { floor: '3F', zone: 'A区', building: '门诊楼', gate: '1号门', elevator: '电梯A', tips: '1号门 → 电梯A → 3F 消化内科' },
  d6: { floor: '4F', zone: 'B区', building: '门诊楼', gate: '1号门', elevator: '电梯B', tips: '1号门 → 电梯B → 4F 神经内科' },
  d7: { floor: '5F', zone: 'B区', building: '门诊楼', gate: '2号门', elevator: '电梯C', tips: '2号门 → 电梯C → 5F 皮肤科' },
  d8: { floor: '2F', zone: 'A区', building: '门诊楼', gate: '1号门', elevator: '电梯A', tips: '1号门 → 电梯A → 2F 骨科' },
  d9: { floor: '3F', zone: 'C区', building: '门诊楼', gate: '1号门', elevator: '电梯A', tips: '1号门 → 电梯A → 3F 耳鼻喉科' }
};

function loadWaitingStore() {
  try { return JSON.parse(localStorage.getItem(WAITING_KEY) || '{}'); } catch { return {}; }
}
function saveWaitingStore(obj) {
  localStorage.setItem(WAITING_KEY, JSON.stringify(obj));
}
function loadMsgReadSet() {
  try { return new Set(JSON.parse(localStorage.getItem(MESSAGES_READ_KEY) || '[]')); } catch { return new Set(); }
}
function saveMsgReadSet(set) {
  localStorage.setItem(MESSAGES_READ_KEY, JSON.stringify([...set]));
}

const MSG_TYPE_LABELS = {
  appointment: '预约提醒',
  exam: '检查预约',
  report: '报告已出',
  delivery: '配送动态',
  system: '系统通知'
};

const MSG_TYPE_API_ALIASES = {
  appointment: ['appointment', 'appointment_reminder'],
  exam: ['exam', 'exam_booking', 'exam_reschedule'],
  report: ['report', 'report_ready'],
  delivery: ['delivery', 'delivery_status'],
  system: ['system']
};

function messageCategory(type) {
  const t = String(type || 'system').toLowerCase();
  if (t === 'appointment' || t === 'appointment_reminder' || t.includes('appointment') || t === '预约提醒') return 'appointment';
  if (t === 'exam' || t === 'exam_booking' || t === 'exam_reschedule' || t.includes('exam') || t.includes('lab') || t === '检查') return 'exam';
  if (t === 'report' || t === 'report_ready' || t.includes('report') || t === '报告已出') return 'report';
  if (t === 'delivery' || t === 'delivery_status' || t.includes('delivery') || t.includes('ship') || t === '配送') return 'delivery';
  return 'system';
}

function seedMockMessages() {
  const now = Date.now();
  return [
    {
      id: 'msg-apt-1',
      type: 'appointment_reminder',
      typeLabel: '预约提醒',
      title: '明日就诊提醒',
      body: '您预约的呼吸内科门诊即将到来，请提前 30 分钟到院报到。携带身份证与医保卡。',
      createdAt: new Date(now - 3600e3).toISOString(),
      read: false,
      relatedId: null,
      relatedType: 'appointment',
      link: '/appointments'
    },
    {
      id: 'msg-apt-2',
      type: 'appointment_reminder',
      typeLabel: '预约提醒',
      title: '可前往报到',
      body: '今日有待就诊预约，可在「候诊报到」页一键报到并查看排队情况。',
      createdAt: new Date(now - 1800e3).toISOString(),
      read: false,
      relatedId: null,
      relatedType: 'waiting',
      link: '/waiting'
    },
    {
      id: 'msg-exam-1',
      type: 'exam_booking',
      typeLabel: '检查预约',
      title: '检查预约成功',
      body: '您已预约「腹部彩超」，请按注意事项准备；可在「我的检查」查看或改约。',
      createdAt: new Date(now - 2400e3).toISOString(),
      read: false,
      relatedId: null,
      relatedType: 'exam',
      link: '/exam-mine'
    },
    {
      id: 'msg-exam-2',
      type: 'exam_reschedule',
      typeLabel: '检查改约',
      title: '检查已改约',
      body: '「血常规」已改至新时段。改约次数有限，请留意注意事项（如空腹）。',
      createdAt: new Date(now - 4800e3).toISOString(),
      read: false,
      relatedId: null,
      relatedType: 'exam',
      link: '/exam-mine'
    },
    {
      id: 'msg-rpt-1',
      type: 'report_ready',
      typeLabel: '报告已出',
      title: '血常规报告已出',
      body: '您的「血常规」检验报告已出具，可在报告中心查看并获取 AI 解读（仅供参考）。',
      createdAt: new Date(now - 7200e3).toISOString(),
      read: false,
      relatedId: 'r-cbc-1',
      relatedType: 'report',
      link: '/reports/r-cbc-1'
    },
    {
      id: 'msg-rpt-2',
      type: 'report_ready',
      typeLabel: '报告已出',
      title: '肝功能报告已出',
      body: '「肝功能」报告已就绪。转氨酶指标请结合临床由医生判读。',
      createdAt: new Date(now - 172800e3).toISOString(),
      read: false,
      relatedId: 'r-liver-1',
      relatedType: 'report',
      link: '/reports/r-liver-1'
    },
    {
      id: 'msg-deliv-1',
      type: 'delivery_status',
      typeLabel: '配送动态',
      title: '药品待发货',
      body: '您的购药配送单已提交，药房备货中（待发货）。可在「我的配送」查看进度。',
      createdAt: new Date(now - 900e3).toISOString(),
      read: false,
      relatedId: null,
      relatedType: 'delivery',
      link: '/pharmacy-deliveries'
    },
    {
      id: 'msg-deliv-2',
      type: 'delivery_status',
      typeLabel: '配送动态',
      title: '药品运输中',
      body: '配送单已揽收，正在运输中。请保持电话畅通以便快递员联系。',
      createdAt: new Date(now - 5400e3).toISOString(),
      read: false,
      relatedId: null,
      relatedType: 'delivery',
      link: '/pharmacy-deliveries'
    },
    {
      id: 'msg-deliv-3',
      type: 'delivery_status',
      typeLabel: '配送动态',
      title: '药品已送达',
      body: '配送单已送达。如有疑问请联系客服（演示环境，非真实物流）。',
      createdAt: new Date(now - 10800e3).toISOString(),
      read: true,
      relatedId: null,
      relatedType: 'delivery',
      link: '/pharmacy-deliveries'
    },
    {
      id: 'msg-sys-1',
      type: 'system',
      typeLabel: '系统通知',
      title: '候诊信息说明',
      body: '候诊队列与预计等待时间为演示数据，仅供参考，请以院内叫号屏与工作人员指引为准。',
      createdAt: new Date(now - 86400e3).toISOString(),
      read: true,
      relatedId: null,
      relatedType: null,
      link: '/waiting'
    }
  ];
}

function normalizeMessage(m, source) {
  if (!m) return null;
  const rawType = m.type || 'system';
  const normType = messageCategory(rawType);
  const typeLabel = m.typeLabel || MSG_TYPE_LABELS[normType] || '系统通知';
  let relatedId = m.relatedId || m.reportId || m.appointmentId || m.bookingId || m.deliveryId || m.examId || null;
  let relatedType = m.relatedType || null;
  const link = m.link || '';
  if (link) {
    const parts = String(link).split('/').filter(Boolean);
    const head = parts[0] || '';
    if ((head === 'reports' || head === 'report') && parts[1]) { relatedId = relatedId || parts[1]; relatedType = 'report'; }
    if ((head === 'appointments' || head === 'appointment') && parts[1]) { relatedId = relatedId || parts[1]; relatedType = 'appointment'; }
    if (head === 'waiting') { relatedType = relatedType || 'waiting'; }
    if (head === 'navigation' && parts[1]) { relatedId = relatedId || parts[1]; relatedType = 'navigation'; }
    if (head === 'exam-mine' || head === 'exam' || head === 'lab-exams' || head === 'exams') {
      relatedType = relatedType || 'exam';
      if (parts[1]) relatedId = relatedId || parts[1];
    }
    if (head === 'pharmacy-deliveries' || head === 'pharmacy-delivery' || head === 'deliveries' || head === 'delivery') {
      relatedType = relatedType || 'delivery';
      if (parts[1]) relatedId = relatedId || parts[1];
    }
  }
  if (!relatedType) {
    if (normType === 'report') relatedType = 'report';
    else if (normType === 'appointment') relatedType = 'appointment';
    else if (normType === 'exam') relatedType = 'exam';
    else if (normType === 'delivery') relatedType = 'delivery';
  }
  return {
    id: m.id,
    type: normType,
    rawType,
    typeLabel,
    title: m.title || '通知',
    body: m.body || m.content || '',
    createdAt: m.createdAt || m.time || new Date().toISOString(),
    read: !!m.read,
    relatedId,
    relatedType,
    link,
    source: source || m.source || 'api'
  };
}

function normalizeWaiting(data, appointment, source) {
  const raw = data?.status || data?.queueStatus || '未报到';
  const meta = WAITING_STATUS_MAP[raw] || WAITING_STATUS_MAP['未报到'];
  const apt = appointment || {};
  const ahead = data?.peopleAhead ?? data?.aheadCount ?? data?.ahead ?? 0;
  const qn = data?.queueNumber ?? data?.queueNo ?? data?.number;
  const slotLabel = data?.slotLabel
    || [data?.date ? dateLabelFromIso(data.date) : '', data?.time].filter(Boolean).join(' ')
    || apt.slotLabel || '';
  const est = data?.estimatedWaitMinutes ?? data?.estimatedWait ?? data?.waitMinutes
    ?? (ahead != null ? Number(ahead) * 8 : 0);
  return {
    id: data?.id || null,
    appointmentId: data?.appointmentId || apt.id || null,
    patientName: data?.patientName || apt.patientName || getActivePatient()?.name || '演示患者',
    departmentId: data?.departmentId || apt.departmentId || null,
    departmentName: data?.departmentName || apt.departmentName || '—',
    doctorName: data?.doctorName || apt.doctorName || '—',
    slotLabel,
    queueNumber: qn != null ? qn : '—',
    peopleAhead: ahead,
    estimatedWaitMinutes: est,
    status: meta.label,
    statusKey: meta.cls,
    rawStatus: raw,
    location: data?.location || '',
    tips: data?.tips || '',
    checkedInAt: data?.checkedInAt || null,
    updatedAt: data?.updatedAt || new Date().toISOString(),
    disclaimer: data?.disclaimer || '候诊信息仅供参考，请以院内叫号为准',
    source: source || data?.source || 'api'
  };
}

function mockWaitingForAppointment(apt) {
  const store = loadWaitingStore();
  const id = apt?.id || 'demo';
  let row = store[id];
  if (!row) {
    const n = 12 + (String(id).length % 20);
    row = {
      appointmentId: id,
      queueNumber: 'A' + String(30 + (String(id).charCodeAt(String(id).length - 1) % 40)).padStart(2, '0'),
      peopleAhead: Math.min(8, Math.max(2, n % 9)),
      estimatedWaitMinutes: null,
      status: '未报到',
      checkedInAt: null,
      updatedAt: new Date().toISOString()
    };
    row.estimatedWaitMinutes = row.peopleAhead * 8;
    store[id] = row;
    saveWaitingStore(store);
  }
  return normalizeWaiting(row, apt, 'mock');
}

function advanceMockWaiting(appointmentId, toStatus) {
  const store = loadWaitingStore();
  const row = store[appointmentId] || {
    appointmentId,
    queueNumber: 'A42',
    peopleAhead: 5,
    estimatedWaitMinutes: 40,
    status: '未报到'
  };
  const cur = row.status || '未报到';
  let next = toStatus;
  if (!next) {
    const idx = WAITING_FLOW.indexOf(cur);
    next = WAITING_FLOW[Math.min(WAITING_FLOW.length - 1, idx + 1)];
  }
  row.status = next;
  if (next === '已报到候诊中' && !row.checkedInAt) {
    row.checkedInAt = new Date().toISOString();
    if (row.peopleAhead == null) row.peopleAhead = 5;
  }
  if (next === '即将叫号') row.peopleAhead = Math.min(row.peopleAhead ?? 1, 1);
  if (next === '就诊中' || next === '已完成') row.peopleAhead = 0;
  row.estimatedWaitMinutes = Math.max(0, (row.peopleAhead || 0) * 8);
  row.updatedAt = new Date().toISOString();
  store[appointmentId] = row;
  saveWaitingStore(store);
  return row;
}

function tickMockWaiting(appointmentId) {
  const store = loadWaitingStore();
  const row = store[appointmentId];
  if (!row) return null;
  const st = row.status;
  if (st !== '已报到候诊中' && st !== '即将叫号') return row;
  if ((row.peopleAhead || 0) > 0) {
    row.peopleAhead = Math.max(0, row.peopleAhead - 1);
    row.estimatedWaitMinutes = row.peopleAhead * 8;
    if (row.peopleAhead <= 1 && st === '已报到候诊中') row.status = '即将叫号';
    if (row.peopleAhead === 0 && row.status === '即将叫号') {
      /* stay soon until user advances */
    }
    row.updatedAt = new Date().toISOString();
    store[appointmentId] = row;
    saveWaitingStore(store);
  }
  return row;
}

function pickWaitingItem(payload, appointmentId) {
  if (!payload) return null;
  if (Array.isArray(payload)) {
    return appointmentId
      ? (payload.find((x) => x.appointmentId === appointmentId) || payload[0] || null)
      : (payload[0] || null);
  }
  if (Array.isArray(payload.items)) {
    const items = payload.items;
    const hit = appointmentId
      ? (items.find((x) => x.appointmentId === appointmentId) || items[0] || null)
      : (items[0] || null);
    if (hit && payload.disclaimer && !hit.disclaimer) hit.disclaimer = payload.disclaimer;
    return hit;
  }
  // single object
  if (payload.appointmentId || payload.queueNo != null || payload.status) return payload;
  return null;
}

async function fetchWaitingList() {
  for (const p of ['/api/waiting/status', '/api/queue']) {
    try {
      const data = await apiFetch(p);
      const items = Array.isArray(data) ? data : (data.items || []);
      if (items.length || (data && data.items)) {
        return items.map((x) => normalizeWaiting(
          data.disclaimer && !x.disclaimer ? { ...x, disclaimer: data.disclaimer } : x,
          null,
          'api'
        ));
      }
    } catch { /* next */ }
  }
  return null;
}

async function fetchWaitingStatus(appointmentId) {
  const aptList = await fetchAppointments().catch(() => loadAppointments());
  const apt = (aptList || []).find((a) => a.id === appointmentId) || { id: appointmentId };
  const tryPaths = [
    appointmentId ? `/api/waiting/status?appointmentId=${encodeURIComponent(appointmentId)}` : '/api/waiting/status',
    appointmentId ? `/api/queue?appointmentId=${encodeURIComponent(appointmentId)}` : '/api/queue'
  ];
  for (const p of tryPaths) {
    try {
      const data = await apiFetch(p);
      const item = pickWaitingItem(data, appointmentId);
      if (item) return normalizeWaiting(item, apt, 'api');
    } catch { /* next */ }
  }
  return mockWaitingForAppointment(apt);
}

async function checkInWaiting(appointmentId) {
  const body = { appointmentId };
  const tryPosts = ['/api/waiting/status', '/api/queue'];
  for (const path of tryPosts) {
    try {
      const data = await apiFetch(path, { method: 'POST', body: JSON.stringify(body) });
      const item = pickWaitingItem(data, appointmentId) || data;
      const aptList = await fetchAppointments().catch(() => loadAppointments());
      const apt = (aptList || []).find((a) => a.id === appointmentId) || { id: appointmentId };
      return normalizeWaiting(item, apt, 'api');
    } catch { /* next */ }
  }
  advanceMockWaiting(appointmentId, '已报到候诊中');
  const aptList = await fetchAppointments().catch(() => loadAppointments());
  const apt = (aptList || []).find((a) => a.id === appointmentId) || { id: appointmentId };
  return mockWaitingForAppointment(apt);
}

function loadMockMessagesMerged() {
  const readSet = loadMsgReadSet();
  let seeded = seedMockMessages().map((m) => {
    const nm = normalizeMessage(m, 'mock');
    if (readSet.has(nm.id)) nm.read = true;
    return nm;
  });
  try {
    const saved = JSON.parse(localStorage.getItem(MESSAGES_KEY) || 'null');
    if (Array.isArray(saved) && saved.length) {
      const byId = Object.fromEntries(seeded.map((m) => [m.id, m]));
      saved.forEach((m) => {
        const nm = normalizeMessage(m, m.source || 'mock');
        if (readSet.has(nm.id)) nm.read = true;
        byId[nm.id] = nm;
      });
      seeded = Object.values(byId);
    }
  } catch { /* ignore */ }
  seeded.sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
  return seeded;
}

function filterMessagesByCategory(list, filter) {
  if (!filter || filter === 'all') return list || [];
  return (list || []).filter((m) => m.type === filter);
}

function apiTypeQueriesForFilter(filter) {
  if (!filter || filter === 'all') return [];
  if (filter === 'appointment') return ['appointment_reminder', 'appointment'];
  if (filter === 'exam') return ['exam', 'exam_booking', 'exam_reschedule'];
  if (filter === 'report') return ['report_ready', 'report'];
  if (filter === 'delivery') return ['delivery_status', 'delivery'];
  if (filter === 'system') return ['system'];
  return [filter];
}

function mergeMissingCategoryMocks(apiList) {
  const list = apiList || [];
  const cats = new Set(list.map((m) => m.type));
  const need = ['exam', 'delivery'].filter((c) => !cats.has(c));
  if (!need.length) return list;
  const extras = loadMockMessagesMerged().filter((m) => need.includes(m.type));
  const byId = Object.fromEntries(list.map((m) => [m.id, m]));
  extras.forEach((m) => { if (!byId[m.id]) byId[m.id] = m; });
  return Object.values(byId).sort((a, b) => String(b.createdAt).localeCompare(String(a.createdAt)));
}

function parseMessagesPayload(data, source) {
  const list = Array.isArray(data) ? data : (data?.items || data?.messages || []);
  const mapped = list.map((m) => normalizeMessage(m, source)).filter(Boolean);
  const unread = (data && typeof data.unreadCount === 'number') ? data.unreadCount : null;
  return { mapped, unread, hasItemsKey: Array.isArray(data?.items) || Array.isArray(data) };
}

async function fetchMessagesFullFromApi() {
  const data = await apiFetch('/api/messages');
  const { mapped, unread, hasItemsKey } = parseMessagesPayload(data, 'api');
  if (!mapped.length && !hasItemsKey && unread == null) return null;
  if (unread != null) state.messagesUnreadApi = unread;
  return mergeMissingCategoryMocks(mapped);
}

async function probeMessagesServerFilter() {
  if (state.messagesFilterServer != null && state._msgFilterProbed) return state.messagesFilterServer;
  state._msgFilterProbed = true;
  try {
    const data = await apiFetch('/api/messages?type=appointment_reminder');
    const { mapped } = parseMessagesPayload(data, 'api');
    const ok = mapped.length > 0 && mapped.every((m) => m.type === 'appointment');
    state.messagesFilterServer = ok;
    return ok;
  } catch {
    state.messagesFilterServer = false;
    return false;
  }
}

async function fetchMessages(opts = {}) {
  const filter = opts.filter != null ? opts.filter : (state.msgFilter || 'all');
  const forceRefresh = !!opts.forceRefresh;
  if (!forceRefresh && state.messagesCache && opts.useCache) {
    return filterMessagesByCategory(state.messagesCache, filter);
  }

  try {
    let full = await fetchMessagesFullFromApi();
    if (full) {
      state.messagesCache = full;
      state.messagesUsingApi = true;
      await probeMessagesServerFilter();
      return filterMessagesByCategory(full, filter);
    }
  } catch { /* mock */ }

  state.messagesUsingApi = false;
  state.messagesFilterServer = false;
  state.messagesUnreadApi = null;
  const seeded = loadMockMessagesMerged();
  state.messagesCache = seeded;
  return filterMessagesByCategory(seeded, filter);
}

async function fetchUnreadMessageCount() {
  try {
    const data = await apiFetch('/api/messages/unread-count');
    const n = data?.unreadCount ?? data?.count ?? data?.unread;
    if (typeof n === 'number') {
      state.messagesUnreadApi = n;
      return n;
    }
  } catch { /* ignore */ }
  try {
    const data = await apiFetch('/api/messages');
    if (typeof data?.unreadCount === 'number') {
      state.messagesUnreadApi = data.unreadCount;
      return data.unreadCount;
    }
  } catch { /* ignore */ }
  if (typeof state.messagesUnreadApi === 'number') return state.messagesUnreadApi;
  if (!state.messagesCache) {
    try { await fetchMessages({ filter: 'all', forceRefresh: true }); } catch { /* ignore */ }
  }
  // API unread excludes supplemental mocks; count unread in cache for badge completeness
  const apiUnread = typeof state.messagesUnreadApi === 'number' ? state.messagesUnreadApi : null;
  if (apiUnread != null && state.messagesUsingApi) {
    const mockExtraUnread = (state.messagesCache || []).filter((m) => m.source === 'mock' && !m.read).length;
    return apiUnread + mockExtraUnread;
  }
  return (state.messagesCache || []).filter((m) => !m.read).length;
}

async function markMessageRead(id) {
  const wasUnread = state.messagesCache?.find((x) => x.id === id && !x.read);
  try {
    await apiFetch(`/api/messages/${encodeURIComponent(id)}/read`, { method: 'PATCH', body: '{}' });
    if (wasUnread && wasUnread.source !== 'mock' && typeof state.messagesUnreadApi === 'number' && state.messagesUnreadApi > 0) {
      state.messagesUnreadApi -= 1;
    }
  } catch {
    const set = loadMsgReadSet();
    set.add(id);
    saveMsgReadSet(set);
  }
  if (state.messagesCache) {
    const m = state.messagesCache.find((x) => x.id === id);
    if (m) m.read = true;
  }
  if (state.messagesUsingApi) {
    try { await fetchUnreadMessageCount(); } catch { /* ignore */ }
  }
  updateMsgBadge();
}

async function updateMsgBadge() {
  try {
    let n = await fetchUnreadMessageCount();
    if (typeof n !== 'number') {
      n = (state.messagesCache || []).filter((m) => !m.read).length;
    }
    ['msgBadge', 'msgBadgeNav'].forEach((id) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (n > 0) {
        el.textContent = n > 99 ? '99+' : String(n);
        el.classList.remove('hidden');
      } else {
        el.classList.add('hidden');
      }
    });
  } catch { /* ignore */ }
}

function formatMsgTimeFull(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso).slice(0, 16);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function stopWaitingTicker() {
  if (state.waitingTimer) {
    clearInterval(state.waitingTimer);
    state.waitingTimer = null;
  }
}

function startWaitingTicker(appointmentId) {
  stopWaitingTicker();
  state.waitingTimer = setInterval(async () => {
    if (state.view !== 'waiting') { stopWaitingTicker(); return; }
    // Prefer refresh from API; on failure tick mock
    try {
      const data = await apiFetch(`/api/waiting/status?appointmentId=${encodeURIComponent(appointmentId)}`);
      const aptList = await fetchAppointments().catch(() => loadAppointments());
      const apt = (aptList || []).find((a) => a.id === appointmentId) || { id: appointmentId };
      state.waitingStatus = normalizeWaiting(data, apt, 'api');
      paintWaitingCard(state.waitingStatus);
      return;
    } catch { /* mock tick */ }
    tickMockWaiting(appointmentId);
    const aptList = await fetchAppointments().catch(() => loadAppointments());
    const apt = (aptList || []).find((a) => a.id === appointmentId) || { id: appointmentId };
    state.waitingStatus = mockWaitingForAppointment(apt);
    paintWaitingCard(state.waitingStatus);
  }, 5000);
}

function paintWaitingCard(w) {
  const host = document.getElementById('waitingLiveCard');
  if (!host || !w) return;
  const flowIdx = WAITING_FLOW.indexOf(w.status);
  host.innerHTML = `
    <div class="waiting-status-chip ${escapeHtml(w.statusKey)}">${escapeHtml(w.status)}</div>
    <div class="waiting-progress" aria-hidden="true">
      ${WAITING_FLOW.map((s, i) => `
        <div class="wp-step ${i < flowIdx ? 'done' : ''} ${i === flowIdx ? 'on' : ''}">
          <span class="wp-dot"></span>${escapeHtml(s.length > 4 ? s.slice(0, 2) : s)}
        </div>`).join('')}
    </div>
    <p class="waiting-queue-label">当前叫号排队号</p>
    <div class="waiting-queue-num">${escapeHtml(String(w.queueNumber))}</div>
    <div class="waiting-stats">
      <div class="waiting-stat"><strong>${escapeHtml(String(w.peopleAhead ?? '—'))}</strong><span>前方等待</span></div>
      <div class="waiting-stat"><strong>${escapeHtml(String(w.estimatedWaitMinutes ?? '—'))}<small style="font-size:0.7rem"> 分</small></strong><span>预计等待</span></div>
    </div>
    <p class="waiting-meta">
      <strong>就诊人</strong> ${escapeHtml(w.patientName)}<br/>
      <strong>科室</strong> ${escapeHtml(w.departmentName)} · <strong>医生</strong> ${escapeHtml(w.doctorName)}
      ${w.slotLabel ? `<br/><strong>时段</strong> ${escapeHtml(w.slotLabel)}` : ''}
      ${w.location ? `<br/><strong>位置</strong> ${escapeHtml(w.location)}` : ''}
      ${w.tips ? `<br/><strong>提示</strong> ${escapeHtml(w.tips)}` : ''}
    </p>
    <div class="waiting-actions" id="waitingActions"></div>
    <p class="waiting-disclaimer">⚠️ ${escapeHtml(w.disclaimer)} · 来源：${sourceLabel(w.source)}</p>
  `;
  const actions = document.getElementById('waitingActions');
  if (!actions) return;
  if (w.status === '未报到') {
    actions.innerHTML = `<button type="button" class="btn primary block" id="btnCheckIn">一键报到</button>`;
    document.getElementById('btnCheckIn').onclick = async () => {
      setLoading(true, '报到中…');
      try {
        state.waitingStatus = await checkInWaiting(w.appointmentId);
        toast('报到成功');
        paintWaitingCard(state.waitingStatus);
        startWaitingTicker(w.appointmentId);
      } finally {
        setLoading(false);
      }
    };
  } else if (w.status === '已报到候诊中' || w.status === '即将叫号') {
    actions.innerHTML = `
      <button type="button" class="btn ghost block" id="btnRefreshWait">刷新状态</button>
      <button type="button" class="btn ghost block" id="btnSimAdvance">演示：推进叫号</button>
      <button type="button" class="btn ghost block" data-nav-go="nav">查看科室位置</button>`;
    document.getElementById('btnRefreshWait').onclick = () => renderWaiting(w.appointmentId);
    document.getElementById('btnSimAdvance').onclick = async () => {
      setLoading(true, '更新状态…');
      try {
        if (isApiSource(w.source)) {
          state.waitingStatus = await checkInWaiting(w.appointmentId);
          paintWaitingCard(state.waitingStatus);
        } else {
          advanceMockWaiting(w.appointmentId);
          await renderWaiting(w.appointmentId);
        }
      } finally {
        setLoading(false);
      }
    };
    actions.querySelector('[data-nav-go="nav"]').onclick = () => {
      if (w.departmentId) {
        state.currentNavDeptId = w.departmentId;
        showView('nav-detail');
      } else showView('nav');
    };
  } else if (w.status === '就诊中') {
    actions.innerHTML = `
      <button type="button" class="btn ghost block" id="btnSimAdvance">演示：完成就诊</button>`;
    document.getElementById('btnSimAdvance').onclick = async () => {
      if (isApiSource(w.source)) {
        setLoading(true, '更新状态…');
        try {
          state.waitingStatus = await checkInWaiting(w.appointmentId);
          paintWaitingCard(state.waitingStatus);
        } finally { setLoading(false); }
      } else {
        advanceMockWaiting(w.appointmentId, '已完成');
        renderWaiting(w.appointmentId);
      }
    };
  } else {
    actions.innerHTML = `
      <button type="button" class="btn primary block" data-nav-go="home">返回首页</button>
      <button type="button" class="btn ghost block" id="btnResetWait">演示：重置未报到</button>`;
    actions.querySelector('[data-nav-go="home"]').onclick = () => showView('home');
    document.getElementById('btnResetWait').onclick = () => {
      const store = loadWaitingStore();
      delete store[w.appointmentId];
      saveWaitingStore(store);
      renderWaiting(w.appointmentId);
    };
  }
}

async function renderWaiting(forcedAptId) {
  stopWaitingTicker();
  const box = $('#waitingContent');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const apiWaiting = await fetchWaitingList();
  let list;
  if (apiWaiting && apiWaiting.length) {
    list = apiWaiting.map((w) => ({
      id: w.appointmentId,
      departmentName: w.departmentName,
      doctorName: w.doctorName,
      slotLabel: w.slotLabel,
      patientName: w.patientName,
      status: w.status,
      _waiting: w
    }));
  } else {
    list = (await fetchAppointments().catch(() => loadAppointments()))
      .filter((a) => {
        const st = a.status || '';
        return !st.includes('取消') && !st.includes('完成') && !st.includes('已就诊');
      });
  }
  const aptId = forcedAptId || state.waitingAppointmentId || list[0]?.id || null;
  state.waitingAppointmentId = aptId;

  if (!list.length && !aptId) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="big">🎫</div>
        <p>暂无待就诊预约</p>
        <p class="ref-note">请先预约挂号，再到本页报到</p>
        <button class="btn primary" style="margin-top:12px" id="waitGoApt">去预约</button>
      </div>
      <p class="waiting-disclaimer">⚠️ 候诊信息仅供参考，请以院内叫号为准</p>`;
    $('#waitGoApt').onclick = () => {
      state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
      showView('appoint');
    };
    return;
  }

  const pickHtml = list.length ? `
    <div class="waiting-pick">
      <p class="section-label" style="margin:0 0 4px">选择预约</p>
      ${list.map((a) => `
        <button type="button" class="waiting-pick-btn ${a.id === aptId ? 'active' : ''}" data-apt="${escapeHtml(a.id)}">
          <strong>${escapeHtml(a.departmentName || '科室')}</strong>
          <small style="display:block;color:var(--text-muted)">${escapeHtml(a.doctorName || '')} · ${escapeHtml(a.slotLabel || '')} · ${escapeHtml(a.patientName || '')}${a.status ? ' · ' + escapeHtml(a.status) : ''}</small>
        </button>`).join('')}
    </div>` : '';

  box.innerHTML = `${pickHtml}<div class="waiting-card" id="waitingLiveCard"></div>`;
  box.querySelectorAll('.waiting-pick-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.waitingAppointmentId = btn.dataset.apt;
      renderWaiting(btn.dataset.apt);
    });
  });

  const status = await fetchWaitingStatus(aptId);
  state.waitingStatus = status;
  paintWaitingCard(status);
  if (status.status === '已报到候诊中' || status.status === '即将叫号') {
    startWaitingTicker(aptId);
  }
}

function msgIconMeta(type) {
  if (type === 'report') return { cls: 'report', icon: '🧪' };
  if (type === 'appointment') return { cls: 'appointment', icon: '📅' };
  if (type === 'exam') return { cls: 'exam', icon: '🩺' };
  if (type === 'delivery') return { cls: 'delivery', icon: '📦' };
  return { cls: 'system', icon: '📢' };
}

function msgPillCls(type) {
  if (type === 'report') return 'ready';
  if (type === 'appointment') return 'pending';
  if (type === 'exam') return 'lab';
  if (type === 'delivery') return 'pending';
  return 'lab';
}

async function renderMessages() {
  const box = $('#messagesList');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const filter = state.msgFilter || 'all';
  $$('#msgTabs .seg-tab').forEach((t) => t.classList.toggle('active', t.dataset.filter === filter));
  const filtered = await fetchMessages({ filter, forceRefresh: true });
  updateMsgBadge();
  const srcNote = state.messagesUsingApi
    ? `<p class="msg-source-hint">已联 8001 · 类型 tabs 本地归一筛选（API 支持 type / unreadCount）· 演示消息非真实推送</p>`
    : `<p class="msg-source-hint">离线 Mock · 演示消息非真实推送</p>`;
  if (!filtered.length) {
    box.innerHTML = `${srcNote}<div class="empty-state"><div class="big">📭</div><p>暂无此类消息</p></div>`;
    return;
  }
  box.innerHTML = srcNote + filtered.map((m) => {
    const meta = msgIconMeta(m.type);
    return `
      <button type="button" class="msg-card ${m.read ? '' : 'unread'}" data-id="${escapeHtml(m.id)}">
        <span class="msg-icon ${meta.cls}">${meta.icon}</span>
        <span class="msg-body">
          <p class="msg-title">${escapeHtml(m.title)}</p>
          <p class="msg-preview"><span class="msg-type-tag">${escapeHtml(m.typeLabel)}</span> · ${escapeHtml(m.body)}</p>
          <p class="msg-time">${escapeHtml(formatMsgTimeFull(m.createdAt))}</p>
        </span>
        ${m.read ? '' : '<span class="msg-unread-dot" aria-label="未读"></span>'}
      </button>`;
  }).join('');
  box.querySelectorAll('.msg-card').forEach((btn) => {
    btn.addEventListener('click', async () => {
      state.currentMessageId = btn.dataset.id;
      await markMessageRead(btn.dataset.id);
      showView('message-detail');
    });
  });
}

async function renderMessageDetail(id) {
  const box = $('#messageDetailContent');
  if (!box) return;
  if (!state.messagesCache) await fetchMessages({ filter: 'all', forceRefresh: true });
  const list = state.messagesCache || [];
  const m = list.find((x) => x.id === id);
  if (!m) {
    box.innerHTML = `<div class="empty-state"><p>消息不存在</p></div>`;
    return;
  }
  await markMessageRead(m.id);
  let actions = '';
  if (m.type === 'report' || m.relatedType === 'report') {
    actions = `<button type="button" class="btn primary block" id="msgGoReport">去查看报告</button>`;
  } else if (m.type === 'exam' || m.relatedType === 'exam') {
    actions = `
      <button type="button" class="btn primary block" id="msgGoExamMine">去我的检查</button>
      <button type="button" class="btn ghost block" id="msgGoExam">检查检验预约</button>`;
  } else if (m.type === 'delivery' || m.relatedType === 'delivery') {
    actions = `
      <button type="button" class="btn primary block" id="msgGoDelivery">去我的配送</button>
      <button type="button" class="btn ghost block" id="msgGoPharmacy">药品配送</button>`;
  } else if (m.relatedType === 'navigation') {
    actions = `<button type="button" class="btn primary block" id="msgGoNav">查看科室导航</button>`;
  } else if (m.type === 'appointment' || m.relatedType === 'waiting' || m.relatedType === 'appointment') {
    actions = `
      <button type="button" class="btn primary block" id="msgGoWaiting">去候诊报到</button>
      <button type="button" class="btn ghost block" id="msgGoMine">我的预约</button>`;
  } else if (m.link === '/waiting' || (m.body || '').includes('候诊')) {
    actions = `<button type="button" class="btn primary block" id="msgGoWaiting">去候诊报到</button>`;
  }
  box.innerHTML = `
    <div class="msg-detail-card">
      <span class="status-pill ${msgPillCls(m.type)}">${escapeHtml(m.typeLabel)}</span>
      <h3>${escapeHtml(m.title)}</h3>
      <p class="msg-time">${escapeHtml(formatMsgTimeFull(m.createdAt))} · ${sourceLabel(m.source)}</p>
      <p class="msg-content">${escapeHtml(m.body)}</p>
      <p class="msg-disclaimer-inline">演示消息，非真实推送通道。</p>
      <div class="actions-row" style="flex-direction:column;gap:8px">${actions}</div>
    </div>`;
  $('#msgGoReport')?.addEventListener('click', () => {
    state.currentReportId = m.relatedId || 'lab-1';
    state.reportsTab = 'lab';
    showView('report-detail');
  });
  $('#msgGoExamMine')?.addEventListener('click', () => showView('exam-mine'));
  $('#msgGoExam')?.addEventListener('click', () => showView('exam'));
  $('#msgGoDelivery')?.addEventListener('click', () => {
    if (m.relatedId) {
      state.pharmDeliveryId = m.relatedId;
      showView('pharmacy-delivery');
    } else {
      showView('pharmacy-deliveries');
    }
  });
  $('#msgGoPharmacy')?.addEventListener('click', () => showView('pharmacy'));
  $('#msgGoWaiting')?.addEventListener('click', () => {
    state.waitingAppointmentId = (m.relatedType === 'appointment' ? m.relatedId : null) || state.waitingAppointmentId;
    showView('waiting');
  });
  $('#msgGoMine')?.addEventListener('click', () => showView('mine'));
  $('#msgGoNav')?.addEventListener('click', () => {
    if (m.relatedId) {
      state.currentNavDeptId = m.relatedId;
      showView('nav-detail');
    } else {
      showView('nav');
    }
  });
}

function parseLocationString(loc) {
  if (!loc) return {};
  if (typeof loc === 'object') return loc;
  const s = String(loc);
  const floorM = s.match(/(\d+F|B\d+)/i);
  const buildingM = s.match(/^(.*?(?:楼|院区|中心))/);
  let zone = '';
  const zoneM = s.match(/(东区|西区|南区|北区|中区|急诊区|[A-D]区)/);
  if (zoneM) zone = zoneM[1];
  return {
    floor: floorM ? floorM[1].toUpperCase() : '',
    building: buildingM ? buildingM[1] : (s.includes('急诊') ? '急诊楼' : '门诊楼'),
    zone,
    raw: s
  };
}

function enrichNavDept(d) {
  const locObj = parseLocationString(d.location);
  const mock = MOCK_NAV_LOCATIONS[d.id] || {};
  const floor = d.floor || locObj.floor || mock.floor || '—';
  const zone = d.zone || locObj.zone || mock.zone || '';
  const building = d.building || locObj.building || mock.building || '门诊楼';
  const locText = typeof d.location === 'string' ? d.location : (locObj.raw || `${building}${floor} ${zone}`.trim());
  let tips = d.tips || d.routeHint || d.route || mock.tips || '';
  if (!tips || !String(tips).includes('→')) {
    const route = `${mock.gate || '1号门'} → ${mock.elevator && mock.elevator !== '—' ? mock.elevator : '直行'} → ${locText || (floor + ' ' + (d.name || ''))}`;
    tips = tips ? `${route}（${tips}）` : route;
  }
  const routeSteps = d.routeSteps || String(tips).split(/\s*→\s*/).filter(Boolean);
  return {
    ...d,
    floor, zone, building, tips, routeSteps,
    locationText: locText,
    gate: d.gate || mock.gate || '1号门',
    elevator: d.elevator || mock.elevator || '电梯A',
    desc: d.intro || d.desc || '',
    disclaimer: d.disclaimer || '导航文案为院内占位，请以现场指引为准'
  };
}

async function fetchNavDepartments() {
  try {
    const data = await apiFetch('/api/navigation/departments');
    const list = Array.isArray(data) ? data : (data.items || data.departments || []);
    if (list.length) return list.map((d) => enrichNavDept({ ...d, source: 'api' }));
  } catch { /* fallthrough */ }
  try {
    const depts = await getDepartments();
    return depts.map((d) => enrichNavDept({ ...d, source: d.source || 'api' }));
  } catch {
    return MOCK_DEPARTMENTS.map((d) => enrichNavDept({ ...d, source: 'mock' }));
  }
}

async function fetchNavDeptDetail(deptId) {
  try {
    const data = await apiFetch(`/api/navigation/${encodeURIComponent(deptId)}`);
    return enrichNavDept({ ...data, id: data.id || deptId, source: 'api' });
  } catch {
    const list = await fetchNavDepartments();
    return list.find((d) => d.id === deptId) || enrichNavDept({ id: deptId, name: '未知科室', source: 'mock' });
  }
}

function renderNavSchematic(activeFloor) {
  const el = $('#navSchematic');
  if (!el) return;
  const floors = ['5F', '4F', '3F', '2F', '1F'];
  const highlight = activeFloor || '';
  el.innerHTML = `
    <svg viewBox="0 0 320 200" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="院区示意图">
      <rect x="20" y="20" width="200" height="160" rx="12" fill="#fff" stroke="#99f6e4" stroke-width="2"/>
      <text x="120" y="42" text-anchor="middle" font-size="12" fill="#0f766e" font-weight="700">门诊楼示意</text>
      ${floors.map((f, i) => {
        const y = 55 + i * 24;
        const on = f === highlight;
        return `<rect x="40" y="${y}" width="160" height="20" rx="4" fill="${on ? '#99f6e4' : '#f0fdfa'}" stroke="#5eead4"/>
          <text x="120" y="${y + 14}" text-anchor="middle" font-size="11" fill="#134e4a">${f}${on ? ' ●' : ''}</text>`;
      }).join('')}
      <rect x="240" y="120" width="60" height="60" rx="8" fill="#fee2e2" stroke="#fca5a5"/>
      <text x="270" y="155" text-anchor="middle" font-size="11" fill="#991b1b">急诊</text>
      <circle cx="50" cy="175" r="6" fill="#0d9488"/>
      <text x="62" y="179" font-size="10" fill="#64748b">1号门</text>
    </svg>
    <p class="schematic-caption">示意占位，非真实地图 / GIS</p>`;
}

async function renderNav() {
  const box = $('#navList');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchNavDepartments();
  state.navDepts = list;
  const q = (state.navQuery || '').trim().toLowerCase();
  const filtered = !q ? list : list.filter((d) =>
    [d.name, d.floor, d.zone, d.building, d.tips, d.desc].join(' ').toLowerCase().includes(q)
  );
  renderNavSchematic(filtered[0]?.floor);
  if (!filtered.length) {
    box.innerHTML = `<div class="empty-state"><p>无匹配科室</p></div>`;
    return;
  }
  box.innerHTML = filtered.map((d) => `
    <button type="button" class="nav-dept-card" data-id="${escapeHtml(d.id)}">
      <span class="nav-dept-floor">${escapeHtml(d.floor)}</span>
      <span>
        <strong>${escapeHtml(d.name)}</strong>
        <small>${escapeHtml(d.building)} ${escapeHtml(d.zone)} · ${escapeHtml(d.tips)}</small>
      </span>
    </button>`).join('');
  box.querySelectorAll('.nav-dept-card').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.currentNavDeptId = btn.dataset.id;
      showView('nav-detail');
    });
  });
}

async function renderNavDetail(deptId) {
  const box = $('#navDetailContent');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const d = await fetchNavDeptDetail(deptId);
  renderNavSchematic(d.floor);
  // keep schematic visible on detail? schematic is on nav view; paint local map here
  box.innerHTML = `
    <div class="report-detail-card">
      <h3>${escapeHtml(d.name)}</h3>
      <dl class="report-kv">
        <dt>位置</dt><dd>${escapeHtml(d.locationText || (d.building + ' ' + d.floor + ' ' + (d.zone || '')).trim())}</dd>
        <dt>楼宇</dt><dd>${escapeHtml(d.building)}</dd>
        <dt>楼层</dt><dd>${escapeHtml(d.floor)} ${escapeHtml(d.zone || '')}</dd>
        <dt>入口</dt><dd>${escapeHtml(d.gate || '—')}</dd>
        <dt>电梯</dt><dd>${escapeHtml(d.elevator || '—')}</dd>
      </dl>
      <div class="nav-detail-map">
        <div style="font-size:2rem;margin-bottom:6px">🗺️</div>
        <strong>${escapeHtml(d.floor)} · ${escapeHtml(d.name)}</strong>
        <p class="ref-note" style="margin:6px 0 0">示意图占位，非真实导航</p>
      </div>
      <h4 style="margin:0 0 8px;font-size:0.85rem;color:var(--text-muted)">路线提示</h4>
      <ul class="nav-route-steps">
        ${(d.routeSteps || []).map((s) => `<li>${escapeHtml(s)}</li>`).join('') || `<li>${escapeHtml(d.tips)}</li>`}
      </ul>
      <p class="waiting-disclaimer" style="margin-top:14px">路线文案为演示占位，请以院内指示牌与工作人员指引为准。</p>
      <div class="actions-row" style="margin-top:12px;gap:8px;flex-wrap:wrap">
        <button type="button" class="btn primary" id="navGoAppoint">预约该科室</button>
        <button type="button" class="btn ghost" id="navBackList">返回列表</button>
      </div>
    </div>`;
  $('#navBackList')?.addEventListener('click', () => showView('nav'));
  $('#navGoAppoint')?.addEventListener('click', () => {
    state.preferredDept = d.name;
    state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
    showView('appoint');
  });
}

/* ========== M3 · 诊后与用药 ========== */

const REFILL_STATUS_MAP = {
  pending: { label: '待审核', cls: 'pending' },
  '待审核': { label: '待审核', cls: 'pending' },
  approved: { label: '已受理', cls: 'accepted' },
  accepted: { label: '已受理', cls: 'accepted' },
  '已受理': { label: '已受理', cls: 'accepted' },
  need_more: { label: '需补充材料', cls: 'need' },
  need_materials: { label: '需补充材料', cls: 'need' },
  '需补充材料': { label: '需补充材料', cls: 'need' },
  rejected: { label: '已拒绝', cls: 'rejected' },
  '已拒绝': { label: '已拒绝', cls: 'rejected' },
  cancelled: { label: '已取消', cls: 'cancelled' },
  '已取消': { label: '已取消', cls: 'cancelled' },
  completed: { label: '已完成', cls: 'done' },
  done: { label: '已完成', cls: 'done' },
  '已完成': { label: '已完成', cls: 'done' }
};

const REFILL_MOCK_FLOW = ['pending', 'approved', 'completed'];
const SCHEDULE_PRESETS = [
  { id: 'morning', label: '早', time: '08:00' },
  { id: 'noon', label: '中', time: '12:00' },
  { id: 'evening', label: '晚', time: '18:00' }
];

function todayKey() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function loadLocalRefills() {
  try { return JSON.parse(localStorage.getItem(REFILLS_KEY) || '[]'); } catch { return []; }
}
function saveLocalRefills(list) {
  localStorage.setItem(REFILLS_KEY, JSON.stringify(list));
}
function loadLocalReminders() {
  try { return JSON.parse(localStorage.getItem(MED_REMINDERS_KEY) || 'null'); } catch { return null; }
}
function saveLocalReminders(list) {
  localStorage.setItem(MED_REMINDERS_KEY, JSON.stringify(list));
}
function loadLocalTodayTaken() {
  try {
    const obj = JSON.parse(localStorage.getItem(MED_TODAY_KEY) || '{}');
    if (obj.date !== todayKey()) return { date: todayKey(), taken: {} };
    return obj;
  } catch {
    return { date: todayKey(), taken: {} };
  }
}
function saveLocalTodayTaken(obj) {
  localStorage.setItem(MED_TODAY_KEY, JSON.stringify(obj));
}
function loadLocalFollowupResponses() {
  try { return JSON.parse(localStorage.getItem(FOLLOWUP_RESP_KEY) || '[]'); } catch { return []; }
}
function saveLocalFollowupResponses(list) {
  localStorage.setItem(FOLLOWUP_RESP_KEY, JSON.stringify(list));
}

function seedRemindersIfNeeded() {
  let list = loadLocalReminders();
  if (Array.isArray(list) && list.length) return list;
  const ap = getActivePatient();
  list = [
    {
      id: 'rmd-seed-1',
      patientId: ap?.id || 'p-self',
      drugName: '氨氯地平片',
      dose: '5mg',
      schedule: ['morning', 'evening'],
      times: ['08:00', '18:00'],
      enabled: true,
      source: 'seed'
    },
    {
      id: 'rmd-seed-2',
      patientId: ap?.id || 'p-self',
      drugName: '二甲双胍缓释片',
      dose: '500mg',
      schedule: ['morning', 'noon', 'evening'],
      times: ['08:00', '12:00', '18:00'],
      enabled: true,
      source: 'seed'
    }
  ];
  saveLocalReminders(list);
  return list;
}

function normalizeRefill(r, source) {
  if (!r) return null;
  const raw = r.status || 'pending';
  const meta = REFILL_STATUS_MAP[raw] || REFILL_STATUS_MAP.pending;
  const drugs = r.drugNames || r.drugs || r.medications || [];
  let drugNames = Array.isArray(drugs)
    ? drugs.map((d) => (typeof d === 'string' ? d : (d.name || d.drugName || ''))).filter(Boolean)
    : String(drugs || '').split(/[,，、]/).map((s) => s.trim()).filter(Boolean);
  if (!drugNames.length && r.medicationName) drugNames = [r.medicationName];
  const dosage = r.dosage || r.dose || '';
  const quantity = r.quantity || '';
  return {
    id: r.id || ('rf-' + Date.now()),
    patientId: r.patientId || '',
    patientName: r.patientName || '',
    departmentId: r.departmentId || '',
    departmentName: r.departmentName || r.department || r.originalDept || '',
    medicationName: r.medicationName || drugNames[0] || '',
    drugNames,
    dosage,
    quantity,
    reason: r.reason || '',
    urgency: r.urgency || 'normal',
    note: r.note || r.remark || r.reviewNote || '',
    reviewNote: r.reviewNote || '',
    status: raw,
    statusLabel: r.statusLabel || meta.label,
    statusCls: meta.cls,
    createdAt: r.createdAt || r.submittedAt || new Date().toISOString(),
    updatedAt: r.updatedAt || r.createdAt || new Date().toISOString(),
    disclaimer: r.disclaimer || '不构成处方，需医生审核；急危请急诊',
    source: source || r.source || 'api'
  };
}

function normalizeReminder(r, source) {
  if (!r) return null;
  let schedule = r.schedule || r.slots || [];
  if (typeof schedule === 'string') schedule = schedule.split(/[,，、]/).map((s) => s.trim()).filter(Boolean);
  const times = r.times || schedule.map((s) => {
    const hit = SCHEDULE_PRESETS.find((p) => p.id === s || p.label === s);
    return hit ? hit.time : (/\d{1,2}:\d{2}/.test(s) ? s : '');
  }).filter(Boolean);
  const schedIds = schedule.map((s) => {
    const hit = SCHEDULE_PRESETS.find((p) => p.id === s || p.label === s || p.time === s);
    return hit ? hit.id : s;
  });
  return {
    id: r.id || ('rmd-' + Date.now()),
    patientId: r.patientId || '',
    drugName: r.drugName || r.name || '',
    dose: r.dose || r.dosage || '',
    schedule: schedIds,
    times,
    enabled: r.enabled !== false && r.enabled !== 0,
    source: source || r.source || 'api'
  };
}

function normalizeTodayItem(t, source) {
  if (!t) return null;
  const time = t.time || '';
  const reminderId = t.reminderId || t.id || '';
  const preset = SCHEDULE_PRESETS.find((p) => p.time === time || p.id === t.slot || p.id === t.scheduleSlot);
  return {
    id: t.id || `${reminderId}-${time || t.slot || 'x'}`,
    reminderId,
    drugName: t.drugName || t.name || '',
    dose: t.dose || '',
    slot: t.slot || t.scheduleSlot || t.schedule || (preset?.id || ''),
    slotLabel: t.slotLabel || t.scheduleLabel || preset?.label || time || t.slot || '',
    time,
    taken: !!(t.taken || t.takenAt || t.done),
    patientId: t.patientId || '',
    source: source || t.source || 'api'
  };
}

function normalizeSurvey(s, source) {
  if (!s) return null;
  const questions = (s.questions || s.items || []).map((q, i) => {
    let type = q.type || (q.options ? 'single' : 'text');
    if (type === 'choice' || type === 'radio') type = 'single';
    if (type === 'yes-no') type = 'yesno';
    const options = q.options || (type === 'yesno' ? ['是', '否'] : (type === 'scale' ? ['1', '2', '3', '4', '5'] : undefined));
    return {
      id: q.id || `q${i + 1}`,
      type,
      label: q.label || q.title || q.text || `问题 ${i + 1}`,
      options,
      required: q.required !== false
    };
  });
  return {
    id: s.id || ('sv-' + Date.now()),
    title: s.title || s.name || '随访问卷',
    description: s.description || s.desc || '',
    estimatedMinutes: s.estimatedMinutes || s.minutes || 3,
    questions,
    source: source || s.source || 'api'
  };
}

function normalizeFollowupResponse(r, source) {
  if (!r) return null;
  return {
    id: r.id || ('fr-' + Date.now()),
    surveyId: r.surveyId || '',
    surveyTitle: r.surveyTitle || r.title || '问卷',
    patientId: r.patientId || '',
    patientName: r.patientName || '',
    answers: r.answers || {},
    submittedAt: r.submittedAt || r.createdAt || new Date().toISOString(),
    source: source || r.source || 'api'
  };
}

function asList(data, keys = ['items', 'data', 'results', 'refills', 'reminders', 'surveys', 'responses', 'bills', 'logs', 'audit', 'orders', 'addresses', 'deliveries']) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== 'object') return [];
  for (const k of keys) {
    if (Array.isArray(data[k])) return data[k];
  }
  return [];
}

/* ----- Refills API / Mock ----- */
async function fetchRefills() {
  try {
    // List all demo applications; create still binds active patientId
    const data = await apiFetch('/api/refills');
    const list = asList(data).map((r) => normalizeRefill(r, 'api')).filter(Boolean);
    if (data && data.disclaimer && list[0] && !list[0].disclaimer) {
      list.forEach((r) => { r.disclaimer = data.disclaimer; });
    }
    if (list.length) {
      const local = loadLocalRefills().filter((x) => x.source === 'mock' || x.source === 'seed');
      const ids = new Set(list.map((x) => x.id));
      saveLocalRefills([...list, ...local.filter((x) => !ids.has(x.id))]);
      return list;
    }
    return loadLocalRefills().map((r) => normalizeRefill(r, r.source || 'mock'));
  } catch {
    return loadLocalRefills().map((r) => normalizeRefill(r, r.source || 'mock'));
  }
}

async function createRefill(payload) {
  const ap = getActivePatient();
  const medicationName = payload.medicationName || (payload.drugNames || []).join('、') || '';
  const body = {
    patientId: ap?.id,
    medicationName,
    dosage: payload.dosage || '',
    quantity: payload.quantity || '',
    reason: payload.reason || '',
    departmentId: payload.departmentId || ''
  };
  try {
    const data = await apiFetch('/api/refills', { method: 'POST', body: JSON.stringify(body) });
    const item = normalizeRefill(data.item || data.refill || data, 'api');
    // if API ignored free-text dept name, keep UI label from form
    if (!item.departmentName && payload.departmentName) item.departmentName = payload.departmentName;
    const list = loadLocalRefills();
    list.unshift(item);
    saveLocalRefills(list);
    return item;
  } catch {
    const item = normalizeRefill({
      id: 'rf-mock-' + Date.now(),
      patientId: ap?.id,
      patientName: ap?.name,
      medicationName,
      drugNames: payload.drugNames || [medicationName],
      dosage: payload.dosage || '',
      quantity: payload.quantity || '',
      departmentId: payload.departmentId || '',
      departmentName: payload.departmentName || '',
      reason: payload.reason || '',
      urgency: payload.urgency || 'normal',
      note: payload.note || '',
      status: 'pending',
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      source: 'mock'
    }, 'mock');
    const list = loadLocalRefills();
    list.unshift(item);
    saveLocalRefills(list);
    return item;
  }
}

function nextRefillStatus(cur, action) {
  if (action === 'reject') return 'rejected';
  if (action === 'cancel') return 'cancelled';
  if (action === 'need_more') return 'need_more';
  if (action === 'complete') return 'completed';
  if (action === 'advance') {
    if (cur === 'pending' || cur === '待审核') return 'approved';
    if (cur === 'approved' || cur === 'accepted' || cur === '已受理') return 'completed';
    if (cur === 'need_more' || cur === '需补充材料') return 'pending';
    return cur;
  }
  return cur;
}

async function patchRefill(id, patch) {
  const list0 = loadLocalRefills();
  const cur0 = list0.find((x) => x.id === id);
  let status = patch.status;
  if (!status && patch.action) status = nextRefillStatus(cur0?.status || 'pending', patch.action);
  // API only accepts pending|approved|rejected|cancelled — map mock-only statuses for request
  const apiStatus = ({
    completed: 'approved',
    done: 'approved',
    '已完成': 'approved',
    need_more: 'pending',
    need_materials: 'pending',
    '需补充材料': 'pending',
    '已受理': 'approved',
    '待审核': 'pending',
    '已拒绝': 'rejected',
    '已取消': 'cancelled'
  })[status] || status;

  try {
    const body = { status: apiStatus };
    if (patch.reviewNote != null) body.reviewNote = patch.reviewNote;
    else if (patch.note != null) body.reviewNote = patch.note;
    const data = await apiFetch(`/api/refills/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body)
    });
    let item = normalizeRefill(data.item || data.refill || data, 'api');
    // keep richer local status if we advanced to completed/need_more for demo UX
    if (status && status !== apiStatus) {
      item = normalizeRefill({ ...item, status }, item.source);
    }
    const list = loadLocalRefills();
    const idx = list.findIndex((x) => x.id === id);
    if (idx >= 0) list[idx] = { ...list[idx], ...item };
    else list.unshift(item);
    saveLocalRefills(list);
    return item;
  } catch {
    const list = loadLocalRefills();
    const idx = list.findIndex((x) => x.id === id);
    if (idx < 0) throw new Error('not found');
    const cur = list[idx];
    const item = normalizeRefill({
      ...cur,
      status: status || cur.status,
      reviewNote: patch.reviewNote != null ? patch.reviewNote : cur.reviewNote,
      note: patch.note != null ? patch.note : cur.note,
      updatedAt: new Date().toISOString(),
      source: 'mock'
    }, 'mock');
    list[idx] = item;
    saveLocalRefills(list);
    return item;
  }
}

/* ----- Medications API / Mock ----- */
async function fetchReminders() {
  seedRemindersIfNeeded();
  try {
    const data = await apiFetch('/api/medications/reminders');
    const list = asList(data).map((r) => normalizeReminder(r, 'api')).filter(Boolean);
    if (list.length) {
      saveLocalReminders(list);
      return list;
    }
    return seedRemindersIfNeeded().map((r) => normalizeReminder(r, r.source || 'mock'));
  } catch {
    return seedRemindersIfNeeded().map((r) => normalizeReminder(r, r.source || 'mock'));
  }
}

async function createReminder(payload) {
  const ap = getActivePatient();
  const times = payload.times || [];
  const freq = payload.frequency || (
    times.length === 1 ? '每日一次' : times.length === 2 ? '每日两次' : times.length >= 3 ? '每日三次' : ''
  );
  const body = {
    patientId: ap?.id,
    drugName: payload.drugName,
    dose: payload.dose,
    frequency: freq,
    times,
    enabled: payload.enabled !== false
  };
  try {
    const data = await apiFetch('/api/medications/reminders', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    const item = normalizeReminder(data.item || data.reminder || data, 'api');
    const list = loadLocalReminders() || [];
    list.unshift(item);
    saveLocalReminders(list);
    return item;
  } catch {
    const item = normalizeReminder({
      id: 'rmd-mock-' + Date.now(),
      ...body,
      source: 'mock'
    }, 'mock');
    const list = loadLocalReminders() || [];
    list.unshift(item);
    saveLocalReminders(list);
    return item;
  }
}

async function patchReminder(id, patch) {
  try {
    const data = await apiFetch(`/api/medications/reminders/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch)
    });
    const item = normalizeReminder(data.item || data.reminder || data, 'api');
    const list = loadLocalReminders() || [];
    const idx = list.findIndex((x) => x.id === id);
    if (idx >= 0) list[idx] = { ...list[idx], ...item };
    saveLocalReminders(list);
    return item;
  } catch {
    const list = loadLocalReminders() || [];
    const idx = list.findIndex((x) => x.id === id);
    if (idx < 0) throw new Error('not found');
    list[idx] = normalizeReminder({ ...list[idx], ...patch, source: 'mock' }, 'mock');
    saveLocalReminders(list);
    return list[idx];
  }
}

function buildTodayFromReminders(reminders) {
  const takenMap = loadLocalTodayTaken().taken || {};
  const items = [];
  reminders.filter((r) => r.enabled).forEach((r) => {
    const slots = (r.schedule && r.schedule.length)
      ? r.schedule
      : (r.times || []).map((t) => {
        const hit = SCHEDULE_PRESETS.find((p) => p.time === t);
        return hit ? hit.id : t;
      });
    slots.forEach((slot, i) => {
      const preset = SCHEDULE_PRESETS.find((p) => p.id === slot || p.label === slot);
      const time = (r.times && r.times[i]) || preset?.time || '';
      const id = `${r.id}-${slot || time || i}`;
      items.push(normalizeTodayItem({
        id,
        reminderId: r.id,
        drugName: r.drugName,
        dose: r.dose,
        slot: preset?.id || slot,
        slotLabel: preset?.label || slot,
        time,
        taken: !!takenMap[id],
        source: r.source
      }, r.source));
    });
  });
  const order = { morning: 1, noon: 2, evening: 3 };
  items.sort((a, b) => (order[a.slot] || 9) - (order[b.slot] || 9) || String(a.time).localeCompare(String(b.time)));
  return items;
}

async function fetchTodayMeds() {
  const reminders = await fetchReminders();
  try {
    const data = await apiFetch('/api/medications/today');
    const list = asList(data, ['items', 'data', 'today', 'medications']).map((t) => normalizeTodayItem(t, 'api'));
    if (list.length) {
      const takenMap = loadLocalTodayTaken().taken || {};
      return list.map((t) => ({ ...t, taken: t.taken || !!takenMap[t.id] }));
    }
    return buildTodayFromReminders(reminders);
  } catch {
    return buildTodayFromReminders(reminders);
  }
}

async function markTodayTaken(itemId, taken = true, meta = {}) {
  const obj = loadLocalTodayTaken();
  obj.date = todayKey();
  obj.taken = obj.taken || {};
  if (taken) obj.taken[itemId] = new Date().toISOString();
  else delete obj.taken[itemId];
  saveLocalTodayTaken(obj);

  const reminderId = meta.reminderId || String(itemId).replace(/-(\d{1,2}:\d{2})$/, '').replace(/-(morning|noon|evening)$/, '') || itemId;
  const time = meta.time || (String(itemId).match(/(\d{1,2}:\d{2})$/) || [])[1] || '';
  if (reminderId && time) {
    try {
      const body = taken ? { takenTime: time } : { untakenTime: time };
      await apiFetch(`/api/medications/reminders/${encodeURIComponent(reminderId)}`, {
        method: 'PATCH',
        body: JSON.stringify(body)
      });
    } catch { /* local already saved */ }
  }
  return true;
}

/* ----- Followups API / Mock ----- */
const SEED_SURVEYS = [
  {
    id: 'sv-post-opd',
    title: '门诊复诊随访',
    description: '了解您复诊后的症状变化与用药情况',
    estimatedMinutes: 3,
    questions: [
      { id: 'q1', type: 'scale', label: '目前整体不适程度（1 很轻 · 5 很重）', options: ['1', '2', '3', '4', '5'] },
      { id: 'q2', type: 'yesno', label: '是否仍按医嘱规律用药？', options: ['是', '否'] },
      { id: 'q3', type: 'yesno', label: '近期是否出现新的不适或不良反应？', options: ['是', '否'] },
      { id: 'q4', type: 'text', label: '如有补充说明，请简要描述' }
    ],
    source: 'seed'
  },
  {
    id: 'sv-med-safety',
    title: '用药安全随访',
    description: '关注漏服、副作用与复诊计划',
    estimatedMinutes: 2,
    questions: [
      { id: 'q1', type: 'yesno', label: '过去一周是否有漏服？', options: ['是', '否'] },
      { id: 'q2', type: 'scale', label: '对当前用药方案的信心（1–5）', options: ['1', '2', '3', '4', '5'] },
      { id: 'q3', type: 'text', label: '希望医生重点关注的问题' }
    ],
    source: 'seed'
  }
];

async function fetchSurveys() {
  try {
    const data = await apiFetch('/api/followups/surveys');
    const list = asList(data).map((s) => normalizeSurvey(s, 'api')).filter(Boolean);
    return list.length ? list : SEED_SURVEYS.map((s) => normalizeSurvey(s, 'seed'));
  } catch {
    return SEED_SURVEYS.map((s) => normalizeSurvey(s, 'seed'));
  }
}

async function fetchFollowupResponses() {
  const ap = getActivePatient();
  try {
    const q = ap?.id ? `?patientId=${encodeURIComponent(ap.id)}` : '';
    const data = await apiFetch(`/api/followups/responses${q}`);
    const list = asList(data).map((r) => normalizeFollowupResponse(r, 'api')).filter(Boolean);
    if (list.length) {
      const local = loadLocalFollowupResponses().filter((x) => x.source === 'mock' || x.source === 'seed');
      const ids = new Set(list.map((x) => x.id));
      saveLocalFollowupResponses([...list, ...local.filter((x) => !ids.has(x.id))]);
    }
    return list.length ? list : loadLocalFollowupResponses().map((r) => normalizeFollowupResponse(r, r.source || 'mock'));
  } catch {
    return loadLocalFollowupResponses().map((r) => normalizeFollowupResponse(r, r.source || 'mock'));
  }
}

async function submitSurvey(surveyId, answers, surveyMeta) {
  const ap = getActivePatient();
  const body = {
    patientId: ap?.id,
    patientName: ap?.name,
    answers
  };
  try {
    const data = await apiFetch(`/api/followups/surveys/${encodeURIComponent(surveyId)}/submit`, {
      method: 'POST',
      body: JSON.stringify(body)
    });
    const item = normalizeFollowupResponse(data.item || data.response || {
      ...data,
      surveyId,
      surveyTitle: surveyMeta?.title,
      answers,
      patientId: ap?.id,
      patientName: ap?.name
    }, 'api');
    const list = loadLocalFollowupResponses();
    list.unshift(item);
    saveLocalFollowupResponses(list);
    return item;
  } catch {
    const item = normalizeFollowupResponse({
      id: 'fr-mock-' + Date.now(),
      surveyId,
      surveyTitle: surveyMeta?.title || '问卷',
      patientId: ap?.id,
      patientName: ap?.name,
      answers,
      submittedAt: new Date().toISOString(),
      source: 'mock'
    }, 'mock');
    const list = loadLocalFollowupResponses();
    list.unshift(item);
    saveLocalFollowupResponses(list);
    return item;
  }
}

/* ----- Render: Refills ----- */
function syncSegTabs(rootSel, active) {
  $$(`${rootSel} .seg-tab`).forEach((t) => t.classList.toggle('active', t.dataset.tab === active));
}

async function renderRefills() {
  const box = $('#refillsContent');
  if (!box) return;
  syncSegTabs('#refillTabs', state.refillTab);
  const ap = getActivePatient();

  if (state.refillTab === 'form') {
    const depts = await getDepartments();
    const deptOpts = depts.map((d) =>
      `<option value="${escapeHtml(d.id)}">${escapeHtml(d.name)}</option>`
    ).join('');
    box.innerHTML = `
      <form id="refillForm" class="form-stack" autocomplete="off">
        <div class="info-chip">当前就诊人：<strong>${escapeHtml(ap?.name || '—')}</strong>
          <button type="button" class="link-btn" id="rfSwitchPatient">切换</button>
        </div>
        <label class="field">
          <span>原就诊科室 <em>*</em></span>
          <select id="rfDeptId" required>
            <option value="">请选择科室</option>
            ${deptOpts}
          </select>
        </label>
        <label class="field">
          <span>原用药名称 <em>*</em></span>
          <input type="text" id="rfMedName" required maxlength="80" placeholder="例如：氨氯地平片" />
        </label>
        <div class="field-row">
          <label class="field">
            <span>剂量</span>
            <input type="text" id="rfDosage" maxlength="40" placeholder="如：5mg 每日一次" />
          </label>
          <label class="field">
            <span>数量</span>
            <input type="text" id="rfQty" maxlength="20" placeholder="如：30片" />
          </label>
        </div>
        <label class="field">
          <span>申请原因 <em>*</em></span>
          <textarea id="rfReason" rows="3" required maxlength="300" placeholder="例如：慢性病稳定，需续开一个月用量"></textarea>
        </label>
        <fieldset class="field">
          <legend>紧急程度</legend>
          <div class="seg" id="rfUrgency">
            <label><input type="radio" name="rfUrgency" value="normal" checked /><span>常规</span></label>
            <label><input type="radio" name="rfUrgency" value="soon" /><span>尽快</span></label>
            <label><input type="radio" name="rfUrgency" value="urgent" /><span>较急</span></label>
          </div>
        </fieldset>
        <label class="field">
          <span>补充说明（可选）</span>
          <textarea id="rfNote" rows="2" maxlength="200" placeholder="过敏变化、近期检验等"></textarea>
        </label>
        <p class="waiting-disclaimer">提交后仅为申请记录，不构成处方；须医生审核。急危请急诊。</p>
        <button type="submit" class="btn primary block">提交申请</button>
      </form>`;
    $('#rfSwitchPatient')?.addEventListener('click', () => showView('patients'));
    $('#refillForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const departmentId = $('#rfDeptId').value;
      const departmentName = $('#rfDeptId').selectedOptions?.[0]?.textContent || '';
      const medicationName = $('#rfMedName').value.trim();
      const dosage = $('#rfDosage').value.trim();
      const quantity = $('#rfQty').value.trim();
      const reason = $('#rfReason').value.trim();
      const urgency = ($('input[name="rfUrgency"]:checked') || {}).value || 'normal';
      const note = $('#rfNote').value.trim();
      if (!departmentId || !medicationName || !reason) {
        toast('请完整填写必填项');
        return;
      }
      if (urgency === 'urgent') {
        toast('较急情况建议优先线下复诊或急诊');
      }
      // ensure patient id synced with API when possible
      try { await fetchPatients(); } catch { /* ignore */ }
      setLoading(true, '提交申请中…');
      try {
        await createRefill({
          departmentId,
          departmentName,
          medicationName,
          drugNames: [medicationName],
          dosage,
          quantity,
          reason: note ? `${reason}（说明：${note}）` : reason,
          urgency,
          note
        });
        toast('已提交，等待医生审核');
        state.refillTab = 'list';
        await renderRefills();
      } finally {
        setLoading(false);
      }
    });
    return;
  }

  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchRefills();
  const filtered = list;
  if (!filtered.length) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="big">💊</div>
        <p>暂无续方申请</p>
        <p class="ref-note">当前就诊人：${escapeHtml(ap?.name || '—')}</p>
        <button type="button" class="btn primary" id="rfGoForm" style="margin-top:12px">新建申请</button>
      </div>`;
    $('#rfGoForm')?.addEventListener('click', () => {
      state.refillTab = 'form';
      renderRefills();
    });
    return;
  }
  box.innerHTML = filtered.map((r) => `
    <article class="m3-card refill-card">
      <div class="m3-card-head">
        <h4>${escapeHtml(r.medicationName || (r.drugNames || []).join('、') || '续方申请')}</h4>
        <span class="status-pill ${r.statusCls}">${escapeHtml(r.statusLabel)}</span>
      </div>
      <p class="meta">科室：${escapeHtml(r.departmentName || '—')}
        ${r.dosage || r.quantity ? ` · ${escapeHtml([r.dosage, r.quantity].filter(Boolean).join(' / '))}` : ''}</p>
      <p class="meta">原因：${escapeHtml(r.reason || '—')}</p>
      ${r.reviewNote ? `<p class="meta">审核备注：${escapeHtml(r.reviewNote)}</p>` : ''}
      <p class="ref-note">${escapeHtml(r.disclaimer)} · ${sourceLabel(r.source)} · ${escapeHtml(String(r.createdAt).slice(0, 16).replace('T', ' '))}</p>
      <div class="m3-card-actions">
        ${r.status === 'pending' || r.status === '待审核' ? `
          <button type="button" class="btn ghost sm" data-advance="${escapeHtml(r.id)}">演示推进</button>
          <button type="button" class="btn ghost sm" data-need="${escapeHtml(r.id)}">需补充材料</button>
          <button type="button" class="btn ghost sm" data-reject="${escapeHtml(r.id)}">模拟拒绝</button>` : ''}
        ${r.status === 'approved' || r.status === 'accepted' || r.status === '已受理' || r.status === 'need_more' || r.status === '需补充材料' ? `
          <button type="button" class="btn ghost sm" data-advance="${escapeHtml(r.id)}">演示推进</button>` : ''}
        ${r.status === 'need_more' || r.status === '需补充材料' ? `
          <button type="button" class="btn primary sm" data-resubmit="${escapeHtml(r.id)}">去补充</button>` : ''}
      </div>
    </article>`).join('') + `
    <button type="button" class="btn primary block" id="rfNew" style="margin-top:8px">＋ 新建申请</button>`;

  $('#rfNew')?.addEventListener('click', () => {
    state.refillTab = 'form';
    renderRefills();
  });
  box.querySelectorAll('[data-advance]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      setLoading(true, '更新状态…');
      try {
        await patchRefill(btn.dataset.advance, { action: 'advance' });
        toast('状态已更新');
        await renderRefills();
      } finally { setLoading(false); }
    });
  });
  box.querySelectorAll('[data-need]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await patchRefill(btn.dataset.need, { action: 'need_more' });
      toast('已标记需补充材料');
      await renderRefills();
    });
  });
  box.querySelectorAll('[data-reject]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      await patchRefill(btn.dataset.reject, { action: 'reject', status: 'rejected' });
      toast('已标记拒绝');
      await renderRefills();
    });
  });
  box.querySelectorAll('[data-resubmit]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.refillTab = 'form';
      renderRefills();
      toast('请补充说明后重新提交');
    });
  });
}

/* ----- Render: Meds ----- */
async function renderMeds() {
  const box = $('#medsContent');
  if (!box) return;
  syncSegTabs('#medsTabs', state.medsTab);
  const ap = getActivePatient();

  if (state.medsTab === 'add') {
    box.innerHTML = `
      <form id="medForm" class="form-stack" autocomplete="off">
        <div class="info-chip">为 <strong>${escapeHtml(ap?.name || '—')}</strong> 添加提醒</div>
        <label class="field">
          <span>药品名称 <em>*</em></span>
          <input type="text" id="medName" required maxlength="40" placeholder="例如：氨氯地平片" />
        </label>
        <label class="field">
          <span>剂量 <em>*</em></span>
          <input type="text" id="medDose" required maxlength="30" placeholder="例如：5mg / 1 片" />
        </label>
        <fieldset class="field">
          <legend>服用时段 <em>*</em></legend>
          <div class="chips" id="medSchedule">
            ${SCHEDULE_PRESETS.map((p) => `
              <label class="chip"><input type="checkbox" name="medSched" value="${p.id}" /><span>${p.label} ${p.time}</span></label>
            `).join('')}
          </div>
        </fieldset>
        <label class="switch-row">
          <span>启用提醒</span>
          <input type="checkbox" id="medEnabled" checked />
        </label>
        <button type="submit" class="btn primary block">保存提醒</button>
      </form>`;
    $('#medForm')?.addEventListener('submit', async (e) => {
      e.preventDefault();
      const drugName = $('#medName').value.trim();
      const dose = $('#medDose').value.trim();
      const schedule = $$('input[name="medSched"]:checked').map((c) => c.value);
      const enabled = $('#medEnabled').checked;
      if (!drugName || !dose || !schedule.length) {
        toast('请填写药品、剂量并选择时段');
        return;
      }
      const times = schedule.map((id) => SCHEDULE_PRESETS.find((p) => p.id === id)?.time).filter(Boolean);
      setLoading(true, '保存中…');
      try {
        await createReminder({ drugName, dose, schedule, times, enabled });
        toast('已添加用药提醒');
        state.medsTab = 'list';
        await renderMeds();
      } finally { setLoading(false); }
    });
    return;
  }

  box.innerHTML = `<div class="empty-state">加载中…</div>`;

  if (state.medsTab === 'today') {
    const items = await fetchTodayMeds();
    if (!items.length) {
      box.innerHTML = `
        <div class="empty-state">
          <div class="big">⏰</div>
          <p>今日暂无待服</p>
          <button type="button" class="btn primary" id="medGoAdd" style="margin-top:12px">添加提醒</button>
        </div>`;
      $('#medGoAdd')?.addEventListener('click', () => { state.medsTab = 'add'; renderMeds(); });
      return;
    }
    const pending = items.filter((x) => !x.taken).length;
    box.innerHTML = `
      <div class="today-summary">
        <strong>今日待服</strong>
        <span>${pending} / ${items.length} 未服</span>
      </div>
      <div class="today-list">
        ${items.map((t) => `
          <label class="today-item ${t.taken ? 'taken' : ''}">
            <input type="checkbox" data-today-id="${escapeHtml(t.id)}"
              data-reminder-id="${escapeHtml(t.reminderId || '')}"
              data-time="${escapeHtml(t.time || '')}"
              ${t.taken ? 'checked' : ''} />
            <span class="today-body">
              <strong>${escapeHtml(t.drugName)}</strong>
              <small>${escapeHtml(t.slotLabel || '')}${t.time ? ' · ' + escapeHtml(t.time) : ''} · ${escapeHtml(t.dose || '')}</small>
            </span>
          </label>`).join('')}
      </div>
      <p class="ref-note" style="margin-top:10px">打卡同步服务端 takenTime（失败则本地） · ${sourceLabel(items[0]?.source)}</p>`;
    box.querySelectorAll('[data-today-id]').forEach((cb) => {
      cb.addEventListener('change', async () => {
        await markTodayTaken(cb.dataset.todayId, cb.checked, {
          reminderId: cb.dataset.reminderId,
          time: cb.dataset.time
        });
        toast(cb.checked ? '已标记已服' : '已取消');
        await renderMeds();
      });
    });
    return;
  }

  // list
  const list = await fetchReminders();
  if (!list.length) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="big">💊</div>
        <p>还没有用药提醒</p>
        <button type="button" class="btn primary" id="medGoAdd2" style="margin-top:12px">添加提醒</button>
      </div>`;
    $('#medGoAdd2')?.addEventListener('click', () => { state.medsTab = 'add'; renderMeds(); });
    return;
  }
  box.innerHTML = list.map((r) => {
    const sched = (r.schedule || []).map((s) => {
      const p = SCHEDULE_PRESETS.find((x) => x.id === s);
      return p ? `${p.label}${p.time}` : s;
    }).join(' · ') || (r.times || []).join(' · ');
    return `
      <article class="m3-card">
        <div class="m3-card-head">
          <h4>${escapeHtml(r.drugName)}</h4>
          <label class="switch-inline">
            <input type="checkbox" data-toggle="${escapeHtml(r.id)}" ${r.enabled ? 'checked' : ''} />
            <span>${r.enabled ? '开' : '关'}</span>
          </label>
        </div>
        <p class="meta">剂量：${escapeHtml(r.dose || '—')}</p>
        <p class="meta">时段：${escapeHtml(sched || '—')}</p>
        <p class="ref-note">${sourceLabel(r.source)}</p>
      </article>`;
  }).join('') + `
    <button type="button" class="btn primary block" id="medAddBtn" style="margin-top:8px">＋ 添加提醒</button>`;
  $('#medAddBtn')?.addEventListener('click', () => { state.medsTab = 'add'; renderMeds(); });
  box.querySelectorAll('[data-toggle]').forEach((cb) => {
    cb.addEventListener('change', async () => {
      await patchReminder(cb.dataset.toggle, { enabled: cb.checked });
      toast(cb.checked ? '已启用' : '已关闭');
      await renderMeds();
    });
  });
}

/* ----- Render: Followups ----- */
async function renderFollowups() {
  const box = $('#followupsContent');
  if (!box) return;
  syncSegTabs('#followupTabs', state.followupTab);
  box.innerHTML = `<div class="empty-state">加载中…</div>`;

  if (state.followupTab === 'history') {
    const list = await fetchFollowupResponses();
    if (!list.length) {
      box.innerHTML = `
        <div class="empty-state">
          <div class="big">📝</div>
          <p>暂无填写记录</p>
          <button type="button" class="btn primary" id="fuGoSurveys" style="margin-top:12px">去填问卷</button>
        </div>`;
      $('#fuGoSurveys')?.addEventListener('click', () => {
        state.followupTab = 'surveys';
        renderFollowups();
      });
      return;
    }
    box.innerHTML = list.map((r) => `
      <article class="m3-card">
        <div class="m3-card-head">
          <h4>${escapeHtml(r.surveyTitle)}</h4>
          <span class="status-pill done">已提交</span>
        </div>
        <p class="meta">${escapeHtml(String(r.submittedAt).slice(0, 16).replace('T', ' '))}
          ${r.patientName ? ` · ${escapeHtml(r.patientName)}` : ''}</p>
        <ul class="answer-preview">
          ${Object.entries(r.answers || {}).slice(0, 4).map(([k, v]) =>
            `<li><span>${escapeHtml(k)}</span>：${escapeHtml(typeof v === 'object' ? JSON.stringify(v) : String(v))}</li>`
          ).join('') || '<li>无明细</li>'}
        </ul>
        <p class="ref-note">${sourceLabel(r.source)}</p>
      </article>`).join('');
    return;
  }

  const surveys = await fetchSurveys();
  if (!surveys.length) {
    box.innerHTML = `<div class="empty-state"><p>暂无可用问卷</p></div>`;
    return;
  }
  box.innerHTML = surveys.map((s) => `
    <button type="button" class="m3-card survey-card" data-sid="${escapeHtml(s.id)}">
      <div class="m3-card-head">
        <h4>${escapeHtml(s.title)}</h4>
        <span class="status-pill lab">约 ${escapeHtml(String(s.estimatedMinutes))} 分钟</span>
      </div>
      <p class="meta">${escapeHtml(s.description || '')}</p>
      <p class="ref-note">${(s.questions || []).length} 题 · ${sourceLabel(s.source)}</p>
    </button>`).join('');
  box.querySelectorAll('[data-sid]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.currentSurveyId = btn.dataset.sid;
      showView('followup-form');
    });
  });
}

async function renderFollowupForm(surveyId) {
  const box = $('#followupFormContent');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const surveys = await fetchSurveys();
  const survey = surveys.find((s) => s.id === surveyId) || surveys[0];
  if (!survey) {
    box.innerHTML = `<div class="empty-state"><p>问卷不存在</p>
      <button type="button" class="btn ghost" id="fuBack">返回</button></div>`;
    $('#fuBack')?.addEventListener('click', () => showView('followups'));
    return;
  }
  state.currentSurveyId = survey.id;
  box.innerHTML = `
    <div class="m3-disclaimer soft"><p>${escapeHtml(survey.description || '诊后随访仅供参考，不能替代面诊。')}</p></div>
    <form id="surveyForm" class="form-stack">
      <h3 class="section-label" style="margin-top:0">${escapeHtml(survey.title)}</h3>
      ${(survey.questions || []).map((q) => {
        if (q.type === 'single' || q.type === 'scale' || q.type === 'choice' || q.type === 'yesno' || q.type === 'yes-no') {
          const opts = q.options || (String(q.type).includes('yes') ? ['是', '否'] : ['1', '2', '3', '4', '5']);
          return `
            <fieldset class="field">
              <legend>${escapeHtml(q.label)}${q.required ? ' <em>*</em>' : ''}</legend>
              <div class="seg wrap">
                ${opts.map((o) => `
                  <label><input type="radio" name="${escapeHtml(q.id)}" value="${escapeHtml(o)}" ${q.required ? 'required' : ''} /><span>${escapeHtml(o)}</span></label>
                `).join('')}
              </div>
            </fieldset>`;
        }
        if (q.type === 'number') {
          return `
            <label class="field">
              <span>${escapeHtml(q.label)}${q.required ? ' <em>*</em>' : ''}</span>
              <input type="number" name="${escapeHtml(q.id)}" ${q.required ? 'required' : ''} placeholder="请输入数字" />
            </label>`;
        }
        return `
          <label class="field">
            <span>${escapeHtml(q.label)}${q.required ? ' <em>*</em>' : ''}</span>
            <textarea name="${escapeHtml(q.id)}" rows="2" maxlength="300" ${q.required ? 'required' : ''} placeholder="请填写"></textarea>
          </label>`;
      }).join('')}
      <button type="submit" class="btn primary block">提交问卷</button>
      <button type="button" class="btn ghost block" id="fuCancel">取消</button>
    </form>`;
  $('#fuCancel')?.addEventListener('click', () => showView('followups'));
  $('#surveyForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const answers = {};
    (survey.questions || []).forEach((q) => {
      if (q.type === 'text' || q.type === 'number') {
        const raw = (e.target.elements[q.id]?.value || '').trim();
        answers[q.id] = q.type === 'number' && raw !== '' ? Number(raw) : raw;
      } else {
        const checked = e.target.querySelector(`input[name="${q.id}"]:checked`);
        answers[q.id] = checked ? checked.value : '';
      }
    });
    setLoading(true, '提交中…');
    try {
      await submitSurvey(survey.id, answers, survey);
      toast('提交成功，感谢反馈');
      state.followupTab = 'history';
      showView('followups');
    } finally {
      setLoading(false);
    }
  });
}

/* ========== M4 · 运营与合规增强 ========== */

const BILL_TYPE_LABEL = {
  registration: '挂号费',
  consult: '诊查费',
  lab: '检验费',
  exam: '检查费',
  medicine: '药费',
  other: '其他费用',
  '挂号费': '挂号费',
  '检查费': '检查费',
  '检验费': '检验费',
  '药费': '药费'
};

function maskIdNumber(id) {
  const s = String(id || '');
  if (s.length < 8) return s ? '****' : '';
  return s.slice(0, 4) + '**********' + s.slice(-4);
}

function maskPhone(phone) {
  const s = String(phone || '');
  if (s.length < 7) return s ? '****' : '';
  return s.slice(0, 3) + '****' + s.slice(-4);
}

/** 18 位身份证：格式 + 宽松校验码 */
function validateCnIdNumber(raw) {
  const id = String(raw || '').trim().toUpperCase();
  if (!id) return { ok: false, message: '请填写身份证号' };
  if (!/^\d{17}[\dX]$/.test(id)) {
    return { ok: false, message: '请输入 18 位身份证号（末位可为 X）' };
  }
  const weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2];
  const checks = '10X98765432';
  let sum = 0;
  for (let i = 0; i < 17; i++) sum += Number(id[i]) * weights[i];
  const expect = checks[sum % 11];
  if (id[17] !== expect) {
    return { ok: false, message: '身份证校验位不正确，请核对' };
  }
  return { ok: true, value: id };
}

function validateCnPhone(raw) {
  const p = String(raw || '').trim();
  if (!p) return { ok: false, message: '请填写手机号' };
  if (!/^1\d{10}$/.test(p)) return { ok: false, message: '请输入 11 位大陆手机号' };
  return { ok: true, value: p };
}

function seedBillsIfNeeded() {
  try {
    const existing = JSON.parse(localStorage.getItem(BILLS_KEY) || 'null');
    if (Array.isArray(existing) && existing.length) return existing;
  } catch { /* ignore */ }
  const ap = getActivePatient();
  const now = Date.now();
  const list = [
    {
      id: 'bill-seed-1',
      type: 'registration',
      title: '挂号费 · 呼吸内科',
      description: '普通门诊号源',
      amount: 25,
      status: 'unpaid',
      patientId: ap?.id || 'p-self',
      patientName: ap?.name || '本人',
      createdAt: new Date(now - 3600e3).toISOString(),
      source: 'seed'
    },
    {
      id: 'bill-seed-2',
      type: 'lab',
      title: '检验费 · 血常规',
      description: '门诊检验',
      amount: 48.5,
      status: 'unpaid',
      patientId: ap?.id || 'p-self',
      patientName: ap?.name || '本人',
      createdAt: new Date(now - 7200e3).toISOString(),
      source: 'seed'
    },
    {
      id: 'bill-seed-3',
      type: 'exam',
      title: '检查费 · 胸部 CT',
      description: '影像检查',
      amount: 320,
      status: 'unpaid',
      patientId: ap?.id || 'p-self',
      patientName: ap?.name || '本人',
      createdAt: new Date(now - 86400e3).toISOString(),
      source: 'seed'
    },
    {
      id: 'bill-seed-4',
      type: 'medicine',
      title: '药费 · 门诊取药',
      description: '已完成取药',
      amount: 86.2,
      status: 'paid',
      paidAt: new Date(now - 172800e3).toISOString(),
      receiptNo: 'RCPT-DEMO-0001',
      patientId: ap?.id || 'p-self',
      patientName: ap?.name || '本人',
      createdAt: new Date(now - 200000e3).toISOString(),
      source: 'seed'
    }
  ];
  localStorage.setItem(BILLS_KEY, JSON.stringify(list));
  return list;
}

function loadLocalBills() {
  return seedBillsIfNeeded();
}

function saveLocalBills(list) {
  localStorage.setItem(BILLS_KEY, JSON.stringify(list));
}

function normalizeBill(b, source) {
  if (!b) return null;
  const rawStatus = String(b.status || b.payStatus || 'unpaid').toLowerCase();
  let status = 'unpaid';
  if (['paid', 'success', '已缴', '已支付', 'paid_success'].includes(rawStatus) || rawStatus.includes('paid')) {
    status = 'paid';
  } else if (['unpaid', 'pending', '待缴', '待支付', 'to_pay'].includes(rawStatus) || rawStatus.includes('unpaid')) {
    status = 'unpaid';
  } else if (rawStatus.includes('缴') && !rawStatus.includes('待')) {
    status = 'paid';
  }
  const lineItems = Array.isArray(b.items)
    ? b.items.map((it) => ({
        name: it.name || it.title || it.itemName || '项目',
        amount: Number(it.amount ?? it.fee ?? 0)
      }))
    : [];
  const type = b.type || b.billType || b.category || (lineItems[0]?.name?.includes('挂号') ? 'registration'
    : lineItems[0]?.name?.includes('检验') || lineItems[0]?.name?.includes('血') ? 'lab'
    : lineItems[0]?.name?.includes('CT') || lineItems[0]?.name?.includes('检查') ? 'exam'
    : lineItems[0]?.name?.includes('药') ? 'medicine' : 'other');
  const amount = Number(b.amount ?? b.total ?? b.fee ?? 0);
  const descFromItems = lineItems.map((x) => x.name).filter(Boolean).join('、');
  return {
    id: b.id || b.billId || ('bill-' + Date.now()),
    type,
    typeLabel: BILL_TYPE_LABEL[type] || '费用',
    title: b.title || b.name || `${BILL_TYPE_LABEL[type] || '费用'}`,
    description: b.description || b.desc || b.remark || descFromItems || '',
    lineItems,
    amount: Number.isFinite(amount) ? amount : 0,
    currency: b.currency || 'CNY',
    status,
    statusLabel: status === 'paid' ? '已缴' : '待缴',
    patientId: b.patientId || '',
    patientName: b.patientName || '',
    createdAt: b.createdAt || b.createTime || new Date().toISOString(),
    paidAt: b.paidAt || b.payTime || '',
    receiptNo: b.receiptNo || b.receiptId || b.transactionId || '',
    disclaimer: b.disclaimer || '演示环境，非真实扣款',
    source: source || b.source || 'mock'
  };
}

function formatMoney(n) {
  const v = Number(n) || 0;
  return '¥' + v.toFixed(2);
}

async function fetchBills() {
  try {
    const data = await apiFetch('/api/bills');
    const list = asList(data, ['bills', 'items', 'data', 'results']).map((b) => normalizeBill(b, 'api')).filter(Boolean);
    if (list.length) {
      // keep API list as cache but do not wipe seed structure oddly
      saveLocalBills(list.map((b) => ({ ...b, source: 'api' })));
      return list;
    }
  } catch { /* fallthrough */ }
  return loadLocalBills().map((b) => normalizeBill(b, b.source || 'mock'));
}

async function payBill(billId) {
  try {
    const data = await apiFetch(`/api/bills/${encodeURIComponent(billId)}/pay`, {
      method: 'POST',
      body: JSON.stringify({ channel: 'mock', demo: true })
    });
    const bill = normalizeBill(data.bill || data.item || data, 'api');
    if (bill) {
      bill.status = 'paid';
      bill.statusLabel = '已缴';
      bill.paidAt = bill.paidAt || data.paidAt || new Date().toISOString();
      bill.receiptNo = bill.receiptNo || data.receiptNo || data.transactionId || ('RCPT-' + bill.id + '-' + Date.now());
      const local = loadLocalBills();
      const idx = local.findIndex((x) => String(x.id) === String(bill.id));
      if (idx >= 0) local[idx] = { ...local[idx], ...bill, source: 'api' };
      else local.unshift({ ...bill, source: 'api' });
      saveLocalBills(local);
      return {
        bill,
        receipt: {
          receiptNo: bill.receiptNo,
          paidAt: bill.paidAt,
          amount: bill.amount,
          title: bill.title,
          channel: data.channel || '模拟支付',
          disclaimer: data.disclaimer || bill.disclaimer || '演示环境，非真实扣款',
          source: 'api'
        }
      };
    }
  } catch { /* mock */ }

  const local = loadLocalBills();
  const idx = local.findIndex((x) => String(x.id) === String(billId));
  if (idx < 0) throw new Error('账单不存在');
  const bill = normalizeBill(local[idx], local[idx].source || 'mock');
  if (bill.status === 'paid') {
    return {
      bill,
      receipt: {
        receiptNo: bill.receiptNo || ('RCPT-MOCK-' + bill.id),
        paidAt: bill.paidAt || new Date().toISOString(),
        amount: bill.amount,
        title: bill.title,
        channel: '模拟支付',
        disclaimer: '演示环境，非真实扣款',
        source: 'mock'
      }
    };
  }
  bill.status = 'paid';
  bill.statusLabel = '已缴';
  bill.paidAt = new Date().toISOString();
  bill.receiptNo = 'RCPT-MOCK-' + Date.now();
  local[idx] = { ...local[idx], ...bill, source: 'mock' };
  saveLocalBills(local);
  return {
    bill,
    receipt: {
      receiptNo: bill.receiptNo,
      paidAt: bill.paidAt,
      amount: bill.amount,
      title: bill.title,
      channel: '模拟支付',
      disclaimer: '演示环境，非真实扣款',
      source: 'mock'
    }
  };
}

function loadLocalIdentity() {
  try {
    const obj = JSON.parse(localStorage.getItem(IDENTITY_KEY) || 'null');
    if (obj && typeof obj === 'object') return obj;
  } catch { /* ignore */ }
  return {
    name: '',
    idNumber: '',
    phone: '',
    hospitalCardNo: '',
    bound: false,
    updatedAt: '',
    realNameMasked: '',
    idCardMasked: '',
    visitCardLast4: ''
  };
}

function saveLocalIdentity(obj) {
  localStorage.setItem(IDENTITY_KEY, JSON.stringify(obj));
}

function normalizeIdentity(data, source) {
  if (!data) return null;
  const inner = data.binding || data.identity || data;
  const name = inner.name || inner.realName || '';
  const idNumber = inner.idNumber || inner.idNo || inner.idCard || '';
  const phone = inner.phone || inner.mobile || '';
  const hospitalCardNo = inner.hospitalCardNo || inner.cardNo || inner.visitCardNo || '';
  const realNameMasked = inner.realNameMasked || (name ? (name[0] + '*') : '');
  const idCardMasked = inner.idCardMasked || (idNumber ? maskIdNumber(idNumber) : '');
  const visitCardLast4 = inner.visitCardLast4 || (hospitalCardNo ? String(hospitalCardNo).slice(-4) : '');
  const bound = !!(inner.bound || inner.verified || name || idNumber || realNameMasked || idCardMasked);
  return {
    name,
    idNumber,
    phone,
    hospitalCardNo,
    realNameMasked,
    idCardMasked,
    visitCardLast4,
    bound,
    updatedAt: inner.updatedAt || inner.updateTime || '',
    disclaimer: data.disclaimer || inner.disclaimer || '演示占位，不对接公安/医保实名核验',
    source: source || 'mock'
  };
}

async function fetchIdentityBinding() {
  for (const path of ['/api/identity/binding', '/api/identity']) {
    try {
      const data = await apiFetch(path);
      const norm = normalizeIdentity(data, 'api');
      if (norm) {
        const prev = loadLocalIdentity();
        // API returns masked only — preserve local plaintext draft fields if same binding session
        const merged = {
          ...prev,
          ...norm,
          name: norm.name || prev.name || '',
          idNumber: norm.idNumber || prev.idNumber || '',
          phone: norm.phone || prev.phone || '',
          hospitalCardNo: norm.hospitalCardNo || prev.hospitalCardNo || '',
          source: 'api'
        };
        saveLocalIdentity(merged);
        return merged;
      }
    } catch { /* try next */ }
  }
  const local = loadLocalIdentity();
  return normalizeIdentity(local, 'mock');
}

async function saveIdentityBinding(payload) {
  // Backend UpdateIdentityRequest: realName / idNumber / visitCardNo
  const apiBody = {
    realName: payload.name,
    idNumber: payload.idNumber,
    visitCardNo: payload.hospitalCardNo || ''
  };
  const localExtra = {
    name: payload.name,
    idNumber: payload.idNumber,
    phone: payload.phone || '',
    hospitalCardNo: payload.hospitalCardNo || ''
  };
  for (const path of ['/api/identity/binding', '/api/identity']) {
    try {
      const data = await apiFetch(path, { method: 'PUT', body: JSON.stringify(apiBody) });
      const norm = normalizeIdentity(data, 'api') || normalizeIdentity({
        ...localExtra,
        bound: true,
        updatedAt: new Date().toISOString()
      }, 'api');
      const merged = {
        ...norm,
        name: payload.name,
        idNumber: payload.idNumber,
        phone: payload.phone || '',
        hospitalCardNo: payload.hospitalCardNo || '',
        bound: true,
        source: 'api'
      };
      saveLocalIdentity(merged);
      return merged;
    } catch { /* try next */ }
  }
  const local = {
    ...localExtra,
    bound: true,
    realNameMasked: payload.name ? (payload.name[0] + '*') : '',
    idCardMasked: maskIdNumber(payload.idNumber),
    visitCardLast4: payload.hospitalCardNo ? String(payload.hospitalCardNo).slice(-4) : '',
    updatedAt: new Date().toISOString(),
    disclaimer: '演示占位，不对接公安/医保实名核验',
    source: 'mock'
  };
  saveLocalIdentity(local);
  return normalizeIdentity(local, 'mock');
}

async function fetchAuditLogs() {
  try {
    const data = await apiFetch('/api/audit');
    const list = asList(data, ['logs', 'items', 'data', 'audit', 'results']);
    if (Array.isArray(list) && list.length) {
      return list.slice(0, 20).map((x) => ({
        id: x.id || '',
        action: x.detail || x.action || x.event || x.message || x.op || '操作',
        at: x.createdAt || x.at || x.time || '',
        source: 'api'
      }));
    }
  } catch { /* mock */ }
  return [
    { id: 'a1', action: '查看导诊建议', at: new Date(Date.now() - 3600e3).toISOString(), source: 'mock' },
    { id: 'a2', action: '创建预约（演示）', at: new Date(Date.now() - 7200e3).toISOString(), source: 'mock' },
    { id: 'a3', action: '打开设置与须知', at: new Date().toISOString(), source: 'mock' }
  ];
}

function clearDemoLocalData() {
  const keys = [
    STORAGE_KEY, PATIENTS_KEY, ACTIVE_PATIENT_KEY, PROFILES_KEY, PRECONSULT_KEY,
    REPORTS_CACHE_KEY, REFILLS_KEY, MED_REMINDERS_KEY, MED_TODAY_KEY, FOLLOWUP_RESP_KEY,
    BILLS_KEY, IDENTITY_KEY, DC_SESSIONS_KEY, EXAM_BOOKINGS_KEY, EXAM_SLOTS_KEY,
    PHARMACY_ORDERS_KEY, PHARMACY_ADDRESSES_KEY, PHARMACY_DELIVERIES_KEY, CHRONIC_VITALS_KEY,
    'triage_messages_v1', 'triage_waiting_v1', 'triage_messages_read_v1',
    'triage_demo_step_done_v1'
  ];
  keys.forEach((k) => {
    try { localStorage.removeItem(k); } catch (_) {}
  });
}

async function renderBills() {
  const box = $('#billsContent');
  if (!box) return;
  syncSegTabs('#billsTabs', state.billsFilter);
  // syncSegTabs uses data-tab; bills use data-filter — set manually
  $$('#billsTabs .seg-tab').forEach((t) => {
    t.classList.toggle('active', (t.dataset.filter || '') === state.billsFilter);
  });
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchBills();
  const filtered = list.filter((b) => {
    if (state.billsFilter === 'unpaid') return b.status === 'unpaid';
    if (state.billsFilter === 'paid') return b.status === 'paid';
    return true;
  });
  if (!filtered.length) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="big">💳</div>
        <p>${state.billsFilter === 'paid' ? '暂无已缴账单' : state.billsFilter === 'unpaid' ? '暂无待缴账单' : '暂无账单'}</p>
        <p class="ref-note">演示环境，非真实扣款</p>
      </div>`;
    return;
  }
  box.innerHTML = filtered.map((b) => `
    <button type="button" class="m3-card bill-card" data-bid="${escapeHtml(b.id)}">
      <div class="m3-card-head">
        <h4>${escapeHtml(b.title)}</h4>
        <span class="status-pill ${b.status === 'paid' ? 'paid' : 'unpaid'}">${escapeHtml(b.statusLabel)}</span>
      </div>
      <p class="meta">${escapeHtml(b.description || b.typeLabel)}
        ${b.patientId ? '<br/>就诊人 ID：' + escapeHtml(b.patientId) : ''}
        ${b.patientName ? '<br/>就诊人：' + escapeHtml(b.patientName) : ''}</p>
      <div class="m3-card-head" style="margin:8px 0 0;align-items:center">
        <span class="bill-amount ${b.status === 'paid' ? 'paid' : ''}">${formatMoney(b.amount)}</span>
        <span class="meta">${b.status === 'paid' ? '查看回执' : '去支付 →'}</span>
      </div>
      <p class="ref-note">${sourceLabel(b.source)} · 演示非真实扣款</p>
    </button>`).join('');
  box.querySelectorAll('[data-bid]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.currentBillId = btn.dataset.bid;
      state.lastPayReceipt = null;
      showView('bill-pay');
    });
  });
}

async function renderBillPay(billId) {
  const box = $('#billPayContent');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;

  if (state.lastPayReceipt && state.lastPayReceipt.billId === billId) {
    const r = state.lastPayReceipt;
    box.innerHTML = `
      <div class="pay-receipt">
        <div class="receipt-icon">✓</div>
        <h3>模拟支付成功</h3>
        <p class="meta">演示环境，非真实扣款</p>
        <div class="receipt-amount">${formatMoney(r.amount)}</div>
        <dl>
          <dt>项目</dt><dd>${escapeHtml(r.title)}</dd>
          <dt>回执号</dt><dd>${escapeHtml(r.receiptNo)}</dd>
          <dt>时间</dt><dd>${escapeHtml(String(r.paidAt).slice(0, 19).replace('T', ' '))}</dd>
          <dt>渠道</dt><dd>${escapeHtml(r.channel || '模拟支付')}</dd>
          <dt>来源</dt><dd>${escapeHtml(sourceLabel(r.source))}</dd>
        </dl>
      </div>
      <p class="ref-note" style="margin:12px 0">${escapeHtml(r.disclaimer || '演示环境，非真实扣款')}</p>
      <button type="button" class="btn primary block" id="billBackList">返回账单列表</button>
      <button type="button" class="btn ghost block" id="billGoMine" style="margin-top:8px">回到「我的」</button>`;
    $('#billBackList')?.addEventListener('click', () => {
      state.billsFilter = 'paid';
      showView('bills');
    });
    $('#billGoMine')?.addEventListener('click', () => showView('mine'));
    return;
  }

  const list = await fetchBills();
  const bill = list.find((b) => String(b.id) === String(billId));
  if (!bill) {
    box.innerHTML = `<div class="empty-state"><p>账单不存在</p>
      <button type="button" class="btn ghost" id="billMissingBack">返回</button></div>`;
    $('#billMissingBack')?.addEventListener('click', () => showView('bills'));
    return;
  }

  if (bill.status === 'paid') {
    state.lastPayReceipt = {
      billId: bill.id,
      receiptNo: bill.receiptNo || ('RCPT-' + bill.id),
      paidAt: bill.paidAt || bill.createdAt,
      amount: bill.amount,
      title: bill.title,
      channel: '模拟支付',
      disclaimer: bill.disclaimer,
      source: bill.source
    };
    return renderBillPay(billId);
  }

  const linesHtml = (bill.lineItems || []).length
    ? `<ul class="answer-preview">${bill.lineItems.map((it) =>
        `<li><span>${escapeHtml(it.name)}</span>：${formatMoney(it.amount)}</li>`).join('')}</ul>`
    : (bill.description ? `<p class="meta">${escapeHtml(bill.description)}</p>` : '');
  box.innerHTML = `
    <div class="confirm-pay-card">
      <p class="meta">待支付</p>
      <h3 style="margin:0">${escapeHtml(bill.title)}</h3>
      ${linesHtml}
      <div class="big-amt">${formatMoney(bill.amount)}</div>
      <p class="meta">${bill.patientName ? '就诊人：' + escapeHtml(bill.patientName) + ' · ' : ''}${bill.patientId ? 'ID ' + escapeHtml(bill.patientId) + ' · ' : ''}${sourceLabel(bill.source)}</p>
    </div>
    <div class="m3-disclaimer soft" role="note">
      <p><strong>演示环境，非真实扣款。</strong>点击下方按钮仅模拟支付成功，不会连接微信/支付宝等真实网关。</p>
    </div>
    <button type="button" class="btn primary block" id="btnConfirmPay">确认模拟支付</button>
    <button type="button" class="btn ghost block" id="btnCancelPay" style="margin-top:8px">取消</button>`;
  $('#btnCancelPay')?.addEventListener('click', () => showView('bills'));
  $('#btnConfirmPay')?.addEventListener('click', async () => {
    setLoading(true, '模拟支付中…');
    try {
      const result = await payBill(bill.id);
      state.lastPayReceipt = {
        billId: result.bill.id,
        ...result.receipt
      };
      toast('模拟支付成功');
      await renderBillPay(bill.id);
    } catch (e) {
      toast('支付失败，请重试');
    } finally {
      setLoading(false);
    }
  });
}

async function renderIdentity() {
  const box = $('#identityContent');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const binding = await fetchIdentityBinding();
  const ap = getActivePatient();
  box.innerHTML = `
    <div class="identity-banner" role="note">
      <span aria-hidden="true">ℹ️</span>
      <span>演示占位，不对接公安 / 医保实名核验。信息仅用于本机演示或演示 API。</span>
    </div>
    <div class="info-chip" style="margin-bottom:12px">
      <span>状态</span>
      <strong>${binding.bound ? '已绑定（演示）' : '未绑定'}</strong>
      <span class="status-pill ${binding.bound ? 'bound' : 'unbound'}">${binding.bound ? '已保存' : '待完善'}</span>
      ${binding.realNameMasked ? `<span class="meta">${escapeHtml(binding.realNameMasked)}</span>` : ''}
      ${binding.idCardMasked ? `<span class="masked-id meta">${escapeHtml(binding.idCardMasked)}</span>` : ''}
      ${binding.visitCardLast4 ? `<span class="meta">卡尾号 ${escapeHtml(binding.visitCardLast4)}</span>` : ''}
    </div>
    <form id="identityForm" class="form-stack" autocomplete="off">
      <label class="field" id="idNameField">
        <span>真实姓名 <em>*</em></span>
        <input type="text" id="idName" maxlength="30" required placeholder="与证件一致的姓名"
          value="${escapeHtml(binding.name || ap?.name || '')}" />
        <span class="field-error" id="idNameErr"></span>
      </label>
      <label class="field" id="idNumberField">
        <span>身份证号 <em>*</em></span>
        <input type="text" id="idNumber" maxlength="18" required placeholder="18 位身份证号"
          value="${escapeHtml(binding.idNumber || '')}" inputmode="text" />
        <span class="field-error" id="idNumberErr"></span>
      </label>
      <label class="field" id="idPhoneField">
        <span>手机号 <em>*</em></span>
        <input type="tel" id="idPhone" maxlength="11" required placeholder="11 位手机号"
          value="${escapeHtml(binding.phone || ap?.phone || '')}" inputmode="numeric" />
        <span class="field-error" id="idPhoneErr"></span>
      </label>
      <label class="field">
        <span>医院就诊卡号（可选）</span>
        <input type="text" id="idCardNo" maxlength="32" placeholder="院内就诊卡 / 病历号"
          value="${escapeHtml(binding.hospitalCardNo || '')}" />
      </label>
      ${binding.bound && binding.idNumber ? `
        <p class="ref-note">当前证件脱敏展示：<span class="masked-id">${escapeHtml(maskIdNumber(binding.idNumber))}</span>
          · 手机 ${escapeHtml(maskPhone(binding.phone))}</p>` : ''}
      <p class="ref-note">${sourceLabel(binding.source)} · ${escapeHtml(binding.disclaimer || '')}</p>
      <button type="submit" class="btn primary block">保存绑定</button>
      <button type="button" class="btn ghost block" id="idGoSettings">查看操作须知</button>
    </form>`;

  const clearErr = (fieldId, errId) => {
    $(fieldId)?.classList.remove('has-error');
    const err = $(errId);
    if (err) err.textContent = '';
  };
  const showErr = (fieldId, errId, msg) => {
    $(fieldId)?.classList.add('has-error');
    const err = $(errId);
    if (err) err.textContent = msg;
  };

  $('#idGoSettings')?.addEventListener('click', () => showView('settings'));
  $('#identityForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    clearErr('#idNameField', '#idNameErr');
    clearErr('#idNumberField', '#idNumberErr');
    clearErr('#idPhoneField', '#idPhoneErr');
    const name = ($('#idName')?.value || '').trim();
    const idRaw = ($('#idNumber')?.value || '').trim();
    const phoneRaw = ($('#idPhone')?.value || '').trim();
    const hospitalCardNo = ($('#idCardNo')?.value || '').trim();
    let ok = true;
    if (!name || name.length < 2) {
      showErr('#idNameField', '#idNameErr', '请填写至少 2 个字的姓名');
      ok = false;
    }
    const idv = validateCnIdNumber(idRaw);
    if (!idv.ok) {
      showErr('#idNumberField', '#idNumberErr', idv.message);
      ok = false;
    }
    const phv = validateCnPhone(phoneRaw);
    if (!phv.ok) {
      showErr('#idPhoneField', '#idPhoneErr', phv.message);
      ok = false;
    }
    if (!ok) {
      toast('请修正表单错误');
      return;
    }
    setLoading(true, '保存中…');
    try {
      const saved = await saveIdentityBinding({
        name,
        idNumber: idv.value,
        phone: phv.value,
        hospitalCardNo
      });
      toast(saved.source === 'api' ? '已保存到服务端' : '已保存到本机（演示）');
      await renderIdentity();
    } catch {
      toast('保存失败');
    } finally {
      setLoading(false);
    }
  });
}

async function renderSettings() {
  const box = $('#settingsContent');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const audits = await fetchAuditLogs();
  const auditSource = audits[0]?.source || 'mock';
  box.innerHTML = `
    <div class="settings-block">
      <h3>⚠️ 免责声明</h3>
      <p>本应用为<strong>就医辅助演示产品</strong>，提供的症状导诊、智能问诊、检查检验预约、报告解读、续方申请、用药提醒、随访问卷、缴费与实名绑定等功能，均为辅助信息或演示流程。</p>
      <p><strong>不能替代执业医师面诊、诊断、处方或急诊处置。</strong>急危重症（如胸痛、大出血、意识障碍、严重呼吸困难等）请立即前往急诊或拨打 120。</p>
      <p>在线缴费为<strong>模拟支付</strong>，不产生真实扣款；检查检验预约为<strong>演示 Mock</strong>，非真实院内预约/HIS；药品配送为<strong>演示 Mock</strong>，非真实处方流转/非真实物流配送；实名 / 就诊卡绑定为<strong>演示占位</strong>，不对接公安或医保核验系统；图文/视频接诊为<strong>演示 Mock</strong>，非真实诊疗与视频通话。</p>
    </div>
    <div class="settings-block">
      <h3>📋 操作须知</h3>
      <ul>
        <li><strong>只读辅助</strong>：导诊与 AI 结果旁均有「仅供参考，需医生确认 / 不能替代面诊」提示。</li>
        <li><strong>急危优先</strong>：出现急危关键词时会显示醒目横幅，请优先就医而非继续在线流程。</li>
        <li><strong>隐私最小化</strong>：演示数据可存于本机 localStorage；请勿录入真实敏感信息用于生产。</li>
        <li><strong>演示数据</strong>：账单、预约、续方等可为 Mock；接口可用时优先走 ${API_BASE}。</li>
        <li><strong>非真实医疗文书</strong>：续方申请不构成处方；缴费回执非正式发票。</li>
      </ul>
    </div>
    <div class="settings-block">
      <h3>ℹ️ 版本与 PWA</h3>
      <p class="meta">前端版本：<strong>${APP_VERSION}</strong> · Service Worker：triage-shell-v16-guardrail-020</p>
      <p class="meta">打开地址：${location.origin}/ · API：${API_BASE}</p>
      <p>可在浏览器菜单中「安装应用 / 添加到主屏幕」。改版后请硬刷新（Ctrl/Cmd+Shift+R）。</p>
    </div>
    <div class="settings-block">
      <h3>🧾 最近操作（演示审计）</h3>
      <p class="meta">来源：${sourceLabel(auditSource)} · GET /api/audit（可选）</p>
      <ul class="audit-list">
        ${audits.map((a) => `
          <li>
            <span>${escapeHtml(a.action)}</span>
            <span class="when">${escapeHtml(String(a.at).slice(0, 16).replace('T', ' '))}</span>
          </li>`).join('') || '<li>暂无记录</li>'}
      </ul>
    </div>
    <div class="settings-block">
      <h3>🗑️ 清除本机演示数据</h3>
      <p>将清除预约、检查检验预约、就诊人、档案、账单、实名绑定、续方用药随访等 localStorage 演示数据，不影响服务器。</p>
      <button type="button" class="btn ghost block" id="btnClearDemo">清除演示数据并刷新</button>
    </div>
    <button type="button" class="btn primary block" id="settingsGoIdentity">去实名 / 就诊卡绑定</button>
    <button type="button" class="btn ghost block" id="settingsGoBills" style="margin-top:8px">去在线缴费</button>
    <button type="button" class="btn ghost block" id="settingsGoExam" style="margin-top:8px">去检查检验预约</button>
    <button type="button" class="btn ghost block" id="settingsGoPharmacy" style="margin-top:8px">去药品配送</button>
  `;
  $('#settingsGoIdentity')?.addEventListener('click', () => showView('identity'));
  $('#settingsGoBills')?.addEventListener('click', () => showView('bills'));
  $('#settingsGoExam')?.addEventListener('click', () => showView('exam'));
  $('#settingsGoPharmacy')?.addEventListener('click', () => showView('pharmacy'));
  $('#btnClearDemo')?.addEventListener('click', () => {
    if (!confirm('确定清除本机全部演示数据？此操作不可撤销。')) return;
    clearDemoLocalData();
    toast('已清除，即将刷新');
    setTimeout(() => location.reload(), 600);
  });
}

/* ========== M5 · 在线接诊 Mock（医生图文/视频，非 AI 导诊） ========== */

const DC_DISCLAIMER = '演示环境，非真实诊疗 / 非真实视频通话';
const DC_DOCTOR_REPLIES = [
  '您好，我是值班医生。请再补充一下症状持续了多久？',
  '收到。有无发热、胸闷或加重因素？请简明描述。',
  '建议先注意休息与观察；如出现急危症状请立即急诊或拨打 120。本对话为演示，不能替代面诊。'
];

function stopDcTimers() {
  if (state.dcQueueTimer) {
    clearInterval(state.dcQueueTimer);
    state.dcQueueTimer = null;
  }
  if (state.dcPollTimer) {
    clearInterval(state.dcPollTimer);
    state.dcPollTimer = null;
  }
}

function dcStatusLabel(st) {
  const m = {
    queued: '排队中',
    waiting_doctor: '等待医生',
    in_progress: '接诊中',
    ended: '已结束'
  };
  return m[st] || st || '—';
}

function dcModeLabel(mode) {
  return mode === 'video' ? '视频问诊' : '图文问诊';
}

function normalizeDcSession(s, source) {
  if (!s) return null;
  const msgs = Array.isArray(s.messages) ? s.messages.map((m, i) => ({
    id: m.id || `m-${i}`,
    role: m.role || m.senderRole || 'system',
    content: m.content || m.text || '',
    createdAt: m.createdAt || m.time || ''
  })) : [];
  return {
    id: s.id,
    mode: s.mode === 'video' ? 'video' : 'text',
    status: s.status || 'queued',
    patientId: s.patientId || '',
    patientName: s.patientName || '',
    doctorId: s.doctorId || '',
    doctorName: s.doctorName || '',
    departmentId: s.departmentId || '',
    departmentName: s.departmentName || '',
    chiefComplaint: s.chiefComplaint || s.chief || '',
    queuePosition: Number(s.queuePosition ?? 0),
    createdAt: s.createdAt || '',
    acceptedAt: s.acceptedAt || '',
    endedAt: s.endedAt || '',
    summary: s.summary || '',
    videoState: s.videoState || 'idle',
    disclaimer: s.disclaimer || DC_DISCLAIMER,
    messages: msgs,
    messageCount: s.messageCount ?? msgs.length,
    roomId: s.roomId || '',
    source: source || s.source || 'api'
  };
}

function seedDcSessionsIfNeeded() {
  try {
    const existing = JSON.parse(localStorage.getItem(DC_SESSIONS_KEY) || 'null');
    if (Array.isArray(existing) && existing.length) return existing;
  } catch { /* ignore */ }
  const ap = getActivePatient();
  const now = Date.now();
  const list = [
    {
      id: 'dc-seed-wait-1',
      mode: 'text',
      status: 'waiting_doctor',
      patientId: ap?.id || 'p-self',
      patientName: ap?.name || '本人',
      doctorName: '',
      departmentName: '呼吸内科',
      chiefComplaint: '咳嗽伴低热两天（演示待接诊）',
      queuePosition: 2,
      createdAt: new Date(now - 600e3).toISOString(),
      videoState: 'idle',
      messages: [],
      summary: '',
      source: 'seed'
    },
    {
      id: 'dc-seed-done-1',
      mode: 'video',
      status: 'ended',
      patientId: ap?.id || 'p-self',
      patientName: ap?.name || '本人',
      doctorName: '王晓明',
      departmentName: '全科医学',
      chiefComplaint: '咽痛一天（演示已结束）',
      queuePosition: 0,
      createdAt: new Date(now - 86400e3).toISOString(),
      acceptedAt: new Date(now - 86000e3).toISOString(),
      endedAt: new Date(now - 85000e3).toISOString(),
      videoState: 'ended',
      summary: '建议多饮水，观察体温；如加重请门诊复诊。（演示小结）',
      messages: [
        { id: 'sm1', role: 'system', content: '医生 王晓明 已接诊', createdAt: new Date(now - 86000e3).toISOString() },
        { id: 'sm2', role: 'patient', content: '医生您好，喉咙痛一天了', createdAt: new Date(now - 85900e3).toISOString() },
        { id: 'sm3', role: 'doctor', content: '有无发热？能否正常进食？', createdAt: new Date(now - 85800e3).toISOString() },
        { id: 'sm4', role: 'patient', content: '没有发热，可以进食', createdAt: new Date(now - 85700e3).toISOString() }
      ],
      source: 'seed'
    }
  ];
  localStorage.setItem(DC_SESSIONS_KEY, JSON.stringify(list));
  return list;
}

function loadLocalDcSessions() {
  return seedDcSessionsIfNeeded();
}

function saveLocalDcSessions(list) {
  localStorage.setItem(DC_SESSIONS_KEY, JSON.stringify(list));
}

function upsertLocalDcSession(session) {
  const list = loadLocalDcSessions();
  const idx = list.findIndex((x) => String(x.id) === String(session.id));
  const raw = { ...session, source: session.source || 'mock' };
  if (idx >= 0) list[idx] = { ...list[idx], ...raw };
  else list.unshift(raw);
  saveLocalDcSessions(list);
  return raw;
}

async function dcApiFetch(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {})
  };
  try {
    return await apiFetch(path, { ...options, headers });
  } catch (e1) {
    // alias fallback /api/consultations
    const alt = path
      .replace(/^\/api\/doctor-consult\/sessions\/?/, '/api/consultations/')
      .replace(/\/accept$/, '') // consultations use PATCH status
      ;
    if (path.includes('/accept')) {
      const id = path.split('/sessions/')[1]?.split('/')[0];
      try {
        return await apiFetch(`/api/consultations/${encodeURIComponent(id)}`, {
          method: 'PATCH',
          headers: { ...headers, 'X-Role': 'doctor' },
          body: JSON.stringify({ status: 'in_progress' })
        });
      } catch { throw e1; }
    }
    if (path === '/api/doctor-consult/sessions' || path.startsWith('/api/doctor-consult/sessions?')) {
      const q = path.includes('?') ? path.slice(path.indexOf('?')) : '';
      try {
        return await apiFetch('/api/consultations/' + (q || ''), { ...options, headers });
      } catch { throw e1; }
    }
    if (path.includes('/sessions/')) {
      try {
        return await apiFetch(alt.replace(/\/$/, ''), { ...options, headers });
      } catch { throw e1; }
    }
    throw e1;
  }
}

async function createDcSession({ mode, chiefComplaint, departmentName, departmentId, patientId }) {
  const body = {
    mode,
    chiefComplaint,
    departmentName,
    departmentId: departmentId || undefined,
    patientId: patientId || undefined
  };
  try {
    const data = await dcApiFetch('/api/doctor-consult/sessions', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    const session = normalizeDcSession(data, 'api');
    state.dcUsingApi = true;
    upsertLocalDcSession({ ...session, source: 'api' });
    return session;
  } catch {
    state.dcUsingApi = false;
    const ap = getActivePatient();
    const id = 'dc-local-' + Date.now();
    const session = normalizeDcSession({
      id,
      mode,
      status: 'queued',
      patientId: patientId || ap?.id || 'p-self',
      patientName: ap?.name || '本人',
      departmentName: departmentName || '全科医学',
      departmentId: departmentId || '',
      chiefComplaint,
      queuePosition: 3,
      createdAt: new Date().toISOString(),
      videoState: 'idle',
      messages: [{
        id: 'sys-0',
        role: 'system',
        content: '已进入排队，请稍候（本机 Mock）',
        createdAt: new Date().toISOString()
      }],
      disclaimer: DC_DISCLAIMER
    }, 'mock');
    upsertLocalDcSession(session);
    return session;
  }
}

async function fetchDcSessions({ role = 'patient', status } = {}) {
  try {
    let path = `/api/doctor-consult/sessions?role=${encodeURIComponent(role)}`;
    if (status) path += `&status=${encodeURIComponent(status)}`;
    const data = await dcApiFetch(path);
    const list = asList(data, ['items', 'sessions', 'data', 'results'])
      .map((s) => normalizeDcSession(s, 'api')).filter(Boolean);
    if (list.length || Array.isArray(data?.items)) {
      state.dcUsingApi = true;
      // merge into local cache lightly
      list.forEach((s) => upsertLocalDcSession({ ...s, source: 'api' }));
      return list;
    }
  } catch { /* fallthrough */ }
  state.dcUsingApi = false;
  return loadLocalDcSessions().map((s) => normalizeDcSession(s, s.source || 'mock'));
}

async function fetchDcSession(id) {
  try {
    const data = await dcApiFetch(`/api/doctor-consult/sessions/${encodeURIComponent(id)}`);
    const session = normalizeDcSession(data, 'api');
    state.dcUsingApi = true;
    upsertLocalDcSession({ ...session, source: 'api' });
    return session;
  } catch {
    state.dcUsingApi = false;
    const hit = loadLocalDcSessions().find((s) => String(s.id) === String(id));
    return hit ? normalizeDcSession(hit, hit.source || 'mock') : null;
  }
}

async function acceptDcSession(id) {
  try {
    const data = await dcApiFetch(`/api/doctor-consult/sessions/${encodeURIComponent(id)}/accept`, {
      method: 'POST',
      headers: { 'X-Role': 'doctor' },
      body: JSON.stringify({})
    });
    const session = normalizeDcSession(data, 'api');
    upsertLocalDcSession({ ...session, source: 'api' });
    return session;
  } catch {
    const hit = loadLocalDcSessions().find((s) => String(s.id) === String(id));
    if (!hit) throw new Error('会话不存在');
    const doctorName = hit.doctorName || '王晓明';
    const next = normalizeDcSession({
      ...hit,
      status: 'in_progress',
      doctorName,
      queuePosition: 0,
      acceptedAt: new Date().toISOString(),
      videoState: hit.mode === 'video' ? 'connecting' : 'idle',
      messages: [
        ...(hit.messages || []),
        { id: 'sys-accept-' + Date.now(), role: 'system', content: `医生 ${doctorName} 已接诊`, createdAt: new Date().toISOString() }
      ]
    }, 'mock');
    upsertLocalDcSession(next);
    return next;
  }
}

async function postDcMessage(id, role, content) {
  try {
    const data = await dcApiFetch(`/api/doctor-consult/sessions/${encodeURIComponent(id)}/messages`, {
      method: 'POST',
      headers: { 'X-Role': role },
      body: JSON.stringify({ role, content })
    });
    // refresh full session
    return await fetchDcSession(id);
  } catch {
    const hit = loadLocalDcSessions().find((s) => String(s.id) === String(id));
    if (!hit) throw new Error('会话不存在');
    const msgs = [...(hit.messages || []), {
      id: 'm-' + Date.now(),
      role,
      content,
      createdAt: new Date().toISOString()
    }];
    // auto doctor reply for patient messages in mock
    if (role === 'patient' && hit.status === 'in_progress') {
      const reply = DC_DOCTOR_REPLIES[Math.min(msgs.filter((m) => m.role === 'patient').length - 1, DC_DOCTOR_REPLIES.length - 1)];
      msgs.push({
        id: 'm-doc-' + Date.now(),
        role: 'doctor',
        content: reply,
        createdAt: new Date().toISOString()
      });
    }
    const next = normalizeDcSession({ ...hit, messages: msgs }, 'mock');
    upsertLocalDcSession(next);
    return next;
  }
}

async function endDcSession(id, summary) {
  try {
    const data = await dcApiFetch(`/api/doctor-consult/sessions/${encodeURIComponent(id)}/end`, {
      method: 'POST',
      headers: { 'X-Role': 'patient' },
      body: JSON.stringify({ summary: summary || '' })
    });
    const session = normalizeDcSession(data, 'api');
    upsertLocalDcSession({ ...session, source: 'api' });
    return session;
  } catch {
    const hit = loadLocalDcSessions().find((s) => String(s.id) === String(id));
    if (!hit) throw new Error('会话不存在');
    const autoSummary = summary || buildDcAutoSummary(hit);
    const next = normalizeDcSession({
      ...hit,
      status: 'ended',
      endedAt: new Date().toISOString(),
      summary: autoSummary,
      videoState: hit.mode === 'video' ? 'ended' : (hit.videoState || 'idle')
    }, 'mock');
    upsertLocalDcSession(next);
    return next;
  }
}

function buildDcAutoSummary(session) {
  const msgs = (session.messages || []).filter((m) => m.role === 'patient' || m.role === 'doctor');
  const snippet = msgs.slice(-4).map((m) => `${m.role === 'doctor' ? '医' : '患'}：${m.content}`).join('；');
  return `主诉「${session.chiefComplaint || '—'}」已完成演示接诊。${snippet ? '对话摘要：' + snippet : ''}（演示小结，非真实诊疗）`;
}

function dcDurationText(session) {
  const start = session.acceptedAt || session.createdAt;
  const end = session.endedAt || new Date().toISOString();
  if (!start) return '—';
  const a = Date.parse(start);
  const b = Date.parse(end);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return '—';
  const mins = Math.max(1, Math.round((b - a) / 60000));
  return `${mins} 分钟`;
}

function renderConsultHub() {
  const box = $('#consultHub');
  if (!box) return;
  box.innerHTML = `
    <button type="button" class="entry-card" data-nav="chat">
      <span class="entry-icon" style="--c:#2563eb">💬</span>
      <span class="entry-body">
        <strong>智能问诊</strong>
        <small>AI 多轮澄清 · 导诊小结（非医生接诊）</small>
      </span>
      <span class="entry-arrow">→</span>
    </button>
    <button type="button" class="entry-card" data-nav="dc-start" data-mode="text">
      <span class="entry-icon" style="--c:#0ea5e9">📝</span>
      <span class="entry-body">
        <strong>图文问诊</strong>
        <small>医生接诊 Mock · 排队与聊天</small>
      </span>
      <span class="entry-arrow">→</span>
    </button>
    <button type="button" class="entry-card" data-nav="dc-start" data-mode="video">
      <span class="entry-icon" style="--c:#7c3aed">📹</span>
      <span class="entry-body">
        <strong>视频问诊</strong>
        <small>占位画面 · 模拟接通</small>
      </span>
      <span class="entry-arrow">→</span>
    </button>
    <button type="button" class="entry-card" data-nav="dc-list">
      <span class="entry-icon" style="--c:#0369a1">🗂️</span>
      <span class="entry-body">
        <strong>我的接诊</strong>
        <small>进行中 / 已结束回看</small>
      </span>
      <span class="entry-arrow">→</span>
    </button>`;
  box.querySelectorAll('[data-nav]').forEach((b) => {
    b.addEventListener('click', () => {
      if (b.dataset.mode) state.dcMode = b.dataset.mode;
      if (b.dataset.nav === 'chat' && state.chatDone) resetChatSession();
      showView(b.dataset.nav);
    });
  });
}

function renderDcStart() {
  const box = $('#dcStartContent');
  if (!box) return;
  const mode = state.dcMode === 'video' ? 'video' : 'text';
  state.dcMode = mode;
  const ap = getActivePatient();
  const depts = MOCK_DEPARTMENTS;
  box.innerHTML = `
    <div class="info-chip" style="margin-bottom:12px">
      <span class="dc-mode-pill ${mode}">${mode === 'video' ? '📹' : '📝'} ${escapeHtml(dcModeLabel(mode))}</span>
      <span>就诊人：<strong>${escapeHtml(ap?.name || '本人')}</strong></span>
    </div>
    <div class="field">
      <span>选择科室 <em>*</em></span>
      <div class="dc-dept-grid" id="dcDeptGrid">
        ${depts.map((d, i) => `
          <button type="button" class="dc-dept-chip${i === 0 ? ' active' : ''}" data-id="${escapeHtml(d.id)}" data-name="${escapeHtml(d.name)}">
            ${escapeHtml(d.name)}
            <small>${escapeHtml(d.desc || d.intro || '')}</small>
          </button>`).join('')}
      </div>
    </div>
    <label class="field">
      <span>主诉 <em>*</em></span>
      <textarea id="dcChief" rows="3" placeholder="例如：咳嗽三天，伴轻微咽痛…"></textarea>
    </label>
    <div class="quick-fill" style="margin-bottom:12px">
      <span>快速演示：</span>
      <button type="button" class="link-btn" id="dcFillMild">普通示例</button>
    </div>
    <button type="button" class="btn primary block" id="dcBtnStart">确认开始${escapeHtml(dcModeLabel(mode))}</button>
    <button type="button" class="btn ghost block" id="dcBtnList" style="margin-top:8px">查看我的接诊</button>
    <p class="ref-note" style="margin-top:12px">${escapeHtml(DC_DISCLAIMER)}</p>
  `;
  let selected = { id: depts[0].id, name: depts[0].name };
  box.querySelectorAll('.dc-dept-chip').forEach((chip) => {
    chip.addEventListener('click', () => {
      box.querySelectorAll('.dc-dept-chip').forEach((c) => c.classList.remove('active'));
      chip.classList.add('active');
      selected = { id: chip.dataset.id, name: chip.dataset.name };
    });
  });
  $('#dcFillMild')?.addEventListener('click', () => {
    $('#dcChief').value = mode === 'video' ? '头晕两天，站立时明显（视频问诊演示）' : '咳嗽三天，偶有低热（图文问诊演示）';
  });
  $('#dcBtnList')?.addEventListener('click', () => showView('dc-list'));
  $('#dcBtnStart')?.addEventListener('click', async () => {
    const chief = ($('#dcChief')?.value || '').trim();
    if (!chief) {
      toast('请填写主诉');
      return;
    }
    setLoading(true, '正在发起问诊…');
    try {
      const session = await createDcSession({
        mode,
        chiefComplaint: chief,
        departmentName: selected.name,
        departmentId: selected.id,
        patientId: ap?.id
      });
      state.dcSessionId = session.id;
      state.dcSession = session;
      state.dcVideoLocal = null;
      toast(session.source === 'api' ? '已创建会话（API）' : '已创建会话（本机 Mock）');
      showView('dc-queue');
    } catch (e) {
      toast('发起失败，请重试');
    } finally {
      setLoading(false);
    }
  });
}

function renderDcQueue() {
  const box = $('#dcQueueContent');
  if (!box) return;
  const session = state.dcSession;
  if (!session) {
    box.innerHTML = `<div class="empty-state"><p>暂无排队会话</p><button class="btn primary" id="dcQGoStart">去发起</button></div>`;
    $('#dcQGoStart')?.addEventListener('click', () => showView('dc-start'));
    return;
  }
  if (session.status === 'in_progress') {
    showView('dc-session');
    return;
  }
  if (session.status === 'ended') {
    showView('dc-summary');
    return;
  }
  const waitMin = Math.max(1, (session.queuePosition || 1) * 2);
  box.innerHTML = `
    <div class="dc-queue-card">
      <span class="dc-mode-pill ${session.mode}">${escapeHtml(dcModeLabel(session.mode))}</span>
      <p class="meta" style="margin-top:10px">${escapeHtml(session.departmentName || '')} · ${escapeHtml(session.patientName || '')}</p>
      <div class="dc-queue-pos">${escapeHtml(String(session.queuePosition || 1))}</div>
      <p><strong>当前排队位</strong></p>
      <p class="meta">预计等待约 ${waitMin} 分钟 · ${escapeHtml(dcStatusLabel(session.status))}</p>
      <p class="meta" style="margin-top:8px">主诉：${escapeHtml(session.chiefComplaint || '—')}</p>
    </div>
    <button type="button" class="btn primary block" id="dcBtnMockAccept">模拟医生已接诊</button>
    <button type="button" class="btn ghost block" id="dcBtnRefreshQ" style="margin-top:8px">刷新排队状态</button>
    <p class="ref-note" style="margin-top:12px">来源：${sourceLabel(session.source)} · ${escapeHtml(session.disclaimer || DC_DISCLAIMER)}</p>
  `;
  $('#dcBtnMockAccept')?.addEventListener('click', async () => {
    setLoading(true, '模拟接诊中…');
    try {
      const next = await acceptDcSession(session.id);
      state.dcSession = next;
      toast('医生已接诊');
      showView('dc-session');
    } catch {
      toast('接诊失败');
    } finally {
      setLoading(false);
    }
  });
  $('#dcBtnRefreshQ')?.addEventListener('click', async () => {
    const next = await fetchDcSession(session.id);
    if (next) {
      state.dcSession = next;
      renderDcQueue();
    }
  });

  stopDcTimers();
  // Mock: auto advance queue then accept in 2.5–4s if still mock / waiting
  let ticks = 0;
  state.dcQueueTimer = setInterval(async () => {
    ticks += 1;
    if (state.view !== 'dc-queue') {
      stopDcTimers();
      return;
    }
    // poll API
    try {
      const latest = await fetchDcSession(session.id);
      if (latest) {
        state.dcSession = latest;
        if (latest.status === 'in_progress') {
          stopDcTimers();
          toast('医生已接诊');
          showView('dc-session');
          return;
        }
        // mock queue countdown locally when not api-driven accept
        if (!state.dcUsingApi && latest.queuePosition > 0 && ticks % 2 === 0) {
          latest.queuePosition = Math.max(0, latest.queuePosition - 1);
          if (latest.queuePosition === 0) latest.status = 'waiting_doctor';
          upsertLocalDcSession(latest);
          state.dcSession = latest;
        }
        if (!state.dcUsingApi && ticks >= 3) {
          stopDcTimers();
          const next = await acceptDcSession(session.id);
          state.dcSession = next;
          toast('医生已接诊（自动模拟）');
          showView('dc-session');
          return;
        }
        // refresh UI numbers without full remount of listeners awkwardly
        const posEl = box.querySelector('.dc-queue-pos');
        if (posEl) posEl.textContent = String(latest.queuePosition || 1);
      }
    } catch { /* ignore */ }
  }, 1200);
}

function dcVideoStateLabel(vs) {
  const m = { idle: '待接通', connecting: '模拟接通中…', connected: '已接通（演示）', ended: '通话已结束' };
  return m[vs] || vs || '待接通';
}

function renderDcSession() {
  const box = $('#dcSessionContent');
  if (!box) return;
  const session = state.dcSession;
  if (!session) {
    box.innerHTML = `<div class="empty-state"><p>会话不存在</p></div>`;
    return;
  }
  if (session.status === 'ended') {
    showView('dc-summary');
    return;
  }
  const videoState = state.dcVideoLocal || session.videoState || 'idle';
  const docName = session.doctorName || '值班医生';
  const initial = docName.charAt(0) || '医';
  box.innerHTML = `
    <div class="dc-session-head">
      <span class="dc-mode-pill ${session.mode}">${escapeHtml(dcModeLabel(session.mode))}</span>
      <div class="doc-meta">
        <strong>${escapeHtml(docName)}</strong>
        <small>${escapeHtml(session.departmentName || '')} · ${escapeHtml(dcStatusLabel(session.status))}</small>
      </div>
      <button type="button" class="btn ghost sm" id="dcBtnEnd">结束</button>
    </div>
    ${session.mode === 'video' ? `
      <div class="dc-video-stage" id="dcVideoStage">
        <span class="dc-video-badge">视频占位 · 演示</span>
        <div class="dc-video-avatar">${escapeHtml(initial)}</div>
        <div class="dc-video-status" id="dcVideoStatus">${escapeHtml(dcVideoStateLabel(videoState))}</div>
        <div class="dc-video-actions">
          ${videoState !== 'connected' && videoState !== 'ended' ? '<button type="button" class="btn" id="dcBtnConnect">模拟接通</button>' : ''}
          <button type="button" class="btn" id="dcBtnVideoHint">非真实通话</button>
        </div>
      </div>` : ''}
    <div class="dc-msg-pane" id="dcMsgPane"></div>
    <div class="dc-composer">
      <input type="text" id="dcMsgInput" placeholder="输入想对医生说的话…" maxlength="500" />
      <button type="button" class="btn primary" id="dcBtnSend">发送</button>
    </div>
    <p class="ref-note">${escapeHtml(session.disclaimer || DC_DISCLAIMER)} · 来源 ${sourceLabel(session.source)}</p>
  `;
  paintDcMessages(session);
  $('#dcBtnConnect')?.addEventListener('click', () => {
    state.dcVideoLocal = 'connected';
    const st = $('#dcVideoStatus');
    if (st) st.textContent = dcVideoStateLabel('connected');
    $('#dcBtnConnect')?.remove();
    toast('已模拟接通（无音视频）');
  });
  $('#dcBtnVideoHint')?.addEventListener('click', () => toast(DC_DISCLAIMER));
  $('#dcBtnEnd')?.addEventListener('click', async () => {
    if (!confirm('确认结束本次接诊？')) return;
    setLoading(true, '结束接诊…');
    try {
      const next = await endDcSession(session.id);
      state.dcSession = next;
      state.dcVideoLocal = 'ended';
      stopDcTimers();
      showView('dc-summary');
    } catch {
      toast('结束失败');
    } finally {
      setLoading(false);
    }
  });
  const send = async () => {
    const input = $('#dcMsgInput');
    const text = (input?.value || '').trim();
    if (!text) return;
    input.value = '';
    try {
      const next = await postDcMessage(session.id, 'patient', text);
      state.dcSession = next;
      paintDcMessages(next);
    } catch {
      toast('发送失败');
    }
  };
  $('#dcBtnSend')?.addEventListener('click', send);
  $('#dcMsgInput')?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      send();
    }
  });

  // poll while in session (API doctor replies)
  stopDcTimers();
  state.dcPollTimer = setInterval(async () => {
    if (state.view !== 'dc-session') {
      stopDcTimers();
      return;
    }
    const latest = await fetchDcSession(session.id);
    if (!latest) return;
    state.dcSession = latest;
    if (latest.status === 'ended') {
      stopDcTimers();
      showView('dc-summary');
      return;
    }
    paintDcMessages(latest);
  }, 2500);
}

function paintDcMessages(session) {
  const pane = $('#dcMsgPane');
  if (!pane) return;
  const msgs = session.messages || [];
  if (!msgs.length) {
    pane.innerHTML = `<div class="dc-msg system">可开始与医生文字交流。演示环境，非真实诊疗。</div>`;
    return;
  }
  pane.innerHTML = msgs.map((m) => {
    const role = m.role === 'patient' ? 'patient' : m.role === 'doctor' ? 'doctor' : 'system';
    const when = m.createdAt ? String(m.createdAt).replace('T', ' ').slice(0, 16) : '';
    return `<div class="dc-msg ${role}">${escapeHtml(m.content || '')}${when ? `<span class="when">${escapeHtml(when)}</span>` : ''}</div>`;
  }).join('');
  pane.scrollTop = pane.scrollHeight;
}

function renderDcSummary() {
  const box = $('#dcSummaryContent');
  if (!box) return;
  const session = state.dcSession;
  if (!session) {
    box.innerHTML = `<div class="empty-state"><p>暂无小结</p><button class="btn primary" id="dcSumList">我的接诊</button></div>`;
    $('#dcSumList')?.addEventListener('click', () => showView('dc-list'));
    return;
  }
  const transcript = (session.messages || [])
    .filter((m) => m.role === 'patient' || m.role === 'doctor')
    .map((m) => `${m.role === 'doctor' ? '医生' : '患者'}：${m.content}`)
    .join('\n');
  box.innerHTML = `
    <div class="m3-disclaimer" role="note">
      <strong>${escapeHtml(session.disclaimer || DC_DISCLAIMER)}</strong>
      <p>以下小结仅用于产品演示，不能作为诊断、处方或正式医疗文书。</p>
    </div>
    <div class="dc-summary-card">
      <h3>接诊小结</h3>
      <div class="dc-summary-row"><span>方式</span><strong>${escapeHtml(dcModeLabel(session.mode))}</strong></div>
      <div class="dc-summary-row"><span>科室</span><strong>${escapeHtml(session.departmentName || '—')}</strong></div>
      <div class="dc-summary-row"><span>医生</span><strong>${escapeHtml(session.doctorName || '—')}</strong></div>
      <div class="dc-summary-row"><span>就诊人</span><strong>${escapeHtml(session.patientName || '—')}</strong></div>
      <div class="dc-summary-row"><span>主诉</span><strong>${escapeHtml(session.chiefComplaint || '—')}</strong></div>
      <div class="dc-summary-row"><span>时长</span><strong>${escapeHtml(dcDurationText(session))}</strong></div>
      <div class="dc-summary-row"><span>状态</span><strong>${escapeHtml(dcStatusLabel(session.status))}</strong></div>
      <p style="margin:12px 0 6px;font-weight:600;font-size:0.9rem">医生小结</p>
      <p style="margin:0;font-size:0.9rem;line-height:1.5">${escapeHtml(session.summary || '（暂无文字小结）')}</p>
      <p style="margin:12px 0 6px;font-weight:600;font-size:0.9rem">对话摘要</p>
      <div class="dc-transcript">${escapeHtml(transcript || '暂无对话')}</div>
    </div>
    <button type="button" class="btn primary block" id="dcSumAgain">再发起一次</button>
    <button type="button" class="btn ghost block" id="dcSumList2" style="margin-top:8px">返回我的接诊</button>
  `;
  $('#dcSumAgain')?.addEventListener('click', () => {
    state.dcMode = session.mode || 'text';
    showView('dc-start');
  });
  $('#dcSumList2')?.addEventListener('click', () => showView('dc-list'));
}

async function renderDcList() {
  const box = $('#dcListContent');
  if (!box) return;
  $$('#dcListTabs .seg-tab').forEach((t) => {
    t.classList.toggle('active', (t.dataset.filter || '') === state.dcListFilter);
  });
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchDcSessions({ role: 'patient' });
  const filtered = list.filter((s) => {
    if (state.dcListFilter === 'ended') return s.status === 'ended';
    if (state.dcListFilter === 'active') return s.status !== 'ended';
    return true;
  });
  if (!filtered.length) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="big">🗂️</div>
        <p>暂无接诊会话</p>
        <button class="btn primary" style="margin-top:12px" id="dcListStart">发起图文问诊</button>
      </div>`;
    $('#dcListStart')?.addEventListener('click', () => {
      state.dcMode = 'text';
      showView('dc-start');
    });
    return;
  }
  box.innerHTML = filtered.map((s) => `
    <button type="button" class="m3-card" data-id="${escapeHtml(s.id)}">
      <div class="m3-card-head">
        <h4>${escapeHtml(s.departmentName || '接诊')} · ${escapeHtml(dcModeLabel(s.mode))}</h4>
        <span class="status-pill ${s.status === 'ended' ? 'done' : s.status === 'in_progress' ? 'accepted' : 'need'}">${escapeHtml(dcStatusLabel(s.status))}</span>
      </div>
      <p class="meta">主诉：${escapeHtml(s.chiefComplaint || '—')}<br/>
        医生：${escapeHtml(s.doctorName || '待分配')} · ${escapeHtml(String(s.createdAt || '').replace('T', ' ').slice(0, 16))}
      </p>
      <p class="ref-note">来源：${sourceLabel(s.source)}</p>
    </button>
  `).join('');
  box.querySelectorAll('.m3-card').forEach((btn) => {
    btn.addEventListener('click', async () => {
      setLoading(true, '打开会话…');
      try {
        const s = await fetchDcSession(btn.dataset.id);
        state.dcSession = s;
        state.dcSessionId = s?.id;
        state.dcVideoLocal = null;
        if (!s) { toast('会话不存在'); return; }
        if (s.status === 'ended') showView('dc-summary');
        else if (s.status === 'in_progress') showView('dc-session');
        else showView('dc-queue');
      } finally {
        setLoading(false);
      }
    });
  });
}

// tabs for dc list
document.addEventListener('click', (e) => {
  const tab = e.target.closest('#dcListTabs .seg-tab');
  if (!tab) return;
  state.dcListFilter = tab.dataset.filter || 'active';
  renderDcList();
});

/* ========== M6 · 检查检验预约与改约 ========== */

const EXAM_MAX_RESCHEDULE = 3;
const EXAM_DISCLAIMER = '演示环境，非真实院内预约/HIS';

const EXAM_SEED_ITEMS = [
  {
    id: 'exam-cbc', name: '血常规', category: 'lab', durationMinutes: 15, price: 25,
    location: '医技楼1F 抽血窗口',
    prepSummary: '建议空腹或不严格空腹均可',
    prepNotes: '建议空腹或不严格空腹均可；采血前勿剧烈运动；请携带就诊卡排队取号。抽血前可少量清水。',
    specialTips: ['采血前勿剧烈运动', '携带就诊卡取号']
  },
  {
    id: 'exam-lft', name: '肝功', category: 'lab', durationMinutes: 20, price: 68,
    location: '医技楼1F 抽血窗口',
    prepSummary: '需空腹 8–12 小时',
    prepNotes: '需空腹 8–12 小时（可少量清水）；采血前停用影响肝酶的保健品请遵医嘱。',
    specialTips: ['空腹抽血', '可少量清水']
  },
  {
    id: 'exam-abd-us', name: '腹部B超', category: 'imaging', durationMinutes: 30, price: 120,
    location: '医技楼2F 超声科',
    prepSummary: '空腹；部分检查需憋尿',
    prepNotes: '需空腹 8 小时以上；胆囊检查前勿进油腻食物；下腹部/泌尿系超声请提前憋尿约 1–2 小时；请穿着宽松上衣。',
    specialTips: ['空腹', '憋尿（下腹/泌尿）', '宽松上衣']
  },
  {
    id: 'exam-chest-ct', name: '胸部CT', category: 'imaging', durationMinutes: 25, price: 320,
    location: '医技楼1F 放射科CT室',
    prepSummary: '告知孕情；增强需碘过敏史',
    prepNotes: '检查前摘除项链、金属扣、文胸钢圈等金属物件；务必告知是否怀孕或备孕。增强 CT 需另开对比剂知情同意，请如实告知碘过敏史、哮喘、肾功能不全等。本演示非真实放射预约。',
    specialTips: ['孕情/备孕告知', '碘过敏史（增强）', '去除金属物件']
  },
  {
    id: 'exam-ecg', name: '心电图', category: 'imaging', durationMinutes: 10, price: 30,
    location: '门诊楼4F 心电图室',
    prepSummary: '安静休息 5–10 分钟',
    prepNotes: '检查前安静休息 5–10 分钟；避免剧烈运动与浓茶咖啡；保持胸部皮肤清洁干燥。',
    specialTips: ['安静休息', '避免浓茶咖啡']
  },
  {
    id: 'exam-ua', name: '尿常规', category: 'lab', durationMinutes: 10, price: 15,
    location: '医技楼1F 检验采样处',
    prepSummary: '中段尿；可适度憋尿',
    prepNotes: '采集中段尿；女性避开月经期；采样前清洁外阴；适度憋尿约 1–2 小时更利于取样。',
    specialTips: ['中段尿', '避开月经期']
  }
];

function resetExamBookState(extra = {}) {
  state.examBook = {
    step: 1,
    date: null,
    slot: null,
    mode: 'book',
    bookingId: null,
    ...extra
  };
}

function examCategoryLabel(cat) {
  if (cat === 'lab' || cat === '检验') return '检验';
  if (cat === 'imaging' || cat === '检查' || cat === 'other') return '检查';
  return cat || '检查';
}

function examStatusLabel(st) {
  const s = String(st || '').toLowerCase();
  if (s === 'cancelled' || s.includes('取消')) return '已取消';
  if (s === 'confirmed' || s === 'booked' || s === 'scheduled' || s.includes('预约') || s.includes('确认')) return '已预约';
  if (s === 'completed' || s === 'done' || s.includes('完成')) return '已完成';
  return st || '已预约';
}

function normalizeExamItem(it, source) {
  if (!it) return null;
  const catRaw = it.category || it.type || 'lab';
  const category = (catRaw === '检验' || catRaw === 'lab') ? 'lab'
    : (catRaw === '检查' || catRaw === 'imaging' || catRaw === 'other') ? (catRaw === 'other' ? 'imaging' : 'imaging')
    : String(catRaw).toLowerCase().includes('lab') ? 'lab' : 'imaging';
  const prepNotes = it.prepNotes || it['注意事项'] || it.precautions || it.notes || '';
  const prepSummary = it.prepSummary || it.summary || (prepNotes ? String(prepNotes).slice(0, 28) + (String(prepNotes).length > 28 ? '…' : '') : '请按医嘱准备');
  const specialTips = Array.isArray(it.specialTips) ? it.specialTips
    : Array.isArray(it.tips) ? it.tips
    : [];
  return {
    id: it.id || it.examId || it.itemId,
    name: it.name || it.title || it.examName || '检查项目',
    category,
    categoryLabel: examCategoryLabel(category),
    durationMinutes: Number(it.durationMinutes ?? it.duration ?? it.minutes ?? 20) || 20,
    price: Number(it.price ?? it.fee ?? it.amount ?? 0) || 0,
    location: it.location || it.place || '演示院区 · 医技楼',
    prepSummary,
    prepNotes: prepNotes || prepSummary,
    specialTips,
    disclaimer: it.disclaimer || EXAM_DISCLAIMER,
    maxReschedule: Number(it.maxReschedule ?? EXAM_MAX_RESCHEDULE) || EXAM_MAX_RESCHEDULE,
    source: source || it.source || 'api'
  };
}

function normalizeExamSlot(s, examId, source) {
  if (!s) return null;
  const remaining = s.remaining != null ? Number(s.remaining) : (s.available === false ? 0 : 4);
  const available = s.available != null ? !!s.available : remaining > 0;
  return {
    id: s.id || s.slotId || `${examId}-${s.date}-${s.time}`,
    examId: s.examId || examId,
    date: s.date || '',
    time: s.time || s.timeLabel || '',
    remaining,
    available,
    dateLabel: s.dateLabel || dateLabelFromIso(s.date),
    source: source || s.source || 'api'
  };
}

function normalizeExamBooking(b, source) {
  if (!b) return null;
  const raw = String(b.status || 'confirmed').toLowerCase();
  let status = 'confirmed';
  if (raw.includes('cancel') || raw.includes('取消')) status = 'cancelled';
  else if (raw.includes('complete') || raw.includes('完成') || raw.includes('done')) status = 'completed';
  else status = 'confirmed';
  const maxR = Number(b.maxReschedule ?? EXAM_MAX_RESCHEDULE) || EXAM_MAX_RESCHEDULE;
  const rescheduleCount = Number(b.rescheduleCount ?? b.rescheduleTimes ?? 0) || 0;
  const prepNotes = b.prepNotes || b['注意事项'] || b.precautions || '';
  return {
    id: b.id || b.bookingId || ('leb-' + Date.now()),
    examId: b.examId || b.itemId || '',
    examName: b.examName || b.name || b.title || '检查项目',
    slotId: b.slotId || '',
    date: b.date || '',
    time: b.time || '',
    dateLabel: b.dateLabel || dateLabelFromIso(b.date),
    patientId: b.patientId || '',
    patientName: b.patientName || '',
    status,
    statusLabel: examStatusLabel(status),
    rescheduleCount,
    maxReschedule: maxR,
    canReschedule: status === 'confirmed' && rescheduleCount < maxR,
    location: b.location || '演示院区 · 医技楼',
    prepNotes,
    category: b.category || '',
    categoryLabel: examCategoryLabel(b.category || 'lab'),
    price: Number(b.price ?? 0) || 0,
    durationMinutes: Number(b.durationMinutes ?? 0) || 0,
    orderNo: b.orderNo || b.bookingNo || b.id || '',
    createdAt: b.createdAt || '',
    updatedAt: b.updatedAt || '',
    cancelledAt: b.cancelledAt || '',
    disclaimer: b.disclaimer || EXAM_DISCLAIMER,
    source: source || b.source || 'api'
  };
}

function loadLocalExamBookings() {
  try {
    const list = JSON.parse(localStorage.getItem(EXAM_BOOKINGS_KEY) || '[]');
    return Array.isArray(list) ? list : [];
  } catch { return []; }
}

function saveLocalExamBookings(list) {
  localStorage.setItem(EXAM_BOOKINGS_KEY, JSON.stringify(list));
}

function loadLocalExamSlotsMap() {
  try {
    const m = JSON.parse(localStorage.getItem(EXAM_SLOTS_KEY) || '{}');
    return m && typeof m === 'object' ? m : {};
  } catch { return {}; }
}

function saveLocalExamSlotsMap(m) {
  localStorage.setItem(EXAM_SLOTS_KEY, JSON.stringify(m));
}

function examNext7Dates() {
  const out = [];
  const now = new Date();
  for (let i = 0; i < 7; i++) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() + i);
    const iso = d.toISOString().slice(0, 10);
    out.push({ date: iso, label: dateLabelFromIso(iso), weekday: ['日', '一', '二', '三', '四', '五', '六'][d.getDay()] });
  }
  return out;
}

function mockGenerateSlots(examId, date) {
  const map = loadLocalExamSlotsMap();
  const key = `${examId}|${date}`;
  if (Array.isArray(map[key]) && map[key].length) {
    return map[key].map((s) => normalizeExamSlot(s, examId, 'mock'));
  }
  const times = ['07:30', '08:00', '08:30', '09:00', '09:30', '10:00', '10:30', '14:00', '14:30', '15:00', '15:30'];
  const booked = loadLocalExamBookings().filter(
    (b) => b.examId === examId && b.date === date && b.status !== 'cancelled'
  );
  const used = {};
  booked.forEach((b) => { used[b.slotId] = (used[b.slotId] || 0) + 1; });
  const slots = times.map((t, i) => {
    const id = `mockslot-${examId}-${date}-${t.replace(':', '')}`;
    const remaining = Math.max(0, 4 - (used[id] || 0));
    return {
      id, examId, date, time: t, remaining, available: remaining > 0,
      dateLabel: dateLabelFromIso(date)
    };
  });
  map[key] = slots;
  saveLocalExamSlotsMap(map);
  return slots.map((s) => normalizeExamSlot(s, examId, 'mock'));
}

function mockReleaseSlot(slotId) {
  if (!slotId) return;
  const map = loadLocalExamSlotsMap();
  Object.keys(map).forEach((k) => {
    map[k] = (map[k] || []).map((s) => {
      if (s.id !== slotId) return s;
      const rem = Math.min(4, (Number(s.remaining) || 0) + 1);
      return { ...s, remaining: rem, available: rem > 0 };
    });
  });
  saveLocalExamSlotsMap(map);
}

function mockOccupySlot(slotId) {
  if (!slotId) return;
  const map = loadLocalExamSlotsMap();
  Object.keys(map).forEach((k) => {
    map[k] = (map[k] || []).map((s) => {
      if (s.id !== slotId) return s;
      const rem = Math.max(0, (Number(s.remaining) || 0) - 1);
      return { ...s, remaining: rem, available: rem > 0 };
    });
  });
  saveLocalExamSlotsMap(map);
}

async function fetchExamItems(category) {
  const paths = ['/api/lab-exams', '/api/exams', '/api/exams/catalog', '/api/exam-items'];
  const q = category && category !== 'all' ? `?category=${encodeURIComponent(category === 'imaging' ? 'imaging' : 'lab')}` : '';
  for (const base of paths) {
    try {
      const data = await apiFetch(base + (base.includes('?') ? '' : q));
      let list = asList(data, ['items', 'exams', 'data', 'results', 'catalog']);
      if (!list.length && Array.isArray(data)) list = data;
      const mapped = list.map((x) => normalizeExamItem(x, 'api')).filter(Boolean);
      if (mapped.length) {
        state.examUsingApi = true;
        if (category === 'lab') return mapped.filter((x) => x.category === 'lab');
        if (category === 'imaging') return mapped.filter((x) => x.category !== 'lab');
        return mapped;
      }
    } catch { /* try next */ }
  }
  state.examUsingApi = false;
  let seed = EXAM_SEED_ITEMS.map((x) => normalizeExamItem(x, 'mock'));
  if (category === 'lab') seed = seed.filter((x) => x.category === 'lab');
  if (category === 'imaging') seed = seed.filter((x) => x.category !== 'lab');
  return seed;
}

async function fetchExamItem(examId) {
  const paths = [
    `/api/lab-exams/${encodeURIComponent(examId)}`,
    `/api/exams/${encodeURIComponent(examId)}`,
    `/api/exam-items/${encodeURIComponent(examId)}`
  ];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      const item = normalizeExamItem(data.item || data.exam || data, 'api');
      if (item?.id) return item;
    } catch { /* next */ }
  }
  const all = await fetchExamItems('all');
  return all.find((x) => String(x.id) === String(examId)) || null;
}

async function fetchExamSlots(examId, date) {
  const paths = [
    `/api/lab-exams/${encodeURIComponent(examId)}/slots?date=${encodeURIComponent(date)}`,
    `/api/exams/${encodeURIComponent(examId)}/slots?date=${encodeURIComponent(date)}`,
    `/api/exam-items/${encodeURIComponent(examId)}/slots?date=${encodeURIComponent(date)}`
  ];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      let list = asList(data, ['items', 'slots', 'data', 'results']);
      if (!list.length && Array.isArray(data)) list = data;
      const mapped = list.map((s) => normalizeExamSlot(s, examId, 'api')).filter(Boolean);
      if (mapped.length) {
        state.examUsingApi = true;
        return mapped;
      }
    } catch { /* next */ }
  }
  state.examUsingApi = false;
  return mockGenerateSlots(examId, date);
}

async function fetchExamBookings() {
  const paths = ['/api/lab-exam-bookings', '/api/exam-appointments', '/api/exam-bookings'];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      let list = asList(data, ['items', 'bookings', 'data', 'results']);
      if (!list.length && Array.isArray(data)) list = data;
      const mapped = list.map((b) => normalizeExamBooking(b, 'api')).filter(Boolean);
      // Treat any well-formed list response (incl. empty items[]) as API success
      if (Array.isArray(data?.items) || mapped.length || Array.isArray(data)) {
        state.examUsingApi = true;
        saveLocalExamBookings(mapped.map((b) => ({ ...b, source: 'api' })));
        return mapped;
      }
    } catch { /* next */ }
  }
  state.examUsingApi = false;
  return loadLocalExamBookings().map((b) => normalizeExamBooking(b, b.source || 'mock'));
}

async function fetchExamBooking(id) {
  const paths = [
    `/api/lab-exam-bookings/${encodeURIComponent(id)}`,
    `/api/exam-appointments/${encodeURIComponent(id)}`,
    `/api/exam-bookings/${encodeURIComponent(id)}`
  ];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      const b = normalizeExamBooking(data.booking || data.item || data, 'api');
      if (b?.id) {
        state.examUsingApi = true;
        return b;
      }
    } catch { /* next */ }
  }
  const local = loadLocalExamBookings().find((x) => String(x.id) === String(id));
  return local ? normalizeExamBooking(local, local.source || 'mock') : null;
}

async function createExamBooking({ examId, slotId, date, time }) {
  const ap = getActivePatient();
  const body = {
    examId,
    itemId: examId, // alias for /api/exam-bookings
    slotId,
    patientId: ap?.id || null,
    patientName: ap?.name || '演示患者'
  };
  const paths = ['/api/lab-exam-bookings', '/api/exam-appointments', '/api/exam-bookings'];
  for (const p of paths) {
    try {
      const data = await apiFetch(p, { method: 'POST', body: JSON.stringify(body) });
      const b = normalizeExamBooking(data.booking || data.item || data, 'api');
      if (b?.id) {
        state.examUsingApi = true;
        const local = loadLocalExamBookings();
        const idx = local.findIndex((x) => String(x.id) === String(b.id));
        if (idx >= 0) local[idx] = { ...local[idx], ...b, source: 'api' };
        else local.unshift({ ...b, source: 'api' });
        saveLocalExamBookings(local);
        return b;
      }
    } catch { /* next */ }
  }
  // Mock
  state.examUsingApi = false;
  const item = (await fetchExamItem(examId)) || EXAM_SEED_ITEMS.find((x) => x.id === examId);
  const booking = normalizeExamBooking({
    id: 'leb-mock-' + Date.now(),
    examId,
    slotId,
    date,
    time,
    patientId: ap?.id || '',
    patientName: ap?.name || '演示患者',
    status: 'confirmed',
    rescheduleCount: 0,
    maxReschedule: EXAM_MAX_RESCHEDULE,
    examName: item?.name,
    location: item?.location,
    prepNotes: item?.prepNotes,
    category: item?.category,
    price: item?.price,
    durationMinutes: item?.durationMinutes,
    createdAt: new Date().toISOString().replace('T', ' ').slice(0, 19),
    source: 'mock'
  }, 'mock');
  mockOccupySlot(slotId);
  const local = loadLocalExamBookings();
  local.unshift(booking);
  saveLocalExamBookings(local);
  return booking;
}

async function rescheduleExamBooking(bookingId, { slotId, date, time }) {
  const body = {};
  if (slotId) body.slotId = slotId;
  if (date) body.date = date;
  if (time) body.time = time;
  // Prefer PATCH on lab-exam-bookings; also try POST .../reschedule aliases
  const attempts = [
    { method: 'PATCH', path: `/api/lab-exam-bookings/${encodeURIComponent(bookingId)}` },
    { method: 'PATCH', path: `/api/exam-appointments/${encodeURIComponent(bookingId)}` },
    { method: 'POST', path: `/api/lab-exam-bookings/${encodeURIComponent(bookingId)}/reschedule` },
    { method: 'POST', path: `/api/exam-bookings/${encodeURIComponent(bookingId)}/reschedule` },
    { method: 'PATCH', path: `/api/exam-bookings/${encodeURIComponent(bookingId)}` }
  ];
  for (const a of attempts) {
    try {
      const data = await apiFetch(a.path, { method: a.method, body: JSON.stringify(body) });
      const b = normalizeExamBooking(data.booking || data.item || data, 'api');
      if (b?.id) {
        state.examUsingApi = true;
        const local = loadLocalExamBookings();
        const idx = local.findIndex((x) => String(x.id) === String(b.id));
        if (idx >= 0) local[idx] = { ...local[idx], ...b, source: 'api' };
        else local.unshift({ ...b, source: 'api' });
        saveLocalExamBookings(local);
        return b;
      }
    } catch { /* next */ }
  }
  // Mock
  state.examUsingApi = false;
  const local = loadLocalExamBookings();
  const idx = local.findIndex((x) => String(x.id) === String(bookingId));
  if (idx < 0) throw new Error('预约不存在');
  const cur = normalizeExamBooking(local[idx], local[idx].source || 'mock');
  if (cur.status === 'cancelled') throw new Error('预约已取消，无法改约');
  if (cur.rescheduleCount >= (cur.maxReschedule || EXAM_MAX_RESCHEDULE)) {
    throw new Error(`已达改约上限（${cur.maxReschedule || EXAM_MAX_RESCHEDULE} 次）`);
  }
  mockReleaseSlot(cur.slotId);
  mockOccupySlot(slotId);
  const next = {
    ...cur,
    slotId,
    date: date || cur.date,
    time: time || cur.time,
    dateLabel: dateLabelFromIso(date || cur.date),
    rescheduleCount: cur.rescheduleCount + 1,
    updatedAt: new Date().toISOString().replace('T', ' ').slice(0, 19),
    source: 'mock'
  };
  next.canReschedule = next.rescheduleCount < (next.maxReschedule || EXAM_MAX_RESCHEDULE);
  local[idx] = next;
  saveLocalExamBookings(local);
  return normalizeExamBooking(next, 'mock');
}

async function cancelExamBooking(bookingId) {
  const attempts = [
    { method: 'POST', path: `/api/lab-exam-bookings/${encodeURIComponent(bookingId)}/cancel`, body: '{}' },
    { method: 'POST', path: `/api/exam-appointments/${encodeURIComponent(bookingId)}/cancel`, body: '{}' },
    { method: 'POST', path: `/api/exam-bookings/${encodeURIComponent(bookingId)}/cancel`, body: '{}' },
    { method: 'PATCH', path: `/api/lab-exam-bookings/${encodeURIComponent(bookingId)}`, body: JSON.stringify({ status: 'cancelled' }) }
  ];
  for (const a of attempts) {
    try {
      const data = await apiFetch(a.path, { method: a.method, body: a.body });
      const b = normalizeExamBooking(data.booking || data.item || data, 'api');
      if (b?.id) {
        state.examUsingApi = true;
        b.status = 'cancelled';
        b.statusLabel = '已取消';
        const local = loadLocalExamBookings();
        const idx = local.findIndex((x) => String(x.id) === String(b.id));
        if (idx >= 0) local[idx] = { ...local[idx], ...b, status: 'cancelled', source: 'api' };
        saveLocalExamBookings(local);
        return b;
      }
    } catch { /* next */ }
  }
  state.examUsingApi = false;
  const local = loadLocalExamBookings();
  const idx = local.findIndex((x) => String(x.id) === String(bookingId));
  if (idx < 0) throw new Error('预约不存在');
  const cur = local[idx];
  mockReleaseSlot(cur.slotId);
  local[idx] = {
    ...cur,
    status: 'cancelled',
    statusLabel: '已取消',
    cancelledAt: new Date().toISOString().replace('T', ' ').slice(0, 19),
    updatedAt: new Date().toISOString().replace('T', ' ').slice(0, 19)
  };
  saveLocalExamBookings(local);
  return normalizeExamBooking(local[idx], 'mock');
}

function setExamBookSteps(step) {
  $$('#examBookSteps .step').forEach((el) => {
    const n = Number(el.dataset.step);
    el.classList.toggle('active', n === step);
    el.classList.toggle('done', n < step);
  });
}

function enrichSpecialTips(item) {
  if (!item) return [];
  const tips = [...(item.specialTips || [])];
  const name = item.name || '';
  const notes = item.prepNotes || '';
  if (/CT|ct/.test(name) || /碘|孕/.test(notes)) {
    if (!tips.some((t) => /碘|孕/.test(t))) {
      tips.push('增强 CT：告知碘过敏 / 哮喘 / 肾功能');
      tips.push('怀孕或备孕请务必告知技师');
    }
  }
  if (/B超|超声|憋尿/.test(name + notes)) {
    if (!tips.some((t) => /憋尿/.test(t))) tips.push('下腹/泌尿系超声：提前憋尿');
  }
  if (/血|肝|空腹/.test(name + notes) && item.category === 'lab') {
    if (!tips.some((t) => /空腹/.test(t))) tips.push('抽血项目请确认是否需空腹');
  }
  return tips;
}

async function renderExamItems() {
  const box = $('#examItemsContent');
  if (!box) return;
  $$('#examCatTabs .seg-tab').forEach((t) => {
    t.classList.toggle('active', (t.dataset.cat || 'all') === state.examCat);
  });
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchExamItems(state.examCat);
  if (!list.length) {
    box.innerHTML = `<div class="empty-state"><div class="big">🔬</div><p>暂无检查检验项目</p></div>`;
    return;
  }
  box.innerHTML = `
    <p class="ref-note" style="margin:0 0 10px">来源：${sourceLabel(state.examUsingApi ? 'api' : 'mock')} · ${EXAM_DISCLAIMER}</p>
    <div class="exam-item-list">
      ${list.map((it) => `
        <button type="button" class="exam-item-card" data-id="${escapeHtml(it.id)}">
          <div class="exam-item-head">
            <span class="exam-cat-pill ${it.category}">${escapeHtml(it.categoryLabel)}</span>
            <strong>${escapeHtml(it.name)}</strong>
            <span class="exam-price">${formatMoney(it.price)}</span>
          </div>
          <p class="meta">约 ${it.durationMinutes} 分钟 · ${escapeHtml(it.location)}</p>
          <p class="exam-prep"><span class="tag">注意</span>${escapeHtml(it.prepSummary)}</p>
        </button>
      `).join('')}
    </div>`;
  box.querySelectorAll('.exam-item-card').forEach((btn) => {
    btn.addEventListener('click', async () => {
      setLoading(true, '打开项目…');
      try {
        const item = list.find((x) => String(x.id) === btn.dataset.id) || await fetchExamItem(btn.dataset.id);
        state.examItem = item;
        resetExamBookState({ mode: 'book' });
        showView('exam-book');
      } finally {
        setLoading(false);
      }
    });
  });
  $('#examGoMine')?.addEventListener('click', () => showView('exam-mine'), { once: true });
}

async function renderExamBook() {
  const box = $('#examBookContent');
  if (!box) return;
  const item = state.examItem;
  const book = state.examBook;
  if (!item) {
    box.innerHTML = `<div class="empty-state"><p>请先选择检查项目</p>
      <button class="btn primary" id="examBookBackItems" style="margin-top:12px">返回项目列表</button></div>`;
    $('#examBookBackItems')?.addEventListener('click', () => showView('exam'));
    return;
  }
  const isResched = book.mode === 'reschedule';
  setExamBookSteps(book.step);
  const tips = enrichSpecialTips(item);

  if (book.step === 1) {
    const dates = examNext7Dates();
    box.innerHTML = `
      <div class="exam-item-summary">
        <div class="exam-item-head">
          <span class="exam-cat-pill ${item.category}">${escapeHtml(item.categoryLabel)}</span>
          <strong>${escapeHtml(item.name)}</strong>
          <span class="exam-price">${formatMoney(item.price)}</span>
        </div>
        <p class="meta">${escapeHtml(item.location)} · 约 ${item.durationMinutes} 分钟</p>
        <p class="exam-mode-tag">${isResched ? '改约中 · 请选择新日期' : '新预约 · 请选择日期（近 7 天）'}</p>
      </div>
      <div class="exam-tips-card">
        <h4>⚠️ 注意事项</h4>
        <p>${escapeHtml(item.prepNotes)}</p>
        ${tips.length ? `<ul>${tips.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>` : ''}
      </div>
      <div class="exam-date-grid" id="examDateGrid">
        ${dates.map((d) => `
          <button type="button" class="exam-date-btn ${book.date === d.date ? 'selected' : ''}" data-date="${d.date}">
            <strong>${escapeHtml(d.date.slice(5))}</strong>
            <small>周${d.weekday}</small>
          </button>`).join('')}
      </div>
      <button class="btn ghost block" id="examBookCancelFlow" style="margin-top:12px">${isResched ? '放弃改约' : '返回项目列表'}</button>
    `;
    $('#examDateGrid')?.querySelectorAll('.exam-date-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        book.date = btn.dataset.date;
        book.slot = null;
        book.step = 2;
        renderExamBook();
      });
    });
    $('#examBookCancelFlow')?.addEventListener('click', () => {
      if (isResched) showView('exam-detail');
      else showView('exam');
    });
    return;
  }

  if (book.step === 2) {
    box.innerHTML = `
      <p class="result-meta" style="margin-top:0">${escapeHtml(item.name)} · ${escapeHtml(dateLabelFromIso(book.date))} · 请选择时段</p>
      <div id="examSlotGrid"><div class="empty-state">加载中…</div></div>
      <button class="btn ghost block" style="margin-top:12px" id="examBookBackDate">上一步</button>`;
    $('#examBookBackDate').onclick = () => { book.step = 1; book.slot = null; renderExamBook(); };
    const slots = await fetchExamSlots(item.id, book.date);
    const grid = $('#examSlotGrid');
    if (!slots.length) {
      grid.innerHTML = `<div class="empty-state"><p>该日暂无号源</p></div>`;
      return;
    }
    grid.innerHTML = `<div class="slot-grid">${slots.map((s) => {
      const disabled = !s.available || s.remaining === 0;
      return `<button type="button" class="slot-btn" data-id="${escapeHtml(s.id)}" ${disabled ? 'disabled' : ''}>
        ${escapeHtml(s.time)}${disabled ? '<br/><small>已满</small>' : (s.remaining != null ? `<br/><small>余${s.remaining}</small>` : '')}
      </button>`;
    }).join('')}</div>
    <p class="ref-note">来源：${sourceLabel(slots[0]?.source || (state.examUsingApi ? 'api' : 'mock'))}</p>`;
    grid.querySelectorAll('.slot-btn:not(:disabled)').forEach((btn) => {
      btn.addEventListener('click', () => {
        book.slot = slots.find((x) => String(x.id) === btn.dataset.id);
        book.step = 3;
        renderExamBook();
      });
    });
    return;
  }

  // step 3 confirm
  const ap = getActivePatient();
  const slot = book.slot;
  box.innerHTML = `
    <div class="confirm-box">
      <h3 style="margin:0 0 12px">${isResched ? '确认改约' : '确认预约信息'}</h3>
      <dl>
        <dt>项目</dt><dd>${escapeHtml(item.name)}（${escapeHtml(item.categoryLabel)}）</dd>
        <dt>地点</dt><dd>${escapeHtml(item.location)}</dd>
        <dt>时段</dt><dd>${escapeHtml(dateLabelFromIso(book.date))} ${escapeHtml(slot?.time || '')}</dd>
        <dt>预计时长</dt><dd>${item.durationMinutes} 分钟</dd>
        <dt>费用占位</dt><dd>${formatMoney(item.price)}</dd>
        <dt>就诊人</dt><dd>${escapeHtml(ap?.name || '演示患者')}（${escapeHtml(ap?.relation || '本人')}）</dd>
        ${isResched ? `<dt>改约次数</dt><dd>将计入改约（上限 ${EXAM_MAX_RESCHEDULE} 次）</dd>` : ''}
      </dl>
      <div class="exam-tips-card" style="margin-top:12px">
        <h4>注意事项全文</h4>
        <p>${escapeHtml(item.prepNotes)}</p>
        ${tips.length ? `<ul>${tips.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>` : ''}
      </div>
      <p class="ref-note">${EXAM_DISCLAIMER}</p>
      <div class="actions-row" style="margin-top:14px">
        <button class="btn primary" id="examConfirmBtn">${isResched ? '确认改约' : '确认预约'}</button>
        <button class="btn ghost" id="examConfirmBack">上一步</button>
      </div>
    </div>`;
  $('#examConfirmBack').onclick = () => { book.step = 2; renderExamBook(); };
  $('#examConfirmBtn').onclick = async () => {
    setLoading(true, isResched ? '改约中…' : '提交预约…');
    try {
      let booking;
      if (isResched && book.bookingId) {
        booking = await rescheduleExamBooking(book.bookingId, {
          slotId: slot.id, date: book.date, time: slot.time
        });
        toast('改约成功');
      } else {
        booking = await createExamBooking({
          examId: item.id, slotId: slot.id, date: book.date, time: slot.time
        });
        toast('预约成功');
      }
      state.examLastBooking = booking;
      state.examCurrentId = booking.id;
      showView('exam-success');
    } catch (err) {
      toast(err?.message || '操作失败，请稍后重试');
    } finally {
      setLoading(false);
    }
  };
}

async function renderExamSuccess() {
  const box = $('#examSuccessContent');
  if (!box) return;
  let b = state.examLastBooking;
  if (!b && state.examCurrentId) b = await fetchExamBooking(state.examCurrentId);
  if (!b) {
    box.innerHTML = `<div class="empty-state"><p>暂无预约结果</p>
      <button class="btn primary" id="examSucGoList">我的检查</button></div>`;
    $('#examSucGoList')?.addEventListener('click', () => showView('exam-mine'));
    return;
  }
  const tips = enrichSpecialTips({
    name: b.examName, prepNotes: b.prepNotes, category: b.category, specialTips: []
  });
  box.innerHTML = `
    <div class="success-panel">
      <div class="big">✅</div>
      <h3>${state.examBook?.mode === 'reschedule' ? '改约成功' : '预约成功'}</h3>
      <p>${escapeHtml(b.examName)} · ${escapeHtml(b.dateLabel || dateLabelFromIso(b.date))} ${escapeHtml(b.time)}</p>
    </div>
    <div class="confirm-box">
      <dl>
        <dt>订单号</dt><dd>${escapeHtml(b.orderNo || b.id)}</dd>
        <dt>地点</dt><dd>${escapeHtml(b.location)}</dd>
        <dt>就诊人</dt><dd>${escapeHtml(b.patientName || '—')}</dd>
        <dt>费用占位</dt><dd>${formatMoney(b.price)}</dd>
        <dt>改约次数</dt><dd>${b.rescheduleCount} / ${b.maxReschedule || EXAM_MAX_RESCHEDULE}</dd>
      </dl>
      <div class="exam-tips-card" style="margin-top:12px">
        <h4>注意事项</h4>
        <p>${escapeHtml(b.prepNotes || '请按医嘱准备')}</p>
        ${tips.length ? `<ul>${tips.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>` : ''}
      </div>
      <p class="ref-note">${escapeHtml(b.disclaimer || EXAM_DISCLAIMER)} · 来源：${sourceLabel(b.source)}</p>
      <div class="actions-row" style="margin-top:14px;justify-content:center">
        <button class="btn primary" id="examSucMine">我的检查</button>
        <button class="btn ghost" id="examSucDetail">查看详情</button>
        <button class="btn ghost" id="examSucHome">返回首页</button>
      </div>
    </div>`;
  $('#examSucMine')?.addEventListener('click', () => showView('exam-mine'));
  $('#examSucDetail')?.addEventListener('click', () => {
    state.examCurrentId = b.id;
    showView('exam-detail');
  });
  $('#examSucHome')?.addEventListener('click', () => showView('home'));
}

async function renderExamMine() {
  const box = $('#examMineContent');
  if (!box) return;
  $$('#examMineTabs .seg-tab').forEach((t) => {
    t.classList.toggle('active', (t.dataset.filter || 'booked') === state.examMineFilter);
  });
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchExamBookings();
  const filtered = list.filter((b) => {
    if (state.examMineFilter === 'cancelled') return b.status === 'cancelled';
    if (state.examMineFilter === 'booked') return b.status === 'confirmed' || b.status === 'completed';
    return true;
  });
  if (!filtered.length) {
    box.innerHTML = `<div class="empty-state"><div class="big">📋</div><p>暂无检查预约</p>
      <p class="ref-note">${EXAM_DISCLAIMER}</p></div>`;
  } else {
    box.innerHTML = `
      <p class="ref-note" style="margin:0 0 10px">来源：${sourceLabel(state.examUsingApi ? 'api' : 'mock')} · 改约上限 ${EXAM_MAX_RESCHEDULE} 次</p>
      ${filtered.map((b) => `
        <div class="exam-booking-card" data-id="${escapeHtml(b.id)}">
          <div class="appt-card-head">
            <h4>${escapeHtml(b.examName)}</h4>
            <span class="status-pill ${b.status === 'cancelled' ? 'cancelled' : 'pending'}">${escapeHtml(b.statusLabel)}</span>
          </div>
          <p class="meta">${escapeHtml(b.dateLabel || dateLabelFromIso(b.date))} ${escapeHtml(b.time)}
            <br/>${escapeHtml(b.location)}
            ${b.patientName ? `<br/>就诊人：${escapeHtml(b.patientName)}` : ''}
            <br/>改约 ${b.rescheduleCount}/${b.maxReschedule || EXAM_MAX_RESCHEDULE}
          </p>
          <div class="appt-actions">
            <button type="button" class="btn ghost sm btn-exam-detail" data-id="${escapeHtml(b.id)}">详情</button>
            ${b.status === 'confirmed' && b.canReschedule ? `<button type="button" class="btn primary sm btn-exam-resched" data-id="${escapeHtml(b.id)}">改约</button>` : ''}
            ${b.status === 'confirmed' && !b.canReschedule ? `<button type="button" class="btn ghost sm" disabled title="已达改约上限">改约已达上限</button>` : ''}
            ${b.status === 'confirmed' ? `<button type="button" class="btn ghost sm btn-exam-cancel" data-id="${escapeHtml(b.id)}">取消</button>` : ''}
          </div>
        </div>
      `).join('')}`;
  }
  box.querySelectorAll('.btn-exam-detail').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.examCurrentId = btn.dataset.id;
      showView('exam-detail');
    });
  });
  box.querySelectorAll('.btn-exam-resched').forEach((btn) => {
    btn.addEventListener('click', () => startExamReschedule(btn.dataset.id));
  });
  box.querySelectorAll('.btn-exam-cancel').forEach((btn) => {
    btn.addEventListener('click', async () => {
      if (!confirm('确定取消该检查预约？取消后不可再改约。')) return;
      setLoading(true, '取消中…');
      try {
        await cancelExamBooking(btn.dataset.id);
        toast('已取消预约');
        await renderExamMine();
      } catch (err) {
        toast(err?.message || '取消失败');
      } finally {
        setLoading(false);
      }
    });
  });
  $('#examMineGoBook')?.addEventListener('click', () => {
    resetExamBookState();
    showView('exam');
  }, { once: true });
}

async function startExamReschedule(bookingId) {
  setLoading(true, '准备改约…');
  try {
    const b = await fetchExamBooking(bookingId);
    if (!b) { toast('预约不存在'); return; }
    if (b.status === 'cancelled') { toast('已取消，无法改约'); return; }
    if (!b.canReschedule) {
      toast(`已达改约上限（${b.maxReschedule || EXAM_MAX_RESCHEDULE} 次）`);
      return;
    }
    let item = await fetchExamItem(b.examId);
    if (!item) {
      item = normalizeExamItem({
        id: b.examId, name: b.examName, category: b.category || 'lab',
        location: b.location, prepNotes: b.prepNotes, price: b.price,
        durationMinutes: b.durationMinutes
      }, b.source);
    }
    state.examItem = item;
    state.examCurrentId = b.id;
    resetExamBookState({ mode: 'reschedule', bookingId: b.id });
    showView('exam-book');
  } finally {
    setLoading(false);
  }
}

async function renderExamDetail() {
  const box = $('#examDetailContent');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const b = await fetchExamBooking(state.examCurrentId);
  if (!b) {
    box.innerHTML = `<div class="empty-state"><p>未找到预约</p>
      <button class="btn primary" id="examDetBack">返回我的检查</button></div>`;
    $('#examDetBack')?.addEventListener('click', () => showView('exam-mine'));
    return;
  }
  const tips = enrichSpecialTips({
    name: b.examName, prepNotes: b.prepNotes, category: b.category, specialTips: []
  });
  const limitHit = b.status === 'confirmed' && !b.canReschedule;
  box.innerHTML = `
    <div class="m3-disclaimer soft" role="note">
      <strong>${escapeHtml(b.disclaimer || EXAM_DISCLAIMER)}</strong>
      <p>订单号 ${escapeHtml(b.orderNo || b.id)} · 来源：${sourceLabel(b.source)}</p>
    </div>
    <div class="confirm-box">
      <div class="appt-card-head" style="margin-bottom:8px">
        <h3 style="margin:0">${escapeHtml(b.examName)}</h3>
        <span class="status-pill ${b.status === 'cancelled' ? 'cancelled' : 'pending'}">${escapeHtml(b.statusLabel)}</span>
      </div>
      <dl>
        <dt>时段</dt><dd>${escapeHtml(b.dateLabel || dateLabelFromIso(b.date))} ${escapeHtml(b.time)}</dd>
        <dt>地点</dt><dd>${escapeHtml(b.location)}</dd>
        <dt>就诊人</dt><dd>${escapeHtml(b.patientName || '—')}</dd>
        <dt>费用</dt><dd>${formatMoney(b.price)}</dd>
        <dt>改约</dt><dd>${b.rescheduleCount} / ${b.maxReschedule || EXAM_MAX_RESCHEDULE}${limitHit ? '（已达上限）' : ''}</dd>
      </dl>
      <div class="exam-tips-card" style="margin-top:12px">
        <h4>特殊检查注意事项</h4>
        <p>${escapeHtml(b.prepNotes || '请按医嘱准备')}</p>
        ${tips.length ? `<ul>${tips.map((t) => `<li>${escapeHtml(t)}</li>`).join('')}</ul>` : ''}
        <p class="ref-note" style="margin-top:8px">CT 请告知孕情与碘过敏史；B 超按项目憋尿/空腹；抽血确认空腹要求。</p>
      </div>
      <div class="actions-row" style="margin-top:14px">
        ${b.status === 'confirmed' && b.canReschedule ? `<button class="btn primary" id="examDetResched">改约</button>` : ''}
        ${limitHit ? `<button class="btn ghost" disabled>改约已达上限</button>` : ''}
        ${b.status === 'confirmed' ? `<button class="btn ghost" id="examDetCancel">取消预约</button>` : ''}
        <button class="btn ghost" id="examDetMine">我的检查</button>
      </div>
      ${limitHit ? `<p class="ref-note">已达改约上限（${b.maxReschedule || EXAM_MAX_RESCHEDULE} 次），无法继续改约。</p>` : ''}
      ${b.status === 'cancelled' ? `<p class="ref-note">已取消，不可再改约。</p>` : ''}
    </div>`;
  $('#examDetResched')?.addEventListener('click', () => startExamReschedule(b.id));
  $('#examDetCancel')?.addEventListener('click', async () => {
    if (!confirm('确定取消该检查预约？取消后不可再改约。')) return;
    setLoading(true, '取消中…');
    try {
      const nb = await cancelExamBooking(b.id);
      state.examLastBooking = nb;
      toast('已取消预约');
      await renderExamDetail();
    } catch (err) {
      toast(err?.message || '取消失败');
    } finally {
      setLoading(false);
    }
  });
  $('#examDetMine')?.addEventListener('click', () => showView('exam-mine'));
}

// M6 tabs
document.addEventListener('click', (e) => {
  const cat = e.target.closest('#examCatTabs .seg-tab');
  if (cat) {
    state.examCat = cat.dataset.cat || 'all';
    renderExamItems();
    return;
  }
  const mf = e.target.closest('#examMineTabs .seg-tab');
  if (mf) {
    state.examMineFilter = mf.dataset.filter || 'booked';
    renderExamMine();
  }
});

/* ========== M7 · 药品配送到家 Mock ========== */

const PHARM_DISCLAIMER = '演示环境，非真实处方流转/非真实物流配送';

const PHARM_STATUS = {
  pending_shipment: { key: 'pending_shipment', label: '待发货', pill: 'pending', step: 0 },
  in_transit: { key: 'in_transit', label: '运输中', pill: 'accepted', step: 1 },
  delivered: { key: 'delivered', label: '已送达', pill: 'done', step: 2 },
  cancelled: { key: 'cancelled', label: '已取消', pill: 'cancelled', step: -1 }
};

const PHARM_STATUS_FLOW = ['pending_shipment', 'in_transit', 'delivered'];

function normalizePharmStatus(raw) {
  const s = String(raw || '').toLowerCase().trim();
  if (!s) return 'pending_shipment';
  if (s === 'cancelled' || s === 'canceled' || s.includes('取消')) return 'cancelled';
  if (s === 'pending' || s === 'pending_shipment' || s.includes('待发') || s === 'created' || s === 'awaiting_shipment') {
    return 'pending_shipment';
  }
  if (s === 'shipped' || s === 'in_transit' || s === 'shipping' || s.includes('运输') || s.includes('在途') || s === 'transit') {
    return 'in_transit';
  }
  if (s === 'delivered' || s === 'done' || s === 'completed' || s.includes('送达') || s.includes('签收')) {
    return 'delivered';
  }
  return 'pending_shipment';
}

function pharmStatusMeta(st) {
  const key = normalizePharmStatus(st);
  return PHARM_STATUS[key] || PHARM_STATUS.pending_shipment;
}

function pharmNowLabel() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
}

const PHARM_SEED_ORDERS = [
  {
    id: 'rx-order-1',
    title: '慢病续方购药',
    type: 'refill',
    typeLabel: '慢病续方',
    department: '心内科',
    doctorName: '王医生',
    status: 'deliverable',
    statusLabel: '可配送',
    createdAt: '2026-10-06 10:20:00',
    items: [
      { name: '氨氯地平片', spec: '5mg×30片', quantity: 1, unit: '盒' },
      { name: '阿司匹林肠溶片', spec: '100mg×30片', quantity: 1, unit: '盒' }
    ],
    amount: 46.8,
    note: '高血压长期用药续方演示单'
  },
  {
    id: 'rx-order-2',
    title: '门诊处方购药',
    type: 'outpatient',
    typeLabel: '门诊处方',
    department: '呼吸内科',
    doctorName: '李医生',
    status: 'deliverable',
    statusLabel: '可配送',
    createdAt: '2026-10-07 15:40:00',
    items: [
      { name: '阿莫西林胶囊', spec: '0.25g×24粒', quantity: 2, unit: '盒' },
      { name: '复方甘草片', spec: '50片', quantity: 1, unit: '瓶' }
    ],
    amount: 38.5,
    note: '门诊开具演示处方，非真实处方流转'
  },
  {
    id: 'rx-order-3',
    title: '内分泌慢病购药',
    type: 'refill',
    typeLabel: '慢病续方',
    department: '内分泌科',
    doctorName: '陈医生',
    status: 'deliverable',
    statusLabel: '可配送',
    createdAt: '2026-10-08 09:05:00',
    items: [
      { name: '二甲双胍缓释片', spec: '0.5g×30片', quantity: 2, unit: '盒' },
      { name: '阿托伐他汀钙片', spec: '20mg×7片', quantity: 1, unit: '盒' }
    ],
    amount: 72.0,
    note: '糖尿病/血脂管理演示购药单'
  }
];

const PHARM_SEED_ADDRESSES = [
  {
    id: 'addr-1',
    name: '张三',
    phone: '13800138000',
    province: '上海市',
    city: '上海市',
    district: '浦东新区',
    detail: '张江路 88 号 导诊台小区 3 栋 502',
    isDefault: true
  }
];

function loadLocalPharmOrders() {
  try {
    const list = JSON.parse(localStorage.getItem(PHARMACY_ORDERS_KEY) || '[]');
    return Array.isArray(list) ? list : [];
  } catch { return []; }
}
function saveLocalPharmOrders(list) {
  localStorage.setItem(PHARMACY_ORDERS_KEY, JSON.stringify(list));
}
function ensureLocalPharmOrders() {
  let list = loadLocalPharmOrders();
  if (!list.length) {
    list = PHARM_SEED_ORDERS.map((o) => ({ ...o, source: 'mock' }));
    saveLocalPharmOrders(list);
  }
  return list;
}

function loadLocalPharmAddresses() {
  try {
    const list = JSON.parse(localStorage.getItem(PHARMACY_ADDRESSES_KEY) || '[]');
    return Array.isArray(list) ? list : [];
  } catch { return []; }
}
function saveLocalPharmAddresses(list) {
  localStorage.setItem(PHARMACY_ADDRESSES_KEY, JSON.stringify(list));
}
function ensureLocalPharmAddresses() {
  let list = loadLocalPharmAddresses();
  if (!list.length) {
    list = PHARM_SEED_ADDRESSES.map((a) => ({ ...a, source: 'mock' }));
    saveLocalPharmAddresses(list);
  }
  return list;
}

function loadLocalPharmDeliveries() {
  try {
    const list = JSON.parse(localStorage.getItem(PHARMACY_DELIVERIES_KEY) || '[]');
    return Array.isArray(list) ? list : [];
  } catch { return []; }
}
function saveLocalPharmDeliveries(list) {
  localStorage.setItem(PHARMACY_DELIVERIES_KEY, JSON.stringify(list));
}

function normalizePharmOrderItem(it) {
  if (!it) return null;
  return {
    name: it.name || it.medicationName || it.drugName || '药品',
    spec: it.spec || it.specification || it.dosage || it.strength || '',
    quantity: Number(it.quantity ?? it.qty ?? 1) || 1,
    unit: it.unit || '盒'
  };
}

function normalizePharmOrder(o, source) {
  if (!o) return null;
  const items = (Array.isArray(o.items) ? o.items : Array.isArray(o.medications) ? o.medications : Array.isArray(o.drugs) ? o.drugs : [])
    .map(normalizePharmOrderItem).filter(Boolean);
  const rawSt = String(o.status || o.orderStatus || 'deliverable').toLowerCase();
  let status = 'deliverable';
  if (rawSt.includes('deliver') && !rawSt.includes('able') && !rawSt.includes('pending')) status = 'delivering';
  if (rawSt === 'delivering' || rawSt === 'shipped' || rawSt === 'in_transit' || rawSt.includes('配送中')) status = 'delivering';
  if (rawSt === 'delivered' || rawSt.includes('已配') || rawSt.includes('完成')) status = 'delivered';
  if (rawSt === 'deliverable' || rawSt === 'ready' || rawSt === 'available' || rawSt.includes('可配')) status = 'deliverable';
  const statusLabel = status === 'deliverable' ? '可配送' : status === 'delivering' ? '配送中' : status === 'delivered' ? '已配送' : (o.statusLabel || status);
  return {
    id: o.id || o.orderId || o.rxOrderId || ('rx-' + Date.now()),
    title: o.title || o.name || o.orderTitle || '购药单',
    type: o.type || o.orderType || 'outpatient',
    typeLabel: o.typeLabel || (o.type === 'refill' ? '慢病续方' : '门诊处方'),
    department: o.department || o.deptName || '',
    doctorName: o.doctorName || o.doctor || '',
    status,
    statusLabel,
    createdAt: o.createdAt || o.created_at || '',
    items,
    amount: Number(o.amount ?? o.totalAmount ?? o.fee ?? 0) || 0,
    note: o.note || o.remark || '',
    disclaimer: o.disclaimer || PHARM_DISCLAIMER,
    source: source || o.source || 'api'
  };
}

function normalizePharmAddress(a, source) {
  if (!a) return null;
  const province = a.province || a.prov || '';
  const city = a.city || '';
  const district = a.district || a.area || '';
  const detail = a.detail || a.address || a.street || '';
  const full = a.fullAddress || a.full || [province, city, district, detail].filter(Boolean).join(' ');
  return {
    id: a.id || a.addressId || ('addr-' + Date.now()),
    name: a.name || a.receiver || a.contactName || '收件人',
    phone: a.phone || a.mobile || a.tel || '',
    province, city, district, detail,
    fullAddress: full,
    isDefault: !!(a.isDefault || a.default || a.is_default),
    source: source || a.source || 'api'
  };
}

function buildTimelineFromStatus(status, existing, createdAt) {
  if (Array.isArray(existing) && existing.length) {
    return existing.map((t) => {
      const st = normalizePharmStatus(t.status || t.code || t.key || t.uiStatus);
      const meta = pharmStatusMeta(st);
      return {
        status: st,
        label: t.label || t.title || meta.label,
        at: t.at || t.time || t.createdAt || '',
        desc: t.desc || t.description || t.message || ''
      };
    });
  }
  const key = normalizePharmStatus(status);
  const step = pharmStatusMeta(key).step;
  const base = createdAt || pharmNowLabel();
  const nodes = [
    { status: 'pending_shipment', label: '待发货', desc: '药店已接单，准备拣货打包' },
    { status: 'in_transit', label: '运输中', desc: '药品已发出，配送途中' },
    { status: 'delivered', label: '已送达', desc: '签收完成（演示）' }
  ];
  return nodes.slice(0, step + 1).map((n, i) => ({
    ...n,
    at: i === 0 ? base : pharmNowLabel()
  }));
}

function normalizePharmDelivery(d, source) {
  if (!d) return null;
  // Prefer uiStatus (pending_shipment/in_transit/delivered) when present; also accept pending/shipped aliases
  const status = normalizePharmStatus(d.uiStatus || d.status || d.deliveryStatus || d.state);
  const meta = pharmStatusMeta(status);
  const addrRaw = d.addressSnapshot || d.address || null;
  const address = addrRaw
    ? normalizePharmAddress(typeof addrRaw === 'object' ? addrRaw : { detail: addrRaw }, source)
    : normalizePharmAddress({
      name: d.receiverName || d.contactName,
      phone: d.receiverPhone || d.phone,
      province: d.province, city: d.city, district: d.district,
      detail: d.addressDetail || d.detail || d.fullAddress
    }, source);
  const items = (Array.isArray(d.items) ? d.items : []).map(normalizePharmOrderItem).filter(Boolean);
  const events = d.trackingEvents || d.timeline || d.tracks || d.trace || d.events || [];
  const timeline = buildTimelineFromStatus(status, events, d.createdAt);
  return {
    id: d.id || d.deliveryId || ('dlv-' + Date.now()),
    orderId: d.orderId || d.rxOrderId || d.pharmacyOrderId || '',
    orderTitle: d.orderTitle || d.title || d.orderName || '购药配送',
    status,
    statusLabel: status === 'cancelled' ? '已取消' : (d.statusLabel || meta.label),
    trackingNo: d.trackingNo || d.trackingNumber || d.courierNo || d.waybillNo || '',
    courier: d.courier || d.carrier || d.logisticsCompany || '演示快递',
    address,
    items,
    amount: Number(d.amount ?? d.totalAmount ?? 0) || 0,
    timeline,
    createdAt: d.createdAt || '',
    updatedAt: d.updatedAt || '',
    deliveredAt: d.deliveredAt || '',
    cancelReason: d.cancelReason || '',
    patientId: d.patientId || '',
    patientName: d.patientName || '',
    disclaimer: d.disclaimer || PHARM_DISCLAIMER,
    source: source || d.source || 'api'
  };
}

async function fetchPharmacyOrders() {
  const paths = ['/api/pharmacy/orders', '/api/rx-orders', '/api/medicine-delivery/orders', '/api/drug-delivery/orders'];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      let list = asList(data, ['items', 'orders', 'data', 'results']);
      if (!list.length && Array.isArray(data)) list = data;
      const mapped = list.map((x) => normalizePharmOrder(x, 'api')).filter(Boolean);
      if (Array.isArray(data?.items) || mapped.length || Array.isArray(data)) {
        state.pharmUsingApi = true;
        saveLocalPharmOrders(mapped.map((o) => ({ ...o, source: 'api' })));
        return mapped;
      }
    } catch { /* next */ }
  }
  state.pharmUsingApi = false;
  return ensureLocalPharmOrders().map((o) => normalizePharmOrder(o, o.source || 'mock'));
}

async function fetchPharmacyOrder(id) {
  const paths = [
    `/api/pharmacy/orders/${encodeURIComponent(id)}`,
    `/api/rx-orders/${encodeURIComponent(id)}`
  ];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      const o = normalizePharmOrder(data.order || data.item || data, 'api');
      if (o?.id) { state.pharmUsingApi = true; return o; }
    } catch { /* next */ }
  }
  const local = ensureLocalPharmOrders().find((x) => String(x.id) === String(id));
  return local ? normalizePharmOrder(local, local.source || 'mock') : null;
}

async function fetchPharmacyAddresses() {
  const paths = ['/api/pharmacy/addresses', '/api/medicine-delivery/addresses', '/api/drug-delivery/addresses'];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      let list = asList(data, ['items', 'addresses', 'data', 'results']);
      if (!list.length && Array.isArray(data)) list = data;
      const mapped = list.map((x) => normalizePharmAddress(x, 'api')).filter(Boolean);
      if (Array.isArray(data?.items) || mapped.length || Array.isArray(data)) {
        state.pharmUsingApi = true;
        saveLocalPharmAddresses(mapped.map((a) => ({ ...a, source: 'api' })));
        return mapped;
      }
    } catch { /* next */ }
  }
  state.pharmUsingApi = false;
  return ensureLocalPharmAddresses().map((a) => normalizePharmAddress(a, a.source || 'mock'));
}

async function createPharmacyAddress(body) {
  const ap = getActivePatient();
  const payload = { ...body, patientId: body.patientId || ap?.id || null };
  const paths = ['/api/pharmacy/addresses', '/api/medicine-delivery/addresses'];
  for (const p of paths) {
    try {
      const data = await apiFetch(p, { method: 'POST', body: JSON.stringify(payload) });
      const a = normalizePharmAddress(data.address || data.item || data, 'api');
      if (a?.id) {
        state.pharmUsingApi = true;
        const local = loadLocalPharmAddresses();
        if (a.isDefault) local.forEach((x) => { x.isDefault = false; });
        local.unshift({ ...a, source: 'api' });
        saveLocalPharmAddresses(local);
        return a;
      }
    } catch { /* next */ }
  }
  state.pharmUsingApi = false;
  const local = ensureLocalPharmAddresses();
  const a = normalizePharmAddress({
    id: 'addr-' + Date.now(),
    ...body,
    isDefault: !!body.isDefault || local.length === 0,
    source: 'mock'
  }, 'mock');
  if (a.isDefault) local.forEach((x) => { x.isDefault = false; });
  local.unshift(a);
  saveLocalPharmAddresses(local);
  return a;
}

async function fetchPharmacyDeliveries() {
  const paths = [
    '/api/pharmacy/deliveries',
    '/api/medicine-delivery',
    '/api/medicine-delivery/deliveries',
    '/api/drug-delivery',
    '/api/deliveries'
  ];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      let list = asList(data, ['items', 'deliveries', 'data', 'results']);
      if (!list.length && Array.isArray(data)) list = data;
      const mapped = list.map((x) => normalizePharmDelivery(x, 'api')).filter(Boolean);
      if (Array.isArray(data?.items) || mapped.length || Array.isArray(data)) {
        state.pharmUsingApi = true;
        saveLocalPharmDeliveries(mapped.map((d) => ({ ...d, source: 'api' })));
        return mapped;
      }
    } catch { /* next */ }
  }
  state.pharmUsingApi = false;
  return loadLocalPharmDeliveries().map((d) => normalizePharmDelivery(d, d.source || 'mock'));
}

async function fetchPharmacyDelivery(id) {
  const paths = [
    `/api/pharmacy/deliveries/${encodeURIComponent(id)}`,
    `/api/medicine-delivery/${encodeURIComponent(id)}`,
    `/api/medicine-delivery/deliveries/${encodeURIComponent(id)}`,
    `/api/drug-delivery/${encodeURIComponent(id)}`,
    `/api/deliveries/${encodeURIComponent(id)}`
  ];
  for (const p of paths) {
    try {
      const data = await apiFetch(p);
      const d = normalizePharmDelivery(data.delivery || data.item || data, 'api');
      if (d?.id) { state.pharmUsingApi = true; return d; }
    } catch { /* next */ }
  }
  const local = loadLocalPharmDeliveries().find((x) => String(x.id) === String(id));
  return local ? normalizePharmDelivery(local, local.source || 'mock') : null;
}

async function createPharmacyDelivery({ orderId, addressId, address }) {
  const ap = getActivePatient();
  const order = await fetchPharmacyOrder(orderId);
  const addr = address || (await fetchPharmacyAddresses()).find((a) => String(a.id) === String(addressId));
  const body = {
    orderId,
    addressId: addressId || addr?.id,
    patientId: ap?.id || null
  };
  if (!body.orderId || !body.addressId) throw new Error('缺少购药单或收货地址');
  // Primary pharmacy path first (true联)
  try {
    const data = await apiFetch('/api/pharmacy/deliveries', { method: 'POST', body: JSON.stringify(body) });
    const d = normalizePharmDelivery(data.delivery || data.item || data, 'api');
    if (d?.id) {
      state.pharmUsingApi = true;
      const local = loadLocalPharmDeliveries();
      const idx = local.findIndex((x) => String(x.id) === String(d.id));
      if (idx >= 0) local[idx] = { ...local[idx], ...d, source: 'api' };
      else local.unshift({ ...d, source: 'api' });
      saveLocalPharmDeliveries(local);
      return d;
    }
  } catch (err) {
    // If pharmacy exists but rejects (4xx/5xx), do not silently Mock
    if (state.pharmUsingApi || String(err?.message || '').startsWith('HTTP')) {
      // still try aliases only on 404
      if (!String(err?.message || '').includes('HTTP 404')) throw err;
    }
  }
  const aliasPaths = [
    '/api/medicine-delivery',
    '/api/medicine-delivery/deliveries',
    '/api/drug-delivery',
    '/api/deliveries'
  ];
  for (const p of aliasPaths) {
    try {
      const data = await apiFetch(p, { method: 'POST', body: JSON.stringify(body) });
      const d = normalizePharmDelivery(data.delivery || data.item || data, 'api');
      if (d?.id) {
        state.pharmUsingApi = true;
        const local = loadLocalPharmDeliveries();
        const idx = local.findIndex((x) => String(x.id) === String(d.id));
        if (idx >= 0) local[idx] = { ...local[idx], ...d, source: 'api' };
        else local.unshift({ ...d, source: 'api' });
        saveLocalPharmDeliveries(local);
        return d;
      }
    } catch { /* next */ }
  }
  state.pharmUsingApi = false;
  const now = pharmNowLabel();
  const d = normalizePharmDelivery({
    id: 'dlv-mock-' + Date.now(),
    orderId,
    orderTitle: order?.title || '购药配送',
    status: 'pending_shipment',
    trackingNo: 'DEMO' + String(Date.now()).slice(-10),
    courier: '演示快递',
    address: addr,
    items: order?.items || [],
    amount: order?.amount || 0,
    timeline: [
      { status: 'pending_shipment', label: '待发货', at: now, desc: '药店已接单，准备拣货打包' }
    ],
    createdAt: now,
    patientId: ap?.id || '',
    patientName: ap?.name || '演示患者',
    source: 'mock'
  }, 'mock');
  const local = loadLocalPharmDeliveries();
  local.unshift(d);
  saveLocalPharmDeliveries(local);
  const orders = ensureLocalPharmOrders();
  const oi = orders.findIndex((x) => String(x.id) === String(orderId));
  if (oi >= 0) {
    orders[oi] = { ...orders[oi], status: 'delivering', statusLabel: '配送中' };
    saveLocalPharmOrders(orders);
  }
  return d;
}

async function advancePharmacyDelivery(id) {
  try {
    const data = await apiFetch(`/api/pharmacy/deliveries/${encodeURIComponent(id)}/advance`, { method: 'POST', body: '{}' });
    const d = normalizePharmDelivery(data.delivery || data.item || data, 'api');
    if (d?.id) {
      state.pharmUsingApi = true;
      const local = loadLocalPharmDeliveries();
      const idx = local.findIndex((x) => String(x.id) === String(d.id));
      if (idx >= 0) local[idx] = { ...local[idx], ...d, source: 'api' };
      else local.unshift({ ...d, source: 'api' });
      saveLocalPharmDeliveries(local);
      return d;
    }
  } catch (err) {
    if (state.pharmUsingApi && !String(err?.message || '').includes('HTTP 404')) throw err;
  }
  const paths = [
    `/api/medicine-delivery/${encodeURIComponent(id)}/advance`,
    `/api/medicine-delivery/deliveries/${encodeURIComponent(id)}/advance`,
    `/api/drug-delivery/${encodeURIComponent(id)}/advance`,
    `/api/deliveries/${encodeURIComponent(id)}/advance`
  ];
  for (const p of paths) {
    try {
      const data = await apiFetch(p, { method: 'POST', body: '{}' });
      const d = normalizePharmDelivery(data.delivery || data.item || data, 'api');
      if (d?.id) {
        state.pharmUsingApi = true;
        const local = loadLocalPharmDeliveries();
        const idx = local.findIndex((x) => String(x.id) === String(d.id));
        if (idx >= 0) local[idx] = { ...local[idx], ...d, source: 'api' };
        else local.unshift({ ...d, source: 'api' });
        saveLocalPharmDeliveries(local);
        return d;
      }
    } catch { /* next */ }
  }
  // also try PATCH status
  const cur = await fetchPharmacyDelivery(id);
  if (!cur) throw new Error('配送单不存在');
  const idxFlow = PHARM_STATUS_FLOW.indexOf(cur.status);
  if (idxFlow < 0 || idxFlow >= PHARM_STATUS_FLOW.length - 1) {
    toast('已是最终状态：已送达');
    return cur;
  }
  const next = PHARM_STATUS_FLOW[idxFlow + 1];
  const patchPaths = [
    `/api/pharmacy/deliveries/${encodeURIComponent(id)}`,
    `/api/deliveries/${encodeURIComponent(id)}`
  ];
  for (const p of patchPaths) {
    try {
      const data = await apiFetch(p, { method: 'PATCH', body: JSON.stringify({ status: next }) });
      const d = normalizePharmDelivery(data.delivery || data.item || data, 'api');
      if (d?.id) {
        state.pharmUsingApi = true;
        const local = loadLocalPharmDeliveries();
        const i = local.findIndex((x) => String(x.id) === String(d.id));
        if (i >= 0) local[i] = { ...local[i], ...d, source: 'api' };
        saveLocalPharmDeliveries(local);
        return d;
      }
    } catch { /* next */ }
  }
  // Mock advance
  state.pharmUsingApi = false;
  const now = pharmNowLabel();
  const meta = pharmStatusMeta(next);
  const timeline = [...(cur.timeline || [])];
  timeline.push({
    status: next,
    label: meta.label,
    at: now,
    desc: next === 'in_transit' ? '药品已发出，配送途中' : '签收完成（演示）'
  });
  const updated = normalizePharmDelivery({
    ...cur,
    status: next,
    statusLabel: meta.label,
    timeline,
    updatedAt: now,
    deliveredAt: next === 'delivered' ? now : cur.deliveredAt,
    source: 'mock'
  }, 'mock');
  const local = loadLocalPharmDeliveries();
  const i = local.findIndex((x) => String(x.id) === String(id));
  if (i >= 0) local[i] = updated;
  else local.unshift(updated);
  saveLocalPharmDeliveries(local);
  if (next === 'delivered' && cur.orderId) {
    const orders = ensureLocalPharmOrders();
    const oi = orders.findIndex((x) => String(x.id) === String(cur.orderId));
    if (oi >= 0) {
      orders[oi] = { ...orders[oi], status: 'delivered', statusLabel: '已配送' };
      saveLocalPharmOrders(orders);
    }
  }
  return updated;
}

function pharmItemsHtml(items) {
  if (!items?.length) return '<p class="ref-note">暂无药品明细</p>';
  return `<ul class="pharm-item-list">${items.map((it) => `
    <li>
      <strong>${escapeHtml(it.name)}</strong>
      <span>${escapeHtml(it.spec || '')}</span>
      <em>×${escapeHtml(String(it.quantity))}${escapeHtml(it.unit || '')}</em>
    </li>`).join('')}</ul>`;
}

function pharmTimelineHtml(delivery) {
  const cur = normalizePharmStatus(delivery.status);
  if (cur === 'cancelled') {
    const events = delivery.timeline || [];
    return `
      <ol class="pharm-timeline" aria-label="物流时间轴">
        ${events.map((n, i) => `
          <li class="${i === events.length - 1 ? 'active' : 'done'}">
            <span class="pharm-tl-dot" aria-hidden="true"></span>
            <div class="pharm-tl-body">
              <strong>${escapeHtml(n.label || pharmStatusMeta(n.status).label)}</strong>
              ${n.at ? `<small>${escapeHtml(n.at)}</small>` : ''}
              ${n.desc ? `<p>${escapeHtml(n.desc)}</p>` : ''}
            </div>
          </li>`).join('') || `<li class="active"><span class="pharm-tl-dot"></span><div class="pharm-tl-body"><strong>已取消</strong><p>${escapeHtml(delivery.cancelReason || '配送已取消（演示）')}</p></div></li>`}
      </ol>`;
  }
  const curStep = pharmStatusMeta(cur).step;
  const nodes = PHARM_STATUS_FLOW.map((k) => {
    const meta = PHARM_STATUS[k];
    const hit = (delivery.timeline || []).find((t) => normalizePharmStatus(t.status) === k);
    const done = meta.step < curStep;
    const active = meta.step === curStep;
    return { ...meta, at: hit?.at || '', desc: hit?.desc || '', done, active };
  });
  return `
    <ol class="pharm-timeline" aria-label="物流时间轴">
      ${nodes.map((n) => `
        <li class="${n.done ? 'done' : ''} ${n.active ? 'active' : ''} ${n.step > curStep ? 'todo' : ''}">
          <span class="pharm-tl-dot" aria-hidden="true"></span>
          <div class="pharm-tl-body">
            <strong>${escapeHtml(n.label)}</strong>
            ${n.at ? `<small>${escapeHtml(n.at)}</small>` : (n.step > curStep ? '<small>待更新</small>' : '')}
            ${n.desc ? `<p>${escapeHtml(n.desc)}</p>` : ''}
          </div>
        </li>`).join('')}
    </ol>`;
}

async function renderPharmacyOrders() {
  const box = $('#pharmacyOrdersContent');
  if (!box) return;
  $$('#pharmOrderTabs .seg-tab').forEach((t) => {
    t.classList.toggle('active', (t.dataset.filter || '') === state.pharmOrderFilter);
  });
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchPharmacyOrders();
  const filtered = list.filter((o) => {
    if (state.pharmOrderFilter === 'deliverable') return o.status === 'deliverable';
    return true;
  });
  if (!filtered.length) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="big">📦</div>
        <p>${state.pharmOrderFilter === 'deliverable' ? '暂无可配送购药单' : '暂无购药单'}</p>
        <p class="ref-note">${state.pharmOrderFilter === 'deliverable' ? '可切换「全部」查看历史单，或到「我的配送」追踪物流。' : PHARM_DISCLAIMER}</p>
        ${state.pharmOrderFilter === 'deliverable' ? '<button type="button" class="btn ghost" id="pharmEmptyAll" style="margin-top:10px">查看全部购药单</button>' : ''}
      </div>`;
    $('#pharmEmptyAll')?.addEventListener('click', () => {
      state.pharmOrderFilter = 'all';
      renderPharmacyOrders();
    });
    return;
  }
  box.innerHTML = filtered.map((o) => `
    <article class="pharm-order-card" data-id="${escapeHtml(o.id)}">
      <div class="pharm-order-head">
        <div>
          <span class="exam-cat-pill lab">${escapeHtml(o.typeLabel || '购药单')}</span>
          <h3>${escapeHtml(o.title)}</h3>
        </div>
        <span class="status-pill ${o.status === 'deliverable' ? 'ready' : o.status === 'delivered' ? 'done' : 'pending'}">${escapeHtml(o.statusLabel)}</span>
      </div>
      <p class="pharm-meta">${escapeHtml(o.department || '—')} · ${escapeHtml(o.doctorName || '—')} · ${escapeHtml(o.createdAt || '')}</p>
      ${pharmItemsHtml(o.items)}
      <div class="pharm-order-foot">
        <strong>${formatMoney(o.amount)}</strong>
        <button type="button" class="btn primary sm" data-pharm-ship="${escapeHtml(o.id)}" ${o.status !== 'deliverable' ? 'disabled' : ''}>
          ${o.status === 'deliverable' ? '去配送' : o.statusLabel}
        </button>
      </div>
      <p class="ref-note">${sourceLabel(o.source)} · ${escapeHtml(o.disclaimer || PHARM_DISCLAIMER)}</p>
    </article>`).join('');
  box.querySelectorAll('[data-pharm-ship]').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const id = btn.getAttribute('data-pharm-ship');
      setLoading(true, '加载购药单…');
      try {
        const order = await fetchPharmacyOrder(id);
        if (!order) { toast('购药单不存在'); return; }
        if (order.status !== 'deliverable') { toast('该单暂不可配送'); return; }
        state.pharmOrderId = order.id;
        state.pharmOrder = order;
        state.pharmAddressId = null;
        showView('pharmacy-address');
      } finally {
        setLoading(false);
      }
    });
  });
}

async function renderPharmacyAddress() {
  const box = $('#pharmacyAddressContent');
  if (!box) return;
  const order = state.pharmOrder || (state.pharmOrderId ? await fetchPharmacyOrder(state.pharmOrderId) : null);
  if (!order) {
    box.innerHTML = `<div class="empty-state"><p>请先选择购药单</p>
      <button class="btn primary" id="pharmAddrBackOrders">返回购药单</button></div>`;
    $('#pharmAddrBackOrders')?.addEventListener('click', () => showView('pharmacy'));
    return;
  }
  state.pharmOrder = order;
  box.innerHTML = `<div class="empty-state">加载地址…</div>`;
  const addrs = await fetchPharmacyAddresses();
  if (!state.pharmAddressId) {
    const def = addrs.find((a) => a.isDefault) || addrs[0];
    state.pharmAddressId = def?.id || null;
  }
  box.innerHTML = `
    <div class="exam-item-summary">
      <div class="exam-item-head">
        <strong>${escapeHtml(order.title)}</strong>
        <span class="exam-price">${formatMoney(order.amount)}</span>
      </div>
      ${pharmItemsHtml(order.items)}
      <p class="ref-note" style="margin-top:8px">不接真实支付 · ${escapeHtml(PHARM_DISCLAIMER)}</p>
    </div>
    <h3 class="section-label">收货地址</h3>
    <div class="pharm-addr-list">
      ${addrs.length ? addrs.map((a) => `
        <label class="pharm-addr-card ${String(a.id) === String(state.pharmAddressId) ? 'selected' : ''}">
          <input type="radio" name="pharmAddr" value="${escapeHtml(a.id)}" ${String(a.id) === String(state.pharmAddressId) ? 'checked' : ''} />
          <div>
            <strong>${escapeHtml(a.name)} <span>${escapeHtml(a.phone)}</span>
              ${a.isDefault ? '<em class="pharm-default">默认</em>' : ''}
            </strong>
            <p>${escapeHtml(a.fullAddress || [a.province, a.city, a.district, a.detail].filter(Boolean).join(' '))}</p>
          </div>
        </label>`).join('') : `<div class="empty-state"><p>暂无地址，请先新增</p></div>`}
    </div>
    <div class="actions-row" style="margin-top:14px;flex-wrap:wrap;gap:8px">
      <button type="button" class="btn ghost" id="pharmAddAddr">新增地址</button>
      <button type="button" class="btn primary" id="pharmSubmitDeliv" ${!addrs.length ? 'disabled' : ''}>确认提交配送</button>
    </div>`;
  box.querySelectorAll('input[name="pharmAddr"]').forEach((inp) => {
    inp.addEventListener('change', () => {
      state.pharmAddressId = inp.value;
      box.querySelectorAll('.pharm-addr-card').forEach((c) => {
        c.classList.toggle('selected', c.querySelector('input')?.value === inp.value);
      });
    });
  });
  $('#pharmAddAddr')?.addEventListener('click', () => {
    state.pharmAddrFormMode = 'add';
    showView('pharmacy-address-form');
  });
  $('#pharmSubmitDeliv')?.addEventListener('click', async () => {
    if (!state.pharmAddressId) { toast('请选择收货地址'); return; }
    setLoading(true, '提交配送…');
    try {
      const d = await createPharmacyDelivery({
        orderId: order.id,
        addressId: state.pharmAddressId
      });
      state.pharmDeliveryId = d.id;
      toast('配送已提交（演示）');
      showView('pharmacy-delivery');
    } catch (err) {
      toast(err?.message || '提交失败');
    } finally {
      setLoading(false);
    }
  });
}

function renderPharmacyAddressForm() {
  const box = $('#pharmacyAddressFormContent');
  if (!box) return;
  box.innerHTML = `
    <form id="pharmAddrForm" class="form-stack" autocomplete="off">
      <label class="field"><span>收件人 <em>*</em></span>
        <input name="name" required maxlength="20" placeholder="姓名" /></label>
      <label class="field"><span>手机号 <em>*</em></span>
        <input name="phone" type="tel" required maxlength="20" placeholder="11 位手机号" /></label>
      <label class="field"><span>省 <em>*</em></span>
        <input name="province" required maxlength="20" placeholder="如：上海市" value="上海市" /></label>
      <label class="field"><span>市 <em>*</em></span>
        <input name="city" required maxlength="20" placeholder="如：上海市" value="上海市" /></label>
      <label class="field"><span>区 <em>*</em></span>
        <input name="district" required maxlength="20" placeholder="如：浦东新区" /></label>
      <label class="field"><span>详细地址 <em>*</em></span>
        <textarea name="detail" rows="2" required maxlength="120" placeholder="街道门牌小区楼栋"></textarea></label>
      <label class="check-row"><input type="checkbox" name="isDefault" checked /> 设为默认地址</label>
      <div class="actions-row">
        <button type="button" class="btn ghost" id="pharmAddrFormCancel">取消</button>
        <button type="submit" class="btn primary">保存地址</button>
      </div>
      <p class="ref-note">${PHARM_DISCLAIMER}</p>
    </form>`;
  $('#pharmAddrFormCancel')?.addEventListener('click', () => showView('pharmacy-address'));
  $('#pharmAddrForm')?.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const body = {
      name: String(fd.get('name') || '').trim(),
      phone: String(fd.get('phone') || '').trim(),
      province: String(fd.get('province') || '').trim(),
      city: String(fd.get('city') || '').trim(),
      district: String(fd.get('district') || '').trim(),
      detail: String(fd.get('detail') || '').trim(),
      isDefault: !!fd.get('isDefault')
    };
    if (!body.name || !body.phone || !body.detail) {
      toast('请填写完整收件信息');
      return;
    }
    setLoading(true, '保存地址…');
    try {
      const a = await createPharmacyAddress(body);
      state.pharmAddressId = a.id;
      toast('地址已保存');
      showView('pharmacy-address');
    } catch (err) {
      toast(err?.message || '保存失败');
    } finally {
      setLoading(false);
    }
  });
}

async function renderPharmacyDeliveries() {
  const box = $('#pharmacyDeliveriesContent');
  if (!box) return;
  $$('#pharmDelivTabs .seg-tab').forEach((t) => {
    t.classList.toggle('active', (t.dataset.filter || '') === state.pharmDelivFilter);
  });
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchPharmacyDeliveries();
  const filtered = list.filter((d) => {
    if (state.pharmDelivFilter === 'active') return d.status !== 'delivered' && d.status !== 'cancelled';
    if (state.pharmDelivFilter === 'delivered') return d.status === 'delivered';
    return true;
  });
  if (!filtered.length) {
    box.innerHTML = `
      <div class="empty-state">
        <div class="big">🚚</div>
        <p>${state.pharmDelivFilter === 'delivered' ? '暂无已送达订单' : state.pharmDelivFilter === 'active' ? '暂无进行中配送' : '暂无配送单'}</p>
        <p class="ref-note">${PHARM_DISCLAIMER}</p>
      </div>`;
    return;
  }
  box.innerHTML = filtered.map((d) => {
    const meta = pharmStatusMeta(d.status);
    const addr = d.address?.fullAddress || [d.address?.province, d.address?.city, d.address?.district, d.address?.detail].filter(Boolean).join(' ');
    return `
    <article class="pharm-deliv-card" data-id="${escapeHtml(d.id)}">
      <div class="pharm-order-head">
        <div>
          <h3>${escapeHtml(d.orderTitle || '购药配送')}</h3>
          <p class="pharm-meta">${escapeHtml(d.courier || '演示快递')} · ${escapeHtml(d.trackingNo || '—')}</p>
        </div>
        <span class="status-pill ${meta.pill}">${escapeHtml(d.statusLabel || meta.label)}</span>
      </div>
      <p class="pharm-addr-line">📍 ${escapeHtml(addr || '—')}</p>
      <div class="pharm-steps-mini" aria-hidden="true">
        ${PHARM_STATUS_FLOW.map((k) => {
          const m = PHARM_STATUS[k];
          const on = m.step <= meta.step;
          return `<span class="${on ? 'on' : ''}">${escapeHtml(m.label)}</span>`;
        }).join('<i></i>')}
      </div>
      <button type="button" class="btn ghost block" data-pharm-open="${escapeHtml(d.id)}" style="margin-top:10px">查看物流详情</button>
      <p class="ref-note">${sourceLabel(d.source)} · ${escapeHtml(d.disclaimer || PHARM_DISCLAIMER)}</p>
    </article>`;
  }).join('');
  box.querySelectorAll('[data-pharm-open]').forEach((btn) => {
    btn.addEventListener('click', () => {
      state.pharmDeliveryId = btn.getAttribute('data-pharm-open');
      showView('pharmacy-delivery');
    });
  });
}

async function renderPharmacyDelivery() {
  const box = $('#pharmacyDeliveryContent');
  if (!box) return;
  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const d = await fetchPharmacyDelivery(state.pharmDeliveryId);
  if (!d) {
    box.innerHTML = `<div class="empty-state"><p>未找到配送单</p>
      <button class="btn primary" id="pharmDetBack">返回我的配送</button></div>`;
    $('#pharmDetBack')?.addEventListener('click', () => showView('pharmacy-deliveries'));
    return;
  }
  const meta = pharmStatusMeta(d.status);
  const addr = d.address;
  const canAdvance = d.status !== 'delivered' && d.status !== 'cancelled';
  box.innerHTML = `
    <div class="m3-disclaimer soft" role="note">
      <strong>${escapeHtml(d.disclaimer || PHARM_DISCLAIMER)}</strong>
      <p>运单 ${escapeHtml(d.trackingNo || d.id)} · 来源：${sourceLabel(d.source)} · 不接真实支付</p>
    </div>
    <div class="pharm-status-hero">
      <span class="status-pill ${meta.pill}">${escapeHtml(d.statusLabel || meta.label)}</span>
      <h3>${escapeHtml(d.orderTitle || '购药配送')}</h3>
      <p>${escapeHtml(d.courier || '演示快递')} · ${escapeHtml(d.trackingNo || '—')}</p>
    </div>
    ${pharmTimelineHtml(d)}
    <div class="confirm-box" style="margin-top:14px">
      <h4 style="margin:0 0 8px">收货信息</h4>
      <dl>
        <dt>收件人</dt><dd>${escapeHtml(addr?.name || '—')} ${escapeHtml(addr?.phone || '')}</dd>
        <dt>地址</dt><dd>${escapeHtml(addr?.fullAddress || [addr?.province, addr?.city, addr?.district, addr?.detail].filter(Boolean).join(' ') || '—')}</dd>
        <dt>就诊人</dt><dd>${escapeHtml(d.patientName || '—')}</dd>
        <dt>金额</dt><dd>${formatMoney(d.amount)}（演示，不支付）</dd>
      </dl>
      <h4 style="margin:12px 0 6px">药品明细</h4>
      ${pharmItemsHtml(d.items)}
      <div class="actions-row" style="margin-top:14px;flex-wrap:wrap;gap:8px">
        ${canAdvance ? `<button type="button" class="btn primary" id="pharmAdvance">模拟物流推进</button>` : ''}
        <button type="button" class="btn ghost" id="pharmDetList">我的配送</button>
        <button type="button" class="btn ghost" id="pharmDetOrders">购药单</button>
      </div>
      ${!canAdvance ? `<p class="ref-note">已送达，演示流程结束。</p>` : `<p class="ref-note">点击「模拟物流推进」：待发货 → 运输中 → 已送达。</p>`}
    </div>`;
  $('#pharmAdvance')?.addEventListener('click', async () => {
    setLoading(true, '推进物流…');
    try {
      const nd = await advancePharmacyDelivery(d.id);
      state.pharmDeliveryId = nd.id;
      toast(pharmStatusMeta(nd.status).label);
      await renderPharmacyDelivery();
    } catch (err) {
      toast(err?.message || '推进失败');
    } finally {
      setLoading(false);
    }
  });
  $('#pharmDetList')?.addEventListener('click', () => showView('pharmacy-deliveries'));
  $('#pharmDetOrders')?.addEventListener('click', () => showView('pharmacy'));
}

// M7 tabs + footer buttons
document.addEventListener('click', (e) => {
  const ot = e.target.closest('#pharmOrderTabs .seg-tab');
  if (ot) {
    state.pharmOrderFilter = ot.dataset.filter || 'deliverable';
    renderPharmacyOrders();
    return;
  }
  const dt = e.target.closest('#pharmDelivTabs .seg-tab');
  if (dt) {
    state.pharmDelivFilter = dt.dataset.filter || 'active';
    renderPharmacyDeliveries();
    return;
  }
  if (e.target.closest('#pharmGoDeliveries')) {
    showView('pharmacy-deliveries');
    return;
  }
  if (e.target.closest('#pharmDelivGoOrders')) {
    showView('pharmacy');
  }
});


/* ========== M9 · 黄金路径一键演示 ========== */
const DEMO_MODE_KEY = 'triage_demo_mode_v1';
const DEMO_STEPS_DONE_KEY = 'triage_demo_step_done_v1';
const DEMO_DISCLAIMER = '演示链路，非真实就医';

const DEMO_STEP_DEFS = [
  { id: 'triage', view: 'symptom' },
  { id: 'appoint', view: 'appoint' },
  { id: 'consult', view: 'chat' },
  { id: 'dc', view: 'dc-start', mode: 'text' },
  { id: 'messages', view: 'messages' }
];

const DEMO_VIEW_TO_STEP = {
  symptom: 'triage',
  result: 'triage',
  appoint: 'appoint',
  chat: 'consult',
  preconsult: 'consult',
  'dc-start': 'dc',
  'dc-queue': 'dc',
  'dc-session': 'dc',
  'dc-summary': 'dc',
  'dc-list': 'dc',
  messages: 'messages',
  'message-detail': 'messages'
};

function isDemoModeOn() {
  try { return localStorage.getItem(DEMO_MODE_KEY) === '1'; } catch { return false; }
}

function setDemoModeOn(on) {
  try { localStorage.setItem(DEMO_MODE_KEY, on ? '1' : '0'); } catch (_) {}
}

function loadDemoStepsDone() {
  try {
    const raw = JSON.parse(localStorage.getItem(DEMO_STEPS_DONE_KEY) || '[]');
    return new Set(Array.isArray(raw) ? raw : []);
  } catch {
    return new Set();
  }
}

function saveDemoStepsDone(set) {
  try { localStorage.setItem(DEMO_STEPS_DONE_KEY, JSON.stringify([...set])); } catch (_) {}
}

function markDemoStepDone(stepId) {
  if (!stepId || !isDemoModeOn()) return;
  const done = loadDemoStepsDone();
  if (done.has(stepId)) {
    renderDemoSteps();
    return;
  }
  done.add(stepId);
  saveDemoStepsDone(done);
  renderDemoSteps();
}

function markDemoStepByView(view) {
  const stepId = DEMO_VIEW_TO_STEP[view];
  if (stepId) markDemoStepDone(stepId);
}

function renderDemoSteps() {
  const bar = $('#demoBar');
  if (!bar) return;
  const on = isDemoModeOn();
  bar.classList.toggle('hidden', !on);
  const toggle = $('#demoModeToggle');
  if (toggle) toggle.checked = on;
  if (!on) return;
  const done = loadDemoStepsDone();
  $$('#demoSteps .demo-step').forEach((li) => {
    const id = li.dataset.step;
    li.classList.toggle('done', done.has(id));
  });
}

async function resetDemoViaApi() {
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timer = ctrl ? setTimeout(() => ctrl.abort(), 8000) : null;
  try {
    const res = await fetch(`${API_BASE}/api/demo/reset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: '{}',
      signal: ctrl ? ctrl.signal : undefined
    });
    if (timer) clearTimeout(timer);
    if (res.ok) {
      let data = {};
      try { data = await res.json(); } catch (_) {}
      return { ok: true, live: true, data };
    }
    return { ok: false, live: false, status: res.status };
  } catch (e) {
    if (timer) clearTimeout(timer);
    return { ok: false, live: false, error: e };
  }
}

async function onDemoReset() {
  if (!confirm('确定重置演示数据？将调用后端 POST /api/demo/reset（非 Mock）。')) return;
  setLoading(true, '重置演示数据…');
  try {
    const result = await resetDemoViaApi();
    if (!(result.live && result.ok && result.data)) {
      const detail = result.status ? `HTTP ${result.status}` : (result.error && result.error.message) || '网络错误';
      toast(`重置失败：${detail}。请确认 8001 已启动且非 prod 拒绝。`);
      return;
    }
    clearDemoLocalData();
    try { localStorage.removeItem(DEMO_STEPS_DONE_KEY); } catch (_) {}
    let msg = result.data.disclaimer || DEMO_DISCLAIMER;
    if (result.data.seedVersion) msg += ` · seed ${result.data.seedVersion}`;
    toast(msg);
    renderDemoSteps();
    setTimeout(() => location.reload(), 700);
  } finally {
    setLoading(false);
  }
}

function goDemoStep(stepId) {
  const def = DEMO_STEP_DEFS.find((d) => d.id === stepId);
  if (!def) return;
  if (def.view === 'chat' && state.chatDone) resetChatSession();
  if (def.view === 'appoint') {
    state.appoint = { step: 1, department: null, doctor: null, slot: null, _success: false };
  }
  if (def.mode) state.dcMode = def.mode;
  markDemoStepDone(stepId);
  showView(def.view);
}

function initDemoMode() {
  const toggle = $('#demoModeToggle');
  const resetBtn = $('#btnDemoReset');
  if (toggle) {
    toggle.checked = isDemoModeOn();
    toggle.addEventListener('change', () => {
      setDemoModeOn(toggle.checked);
      renderDemoSteps();
      if (toggle.checked) toast(DEMO_DISCLAIMER);
    });
  }
  if (resetBtn) {
    resetBtn.addEventListener('click', () => { onDemoReset(); });
  }
  const steps = $('#demoSteps');
  if (steps) {
    steps.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-demo-go]');
      if (!btn) return;
      goDemoStep(btn.dataset.demoGo);
    });
  }
  renderDemoSteps();
}

/* ========== M10 慢病打卡 ========== */
const CHRONIC_DISCLAIMER = '演示数据，非真实慢病管理';
let chronicUsingApi = false;
let chronicSourceHint = '';

function parseChronicDate(iso) {
  if (!iso) return null;
  if (iso instanceof Date) return iso;
  const s = String(iso).trim().replace(' ', 'T');
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

function dayKey(iso) {
  try {
    const d = parseChronicDate(iso) || new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso || '').slice(0, 10);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  } catch {
    return String(iso || '').slice(0, 10);
  }
}

function todayKeyLocal() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function isVitalAbnormal(v) {
  if (!v) return false;
  if (v.abnormal === true) return true;
  if (v.type === 'bp') {
    const s = Number(v.systolic);
    const d = Number(v.diastolic);
    return (Number.isFinite(s) && s >= 140) || (Number.isFinite(d) && d >= 90);
  }
  if (v.type === 'glucose') {
    const g = Number(v.glucose);
    return Number.isFinite(g) && g >= 7.0;
  }
  return false;
}

function normalizeVital(raw, source) {
  if (!raw) return null;
  const type = raw.type === 'glucose' || raw.type === 'bg' ? 'glucose' : 'bp';
  const v = {
    id: raw.id || `cv-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    patientId: raw.patientId || raw.patient_id || '',
    type,
    systolic: raw.systolic != null ? Number(raw.systolic) : null,
    diastolic: raw.diastolic != null ? Number(raw.diastolic) : null,
    glucose: raw.glucose != null ? Number(raw.glucose) : null,
    unit: raw.unit || (type === 'glucose' ? 'mmol/L' : 'mmHg'),
    measuredAt: raw.measuredAt || raw.measured_at || raw.createdAt || new Date().toISOString(),
    note: raw.note || '',
    abnormal: !!raw.abnormal,
    source: source || raw.source || 'api'
  };
  if (!v.abnormal) v.abnormal = isVitalAbnormal(v);
  return v;
}

function loadMockVitalsStore() {
  try {
    const raw = JSON.parse(localStorage.getItem(CHRONIC_VITALS_KEY) || 'null');
    if (raw && typeof raw === 'object') return raw;
  } catch (_) {}
  return {};
}

function saveMockVitalsStore(store) {
  localStorage.setItem(CHRONIC_VITALS_KEY, JSON.stringify(store));
}

function seedMockVitalsForPatient(patientId) {
  const store = loadMockVitalsStore();
  if (Array.isArray(store[patientId]) && store[patientId].length) return store[patientId];
  const list = [];
  const now = new Date();
  // 7 days BP + glucose; day -2 abnormal BP; day -1 high glucose
  for (let i = 6; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i, 8, 30);
    const iso = d.toISOString();
    const sys = i === 2 ? 148 : 118 + (i % 3) * 4;
    const dia = i === 2 ? 92 : 72 + (i % 2) * 4;
    list.push(normalizeVital({
      id: `mock-bp-${patientId}-${i}`,
      patientId,
      type: 'bp',
      systolic: sys,
      diastolic: dia,
      unit: 'mmHg',
      measuredAt: iso,
      note: i === 2 ? '演示异常血压' : ''
    }, 'mock'));
    const glu = i === 1 ? 7.4 : 5.2 + (i % 3) * 0.3;
    const gAt = new Date(d.getTime() + 30 * 60000).toISOString();
    list.push(normalizeVital({
      id: `mock-glu-${patientId}-${i}`,
      patientId,
      type: 'glucose',
      glucose: Math.round(glu * 10) / 10,
      unit: 'mmol/L',
      measuredAt: gAt,
      note: i === 1 ? '演示空腹偏高' : ''
    }, 'mock'));
  }
  store[patientId] = list;
  saveMockVitalsStore(store);
  return list;
}

function getMockVitals(patientId, type, limit) {
  const all = seedMockVitalsForPatient(patientId)
    .filter((v) => !type || v.type === type)
    .sort((a, b) => String(b.measuredAt).localeCompare(String(a.measuredAt)));
  return typeof limit === 'number' ? all.slice(0, limit) : all;
}

function addMockVital(payload) {
  const store = loadMockVitalsStore();
  const pid = payload.patientId;
  if (!Array.isArray(store[pid])) store[pid] = seedMockVitalsForPatient(pid);
  const v = normalizeVital({
    ...payload,
    id: `mock-cv-${Date.now()}`,
    measuredAt: payload.measuredAt || new Date().toISOString()
  }, 'mock');
  store[pid].unshift(v);
  saveMockVitalsStore(store);
  return v;
}

function summarizeVitals(list) {
  const bp = list.filter((v) => v.type === 'bp');
  const glu = list.filter((v) => v.type === 'glucose');
  const last7 = (arr) => {
    const cut = Date.now() - 7 * 86400000;
    return arr.filter((v) => new Date(v.measuredAt).getTime() >= cut);
  };
  const bp7 = last7(bp);
  const g7 = last7(glu);
  const avg = (nums) => {
    const xs = nums.filter((n) => Number.isFinite(n));
    if (!xs.length) return null;
    return Math.round((xs.reduce((a, b) => a + b, 0) / xs.length) * 10) / 10;
  };
  return {
    lastBp: bp[0] || null,
    lastGlucose: glu[0] || null,
    avgSystolic7: avg(bp7.map((v) => v.systolic)),
    avgDiastolic7: avg(bp7.map((v) => v.diastolic)),
    avgGlucose7: avg(g7.map((v) => v.glucose)),
    abnormalCount7: last7(list).filter((v) => v.abnormal).length,
    disclaimer: CHRONIC_DISCLAIMER
  };
}

async function fetchChronicVitals(patientId, type, limit = 30) {
  const q = new URLSearchParams({ patientId, limit: String(limit) });
  if (type) q.set('type', type);
  try {
    const data = await apiFetch(`/api/chronic/vitals?${q.toString()}`);
    const arr = Array.isArray(data) ? data
      : Array.isArray(data?.items) ? data.items
      : Array.isArray(data?.vitals) ? data.vitals
      : Array.isArray(data?.data) ? data.data : [];
    chronicUsingApi = true;
    chronicSourceHint = '已联 8001 /api/chronic/vitals';
    return arr.map((x) => normalizeVital(x, 'api')).filter(Boolean);
  } catch (_) {
    chronicUsingApi = false;
    chronicSourceHint = 'Mock 演示数据（8001 /api/chronic/vitals 不可用）';
    return getMockVitals(patientId, type, limit);
  }
}

async function fetchChronicSummary(patientId) {
  try {
    const data = await apiFetch(`/api/chronic/vitals/summary?patientId=${encodeURIComponent(patientId)}`);
    chronicUsingApi = true;
    const last7 = data.last7 || data.last_7 || {};
    const latest = data.latest || {};
    const lastBp = data.lastBp || data.last_bp || latest.bp || null;
    const lastGlucose = data.lastGlucose || data.last_glucose || latest.glucose || null;
    return {
      lastBp,
      lastGlucose,
      avgSystolic7: data.avgSystolic7 ?? data.avg_systolic_7 ?? last7.bpSystolicAvg ?? last7.bp_systolic_avg ?? null,
      avgDiastolic7: data.avgDiastolic7 ?? data.avg_diastolic_7 ?? last7.bpDiastolicAvg ?? last7.bp_diastolic_avg ?? null,
      avgGlucose7: data.avgGlucose7 ?? data.avg_glucose_7 ?? last7.glucoseAvg ?? last7.glucose_avg ?? null,
      abnormalCount7: data.abnormalCount7 ?? data.abnormal_count_7 ?? data.abnormalCount ?? data.abnormal_count ?? 0,
      disclaimer: data.disclaimer || CHRONIC_DISCLAIMER,
      raw: data
    };
  } catch (_) {
    const list = getMockVitals(patientId, null, 50);
    return summarizeVitals(list);
  }
}

async function postChronicVital(payload) {
  try {
    const data = await apiFetch('/api/chronic/vitals', {
      method: 'POST',
      body: JSON.stringify(payload)
    });
    chronicUsingApi = true;
    chronicSourceHint = '已联 8001 POST /api/chronic/vitals';
    return normalizeVital(data?.vital || data?.data || data, 'api');
  } catch (_) {
    chronicUsingApi = false;
    chronicSourceHint = '已写入本地 Mock（API 不可用）';
    return addMockVital(payload);
  }
}

function hasCheckedInToday(list, type) {
  const today = todayKeyLocal();
  return (list || []).some((v) => v.type === type && dayKey(v.measuredAt) === today);
}

function drawSparkline(canvas, points, opts = {}) {
  if (!canvas) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth || 320;
  const h = canvas.clientHeight || 120;
  canvas.width = Math.floor(w * dpr);
  canvas.height = Math.floor(h * dpr);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!points.length) {
    ctx.fillStyle = '#94a3b8';
    ctx.font = '12px sans-serif';
    ctx.fillText('暂无数据', 12, h / 2);
    return;
  }
  const pad = 12;
  const vals = points.map((p) => p.y);
  let min = Math.min(...vals);
  let max = Math.max(...vals);
  if (min === max) { min -= 1; max += 1; }
  const xAt = (i) => pad + (i / Math.max(points.length - 1, 1)) * (w - pad * 2);
  const yAt = (v) => pad + (1 - (v - min) / (max - min)) * (h - pad * 2);
  // threshold line
  if (opts.threshold != null && opts.threshold >= min && opts.threshold <= max) {
    const ty = yAt(opts.threshold);
    ctx.strokeStyle = '#fca5a5';
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(pad, ty);
    ctx.lineTo(w - pad, ty);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  ctx.strokeStyle = opts.color || '#0d9488';
  ctx.lineWidth = 2;
  ctx.beginPath();
  points.forEach((p, i) => {
    const x = xAt(i);
    const y = yAt(p.y);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();
  points.forEach((p, i) => {
    const x = xAt(i);
    const y = yAt(p.y);
    ctx.fillStyle = p.abnormal ? '#dc2626' : (opts.color || '#0d9488');
    ctx.beginPath();
    ctx.arc(x, y, p.abnormal ? 4 : 3, 0, Math.PI * 2);
    ctx.fill();
  });
}

function renderChronicPatientBar(patients, activeId) {
  const bar = $('#chronicPatientBar');
  if (!bar) return;
  const opts = (patients || []).map((p) =>
    `<option value="${escapeHtml(p.id)}" ${p.id === activeId ? 'selected' : ''}>${escapeHtml(p.name)}（${escapeHtml(p.relation || '')}）</option>`
  ).join('');
  bar.innerHTML = `
    <label class="field" style="flex:1;margin:0">
      <span>就诊人</span>
      <select id="chronicPatientSelect">${opts}</select>
    </label>
    <span class="chronic-today-pill" id="chronicTodayPill">检查中…</span>`;
  $('#chronicPatientSelect')?.addEventListener('change', (e) => {
    setActivePatientId(e.target.value);
    refreshHomePatient();
    renderChronic();
  });
}

function updateChronicTodayPill(list, tab) {
  const pill = $('#chronicTodayPill');
  if (!pill) return;
  if (tab === 'trend') {
    pill.className = 'chronic-today-pill';
    pill.textContent = '近 7 日趋势';
    return;
  }
  const type = tab === 'glucose' ? 'glucose' : 'bp';
  const done = hasCheckedInToday(list, type);
  pill.className = 'chronic-today-pill' + (done ? '' : ' pending');
  pill.textContent = done ? '今日已打卡' : '今日未打卡';
}

function updateChronicAbnormalBanner(list) {
  const box = $('#chronicAbnormalBanner');
  if (!box) return;
  const recent = (list || []).filter((v) => {
    const t = new Date(v.measuredAt).getTime();
    return Date.now() - t <= 7 * 86400000 && v.abnormal;
  });
  if (!recent.length) {
    box.classList.add('hidden');
    box.innerHTML = '';
    return;
  }
  const last = recent[0];
  let detail = '';
  if (last.type === 'bp') detail = `血压 ${last.systolic}/${last.diastolic} mmHg`;
  else detail = `血糖 ${last.glucose} ${last.unit || 'mmol/L'}`;
  box.classList.remove('hidden');
  box.innerHTML = `<strong>异常提示（演示规则）</strong>近 7 日有 ${recent.length} 条异常记录，最近：${escapeHtml(detail)}。收缩压≥140 或舒张压≥90，或空腹血糖≥7.0 视为异常。请结合面诊，勿自行调整用药。`;
}

function formatVitalLabel(v) {
  if (!v) return '—';
  if (v.type === 'bp') return `${v.systolic}/${v.diastolic} mmHg`;
  return `${v.glucose} ${v.unit || 'mmol/L'}`;
}

function formatTimeShort(iso) {
  try {
    const d = parseChronicDate(iso) || new Date(iso);
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mm = String(d.getMinutes()).padStart(2, '0');
    return `${m}-${day} ${hh}:${mm}`;
  } catch {
    return String(iso || '').slice(0, 16);
  }
}

async function renderChronic() {
  const box = $('#chronicContent');
  if (!box) return;
  const tab = state.chronicTab || 'bp';
  $$('#chronicTabs .seg-tab').forEach((t) => {
    t.classList.toggle('active', (t.dataset.tab || '') === tab);
  });

  let patients = [];
  try {
    patients = await fetchPatients();
  } catch (_) {
    patients = loadLocalPatients();
  }
  if (!patients.length) patients = loadLocalPatients();
  const activeId = getActivePatientId();
  renderChronicPatientBar(patients, activeId);

  box.innerHTML = `<div class="empty-state">加载中…</div>`;
  const list = await fetchChronicVitals(activeId, null, 40);
  const summary = await fetchChronicSummary(activeId);
  updateChronicTodayPill(list, tab);
  updateChronicAbnormalBanner(list);
  const hint = $('#chronicSourceHint');
  if (hint) hint.textContent = `${chronicSourceHint || ''} · ${CHRONIC_DISCLAIMER}`;

  if (tab === 'trend') {
    renderChronicTrend(box, list, summary);
    return;
  }
  if (tab === 'glucose') {
    renderChronicGlucoseForm(box, list.filter((v) => v.type === 'glucose'), activeId);
    return;
  }
  renderChronicBpForm(box, list.filter((v) => v.type === 'bp'), activeId);
}

function renderVitalRows(items) {
  if (!items.length) return `<div class="empty-state"><p>暂无记录</p></div>`;
  return `<div class="chronic-list">${items.slice(0, 14).map((v) => `
    <div class="chronic-vital-row ${v.abnormal ? 'abnormal' : ''}">
      <div>
        <div class="vr-val">${escapeHtml(formatVitalLabel(v))}${v.abnormal ? ' <span class="chronic-pill-abn">异常</span>' : ''}</div>
        <div class="vr-meta">${escapeHtml(formatTimeShort(v.measuredAt))}${v.note ? ' · ' + escapeHtml(v.note) : ''}</div>
      </div>
      <div class="vr-meta">${v.source === 'api' ? 'API' : 'Mock'}</div>
    </div>`).join('')}</div>`;
}

function renderChronicBpForm(box, bpList, patientId) {
  const done = hasCheckedInToday(bpList, 'bp');
  box.innerHTML = `
    <div class="chronic-form">
      <div class="field-row">
        <label class="field"><span>收缩压 <em>*</em></span>
          <input type="number" id="bpSys" min="60" max="250" step="1" placeholder="如 120" ${done ? '' : ''} />
          <span class="unit-hint">mmHg · ≥140 演示标异常</span>
        </label>
        <label class="field"><span>舒张压 <em>*</em></span>
          <input type="number" id="bpDia" min="40" max="150" step="1" placeholder="如 80" />
          <span class="unit-hint">mmHg · ≥90 演示标异常</span>
        </label>
      </div>
      <label class="field"><span>备注</span>
        <input type="text" id="bpNote" maxlength="80" placeholder="可选" />
      </label>
      <button type="button" class="btn primary block" id="btnSaveBp">${done ? '再记一条血压' : '提交血压打卡'}</button>
    </div>
    <div class="chronic-chart-card">
      <h3>近 7 日收缩压</h3>
      <div class="chart-meta">虚线为 140 阈值（演示）</div>
      <canvas class="chronic-spark" id="bpSpark" height="120"></canvas>
    </div>
    <h3 class="section-label">最近记录</h3>
    ${renderVitalRows(bpList)}`;
  requestAnimationFrame(() => {
    const pts = bpList
      .filter((v) => Date.now() - new Date(v.measuredAt).getTime() <= 7 * 86400000)
      .slice().reverse()
      .map((v) => ({ y: Number(v.systolic), abnormal: v.abnormal }));
    drawSparkline($('#bpSpark'), pts, { color: '#be123c', threshold: 140 });
  });
  $('#btnSaveBp')?.addEventListener('click', async () => {
    const systolic = Number($('#bpSys')?.value);
    const diastolic = Number($('#bpDia')?.value);
    if (!Number.isFinite(systolic) || !Number.isFinite(diastolic)) {
      toast('请填写收缩压与舒张压');
      return;
    }
    if (systolic < 60 || systolic > 250 || diastolic < 40 || diastolic > 150) {
      toast('血压数值超出合理演示范围');
      return;
    }
    setLoading(true, '提交打卡…');
    try {
      const v = await postChronicVital({
        patientId,
        type: 'bp',
        systolic,
        diastolic,
        unit: 'mmHg',
        measuredAt: new Date().toISOString(),
        note: ($('#bpNote')?.value || '').trim()
      });
      toast(v?.abnormal ? '已记录（演示：标为异常）' : '血压打卡成功');
      await renderChronic();
    } finally {
      setLoading(false);
    }
  });
}

function renderChronicGlucoseForm(box, gList, patientId) {
  const done = hasCheckedInToday(gList, 'glucose');
  box.innerHTML = `
    <div class="chronic-form">
      <div class="field-row">
        <label class="field"><span>血糖 <em>*</em></span>
          <input type="number" id="gluVal" min="1" max="30" step="0.1" placeholder="如 5.6" />
          <span class="unit-hint">默认 mmol/L · 空腹≥7.0 演示标异常</span>
        </label>
        <label class="field"><span>单位</span>
          <select id="gluUnit">
            <option value="mmol/L" selected>mmol/L</option>
            <option value="mg/dL">mg/dL</option>
          </select>
        </label>
      </div>
      <label class="field"><span>备注</span>
        <input type="text" id="gluNote" maxlength="80" placeholder="如空腹 / 餐后" />
      </label>
      <button type="button" class="btn primary block" id="btnSaveGlu">${done ? '再记一条血糖' : '提交血糖打卡'}</button>
    </div>
    <div class="chronic-chart-card">
      <h3>近 7 日血糖</h3>
      <div class="chart-meta">虚线为 7.0 mmol/L 阈值（演示）；mg/dL 将换算后绘图</div>
      <canvas class="chronic-spark" id="gluSpark" height="120"></canvas>
    </div>
    <h3 class="section-label">最近记录</h3>
    ${renderVitalRows(gList)}`;
  requestAnimationFrame(() => {
    const pts = gList
      .filter((v) => Date.now() - new Date(v.measuredAt).getTime() <= 7 * 86400000)
      .slice().reverse()
      .map((v) => {
        let y = Number(v.glucose);
        if (v.unit === 'mg/dL') y = y / 18;
        return { y, abnormal: v.abnormal };
      });
    drawSparkline($('#gluSpark'), pts, { color: '#c2410c', threshold: 7.0 });
  });
  $('#btnSaveGlu')?.addEventListener('click', async () => {
    const glucose = Number($('#gluVal')?.value);
    const unit = $('#gluUnit')?.value || 'mmol/L';
    if (!Number.isFinite(glucose) || glucose <= 0) {
      toast('请填写血糖数值');
      return;
    }
    setLoading(true, '提交打卡…');
    try {
      const v = await postChronicVital({
        patientId,
        type: 'glucose',
        glucose,
        unit,
        measuredAt: new Date().toISOString(),
        note: ($('#gluNote')?.value || '').trim()
      });
      toast(v?.abnormal ? '已记录（演示：标为异常）' : '血糖打卡成功');
      await renderChronic();
    } finally {
      setLoading(false);
    }
  });
}

function renderChronicTrend(box, list, summary) {
  const abn = summary.abnormalCount7 ?? 0;
  box.innerHTML = `
    <div class="chronic-summary-grid">
      <div class="chronic-sum-tile">
        <div class="label">近 7 日平均血压</div>
        <div class="val">${summary.avgSystolic7 != null ? `${summary.avgSystolic7}/${summary.avgDiastolic7 ?? '—'} mmHg` : '—'}</div>
      </div>
      <div class="chronic-sum-tile">
        <div class="label">近 7 日平均血糖</div>
        <div class="val">${summary.avgGlucose7 != null ? `${summary.avgGlucose7} mmol/L` : '—'}</div>
      </div>
      <div class="chronic-sum-tile">
        <div class="label">最近血压</div>
        <div class="val">${summary.lastBp ? escapeHtml(formatVitalLabel(normalizeVital({ ...summary.lastBp, type: 'bp' }))) : '—'}</div>
      </div>
      <div class="chronic-sum-tile ${abn ? 'warn' : ''}">
        <div class="label">近 7 日异常次数</div>
        <div class="val">${abn}</div>
      </div>
    </div>
    <div class="chronic-chart-card">
      <h3>血压趋势（收缩压）</h3>
      <canvas class="chronic-spark" id="trendBpSpark" height="120"></canvas>
    </div>
    <div class="chronic-chart-card">
      <h3>血糖趋势</h3>
      <canvas class="chronic-spark" id="trendGluSpark" height="120"></canvas>
    </div>
    <p class="ref-note">${escapeHtml(summary.disclaimer || CHRONIC_DISCLAIMER)}</p>`;
  requestAnimationFrame(() => {
    const bp = list.filter((v) => v.type === 'bp')
      .filter((v) => Date.now() - new Date(v.measuredAt).getTime() <= 7 * 86400000)
      .slice().reverse()
      .map((v) => ({ y: Number(v.systolic), abnormal: v.abnormal }));
    const glu = list.filter((v) => v.type === 'glucose')
      .filter((v) => Date.now() - new Date(v.measuredAt).getTime() <= 7 * 86400000)
      .slice().reverse()
      .map((v) => {
        let y = Number(v.glucose);
        if (v.unit === 'mg/dL') y = y / 18;
        return { y, abnormal: v.abnormal };
      });
    drawSparkline($('#trendBpSpark'), bp, { color: '#be123c', threshold: 140 });
    drawSparkline($('#trendGluSpark'), glu, { color: '#c2410c', threshold: 7.0 });
  });
}

/* ========== S2 AI 安全护栏（前端） ========== */
const AI_DISCLAIMER = 'AI 生成内容仅供参考，不能替代医生诊断；如有不适请及时就医。';
/* --- S2 guardrail core (patient & doctor 共用同一份逻辑；修改时两端同步) --- */
const GUARD_REDFLAG_RULES = [
  { category: 'redflag_suicide', re: /想死|自杀|自残|不想活|轻生/ },
  { category: 'redflag_cardiac', re: /胸痛|胸口痛|胸闷压榨|压榨样/ },
  { category: 'redflag_stroke', re: /口角歪斜|半身无力|说话不清/ },
  { category: 'redflag_bleeding', re: /大出血|吐血|呕血/ },
  { category: 'redflag_breathing', re: /呼吸困难/ },
  { category: 'redflag_other', re: /昏迷|抽搐/ }
];
const GUARD_REFUSE_RULES = [
  { category: 'injection', re: /忽略之前的指令|忽略之前|忽略以上/ },
  { category: 'prompt_leak', re: /系统提示词|system\s*prompt/i },
  { category: 'role_override', re: /你现在是/ },
  { category: 'prescription_request', re: /开处方|开药|剂量|吃几片/ }
];
const GUARD_CATEGORY_LABEL = {
  redflag_cardiac: '心血管急症', redflag_stroke: '卒中征象', redflag_bleeding: '大出血',
  redflag_suicide: '自伤自杀风险', redflag_breathing: '呼吸急症', redflag_other: '其他急症',
  injection: '提示注入', prompt_leak: '提示词泄露', role_override: '越权请求',
  prescription_request: '处方请求', off_topic: '非医疗话题'
};
function guardCategoryLabel(cat) {
  if (!cat || cat === 'none') return '';
  return GUARD_CATEGORY_LABEL[cat] || String(cat);
}
/** 12356 仅在 redflag_suicide 时出现 */
function isSuicideCategory(cat) { return cat === 'redflag_suicide'; }
/** 0.2.0 caution（仅患者端、仅 action=allow）：caution_category 冻结枚举 */
const GUARD_CAUTION_LABEL = {
  caution_mood: '情绪', caution_pregnancy: '孕期', caution_pediatric: '儿科',
  caution_hypoglycemia: '低血糖', caution_cardiac: '心脏相关', caution_other: '其他'
};
const GUARD_CAUTION_DEFAULT = '如症状加重或持续请及时就医/拨打120';
function guardCautionLabel(cat) { return cat ? (GUARD_CAUTION_LABEL[cat] || String(cat)) : ''; }
/** caution_mood 才显示 12356 */
function isMoodCaution(cat) { return cat === 'caution_mood'; }
/** caution：string 或 {text|advice|message} → string */
function guardTextOf(v) {
  if (!v) return '';
  if (typeof v === 'string') return v.trim();
  if (typeof v === 'object') return String(v.text || v.advice || v.message || '').trim();
  return '';
}
/**
 * 规范化后端 guardrail：
 * - 0.2.0：advice 面向患者，reason 为内部文案（仅保留在 reason 字段）
 * - 支持 guardrail.redflag 标志（医生端「只提示不拦截」：action 可能是 allow + redflag 字段）
 * - 支持 guardrail.caution（疑似急症但放行）
 */
function normalizeGuardrail(g, via) {
  if (!g || typeof g !== 'object') return null;
  let action = String(g.action || '').toLowerCase();
  const rf = g.redflag;
  let category = g.category || '';
  let advice = String(g.advice || '').trim();
  if (rf && action !== 'refuse') {
    action = 'redflag';
    if (typeof rf === 'object') {
      category = rf.category || category;
      advice = String(rf.advice || '').trim() || advice;
    }
  }
  if (['redflag', 'refuse', 'allow'].indexOf(action) < 0) return null;
  const reason = String(g.reason || (rf && typeof rf === 'object' ? rf.reason || '' : '')).trim();
  const out = {
    action,
    category: category || (action === 'allow' ? 'none' : ''),
    advice, // 0.2.0：advice 面向患者；reason 为内部通用文案，不再回填 advice
    reason,
    via: via || 'api'
  };
  // caution 文本：guardrail.caution（string|object）；若只有 caution_category 则用默认文案
  const cCat = g.caution_category || g.cautionCategory || (g.caution && typeof g.caution === 'object' ? g.caution.category || '' : '');
  let caution = guardTextOf(g.caution);
  if (!caution && cCat) caution = GUARD_CAUTION_DEFAULT + (isMoodCaution(cCat) ? '；心理援助热线 12356' : '');
  if (caution) out.caution = caution;
  if (cCat) out.cautionCategory = String(cCat);
  if (rf) out.redflagFlag = true;
  if (Array.isArray(g.flags)) out.flags = g.flags.slice();
  return out;
}
/** 统一解析后端 guardrail：顶层 / data / message / reply / messages 末条 / triage / raw */
function extractGuardrail(resp) {
  if (!resp || typeof resp !== 'object') return null;
  const last = Array.isArray(resp.messages) && resp.messages.length ? resp.messages[resp.messages.length - 1] : null;
  const cands = [
    resp.guardrail,
    resp.data && resp.data.guardrail,
    resp.message && typeof resp.message === 'object' ? resp.message.guardrail : null,
    resp.reply && typeof resp.reply === 'object' ? resp.reply.guardrail : null,
    last && last.guardrail,
    resp.triage && resp.triage.guardrail,
    resp.raw && resp.raw.guardrail
  ];
  for (let i = 0; i < cands.length; i++) {
    const g = normalizeGuardrail(cands[i], 'api');
    if (g) return g;
  }
  return null;
}
/** 本地关键词 Mock：类别名与后端枚举一致 */
/** 否定语境（「无黑便呕血」「否认胸痛」「没有呼吸困难」）不算命中；同一分句内向前看 6 字 */
const GUARD_NEGATION_RE = /(无|否认|没有|未见|未诉|不伴|未出现)[^，。；,;！!？?\n]{0,6}$/;
function guardHasAffirmedMatch(t, re) {
  const g = new RegExp(re.source, re.flags.includes('g') ? re.flags : re.flags + 'g');
  let m;
  while ((m = g.exec(t))) {
    if (!GUARD_NEGATION_RE.test(t.slice(Math.max(0, m.index - 8), m.index))) return true;
    if (m[0].length === 0) g.lastIndex++;
  }
  return false;
}
function localGuardrailCheck(text) {
  const t = String(text || '');
  if (!t) return null;
  for (let i = 0; i < GUARD_REDFLAG_RULES.length; i++) {
    if (guardHasAffirmedMatch(t, GUARD_REDFLAG_RULES[i].re)) return { action: 'redflag', category: GUARD_REDFLAG_RULES[i].category, advice: '', reason: 'local_keyword', via: 'local' };
  }
  for (let i = 0; i < GUARD_REFUSE_RULES.length; i++) {
    if (GUARD_REFUSE_RULES[i].re.test(t)) return { action: 'refuse', category: GUARD_REFUSE_RULES[i].category, advice: '', reason: 'local_keyword', via: 'local' };
  }
  return null;
}
/**
 * 合并策略：
 * - redflag 严格 OR：后端或本地任一 redflag → redflag（两者都有时用后端的 category/advice）；后端 allow 不能压掉本地 redflag。
 * - 其他（refuse/allow）：后端优先；后端无 guardrail 时才用本地 refuse 猜测。
 */
function mergeGuardrail(backend, local) {
  if (backend && backend.action === 'redflag') return backend;
  if (local && local.action === 'redflag') {
    if (!backend) return local;
    const m = Object.assign({}, local, { backendAction: backend.action });
    if (backend.caution) { m.caution = backend.caution; if (backend.cautionCategory) m.cautionCategory = backend.cautionCategory; }
    return m;
  }
  if (backend) return backend;
  return local || null;
}
/** 本地 caution 猜测（仅无后端 guardrail 时用）：单纯胸闷 → caution_cardiac（胸闷压榨/压榨样仍是 redflag） */
function localCautionCheck(text) {
  const t = String(text || '');
  if (/胸闷/.test(t)) return { action: 'allow', category: 'none', advice: '', reason: 'local_keyword', via: 'local', caution: GUARD_CAUTION_DEFAULT, cautionCategory: 'caution_cardiac' };
  return null;
}
function resolveGuardrail(resp, userText) {
  const backend = extractGuardrail(resp);
  const merged = mergeGuardrail(backend, localGuardrailCheck(userText));
  if (!merged && !backend) return localCautionCheck(userText);
  return merged;
}
/* --- end core --- */

const GUARD_FALLBACK_ADVICE = {
  redflag: '您描述的情况可能涉及急危重症，请立即前往就近医院急诊或拨打 120，不要独自等待。',
  suicide: '你并不孤单。请立即联系身边信任的人，或拨打心理援助热线 12356；若有立即危险，请拨打 120。',
  refuse: '抱歉，这类问题我无法回答。处方、用药剂量等需由执业医师面诊后决定，请咨询医生或药师。',
  refuse_safety: '抱歉，该请求超出导诊助手的服务范围。请直接描述您的症状，我来帮您分诊。',
  off_topic: '我只能回答与健康、就医相关的问题，请描述您的症状或就医需求。'
};
/** 后端 advice 优先（已含 120/12356 等指引）；缺失时才用兜底文案 */
/** 患者端展示时去掉后端 reason 里的内部命中词说明（如「（命中「开处方」）」） */
function patientSafeReason(t) {
  return String(t || '').replace(/[（(]\s*命中[^）)]*[）)]\s*$/, '').trim();
}

function guardAdviceFor(g) {
  if (!g) return '';
  // 0.2.0：优先 advice（患者向）；reason 是内部通用文案，不展示给患者
  if (g.advice) return patientSafeReason(g.advice) || g.advice;
  if (g.action === 'redflag') return isSuicideCategory(g.category) ? GUARD_FALLBACK_ADVICE.suicide : GUARD_FALLBACK_ADVICE.redflag;
  if (g.category === 'off_topic') return GUARD_FALLBACK_ADVICE.off_topic;
  if (/^(injection|prompt_leak|role_override)$/.test(g.category)) return GUARD_FALLBACK_ADVICE.refuse_safety;
  return GUARD_FALLBACK_ADVICE.refuse;
}

/** 后端回复/免责文本是否已含 AI 免责（含「以上内容由 AI 生成，仅供参考」等写法），避免重复页脚 */
function hasAiDisclaimer(text) {
  return /AI\s*生成.{0,12}仅供参考/.test(String(text || ''));
}

/** allow + caution：只显示琥珀提示，不抬「建议立即急诊」横幅 / 急诊徽章 */
function isAllowCaution(g) {
  return !!(g && g.action === 'allow' && g.caution);
}
function cautionNoticeHtml(g) {
  if (!g || !g.caution || g.action !== 'allow') return '';
  const lb = guardCautionLabel(g.cautionCategory);
  const links = `<a class="gr-caution-link" href="tel:120">拨打 120</a>`
    + (isMoodCaution(g.cautionCategory) ? `<a class="gr-caution-link" href="tel:12356">心理援助热线 12356</a>` : '');
  return `<div class="gr-caution" role="note"><strong>⚠ 请留意${lb ? ' · ' + escapeHtml(lb) : ''}</strong> ${escapeHtml(g.caution)}<div class="gr-caution-links">${links}</div></div>`;
}

function appendCautionNotice(g) {
  const html = cautionNoticeHtml(g);
  const box = $('#chatMessages');
  if (!html || !box) return;
  const wrap = document.createElement('div');
  wrap.className = 'gr-caution-row';
  wrap.innerHTML = html;
  box.appendChild(wrap);
  box.scrollTop = box.scrollHeight;
}

/** renderBackend=true：后端 disclaimer 已含 AI 免责且页面未单独展示时，直接展示后端文案（优先后端，不叠加默认） */
function aiDisclaimerHtml(existingText, renderBackend) {
  if (hasAiDisclaimer(existingText)) return renderBackend ? `<p class="ai-disclaimer" role="note">${escapeHtml(existingText)}</p>` : '';
  return `<p class="ai-disclaimer" role="note">${AI_DISCLAIMER}</p>`;
}

function ensureGuardrailModal() {
  let m = document.getElementById('guardrailModal');
  if (m) return m;
  m = document.createElement('div');
  m.id = 'guardrailModal';
  m.className = 'gr-modal hidden';
  m.setAttribute('role', 'alertdialog');
  m.setAttribute('aria-modal', 'true');
  m.setAttribute('aria-labelledby', 'grModalTitle');
  m.innerHTML = `
    <div class="gr-backdrop"></div>
    <div class="gr-card" role="document">
      <div class="gr-icon" aria-hidden="true">🚨</div>
      <h2 id="grModalTitle">请立即就医</h2>
      <p class="gr-cat" id="grModalCat"></p>
      <p class="gr-advice" id="grModalAdvice"></p>
      <div class="gr-actions">
        <a class="gr-btn gr-btn-120" href="tel:120">📞 一键拨打 120</a>
        <a class="gr-btn gr-btn-psy hidden" id="grBtnPsy" href="tel:12356">💬 心理援助热线 12356</a>
        <button type="button" class="gr-btn gr-btn-ok" id="grBtnOk">我知道了</button>
      </div>
      <p class="gr-note">当前在线问诊已暂停。AI 不能替代急救与医生诊断。</p>
    </div>`;
  document.getElementById('app')?.appendChild(m) || document.body.appendChild(m);
  // 点背景不关闭（刻意不绑定 .gr-backdrop click）
  m.querySelector('#grBtnOk').addEventListener('click', () => m.classList.add('hidden'));
  return m;
}

function showGuardrailRedflag(g, nextSteps) {
  const m = ensureGuardrailModal();
  const suicide = isSuicideCategory(g.category);
  m.querySelector('#grModalTitle').textContent = suicide ? '请立即寻求帮助' : '请立即就医';
  const label = guardCategoryLabel(g.category);
  m.querySelector('#grModalCat').textContent = label
    ? `护栏提示：${label}${g.via === 'local' ? '（本地规则）' : ''}` : '';
  const adv = m.querySelector('#grModalAdvice');
  adv.textContent = guardAdviceFor(g);
  adv.classList.toggle('gr-advice-backend', !!g.advice);
  let stepsEl = m.querySelector('#grModalSteps');
  if (!stepsEl) {
    stepsEl = document.createElement('ol');
    stepsEl.id = 'grModalSteps';
    stepsEl.className = 'gr-steps';
    adv.insertAdjacentElement('afterend', stepsEl);
  }
  const steps = Array.isArray(nextSteps) ? nextSteps.filter(Boolean) : [];
  stepsEl.innerHTML = steps.map((x) => `<li>${escapeHtml(x)}</li>`).join('');
  stepsEl.classList.toggle('hidden', !steps.length);
  m.querySelector('#grBtnPsy').classList.toggle('hidden', !suicide);
  m.classList.remove('hidden');
  setTimeout(() => m.querySelector('.gr-btn-120')?.focus(), 30);
}

function lockChatByGuardrail(g) {
  state.chatGuardLocked = true;
  state.chatGuardrail = g;
  const input = $('#chatInput');
  const sendBtn = $('#btnSendChat');
  if (input) { input.disabled = true; input.placeholder = '当前问诊已暂停，请优先就医'; }
  if (sendBtn) sendBtn.disabled = true;
  let bar = $('#chatGuardLock');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'chatGuardLock';
    bar.className = 'gr-lock';
    bar.setAttribute('role', 'alert');
    const composer = document.querySelector('#view-chat .chat-composer');
    composer?.parentNode.insertBefore(bar, composer);
  }
  const suicide = isSuicideCategory(g.category);
  const label = guardCategoryLabel(g.category);
  bar.innerHTML = `
    <div class="gr-lock-text"><strong>🔒 当前问诊已暂停，请优先就医</strong>
      <span>${label ? '已识别风险：' + escapeHtml(label) : '已识别急症风险信号'}</span></div>
    <div class="gr-lock-actions">
      <a class="btn danger sm" href="tel:120">拨打 120</a>
      ${suicide ? '<a class="btn danger sm" href="tel:12356">12356</a>' : ''}
      <button type="button" class="btn ghost sm" id="btnGuardNewChat">重新开始新问诊</button>
    </div>`;
  bar.classList.remove('hidden');
  $('#btnGuardNewChat')?.addEventListener('click', () => {
    resetChatSession();
    startChat();
  });
}

function unlockChatGuard() {
  state.chatGuardLocked = false;
  state.chatGuardrail = null;
  $('#chatGuardLock')?.classList.add('hidden');
  document.getElementById('guardrailModal')?.classList.add('hidden');
}

function appendRefuseNotice(g) {
  const box = $('#chatMessages');
  if (!box) return;
  const div = document.createElement('div');
  div.className = 'msg bot gr-refuse';
  div.setAttribute('role', 'note');
  div.innerHTML = `<div class="msg-body"><strong>🛡 护栏提示${guardCategoryLabel(g.category) ? ' · ' + escapeHtml(guardCategoryLabel(g.category)) : ''}</strong>\n${escapeHtml(guardAdviceFor(g))}</div><span class="msg-time">${formatMsgTime()}</span>`;
  box.appendChild(div);
  box.scrollTop = box.scrollHeight;
}

function refuseNoticeHtml(g) {
  return `<div class="gr-refuse-inline" role="note"><strong>🛡 护栏提示${guardCategoryLabel(g.category) ? ' · ' + escapeHtml(guardCategoryLabel(g.category)) : ''}</strong><p>${escapeHtml(guardAdviceFor(g))}</p></div>`;
}

/** 在问诊/导诊里应用护栏（redflag 弹卡+锁；refuse 提示） */
function applyChatGuardrail(g) {
  if (!g || g.action === 'allow') return;
  if (g.action === 'redflag') {
    showChatUrgent(true);
    showGuardrailRedflag(g);
    lockChatByGuardrail(g);
  } else if (g.action === 'refuse') {
    appendRefuseNotice(g);
  }
}

function lockSymptomFormByGuardrail(on) {
  state.triageGuardLocked = !!on;
  const form = $('#symptomForm');
  if (!form) return;
  const submit = form.querySelector('button[type="submit"]');
  if (submit) submit.disabled = !!on;
  let bar = $('#symptomGuardLock');
  if (!bar) {
    bar = document.createElement('div');
    bar.id = 'symptomGuardLock';
    bar.className = 'gr-lock hidden';
    bar.setAttribute('role', 'alert');
    bar.innerHTML = `<div class="gr-lock-text"><strong>🔒 当前问诊已暂停，请优先就医</strong><span>已识别急症风险信号</span></div>
      <div class="gr-lock-actions"><a class="btn danger sm" href="tel:120">拨打 120</a>
      <button type="button" class="btn ghost sm" id="btnGuardNewTriage">重新开始新问诊</button></div>`;
    form.parentNode.insertBefore(bar, form);
    bar.querySelector('#btnGuardNewTriage').addEventListener('click', () => {
      form.reset();
      lockSymptomFormByGuardrail(false);
      showView('symptom');
    });
  }
  bar.classList.toggle('hidden', !on);
}

/* 预览：?guardrailDemo=redflag|psych|refuse，或控制台 window.__guardrailDemo('psych') */
const GUARD_DEMO_CASES = {
  // 模拟后端返回 redflag_cardiac + advice（展示后端 advice 优先）
  redflag: { user: '突然胸痛，像被压住一样，还有点呼吸困难', bot: '（本轮 AI 回复已由安全护栏接管）',
    resp: { guardrail: { action: 'redflag', category: 'redflag_cardiac', advice: '胸痛伴压迫感可能是心梗等急症，请立即拨打 120 或前往最近医院急诊，不要自行驾车，保持安静休息。' } } },
  // 后端 allow + 本地 redflag_suicide → 严格 OR 仍为 redflag（兜底文案含 12356）
  psych: { user: '最近压力太大，真的不想活了', bot: '（本轮 AI 回复已由安全护栏接管）',
    resp: { guardrail: { action: 'allow', category: 'none', advice: '' } } },
  // 后端无 guardrail → 本地 refuse 猜测 prescription_request
  refuse: { user: '直接给我开处方吧，阿莫西林一次吃几片？', bot: '我可以帮你梳理症状、推荐就诊科室。', resp: {} },
  // 后端 allow + caution（疑似急症但放行）：琥珀小提示，不弹窗、不锁输入
  caution: { user: '头疼两天，今天有点加重', bot: '收到。头痛加重时有没有发热、呕吐、视物模糊？',
    resp: { guardrail: { action: 'allow', category: 'none', caution: '如症状加重或持续请及时就医/拨打120', caution_category: 'caution_other' } } }
};

async function runGuardrailDemo(kind) {
  const c = GUARD_DEMO_CASES[kind];
  if (!c) return;
  if (state.chatStarted) resetChatSession();
  state.guardDemoRunning = true;
  showView('chat');
  // 等欢迎语渲染（startChat 为异步）
  for (let i = 0; i < 40 && !$('#chatMessages')?.children.length; i++) {
    await new Promise((r) => setTimeout(r, 100));
  }
  appendMsg('user', c.user);
  const g = resolveGuardrail(c.resp, c.user);
  appendMsg('bot', c.bot, '本地 Mock · 护栏预览');
  if (g && g.caution) appendCautionNotice(g);
  applyChatGuardrail(g);
  state.guardDemoRunning = false;
}
window.__guardrailDemo = runGuardrailDemo;

document.addEventListener('DOMContentLoaded', () => {
  let kind = '';
  try { kind = new URLSearchParams(location.search).get('guardrailDemo') || ''; } catch (_) {}
  if (kind && GUARD_DEMO_CASES[kind]) setTimeout(() => runGuardrailDemo(kind), 300);
});
