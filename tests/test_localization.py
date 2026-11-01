import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("localization", ROOT / "scripts/timeline_localization.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class LocalizationTests(unittest.TestCase):
    def setUp(self):
        self.glossary = json.loads((ROOT / "timeline/localization.json").read_text(encoding="utf-8"))

    def test_official_names_override_old_translations(self):
        localizer = m.Localizer(self.glossary, offline=True)
        self.assertEqual(localizer.title("神聖盾衛技能改善")[0], "聖盾守衛技能改善")
        self.assertEqual(localizer.title("[적용됨] 포비든 알케미스트 개선 업데이트")[0], "[已套用] 禁忌鍊金士 改善更新")
        self.assertEqual(localizer.title("[적용됨] 브리 레흐 던전 업데이트")[0], "[已套用] 布里萊赫 地下城 更新")

    def test_future_regular_notices_translate_without_network(self):
        title = m.Localizer(self.glossary, offline=True).title("(수정2) 11/5(목) 정식 서버 패치 작업 변경점 안내")[0]
        self.assertEqual(title, "(修正2) 11/5（四） 正式伺服器更新內容公告")

    def test_proper_names_keep_original_and_provisional_translation(self):
        title, _, provisional = m.Localizer(self.glossary, offline=True).title("신규 던전 '탈라 가흐' 업데이트 안내")
        self.assertIn("탈라 가흐（塔拉加赫，暫譯）", title)
        self.assertIn("全新 地下城", title)
        self.assertTrue(provisional)
        title = m.Localizer(self.glossary, offline=True).title("RE:ACTION 第一階段")[0]
        self.assertEqual(title, "RE:ACTION 第一階段")
        for name in ("NEW RISE", "NEW LIFE", "RE:ACTION"):
            title, _, provisional = m.Localizer(self.glossary, offline=True).title(name)
            self.assertEqual(title, name)
            self.assertFalse(provisional)

    def test_new_quoted_name_is_translated_once_and_cached_for_offline(self):
        calls = []
        def translator(value):
            calls.append(value)
            return "新星之門"
        localizer = m.Localizer(self.glossary, translator=translator)
        text = "신규 던전 '새별의 문' 업데이트 안내"
        title, method, provisional = localizer.title(text)
        self.assertIn("새별의 문（新星之門，暫譯）", title)
        self.assertEqual(method, "machine")
        self.assertTrue(provisional)
        self.assertEqual(localizer.title(text)[0], title)
        self.assertEqual(len(calls), 1)
        self.assertEqual(m.Localizer(self.glossary, localizer.cache, offline=True).title(text)[0], title)

    def test_bad_translation_cannot_replace_reviewed_names(self):
        calls = []
        def translator(text):
            calls.append(text)
            return "錯誤譯名" if "MABITERM" in text else "希望之光"
        title = m.Localizer(self.glossary, translator=translator).title("브리 레흐 희망의 빛")[0]
        self.assertEqual(title, "布里萊赫 希望之光")
        self.assertEqual(calls[-1], "희망의 빛")
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            m.Localizer(self.glossary, translator=lambda text: text).title("미지의 이름")
        with self.assertRaisesRegex(ValueError, "Missing offline"):
            m.Localizer(self.glossary, offline=True).title("미지의 이름")

    def test_collaboration_review_title_recovers_changed_tokens_and_caches(self):
        calls = []
        def translator(text):
            calls.append(text)
            return "被改動的專名 全時活動" if "MABITERM" in text else "全時"
        original = "[마비노기 X 고깔모자의 아틀리에] 온타임 이벤트 (11/5~11/12)"
        raw = {"events": [], "groups": [], "reviewQueue": [{"title": original}]}
        localizer = m.Localizer(self.glossary, translator=translator)
        row = localizer.apply(raw)["reviewQueue"][0]
        self.assertEqual(row["title"], "[瑪奇 X 고깔모자의 아틀리에（魔法帽的工作室）] 全時 活動 (11/5~11/12)")
        self.assertEqual(row["originalTitle"], original)
        self.assertEqual(raw["reviewQueue"][0]["title"], original)
        self.assertNotIn("MABITERM", calls[-1])
        self.assertEqual(calls[-1], "온타임")
        self.assertEqual(m.Localizer(self.glossary, localizer.cache, offline=True).apply(raw), localizer.apply(raw))

    def test_duplicate_protected_token_cannot_duplicate_a_reviewed_name(self):
        def translator(text):
            return "MABITERM0000TOKEN 希望 MABITERM0000TOKEN" if "MABITERM" in text else "希望之光"
        title = m.Localizer(self.glossary, translator=translator).title("브리 레흐 희망의 빛")[0]
        self.assertEqual(title, "布里萊赫 希望之光")

    def test_protected_name_fallback_still_rejects_incomplete_translation(self):
        def translator(text):
            return "被改動的專名" if "MABITERM" in text else "희망의 빛"
        localizer = m.Localizer(self.glossary, translator=translator)
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            localizer.title("브리 레흐 희망의 빛")
        self.assertFalse(localizer.cache, "failed translations must not enter the cache")

    def test_valid_legacy_cache_needs_no_fragment_translations(self):
        text = "MABITERM0000TOKEN 희망의 빛"
        key = m.hashlib.sha256(f"{self.glossary['revision']}:{text}".encode()).hexdigest()
        cache = {key: {"original": text, "title": "MABITERM0000TOKEN 希望之光"}}
        title = m.Localizer(self.glossary, cache, offline=True).title("브리 레흐 희망의 빛")[0]
        self.assertEqual(title, "布里萊赫 希望之光")

    def test_reordered_or_repeated_names_keep_original_order_and_count(self):
        for text in ("브리 레흐 희망의 빛 에코스톤", "브리 레흐 희망의 빛 브리 레흐"):
            with self.subTest(text=text):
                def translator(value):
                    return "MABITERM0001TOKEN 希望 MABITERM0000TOKEN" if "MABITERM" in value else "希望之光"
                title = m.Localizer(self.glossary, translator=translator).title(text)[0]
                suffix = "回音石" if text.endswith("에코스톤") else "布里萊赫"
                self.assertEqual(title, f"布里萊赫 希望之光 {suffix}")

    def test_published_titles_have_chinese_and_preserve_original_sources(self):
        published = json.loads((ROOT / "update-timeline.json").read_text(encoding="utf-8"))
        cache_path = ROOT / "timeline/translations.json"
        cache = json.loads(cache_path.read_text(encoding="utf-8")) if cache_path.exists() else {}
        localizer = m.Localizer(self.glossary, cache, offline=True)
        # Raw archives may include intentionally excluded notices; only published
        # features and review candidates require localized display titles.
        for row in published["events"] + published.get("reviewQueue", []):
            with self.subTest(title=row["title"]):
                self.assertRegex(row["title"], r"[\u3400-\u9fff]")
        raw = {"events": [{"title": "神聖盾衛技能改善", "kr": {"sources": [{"title": "[적용됨] 세이크리드 가드 개선 업데이트"}]}, "tw": {"sources": []}}], "groups": [], "reviewQueue": []}
        localized = localizer.apply(raw)
        self.assertEqual(localized["events"][0]["title"], "聖盾守衛技能改善")
        self.assertEqual(localized["events"][0]["originalTitle"], "神聖盾衛技能改善")
        self.assertEqual(raw["events"][0]["title"], "神聖盾衛技能改善", "localization must not mutate evidence")
        self.assertIn("originalTitle", localized["events"][0]["kr"]["sources"][0])


if __name__ == "__main__":
    unittest.main()
