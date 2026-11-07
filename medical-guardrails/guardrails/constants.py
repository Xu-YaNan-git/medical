DISCLAIMER = "以上内容由 AI 生成，仅供参考，不能替代医生面诊、诊断或处方；如有急危症状请立即就医或拨打 120。"
AI_NOTICE = "AI 建议，需医生确认"
REDFLAG_ADVICE = "立即急诊/拨打120"
SUICIDE_ADVICE = "立即急诊/拨打120；心理援助热线 12356"

ROLES = ("patient", "doctor")
CAUTION_ADVICE = "如症状加重或持续请及时就医/拨打120"
CAUTION_MOOD_ADVICE = "如症状加重或持续请及时就医/拨打120；心理援助热线 12356"

# Enumerations exposed to UI (frozen)
INPUT_ACTIONS = ("allow", "redflag", "refuse")
REDFLAG_CATEGORIES = (
    "redflag_cardiac", "redflag_stroke", "redflag_bleeding",
    "redflag_suicide", "redflag_breathing", "redflag_other",
)
REFUSE_CATEGORIES = ("injection", "prompt_leak", "role_override", "prescription_request", "off_topic")
INPUT_CATEGORIES = REDFLAG_CATEGORIES + REFUSE_CATEGORIES + ("none",)
CAUTION_CATEGORIES = (
    "caution_mood", "caution_pregnancy", "caution_pediatric",
    "caution_hypoglycemia", "caution_cardiac", "caution_other",
)
