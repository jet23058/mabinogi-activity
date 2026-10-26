"""Traditional Chinese titles: reviewed glossary, reusable rules, then cached MT.

Raw Korean evidence is always kept separately. A translation failure aborts the
build before generated files are replaced, rather than publishing raw headlines.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen

HANGUL = re.compile(r"[\u1100-\u11ff\u3130-\u318f\uac00-\ud7af]")
RULES = [
    (r"정식\s*서버\s*(?:패치|업데이트)\s*작업\s*변경점\s*안내", "正式伺服器更新內容公告"),
    (r"새로운\s*소식\s*업데이트\s*안내", "最新消息公告"),
    (r"콜라보\s*이벤트\s*안내", "合作活動公告"),
    (r"개선\s*업데이트", "改善更新"),
    (r"업데이트\s*안내", "更新公告"),
    (r"입장\s*방식\s*변경", "入場方式調整"),
    (r"강화\s*경험\s*개편", "強化體驗改版"),
    (r"내용\s*추가", "內容追加"),
    (r"적용됨", "已套用"),
    (r"수정", "修正"),
    (r"숏\s*뉴스", "短訊"),
    (r"신규", "全新"),
    (r"던전", "地下城"),
    (r"업데이트", "更新"),
    (r"이벤트", "活動"),
    (r"안내", "公告"),
    (r"1차", "第一階段"), (r"2차", "第二階段"), (r"3차", "第三階段"),
    (r"(\d+)년", r"\1年"), (r"(\d+)월", r"\1月"), (r"(\d+)일", r"\1日"),
]


def translate_public_title(text):
    # Only public announcement headlines are sent; no private user data or keys.
    # This is Google's public web translation endpoint, not the paid Cloud API.
    query = urlencode({"client": "gtx", "sl": "ko", "tl": "zh-TW", "dt": "t", "q": text})
    request = Request("https://translate.googleapis.com/translate_a/single?" + query,
                      headers={"User-Agent": "MabinogiActivityTimeline/1.0"})
    with urlopen(request, timeout=25) as response:
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, list) or not isinstance(payload[0], list):
        raise ValueError("Unexpected translation response")
    return "".join(part[0] for part in payload[0] if isinstance(part, list) and part and isinstance(part[0], str))


class Localizer:
    def __init__(self, glossary, cache=None, *, offline=False, translator=translate_public_title):
        self.glossary = glossary
        self.cache = copy.deepcopy(cache or {})
        self.offline = offline
        self.translator = translator
        self.memo = {}

    def machine(self, text):
        key = hashlib.sha256(f"{self.glossary.get('revision', 1)}:{text}".encode()).hexdigest()
        translated = self.cache.get(key, {}).get("title")
        if not translated:
            if self.offline:
                raise ValueError(f"Missing offline zh-TW translation: {text}")
            translated = self.translator(text)
        if not isinstance(translated, str) or not translated.strip() or HANGUL.search(translated) or not re.search(r"[\u3400-\u9fff]", translated):
            raise ValueError(f"Incomplete zh-TW translation: {text}")
        self.cache[key] = {"original": text, "title": translated.strip()}
        return translated.strip()

    def title(self, original):
        if original in self.memo:
            return self.memo[original]
        text = self.glossary.get("titleOverrides", {}).get(original, original)
        terms = sorted(self.glossary.get("terms", []), key=lambda term: len(term["original"]), reverse=True)
        protected = {}
        provisional = False
        for term in terms:
            # Hide whole reviewed names from both phrase rules and machine translation.
            token = f"MABITERM{len(protected):04d}TOKEN"
            pattern = re.compile(re.escape(term["original"]), re.I)
            if pattern.search(text):
                text = pattern.sub(token, text)
                protected[token] = term["display"]
                provisional |= not term.get("official", False)
        days = dict(zip("월화수목금토일", "一二三四五六日"))
        text = re.sub(r"\(([월화수목금토일])\)", lambda match: f"（{days[match[1]]}）", text)
        for pattern, replacement in RULES:
            text = re.sub(pattern, replacement, text)
        method = "glossary" if text != original else "original"
        # New proper names are often quoted in Korean notices. Keep that name
        # verbatim, and translate only its explanation inside Chinese parentheses.
        def quoted_name(match):
            nonlocal provisional, method
            name = match[1]
            if not HANGUL.search(name):
                return match[0]
            translated = self.machine(name)
            token = f"MABITERM{len(protected):04d}TOKEN"
            protected[token] = f"{name}（{translated}，暫譯）"
            provisional, method = True, "machine"
            return token
        text = re.sub(r"['\"‘“「]([^'\"’”」]+)['\"’”」]", quoted_name, text)
        if HANGUL.search(text):
            # Hash both the input and glossary revision; revised official names invalidate MT.
            translated = self.machine(text)
            if any(token not in translated for token in protected):
                raise ValueError(f"Translation changed a protected name: {original}")
            text, method = translated.strip(), "machine"
        for token, display in protected.items():
            text = text.replace(token, display)
        text = re.sub(r"\s+", " ", text).strip()
        self.memo[original] = (text, method, provisional)
        return self.memo[original]

    def apply(self, data):
        output = copy.deepcopy(data)
        for event in output["events"]:
            original = event["title"]
            event["title"], method, provisional = self.title(original)
            event["originalTitle"] = original
            event["titleLocale"] = "zh-TW"
            event["titleTranslation"] = {"method": method, "provisionalTerms": provisional}
            for region in ("kr", "tw"):
                for source in event[region].get("sources", []):
                    if source.get("title"):
                        source["originalTitle"] = source["title"]
                        source["title"] = self.title(source["title"])[0]
        for group in output["groups"]:
            group["originalTitle"] = group["title"]
            group["title"] = self.glossary.get("groupTitles", {}).get(group["id"], self.title(group["title"])[0])
        for row in output.get("reviewQueue", []):
            row["originalTitle"] = row["title"]
            row["title"] = self.title(row["title"])[0]
        output["localization"] = {"locale": "zh-TW", "revision": self.glossary.get("revision", 1),
                                  "policy": "台版官方名稱優先；未定名專有名詞保留原文並附繁中暫譯；原文獨立保存。"}
        return output
