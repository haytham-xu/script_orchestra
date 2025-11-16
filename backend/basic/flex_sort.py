from typing import List
from natsort import natsorted, natsort_keygen, ns
import re

# 识别的中文数字（简体+常见繁体），支持 1~20
_SIMPLIFY_MAP = {
    "零": "零", "〇": "零",
    "一": "一", "二": "二", "三": "三", "四": "四", "五": "五",
    "六": "六", "七": "七", "八": "八", "九": "九",
    "十": "十", "拾": "十",
    "壹": "一", "贰": "二", "叁": "三", "肆": "四", "伍": "五",
    "陆": "六", "柒": "七", "捌": "八", "玖": "九"
}

_CN_DIGITS = {"零":0,"一":1,"二":2,"三":3,"四":4,"五":5,"六":6,"七":7,"八":8,"九":9}
# 匹配可能的尾部中文数字片段
_CN_TAIL_REGEX = re.compile(r'([零〇一二三四五六七八九十拾壹贰叁肆伍陆柒捌玖]{1,4})$')

_nk = natsort_keygen(alg=ns.INT | ns.IGNORECASE)

def _normalize_cn(s: str) -> str:
    return "".join(_SIMPLIFY_MAP.get(ch, ch) for ch in s)

def _parse_cn_1_to_20(token: str):
    """
    仅解析 1~20：一..九, 十, 十一..十九, 二十
    返回 int 或 None
    """
    if not token:
        return None
    t = _normalize_cn(token)
    # 单字符 1~9
    if t in _CN_DIGITS and _CN_DIGITS[t] != 0:
        return _CN_DIGITS[t]
    # 十
    if t == "十":
        return 10
    # 十一..十九
    if t.startswith("十") and len(t) == 2 and t[1] in _CN_DIGITS and _CN_DIGITS[t[1]] != 0:
        return 10 + _CN_DIGITS[t[1]]
    # 二十
    if t == "二十":
        return 20
    return None

def _has_cn_number(items: List[str]) -> bool:
    return any(_CN_TAIL_REGEX.search(x) and _parse_cn_1_to_20(_CN_TAIL_REGEX.search(x).group(1)) is not None
               for x in items)

def _hybrid_key(name: str):
    """
    key 结构：
    (priority, chinese_number_or_large, natsort_key)
    priority = 0 表示识别到可解析的中文数字，1 表示普通
    """
    m = _CN_TAIL_REGEX.search(name)
    if m:
        num = _parse_cn_1_to_20(m.group(1))
        if num is not None:
            return (0, num, _nk(name))
    return (1, float('inf'), _nk(name))

def flex_natsort(items: List[str]) -> List[str]:
    """
    如果存在中文数字(含常见繁体/大写形式) => 按中文数字 + 自然排序综合。
    否则 => 直接 natsorted。
    """
    if not items:
        return []
    if _has_cn_number(items):
        return sorted(items, key=_hybrid_key)
    return natsorted(items, alg=ns.INT | ns.IGNORECASE)
