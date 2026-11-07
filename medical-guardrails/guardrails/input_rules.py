"""check_input: red flags > refuse (injection / leak / role / prescription / off-topic) > allow.

Pure regex rules, offline. Patterns are matched on normalized text (see normalize.py).
"""

from __future__ import annotations

import re
from typing import Optional, Pattern

from . import llm_judge
from .constants import CAUTION_ADVICE, CAUTION_CATEGORIES, CAUTION_MOOD_ADVICE, REDFLAG_ADVICE, ROLES, SUICIDE_ADVICE
from .normalize import bare, compact
from .pii import mask_pii

# ---------------------------------------------------------------------------
# Red flags. Order = category priority when several match.
# ---------------------------------------------------------------------------

_SEIZURE_PAT = r"(?<!眼皮)(?<!眼)(?<!嘴角)抽搐|抽风|抽过风|羊角风|羊癫疯|惊厥"

_RF_SPEC: list[tuple[str, str, list[str]]] = [
    (
        "redflag_suicide",
        "疑似自伤/自杀倾向",
        [
            r"自杀|轻生|寻死|自残|自尽|割腕|跳楼|跳河|上吊|烧炭(自杀|轻生|寻死)|吞药|遗书",
            r"不想活|活不下去|活够了|想死|去死|死了算了|死了一了百了",
            r"活着[^\n|;；]{0,6}((没|没有|无)(什么|啥)?(意思|意义|盼头|希望|劲)|有什么意思|有啥意思)",
            r"一了百了|(结束|了结|了断)[^\n|;；]{0,4}(生命|自己|这一切|一切|性命)",
            r"伤害自己|(安眠药|药片|药)[^\n|;；]{0,8}(都|全部|全|一次|一把|一瓶|攒)[^\n|;；]{0,6}(吃|吞|准备|备好|攒)",
            r"攒[^\n|;；]{0,4}(安眠药|药片)",
            r"跳下去[^\n|;；]{0,6}(解脱|算了|一了百了|就好了)|解脱了?吧?$|(想|打算|准备|要)(去)?(跳下去|跳楼|跳河|死|了结|结束自己)|不想(再)?活|活腻",
            r"(吞|吃|喝)了?[^\n|;；]{0,4}(一整瓶|整瓶|一瓶|一整盒|一盒|一把|大量|很多|好多|几十)(片|粒)?[^\n|;；]{0,6}(药|片|粒)",
            r"(安眠药|药片|药丸|药)[^\n|;；]{0,4}(囤|攒|存)了?(一|好多|很多|几十|一大)",
            r"(安眠药|药片|药)[^\n|;；]{0,12}(全|全部|一口气|一把)(都)?(吞|吃|喝)(下去|掉|光)",
        ],
    ),
    (
        "redflag_cardiac",
        "胸痛等心源性危险信号",
        [
            r"胸(口|部|前|前区|骨后|骨)?(有点|有些|突然|一阵阵?|剧烈|持续|隐隐|针扎样|刀割样|撕裂样|压榨样|闷)?(作)?(痛|疼)",
            r"心口(有点|突然|一阵阵?|剧烈)?(疼|痛)|心(脏|前区)(有点|突然)?(疼|痛)|心绞痛",
            r"心梗|心肌梗|心脏骤停|心跳骤停|心跳停|主动脉夹层",
            r"压榨(样|感)",
            r"胸(口|部|前|骨)?[^\n|,，。;；!?！？头肚腹腰背腿脚手牙]{0,8}(紧缩|针扎|刀割|撕裂|压榨)",
            r"(胸口窝|胸口|胸部|胸前|胸膛|胸骨后?|心口窝?|心窝子?|心前区)[^\n|;；,，。不没无未]{0,4}(剧痛|剧烈|绞痛|绞着|压榨|撕裂|刀割|针扎|闷痛|好痛|好疼|很痛|很疼|特别痛|特别疼|超痛|超疼|疼得|痛得|疼死|痛死|疼的|痛的)",
            r"(剧烈|突发|突然|持续)(的|性)?(胸|心口|心窝)(口|部|前)?(痛|疼|疼痛)",
            r"(胸|心口|心窝)[^\n|;；]{0,4}像[^\n|;；]{0,8}(压|坐|勒|绑|捆|撕|堵|石头)",
            r"(胸|心口|心窝)[^\n|;；]{0,8}(压|闷|痛|疼|堵|紧)[^\n|;；]{0,10}(二十|20|半小时|30|几十|半个钟头?|一个小时|1小时|一小时)[^\n|;；]{0,10}(不缓解|没缓解|还没好|不见好|还在|还没停|没停)",
            r"胸[^\n|;；]{0,12}(冷汗|大汗|一身汗|全是汗|满头大汗|直冒汗|浑身是汗)",
            r"胸[^\n|;；]{0,4}像[^\n|;；]{0,8}(压|坐|勒|绑|捆|撕|堵|石头)",
            r"胸[^\n|;；]{0,3}(压|堵|憋|闷|不适|难受)[^\n|;；]{0,12}(石头|喘不|大汗|冷汗|出汗|一身汗|左边?(臂|胳膊|肩)|下巴|下颌|濒死)",
            r"(大汗|冷汗|一身汗)[^\n|;；]{0,12}胸(口|闷|部)?",
            r"(胸|心口|心窝|心脏)[^\n|;；]{0,4}(揪|绞|攥|拧)(着|紧|住)?[^\n|;；]{0,2}(疼|痛)",
            r"(疼|痛)(到|至|向|窜到|传到|放射到?|连着)[^\n|;；]{0,4}(左边?(肩|臂|胳膊|手臂)|下巴|下颌|牙)",
            r"(胸|心口)[^\n|;；]{0,10}左边?(臂|胳膊|手臂|肩)[^\n|;；]{0,4}(麻|痛|疼)",
            r"左边?(臂|胳膊|手臂|肩)[^\n|;；]{0,6}(麻|痛|疼)[^\n|;；]{0,10}(胸|心口)",
            r"(胸|心口|心窝)[^\n|;；]{0,4}像[^\n|;；]{0,8}(踩|碾|箍|捏|攥|大象|砖|磨盘|铁板)",
            r"(后背|背部|背上|背后)[^\n|;；]{0,6}(撕开|撕裂|撕扯|被撕|刀割)[^\n|;；]{0,4}(疼|痛)?",
            r"chest[^\n|;；]{0,4}(pain|hurts?|tight|痛|疼|闷|压)",
        ],
    ),
    (
        "redflag_stroke",
        "疑似卒中/急性神经系统症状",
        [
            r"口角歪斜|口眼歪斜|嘴(巴|角)?(突然)?(歪|斜)|脸[^\n|;；]{0,3}歪|面瘫",
            r"(说话|讲话|口齿|言语|吐字|说的话)[^\n|;；]{0,4}(不清|含糊|不利索|不出来|困难|听不懂)|说不出话|大舌头",
            r"(左|右|一|半)(边|侧)(的)?(身子|身体|手脚|胳膊|手臂|手|腿|脚|肢体|脸)[^\n|;；]{0,6}(没劲|没力|无力|麻|不听使唤|动不了|抬不起|拿不住|没知觉)",
            r"半身不遂|偏瘫|中风|卒中|脑梗|脑出血|脑溢血",
            r"(一侧|半边|半侧|一边)(的)?[^\n|;；]{0,2}(脸|嘴|面部|身|身子|手|腿)[^\n|;；]{0,4}(麻|木|歪|没知觉|没劲|无力)",
            r"口水[^\n|;；]{0,4}(往外流|流出来|兜不住|止不住)|说不(利索|清楚|出话)|话[^\n|;；]{0,2}说不(清|利索)",
            r"突然[^\n|;；]{0,4}(看不见|看不清|失明|重影)",
            r"头[^\n|;；]{0,4}(炸裂|爆炸|炸开)|(剧烈|爆炸样|炸裂样|撕裂样|突发剧烈)(的)?头(痛|疼)",
            r"(这辈子|有生以来|一辈子|从来|从没|从未)[^\n|;；]{0,4}(这么|这样|那么)?(疼|痛)过",
            r"最(疼|痛)的一次头(痛|疼)",
            r"头[^\n|;；不没无未]{0,3}(剧痛|痛欲裂|疼欲裂|要炸|快炸|裂开)|头(疼|痛)得(要|快)(炸|裂|死)",
            r"头[^\n|;；]{0,4}像[^\n|;；]{0,6}(劈开|劈|斧头|锤|炸|裂|爆)",
        ],
    ),
    (
        "redflag_bleeding",
        "大出血/消化道出血等危险信号",
        [
            r"大出血|出血不止|血流不止|血止不住|止不住血|(血|出血)[^\n|;；]{0,8}(止不住|停不下|不停地?流)|血[^\n|;；]{0,4}(往外冒|往外涌|往外喷|喷出|哗哗|湿透)",
            r"流了?(好多|很多|一大摊|一地|大量|一大滩)(的)?血|出了?(好多|很多|大量)(的)?血|(一地|满地)(的)?血",
            r"呕血|吐血|吐了[^\n|;；]{0,4}血|(大口|大量|一口一口)[^\n|;；]{0,2}(咯|咳)血|咯血",
            r"(流血|出血|渗血)[^\n|;；]{0,10}(湿透|浸透|不止|止不住|一直不停|很多|好多|大量)|(湿透|浸透)[^\n|;；]{0,6}(血)",
            r"(生完|产后|分娩后|生孩子后|流产后)[^\n|;；]{0,10}(流血|出血)",
            r"咖啡渣|(吐|呕)[^\n|;；]{0,8}(咖啡|血块|带血)",
            r"便血[^\n|;；]{0,6}(很多|大量|不止|晕|头晕|心慌)",
            r"(黑便|柏油|(大便|屎|粪)[^\n|;；]{0,3}黑|拉黑)[^\n|;；]{0,12}(晕|昏|心慌|乏力|冷汗)|(晕|昏)[^\n|;；]{0,12}(黑便|柏油)",
            r"(血)[^\n|;；]{0,2}(一直流|流个不停|流不停|哗哗地?流|止也止不住)",
            r"(咳|吐|呕|咯)了?(一大口|一口|好几口|好多|很多|一大摊|满口|大口)(的)?(鲜)?血",
            r"(怀孕|孕期|孕妇|孕[0-9一二三四五六七八九十]+周)[^\n|;；]{0,10}(大量|很多|好多|止不住|血块|湿透)[^\n|;；]{0,4}(出血|流血|血)",
            r"(孕晚期|怀孕[六七八九]个多?月|孕[23][0-9]周|快生了|临产)[^\n|;；]{0,12}(剧痛|见红|出血|流血)",
            r"阴道[^\n|;；]{0,4}出血[^\n|;；]{0,6}(很多|不止|止不住|大量)|(阴道|下面)[^\n|;；]{0,4}大量出血|(产后|流产)[^\n|;；]{0,6}出血",
        ],
    ),
    (
        "redflag_breathing",
        "呼吸困难/窒息等危险信号",
        [
            r"呼吸困难|喘不(过|上)来?气|上不来气|透不过气|喘不动|无法呼吸|不能呼吸|呼吸急促|窒息|噎住|呼吸[^\n|;；]{0,3}(费劲|吃力)",
            r"(憋|呛|噎)得?[^\n|;；]{0,4}(发紫|发青|紫了|喘不)",
            r"(嘴唇|脸|脸色|嘴)[^\n|;；]{0,3}(发紫|发青|青紫|紫了|乌青)",
            r"(嘴唇|口唇|指甲|嘴)[^\n|;；]{0,4}(紫|乌|青)",
            r"(一躺下|躺下|平躺)[^\n|;；]{0,4}(就)?(喘|憋|上不来)|躺不下|端坐呼吸|(夜里|晚上|半夜)[^\n|;；]{0,4}憋醒",
            r"(卡|呛)(到|住)[^\n|;；]{0,8}(喘不|说不出|发紫|紫|咳不出)",
            r"喘得[^\n|;；]{0,4}(说不|躺不)|说话说不完整|气促|气短[^\n|;；]{0,6}(厉害|加重)",
            r"哮喘[^\n|;；]{0,6}(发作|喷剂没用|不管用|止不住)",
            r"喉咙[^\n|;；]{0,4}(发紧|肿|堵)[^\n|;；]{0,6}(喘|呼吸|说不)",
            r"气[^\n|;；]{0,3}(喘不(上|过|动)|吸不进)|(憋|闷)得?(要死|快死|不行了)|快(要)?(憋死|窒息)",
        ],
    ),
    (
        "redflag_other",
        "中毒/意识障碍/抽搐等其他急危信号",
        [
            r"农药|百草枯|敌敌畏|老鼠药|误(服|喝|吃|食)|中毒|煤气|一氧化碳",
            r"误吞|吞了[^\n|;；]{0,6}(电池|磁|硬币|鱼刺|异物|钉|针|刀片)|纽扣电池",
            r"(眼前一黑|突然)[^\n|;；]{0,6}(倒|晕|摔|栽)|倒(在)?地(上)?(了)?[^\n|;；]{0,4}(醒|起不来|不动)|醒来[^\n|;；]{0,6}不记得|失去意识|没了意识|断片",
            r"说胡话|胡言乱语|意识模糊|神志恍惚|认不出人|叫不出名字",
            r"(脖子|颈部?|颈)[^\n|;；]{0,2}(僵|硬)[^\n|;；]{0,10}(烧|热)|(烧|热)[^\n|;；]{0,10}(脖子|颈部?|颈)[^\n|;；]{0,2}(僵|硬)",
            _SEIZURE_PAT,
            r"昏迷|叫不醒|叫不应|(叫|喊|拍)(他|她|也|都|了)[^\n|;；]{0,3}没(有)?反应|意识不清|神志不清|不省人事|晕过去|晕倒|昏倒|休克",
            r"过敏[^\n|;；]{0,10}(喉咙|呼吸|全身|发紧)|喉头水肿|(嗓子|喉咙|喉头)[^\n|;；]{0,4}(发紧|越来越紧|肿得)",
            r"(大面积|严重)(的)?(烧伤|烫伤)",
            r"从[^\n|;；]{0,6}(楼|高处|梯子)[^\n|;；]{0,4}(摔|掉|坠|跌)|车祸|骨头[^\n|;；]{0,4}(露|戳)出",
            r"高(烧|热)[^\n|;；]{0,8}(脖子硬|颈部僵硬|颈强直|抽)|脖子(发)?硬[^\n|;；]{0,6}(发烧|高烧|发热)",
            r"肚子[^\n|;；]{0,4}硬得?像[^\n|;；]{0,2}板|板状腹",
            r"(肚子|腹部|小腹|下腹|上腹|肚皮)[^\n|;；,，。不没无未]{0,3}(剧痛|剧烈疼痛|疼得打滚|痛得打滚|疼得直不起腰|痛得直不起腰)|(疼|痛)得(满地)?打滚",
            r"一直抽|抽(个)?不停|抽了[^\n|;；]{0,4}(分钟|好久|很久|半天)|抽搐不止|反复抽|翻白眼|眼睛(往上|向上)翻|口吐白沫",
            r"血糖[^\n|;；]{0,6}(?<![0-9.])([0-2]\.[0-9]|[12]点[0-9])(?![0-9])",
            r"叫(都|也)?叫不(太)?醒|叫(他|她)?(的)?(名字)?(也|都)?不(答应|应)|喊(他|她)?(也|都)?不(答应|应)|迷迷糊糊[^\n|;；]{0,6}(叫不|醒不|没反应)",
        ],
    ),
]

_RF: list[tuple[str, str, list[Pattern[str]]]] = [
    (cat, label, [re.compile(p) for p in pats]) for cat, label, pats in _RF_SPEC
]

# ---------------------------------------------------------------------------
# Negation scope (没有胸痛 / 无胸闷、呼吸困难 / 不头晕 / 否认胸痛)
# ---------------------------------------------------------------------------

_CLAUSE_BREAK = re.compile(r"[,，。.!！?？;；\n|:：]|但是?|可是|不过|却|然而|现在|今天|刚才|突然")
_NEG = re.compile(
    r"并没有|从没有|没有|也没|并无|否认|未见|未|没(?!想到|办法|法|多久|过多久|事|关系|用|劲|力)"
    r"|无(?!力|法|缘|故|端|意|论)|不伴有?|不(?!知道|清楚|确定|记得|是|停|住|了|舒服|对劲|行|能|会|敢|想|出|上|过|动|清)"
)
# words between negator and the symptom that break the negation ("没吃饭就胸痛")
_NEG_BREAKERS = re.compile(r"就|开始|又|后|时|然后|才|还|了|吃|喝|做|去|走|跑|睡|在|过")
_NEG_FILLER_OK = re.compile(r"^[\u4e00-\u9fff、和或及也与]{0,12}$")
_BU_FILLERS = {"", "伴", "伴有", "觉得", "感觉", "怎么", "太"}


def _is_negated(text: str, pos: int) -> bool:
    start = 0
    for m in _CLAUSE_BREAK.finditer(text, 0, pos):
        start = m.end()
    prefix = text[start:pos]
    negs = list(_NEG.finditer(prefix))
    if not negs:
        return False
    last = negs[-1]
    between = prefix[last.end():]
    if last.group(0) == "不":
        return between in _BU_FILLERS
    if not _NEG_FILLER_OK.match(between):
        return False
    return not _NEG_BREAKERS.search(between)


_SEG_SPLIT = re.compile(r"[\n|;；]")

# 抽搐/惊厥 mentioned as history or already resolved -> boundary band (caution), not red flag
_SEIZURE_HISTORY = re.compile(r"以前|之前|曾经|有过|病史|既往|小时候|去年|上次|前几年|史|已经好了|就好了|一下就|几秒")

# Same-field co-occurrence (field = text between \n | ; ；). Both terms must be non-negated.
_COMBOS: list[tuple[str, str, str, str]] = [
    (
        "redflag_cardiac", "胸部不适伴出汗/放射痛/气促",
        r"(胸(口窝|口|部|前|膛|骨后?)?|心口|心窝)[^\n|;；不没无未]{0,6}(闷|紧|压|堵|痛|疼|不适|难受|不舒服)|(捂|按|揪|抓)着?(胸|心口|心窝)|chest",
        r"冷汗|大汗|出汗|全是汗|一身汗|虚汗|冒汗|透不过|喘不过|left ?arm|leftarm|左边?(臂|肩|胳膊|手臂)|下巴|下颌|喘不|呼吸困难|上不来气|濒死|要死了",
    ),
    (
        "redflag_suicide", "消极言语伴自伤准备",
        r"(没有|没了)我[^\n|;；]{0,4}(更好|更轻松)|活着(好|真|太)?(累|没劲)|撑不下去|生无可恋|不想拖累|是(个)?(累赘|负担|多余的)|想消失",
        r"(药|安眠药|绳子|刀|炭|农药)[^\n|;；]{0,4}(都|已经|早就)?(准备好|备好|买好|攒好|攒够|准备了)|遗书|后事|交代好",
    ),
    (
        "redflag_bleeding", "孕晚期出血/剧烈腹痛",
        r"孕晚期|怀孕[六七八九]个多?月|孕[23][0-9]周|快生了|临产|预产期",
        r"流血|出血|见红|血块|剧痛|疼得厉害|硬得像|破水",
    ),
    (
        "redflag_bleeding", "黑便/呕血伴头晕",
        r"黑便|柏油|(大便|屎|粪|拉的)[^\n|;；]{0,6}黑|吐血|呕血|便血",
        r"晕|昏|眼前(发)?黑|心慌|冷汗|站不住|没力气",
    ),
    (
        "redflag_other", "低血糖伴意识改变",
        r"低血糖|血糖[^\n|;；]{0,4}(低|掉)|出汗|大汗|冷汗|手抖|发抖",
        r"反应(很|特别|非常|有点)?(慢|迟钝)|叫不醒|糊涂|意识|认不出|答非所问|不答应|没反应|不理人|叫不应",
    ),
]
_COMBO_RX = [(c, l, re.compile(a), re.compile(b)) for c, l, a, b in _COMBOS]


def _first_live(p: Pattern[str], text: str) -> Optional[re.Match]:
    for m in p.finditer(text):
        if not _is_negated(text, m.start()):
            return m
    return None


def _segment_of(norm: str, pos: int) -> str:
    a = max(norm.rfind(c, 0, pos) for c in "\n|;；") + 1
    ends = [x for x in (norm.find(c, pos) for c in "\n|;；") if x != -1]
    return norm[a: min(ends) if ends else len(norm)]


def _find_redflag(norm: str) -> tuple[Optional[tuple[str, str, str]], bool]:
    """-> (hit, seizure_history_seen)."""
    seizure_hist = False
    for cat, label, pats in _RF:
        for p in pats:
            for m in p.finditer(norm):
                if _is_negated(norm, m.start()):
                    continue
                if p.pattern == _SEIZURE_PAT and _SEIZURE_HISTORY.search(_segment_of(norm, m.start())):
                    seizure_hist = True
                    continue
                return (cat, label, m.group(0)), seizure_hist
    for seg in _SEG_SPLIT.split(norm):
        for cat, label, a, b in _COMBO_RX:
            ma, mb = _first_live(a, seg), _first_live(b, seg)
            if ma and mb:
                return (cat, label, f"{ma.group(0)}…{mb.group(0)}"), seizure_hist
    return None, seizure_hist


# ---------------------------------------------------------------------------
# Caution: boundary band, patient role only, action stays allow
# ---------------------------------------------------------------------------

_CAUTION_SPEC: list[tuple[str, str, list[str]]] = [
    ("caution_mood", "消极情绪表达", [
        r"人生(没|没有|无)(啥|什么)?(意思|意义|盼头)|心里(堵得慌|好堵|憋屈得慌)|活着(好|真|太)?(累|没劲)|撑不下去|好绝望|很绝望|太绝望|没有希望|没盼头|生无可恋|心如死灰|好想消失|想消失",
        r"(没有|没了)我[^\n|;；]{0,4}(更好|更轻松)|我是(个)?(累赘|负担|废物)|(自己|我)(就|真|简直)?(是|成了)(个)?(累赘|负担|废物|多余的)|不想拖累|什么都不想做|没人在乎我",
        r"心情(很|好|特别|非常|有点|挺)?(差|不好|低落|郁闷|糟糕|烦|糟)|心里(很|特别|非常)?(难受|不好受|烦|乱)",
        r"(心情|情绪|心里)[^\n|;；]{0,6}(差|不好|低落|郁闷)[^\n|;；]{0,8}(睡不着|失眠|睡不好)|睡不着[^\n|;；]{0,8}(心情|情绪)[^\n|;；]{0,4}(差|不好)",
    ]),
    ("caution_pregnancy", "孕期不适/出血", [
        r"(怀孕|孕期|孕早期|孕中期|孕妇|孕[0-9一二三四五六七八九十]+周|怀了|有喜|早孕)[^\n|;；]{0,12}(见红|出血|流血|血丝|褐色分泌物|有血)",
        r"(见红|出血|流血)[^\n|;；]{0,8}(怀孕|孕期|孕妇)",
        r"(怀孕|孕期|孕早期|孕中期|孕妇|孕[0-9一二三四五六七八九十]+周|怀了|有喜|早孕)(了|啦|咯)?[^\n|;；]{0,8}(肚子(疼|痛|不舒服|难受)|腹痛|肚痛|下腹(疼|痛|隐隐))",
        r"(肚子(疼|痛)|腹痛|肚痛|下腹(疼|痛))[^\n|;；]{0,8}(怀孕|孕期|孕妇|有喜)",
    ]),
    ("caution_pediatric", "小儿高热/抽搐", [
        r"(孩子|宝宝|小孩|儿子|女儿|娃|婴儿|孙子|孙女|闺女)[^\n|;；]{0,10}(高烧|高热|烧到(39|40|三十九|四十)|39度|40度|三十九度|四十度|烧不退|发烧不退|烧得厉害)",
        r"(孩子|宝宝|小孩|儿子|女儿|娃|婴儿)[^\n|;；]{0,10}(抽(了一下|过|了几秒)|惊厥|抽搐)",
        r"高热惊厥|热性惊厥",
    ]),
    ("caution_hypoglycemia", "低血糖样表现", [
        r"低血糖|血糖[^\n|;；]{0,4}(低|偏低|掉得)",
        r"(出汗|冒汗|出虚汗|虚汗|冷汗)[^\n|;；]{0,6}(发抖|手抖|哆嗦|心慌|饿)|(发抖|手抖|哆嗦|心慌)[^\n|;；]{0,6}(出汗|冒汗|虚汗|冷汗)",
    ]),
    ("caution_cardiac", "胸部压迫/闷堵感", [
        r"(胸(口窝|口|部|前|膛)?|心口|心窝)[^\n|;；,，。不没无未]{0,4}(闷|发紧|紧绷|压迫感|压着|堵|憋|不舒服|难受)",
    ]),
]
_CAUTION = [(c, l, [re.compile(p) for p in pats]) for c, l, pats in _CAUTION_SPEC]
assert tuple(c for c, _, _ in _CAUTION_SPEC) + ("caution_other",) == CAUTION_CATEGORIES


def _find_caution(norm: str, seizure_hist: bool) -> Optional[tuple[str, str]]:
    for cat, label, pats in _CAUTION:
        for p in pats:
            if _first_live(p, norm):
                return cat, label
    if seizure_hist:
        return "caution_other", "既往抽搐/惊厥"
    return None


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------

_INSTR = r"(指令|指示|规则|设定|限制|提示|提示词|约束|安全策略|策略|命令|规定|instructions?|rules?|prompts?)"

_REFUSE_SPEC: list[tuple[str, str, list[str], tuple[str, ...]]] = [
    # (category, reason, patterns, roles it applies to)
    (
        "prompt_leak",
        "试图获取系统提示词或内部配置",
        [
            r"(系统|初始|内部|隐藏|原始|底层|预设|开发者)(的)?(提示词|prompt|指令|设定|配置|规则|消息)",
            r"系统提示(的)?(内容|全文|是什么|原文)",
            r"systemprompt|systemmessage|initialprompt|yourprompt|yourinstructions|yoursystem|printyour|revealyour|showyour(prompt|instructions|rules)",
            r"(repeat|print|output)(the)?(text|words|everything|content)?above|whatwereyoutold",
            r"(你的|你收到的|你被设定的|给你的|你被给予的|你内置的)(prompt|提示词|设定|指令|规则|配置|system|初始化)",
            r"(复述|重复|打印|输出|显示|透露|告诉我|发给我|泄露|贴出)(一下)?(你)?(上面|之前|最开始|开头|前面|最初)(收到)?(的)?(内容|话|文字|设定|指令|消息|提示)",
            r"(复述|贴|发|打印|输出|告诉|显示|背)[^\n|;；]{0,8}你(上面|之前|最开始|最初)收到的|你(上面|之前|最开始|最初)收到的[^\n|;；]{0,10}(是什么|内容|原样|贴|发|复述|背)",
            r"第一句(话)?(开始)?(复述|重复|背)",
            r"(开头|最开始|最初|前面|上面|原始|隐藏)(那|的)?(段|条|些)?(设定|提示|指令|规则|prompt)[^\n|;；]{0,8}(复述|重复|原样|一字不差|逐字|贴出|输出|背|发)",
            r"(复述|重复|原样|一字不差|逐字|贴出|输出|背出)[^\n|;；]{0,8}(你的|你)(开头|最开始|最初|前面)?(那|的)?(段|条)?(设定|提示词|指令|规则|prompt)",
            r"apikey|api_key|llm_api_key|密钥|secretkey|访问令牌|底层模型",
            r"(你的?|给你)(后台|背后|内部)[^\n|;；]{0,6}(规矩|规则|设定|指令|提示)|(后台|背后|内部|开发者)[^\n|;；]{0,4}给你[^\n|;；]{0,4}(设|定|写)",
            r"(规矩|规则|设定|提示词|指令|prompt)[^\n|;；?？]{0,1}[?？]?[^\n|;；]{0,2}(全文|原文|完整版?|一字不差)[^\n|;；]{0,4}(贴|发|给|输出|打印|复述)",
        ],
        ROLES,
    ),
    (
        "injection",
        "疑似提示注入/越狱",
        [
            r"(忽略|无视|忘记|忘掉|丢弃|丢掉|不要理会|别管|跳过|覆盖|抛开|放弃)(掉)?(你)?(之前|此前|先前|以上|上面|上述|前面|所有|全部|一切|原来|原有|系统|医疗)?(的)?(所有|全部|一切|安全)?(的)?" + _INSTR,
            r"(忽略|无视|忘记|忘掉|丢弃|丢掉|不要理会|别管|跳过|覆盖|抛开|放弃)(掉|了)?[^\n|;；]{0,4}(之前|此前|先前|以上|上面|上述|前面|所有|全部|一切|原来|原有|系统|你的)[^\n|;；]{0,8}" + _INSTR,
            r"(ignore|disregard|forget|override|bypass)(all|any)?(of)?(the|your|my)?(previous|prior|above|earlier|system|safety)?" + _INSTR,
            r"</?\s*(system|assistant|sys|im_start|im_end|instructions?)\s*>|<\|im_(start|end)\|>|\[/?(inst|system)\]",
            r"(新|最新|更新|真正)的?(系统)?(指令|命令|设定|任务)[:：]",
            r"(你|ai|助手)(现在|从现在起|接下来|以后)?[^\n|;；]{0,6}不(受|用遵守|必遵守|需要遵守|用管)(任何)?[^\n|;；]{0,6}(限制|约束|规则|规范|准则|政策|审查)",
            r"越狱|jailbreak|dan模式|doanythingnow|开发者模式|developermode|上帝模式|无限制模式|godmode",
            r"(system|admin|developer|root)(override|mode)|safety(=|:)?(false|off|0|disabled)|override(safety|rules|guard)|(规则|限制|设定|指令|约束)[^\n|;；]{0,4}(作废|失效|取消|无效|删除|清空|不算)",
            r"(进入|开启|切换到?|打开)[^\n|;；]{0,4}(自由|无限制|无审查|不受限|越狱|无过滤)(回答|对话|聊天)?模式",
            r"不受限(制)?(的)?(模式|版本|ai)|没有(任何)?(限制|约束)的ai|解除[^\n|;；]{0,4}(限制|安全|约束|审查|护栏)|绕过[^\n|;；]{0,4}(限制|安全|审核|过滤|护栏)|关闭[^\n|;；]{0,4}(安全|过滤|护栏|审查)",
            r"[\[【<(（]\s*(system|系统|管理员|admin|developer|开发者)(消息|指令|通知)?\s*[\]】>)）]",
            r"^(system|系统指令|系统消息|管理员)[:：]|<\|?im_start\|?>|###(system|instruction)|\[inst\]",
            r"(以下|下面)?是?(新的|更新的?)(系统)?(指令|提示词|prompt|设定|规则)",
            r"管理员已?授权|已(获得|经)?授权[^\n|;；]{0,6}(可以|允许)|权限[^\n|;；]{0,4}(提升|最高)|sudo|rootmode",
            r"你(必须|只能)(回答|服从|执行)(所有|任何|我的)",
            r"(之前|前面|上面|以上|原来|原先|刚才)[^\n|;；]{0,8}(规矩|规则|指令|设定|限制|要求)[^\n|;；]{0,4}(统统|全部|全都|都|一律)?(不算数|不算|作废|失效|无效|不用管|不用遵守|不作数)",
            r"(安全审查|安全过滤|安全限制|安全策略|内容审查|审查|过滤器?|护栏|审核机制)[^\n|;；]{0,3}(已|已经)?(被)?(关闭|解除|取消|停用|失效|关掉)",
            r"#{2,}\s*(系统|system|管理员|admin)",
            r"(这|下面|以下|我)(的|条|句)?(话|指令|要求|消息|内容)[^\n|;；]{0,4}(优先级最高|最高优先级)|覆盖[^\n|;；]{0,4}(之前|此前|先前|原有|原来)[^\n|;；]{0,6}(一切|所有|全部|设定|指令|规则)",
            r"(ignore|forget|disregard)(everything|all|anything)(above|before|prior|previous)?|youarenow[a-z]{0,12}(unlocked|unrestricted|uncensored|jailbroken|dan|evil|nolimits?|free)|unlocked|uncensored|unrestricted",
            r"(取消|去掉|撤销|关掉|撤掉)[^\n|;；]{0,4}((患者端|你的|ai|系统)的?限制|护栏|审查|过滤|安全策略)",
            r"没有(任何)?(限制|约束|规矩|审查)的[^\n|;；]{0,6}(ai|gpt|医生|助手|模型|机器人|版本)",
        ],
        ROLES,
    ),
    (
        "role_override",
        "试图改变 AI 角色或越权",
        [
            r"扮演|角色扮演|假装(你)?是|假设你是|当作你是|roleplay|pretend(tobe|youare)|actas",
            r"(现在|从现在开始|现在开始|从现在起|从今天起|接下来|今后)(你|您)(就)?(是|当|充当|作为|变成)",
            r"(你|您)(来)?(充当|当作|变成|化身)(我的)?",
            r"(切换|进入|开启|打开|启用)(到)?(医生|管理员|开发者|专家|无限制|调试|debug|admin|医师)(端|模式|身份|权限)",
            r"(以|用)(医生|管理员|开发者|医师)(的)?(身份|权限|视角)(给我|帮我|回答|告诉)",
            r"(以|用|作为)[^\n|;；]{0,6}(医生|医师|药剂师|药师|主任|专家|管理员|开发者|大夫)(的)?(身份|角色|口吻|立场|权限)",
            r"(不要|别)(再)?(说|提)(你是)?(ai|人工智能)|别(再)?(加|带)免责",
            r"(你|您)(现在|从现在起|以后)(就)?是[^\n|;；]{0,8}(医生|医师|药剂师|专家|gpt)",
            r"(就)?当(自己|你自己|你)是[^\n|;；]{0,6}(医生|医师|药剂师|处方系统|系统|专家|大夫)",
            r"以[^\n|;；]{0,6}(的)?身份(命令|要求|授权|通知)你",
            r"(别|不要|不用)[^\n|;；]{0,4}(免责声明|免责|声明)",
        ],
        ROLES,
    ),
    (
        "role_override",
        "患者端冒充医生/管理员",
        [r"我(是|就是)(一名|一个|一位)?(医生|大夫|医师|药师|管理员|开发者|主任)(?!的)"],
        ("patient",),
    ),
    (
        "prescription_request",
        "患者端请求处方或具体剂量",
        [
            r"(开|写)(一|个|张|份|点)?(张|个|份)?(处方|药方|方子)|(开|写)[^\n|;；]{0,10}(处方|药方|方子)|处方药[^\n|;；]{0,4}(给我|开)",
            r"(给我|帮我|替我|能不能|可不可以|能否|麻烦)(直接)?开[^\n|;；]{0,8}(药|抗生素|头孢|阿莫西林|激素|安眠|止痛|消炎|抗病毒|胰岛素|降压|降糖)",
            r"(吃|服|用|喝|喂|给|打|注射|涂|抹|喷|滴|含)(多少|几|多大)(片|粒|颗|毫克|mg|克|g|ml|毫升|袋|支|个单位|单位|滴|剂量|量)",
            r"(一次|每次|一天|每天|每日|一日|一顿)[^\n|;；]{0,2}(几|多少)(片|粒|颗|毫克|mg|次|袋|支|ml|毫升|克|g)",
            r"(剂量|用量|用法用量)(是|为|多少|怎么|如何|应该)|多少(毫克|mg|ml|毫升)|最大剂量|多大剂量|几毫克",
            r"(告诉我|给我|帮我|直接)(说|讲|列|报|定)?[^\n|;；]{0,10}(用量|剂量)",
            r"(该|应该|能|可以|要)?吃(点|些)?什么药|推荐(个|点|一些|一种)?(药|药物)|用什么药(好|最好|能好|治)|什么药(最)?(管用|有效|好使)",
            r"(开|吃|用)(点|些)?(啥|什么|哪种|哪个)药|(整|弄|搞|来)(点|些)(啥|什么)?[^\n|;；]{0,3}(药|抗生素)",
            r"(吃|服|用|喂)(多少|几片|多大量)[^\n|;；]{0,6}(说|告诉|讲|写|列)",
            r"(打印|出具|开具|生成)[^\n|;；]{0,2}(一|张|份)[^\n|;；]{0,8}处方|(打印|出具|开具|生成)[^\n|;；]{0,8}处方[^\n|;；]{0,2}给我",
        ],
        ("patient",),
    ),
]

_OFF_TOPIC = re.compile(
    r"(写|作|编)(一首|一篇|一段|一个|个|首|篇|段)?[^\n|;；]{0,8}(诗|诗歌|作文|小说|代码|程序|脚本|歌词|情书|周报|简历|文案)"
    r"|python|javascript|java|爬虫|股票|a股|基金|彩票|比特币|加密货币|天气预报|今天天气|天气怎么样"
    r"|翻译|translate|讲个?笑话|做(数学|作业)|数学题|推荐(几部|一部|个|些)?(电影|电视剧|小说|游戏|餐厅)"
    r"|足球|nba|比分|星座|算命|塔罗"
    r"|(球赛|比赛|世界杯|欧冠|联赛|选举)[^\n|;；]{0,6}(谁|哪(个|队|边))(会|能)?(赢|夺冠|胜)"
)
# coding / scraping requests are off-topic even when they mention a hospital
_OFF_TOPIC_STRONG = re.compile(r"(帮我|给我|替我|你)(写|编|做)[^\n|;；]{0,6}(代码|程序|脚本|爬虫)|爬虫|写(个|一段)?(python|java|sql)")
_MEDICAL_HINT = re.compile(
    r"痛|疼|病|症|药|医|诊|检查|报告|化验|血|发烧|发热|咳|吐|泻|晕|痒|肿|挂号|科室|体检|治疗|手术|怀孕|孕|月经"
    r"|血压|血糖|胃|肠|肝|肾|心|肺|皮肤|过敏|感冒|失眠|伤|骨|尿|便|呼吸|乏力|不舒服"
)

_REFUSE: list[tuple[str, str, list[Pattern[str]], tuple[str, ...]]] = [
    (cat, reason, [re.compile(p) for p in pats], roles) for cat, reason, pats, roles in _REFUSE_SPEC
]


# 「说明书/用法看不懂」= asking how to read a label, not asking the AI to prescribe
_COMPREHEND = re.compile(r"看不懂|看不明白|看不太懂|没看懂|读不懂|不太懂|什么意思|啥意思|怎么理解|是指|指的是|怎么看|怎么读")
_STRONG_RX = re.compile(
    r"(给我|帮我|替我|你|直接)[^\n|;；]{0,2}(开|写)[^\n|;；]{0,6}(药|处方|方子)|(开|写)(个|张|份|一张|一份)(处方|方子|药)|给我定|帮我定|直接告诉我"
    r"|(我|孩子|宝宝|他|她|老人|我妈|我爸|老公|老婆)[^\n|;；]{0,4}(该|要|能|可以)?(吃|用|服|喂)[^\n|;；]{0,4}(几|多少|多大)"
)


def _find_refuse(norm: str, flat: str, role: str) -> Optional[tuple[str, str, str]]:
    for cat, reason, pats, roles in _REFUSE:
        if role not in roles:
            continue
        if cat == "prescription_request" and _COMPREHEND.search(norm) and not _STRONG_RX.search(norm):
            continue
        for p in pats:
            m = p.search(norm) or p.search(flat)
            if m:
                return cat, reason, m.group(0)
    m = _OFF_TOPIC_STRONG.search(norm)
    if m:
        return "off_topic", "与医疗健康无关的请求", m.group(0)
    m = _OFF_TOPIC.search(norm)
    if m and not _MEDICAL_HINT.search(norm):
        return "off_topic", "与医疗健康无关的请求", m.group(0)
    return None


def _result(action, reason, category, advice, masked, caution=None, caution_category=None) -> dict:
    return {
        "action": action,
        "reason": reason,
        "category": category,
        "advice": advice,
        "masked_text": masked,
        "caution": caution,
        "caution_category": caution_category,
    }


def _rf_advice(cat: str) -> str:
    return SUICIDE_ADVICE if cat == "redflag_suicide" else REDFLAG_ADVICE


def check_input(text: str, role: str = "patient") -> dict:
    """Classify user input before it reaches the LLM.

    Returns {action: allow|redflag|refuse, reason, category, advice, masked_text,
             caution, caution_category}.
    Priority: redflag > refuse > allow. `caution`/`caution_category` are always present and are
    None unless role == "patient" and action == "allow" and a boundary-band rule matched.
    Callers should separate record fields with "\n"; no rule matches across "\n", "|", ";", "；".
    When rules say allow and the optional LLM judge is enabled, it may upgrade the result
    (reason prefixed "[llm] "); it never downgrades a rule redflag/refuse.
    """
    role = role if role in ROLES else "patient"
    raw = text if isinstance(text, str) else ("" if text is None else str(text))
    masked = mask_pii(raw)
    norm = compact(raw)
    flat = bare(raw)

    rf, seizure_hist = _find_redflag(norm)
    if rf:
        cat, label, hit = rf
        return _result("redflag", f"{label}（命中「{hit}」），请立即就医", cat, _rf_advice(cat), masked)

    rq = _find_refuse(norm, flat, role)
    if rq:
        cat, reason, hit = rq
        return _result("refuse", f"{reason}（命中「{hit}」）", cat, None, masked)

    if norm.strip():
        verdict = llm_judge.judge(raw, role)
        if verdict and verdict["action"] == "redflag":
            cat = verdict["category"]
            return _result("redflag", "[llm] " + verdict["reason"], cat, _rf_advice(cat), masked)
        if verdict and verdict["action"] == "refuse":
            return _result("refuse", "[llm] " + verdict["reason"], verdict["category"], None, masked)

    caution = caution_cat = None
    reason = "未命中护栏规则"
    if role == "patient":
        cz = _find_caution(norm, seizure_hist)
        if cz:
            caution_cat, label = cz
            caution = CAUTION_MOOD_ADVICE if caution_cat == "caution_mood" else CAUTION_ADVICE
            reason = f"未达急症标准，但有{label}描述，需留意"
    return _result("allow", reason, "none", None, masked, caution, caution_cat)
