import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from contextlib import contextmanager, nullcontext
from uuid import uuid4
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from research_timeline import AI, ResearchBudgetReached, evidence, research


@contextmanager
def research_directory():
    directory = Path(__file__).resolve().parents[1] / ".cache" / ("test-research-" + uuid4().hex)
    directory.mkdir(parents=True)
    try:
        yield str(directory)
    finally:
        cache = directory / "research"
        if cache.exists():
            for item in cache.iterdir():
                item.unlink()
            cache.rmdir()
        directory.rmdir()


class ResearchTests(unittest.TestCase):
    def test_copilot_uses_stdin_disables_tools_caches_and_limits_calls(self):
        with research_directory() as directory, patch("research_timeline.tempfile.TemporaryDirectory", return_value=nullcontext(directory)), patch.dict("os.environ", {"TIMELINE_AI_PROVIDER": "copilot", "GITHUB_TOKEN": "test-token", "TIMELINE_AI_MAX_CALLS": "1"}), patch("research_timeline.shutil.which", return_value="copilot"), patch("research_timeline.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout='```json\n{"features": []}\n```', stderr="")) as command:
            ai = AI(directory)
            self.assertEqual(ai.ask({"document": "public announcement"}), {"features": []})
            self.assertEqual(ai.ask({"document": "public announcement"}), {"features": []})
            self.assertEqual(command.call_count, 1)
            args, kwargs = command.call_args
            self.assertIn("--disable-builtin-mcps", args[0])
            self.assertIn("--deny-tool", args[0])
            self.assertIn("public announcement", kwargs["input"])
            with self.assertRaises(ResearchBudgetReached):
                ai.ask({"document": "another announcement"})

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
        second, _, _ = research(result, archive, None, model, state, "2026-10-26")
        self.assertEqual(second, result)
        self.assertEqual(model.calls, 2, "cached research must not call the provider again")
        result["events"][0]["tw"] = {"date": None, "status": "pending", "sources": []}
        result["events"][0]["note"] = "第2部獨立日期尚未確認"
        state[archive["kr"][0]["url"]].pop("twFingerprint", None)
        held, candidates, _ = research(result, archive, None, model, state, "2026-10-26")
        self.assertIsNone(held["events"][0]["tw"]["date"], "manual holds must survive cached AI results")
        self.assertEqual(len(candidates), 1)

    def test_date_and_feature_must_be_in_verbatim_evidence(self):
        body = "2026年10月15日更新：新增環境設定匯入與匯出功能。"
        self.assertTrue(evidence({"text": body}, body, "2026-10-15"))
        self.assertFalse(evidence({"text": body}, body, "2026-10-16"))
        self.assertFalse(evidence({"text": body}, "2026年10月15日新增新的神祕副本", "2026-10-15"))
        self.assertFalse(evidence({"text": body}, "新增環境設定匯入與匯出功能。", "2026-10-15"))

    def test_budget_exhaustion_keeps_pending_features_and_resumes(self):
        quote = "2026年10月15日更新：新增環境設定匯入與匯出功能。"
        url = "https://mabinogi.nexon.com/page/news/notice_view.asp?id=1"
        archive = {"kr": [{"url": url, "text": quote}], "tw": []}

        class LimitedModel:
            def ask(self, payload):
                if "knownFeatures" in payload:
                    return {"features": [{"title": "環境設定匯入／匯出", "category": "minor", "releaseDate": "2026-10-15", "quote": quote}]}
                raise ResearchBudgetReached()

        partial, _, state = research({"events": []}, archive, None, LimitedModel(), {}, "2026-10-26")
        self.assertEqual(len(partial["events"]), 1)
        self.assertEqual(partial["events"][0]["tw"]["status"], "pending")
        self.assertNotIn("twFingerprint", state[url])

        class ResumedModel:
            def ask(self, payload):
                self.assert_match_only = "knownFeatures" not in payload
                return {"status": "pending"}

        model = ResumedModel()
        resumed, _, state = research(partial, archive, None, model, state, "2026-10-26")
        self.assertTrue(model.assert_match_only)
        self.assertEqual(resumed, partial)
        self.assertIn("twFingerprint", state[url])
