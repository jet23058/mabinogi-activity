import copy
import importlib.util
from pathlib import Path
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

SPEC = importlib.util.spec_from_file_location("timeline", Path(__file__).resolve().parents[1] / "scripts/update_timeline.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class TimelineTests(unittest.TestCase):
    def test_tw_campaign_without_body_keeps_index_evidence(self):
        class Client:
            def get(self, url, payload=None, **kwargs):
                import json
                if payload is not None:
                    return json.dumps({"code": 1, "data": {"totalPage": 1, "bulletins": [
                        {"bullentinId": 83717, "startDate": "2026-10-01", "title": "G28 campaign"}
                    ]}})
                return json.dumps({"code": 1, "data": {"myDataSet": {"table": []}}})

        rows = m.crawl_tw(Client(), [], "2026-10-26")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["detailStatus"], "unavailable")
        self.assertEqual(rows[0]["text"], "")
        previous = {**rows[0], "text": "previous evidence", "detailStatus": "available"}
        self.assertEqual(m.crawl_tw(Client(), [previous], "2026-10-26")[0], previous)

    def test_kr_list_date_is_scoped_to_row_and_deduplicated(self):
        page = '''<ul><li><a href="notice_view.asp?id=1">G28 更新</a><span>2026.01.13</span></li>
        <li><a href="notice_view.asp?id=2">其他更新</a><span>2026.02.10</span></li>
        <li><a href="notice_view.asp?id=1">G28 更新</a><span>2026.01.13</span></li></ul>'''
        rows = m.kr_rows(page)
        self.assertEqual(len(rows), 2)
        self.assertEqual([r["publishedDate"] for r in rows], ["2026-01-13", "2026-02-10"])
        self.assertTrue(rows[0]["url"].startswith(m.KR))

    def test_patch_date_is_not_publication_date(self):
        title = "[공지] (수정) 7/9(목) 정식 서버 패치 작업 변경점 안내"
        body = "2026.07.07 18:00 2026년 7 월 9 일(목) 패치로 변경되는 항목"
        self.assertEqual(m.release_date(title, body, "2026-07-07"), "2026-07-09")
        self.assertEqual(m.release_date("1/2(금) 정식 서버 패치 작업 변경점 안내", "", "2025-12-30"), "2026-01-02")

    def test_test_and_showcase_are_never_releases(self):
        for title in ("[테스트] RE:ACTION 1차 업데이트", "[개발중] NEW LIFE", "RE:ACTION 사전 등록", "2026 쇼케이스"):
            self.assertIsNone(m.release_date(title, "2026년 7월 9일 패치", "2026-07-07"))
            self.assertFalse(m.relevant(title))

    def test_four_categories(self):
        self.assertEqual(m.classify("G28 2부 업데이트 안내"), ("story", "g28"))
        self.assertEqual(m.classify("RE:ACTION 2차 업데이트 안내"), ("major", "reaction"))
        self.assertEqual(m.classify("마비노기 X 고깔모자의 아틀리에 이벤트")[0], "collaboration")
        self.assertEqual(m.classify("에코스톤 강화 경험 개편")[0], "minor")

    def test_date_validation_and_source_allowlist(self):
        self.assertIsNone(m.iso("2026-02-30"))
        self.assertFalse(m.official("https://mabinogi.nexon.com.evil.test/a", "kr"))
        self.assertFalse(m.official("https://forum.gamer.com.tw/test", "tw"))

    def test_grouping_sort_and_tw_candidates_do_not_confirm_release(self):
        catalog = m.read(m.ROOT / "timeline/curated.json", {})
        tw = [{"title": "6月份改善事項 G28", "text": "G28 暮色的殘虛", "url": m.TW + "/News?bid=123", "publishedDate": "2026-06-18"}]
        result = m.build(catalog, [], tw, "2026-10-26")
        dates = [e["kr"]["date"] for e in result["events"]]
        self.assertEqual(dates, sorted(dates))
        self.assertEqual(len(next(g for g in result["groups"] if g["id"] == "g28")["eventIds"]), 2)
        event = next(e for e in result["events"] if e["id"] == "g28-part1")
        self.assertTrue(event["tw"]["candidateSources"])
        self.assertEqual(event["tw"]["status"], "released")
        self.assertEqual(event["tw"]["date"], "2026-06-18")
        broken = copy.deepcopy(event)
        broken["tw"] = {"date": "2026-06-18", "status": "released", "sources": []}
        with self.assertRaises(AssertionError):
            m.validate_event(broken)

    def test_patch_notices_never_become_timeline_items_and_new_features_wait_for_review(self):
        row = {"title": "9/10(목) 정식 서버 패치 작업 변경점 안내", "url": m.KR + "/page/news/notice_view.asp?id=999", "publishedDate": "2026-09-08", "releaseDate": "2026-09-10"}
        feature = {**row, "title": "全新地下城功能更新", "url": m.KR + "/page/news/notice_view.asp?id=1000"}
        result = m.build({"events": []}, [row, feature], [], "2026-10-26")
        self.assertEqual(result["events"], [])
        self.assertEqual([item["url"] for item in result["reviewQueue"]], [feature["url"]])
        self.assertEqual(result["selectionPolicy"]["mode"], "curated-features")

    def test_reference_features_keep_ambiguous_and_partial_tw_matches(self):
        catalog = m.read(m.ROOT / "timeline/curated.json", {})
        result = m.build(catalog, [], [], "2026-10-26")
        self.assertEqual(len(result["events"]), 29)
        events = {event["id"]: event for event in result["events"]}
        self.assertIsNone(events["g27-part2"]["tw"]["date"])
        self.assertEqual(events["g27-part2"]["tw"]["status"], "pending")
        self.assertTrue(events["g27-part2"]["tw"]["sources"])
        self.assertEqual(events["combat-balance-202606"]["tw"]["matchStatus"], "partial")
        self.assertEqual(len(events["combat-balance-202606"]["tw"]["sources"]), 2)
        for identifier in ("blast-lancer", "g27-part2", "bri-leith-launch"):
            self.assertIn("id=4892509", events[identifier]["kr"]["sources"][0]["url"])
        self.assertFalse(any(m.routine_patch_notice(event["title"]) for event in result["events"]))


if __name__ == "__main__":
    unittest.main()
