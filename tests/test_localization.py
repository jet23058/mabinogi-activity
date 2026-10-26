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
        self.assertEqual(title, "RE:ACTION（再次行動，暫譯） 第一階段")

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
        with self.assertRaisesRegex(ValueError, "protected name"):
            m.Localizer(self.glossary, translator=lambda _: "錯誤譯名").title("브리 레흐 희망의 빛")
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            m.Localizer(self.glossary, translator=lambda text: text).title("미지의 이름")
        with self.assertRaisesRegex(ValueError, "Missing offline"):
            m.Localizer(self.glossary, offline=True).title("미지의 이름")

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
