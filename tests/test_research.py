import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research_timeline import evidence, research


class ResearchTests(unittest.TestCase):
    def test_body_extraction_and_tw_monthly_matching(self):
        kr = "2026年5月14日正式更新：新增環境設定匯入與匯出功能。"
        tw = "2026年10月15日更新：新增環境設定匯入與匯出功能。"
        class Model:
            calls = 0
            def ask(self, payload):
                self.calls += 1
                if "knownFeatures" in payload:
                    self.assert_body = payload["document"]["text"]
                    return {"features": [{"title": "環境設定匯入／匯出", "category": "minor", "releaseDate": "2026-05-14", "quote": kr, "twSearchTerms": ["環境設定"]}]}
                return {"status": "released", "date": "2026-10-15", "url": "https://mabinogi.beanfun.com/News?bid=1", "quote": tw, "matchStatus": "exact"}
        model = Model()
        archive = {"kr": [{"url": "https://mabinogi.nexon.com/page/news/notice_view.asp?id=1", "title": "例行維護", "text": kr}], "tw": [{"url": "https://mabinogi.beanfun.com/News?bid=1", "text": tw}]}
        result, pending, state = research({"events": []}, archive, None, model, {}, "2026-10-26")
        self.assertEqual(result["events"][0]["title"], "環境設定匯入／匯出")
        self.assertEqual(result["events"][0]["tw"]["date"], "2026-10-15")
        self.assertEqual(model.assert_body, kr)
        self.assertEqual(pending, [])
        self.assertEqual(model.calls, 2)
        second, _, _ = research({"events": []}, archive, None, model, state, "2026-10-26")
        self.assertEqual(second, result)
        self.assertEqual(model.calls, 2, "cached research must not call the provider again")
        result["events"][0]["tw"] = {"date": None, "status": "pending", "sources": []}
        result["events"][0]["note"] = "第2部獨立日期尚未確認"
        held, candidates, _ = research(result, archive, None, model, state, "2026-10-26")
        self.assertIsNone(held["events"][0]["tw"]["date"], "manual holds must survive cached AI results")
        self.assertEqual(len(candidates), 1)

    def test_date_and_feature_must_be_in_verbatim_evidence(self):
        body = "2026年10月15日更新：新增環境設定匯入與匯出功能。"
        self.assertTrue(evidence({"text": body}, body, "2026-10-15"))
        self.assertFalse(evidence({"text": body}, body, "2026-10-16"))
        self.assertFalse(evidence({"text": body}, "2026年10月15日新增新的神祕副本", "2026-10-15"))
        self.assertFalse(evidence({"text": body}, "新增環境設定匯入與匯出功能。", "2026-10-15"))
