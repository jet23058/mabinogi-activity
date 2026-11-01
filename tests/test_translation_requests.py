import copy
from datetime import datetime, timedelta, timezone
from email.message import Message
from email.utils import format_datetime
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import timeline_localization as localization
import update_timeline as timeline


def http_error(code=429, retry_after=None):
    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return HTTPError("https://translate.googleapis.com/", code, "test", headers, None)


def response():
    result = MagicMock()
    result.__enter__.return_value.read.return_value = json.dumps([[["測試翻譯"]]]).encode()
    return result


class TranslationRequestTests(unittest.TestCase):
    def test_429_obeys_retry_after_then_succeeds(self):
        with patch.object(localization, "urlopen", side_effect=[http_error(retry_after="12"), response()]) as request, patch.object(localization.time, "sleep") as sleep:
            self.assertEqual(localization.translate_public_title("테스트"), "測試翻譯")
        self.assertEqual(request.call_count, 2)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 12])

    def test_429_http_date_waits_until_server_retry_time(self):
        now = datetime(2026, 11, 1, tzinfo=timezone.utc)
        retry_after = format_datetime(now + timedelta(seconds=30), usegmt=True)
        with patch.object(localization, "datetime") as clock, patch.object(localization, "urlopen", side_effect=[http_error(retry_after=retry_after), response()]), patch.object(localization.time, "sleep") as sleep:
            clock.now.return_value = now
            self.assertEqual(localization.translate_public_title("테스트"), "測試翻譯")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 30])

    def test_persistent_429_is_bounded_and_not_cached(self):
        localizer = localization.Localizer({})
        with patch.object(localization, "urlopen", side_effect=http_error()) as request, patch.object(localization.time, "sleep") as sleep:
            with self.assertRaises(HTTPError):
                localizer.title("테스트")
        self.assertEqual(request.call_count, 4)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 5, 10, 20])
        self.assertFalse(localizer.cache)

    def test_long_retry_after_does_not_retry_early(self):
        with patch.object(localization, "urlopen", side_effect=http_error(retry_after="120")) as request, patch.object(localization.time, "sleep"):
            with self.assertRaises(HTTPError):
                localization.translate_public_title("테스트")
        self.assertEqual(request.call_count, 1)

    def test_invalid_retry_after_uses_backoff(self):
        with patch.object(localization, "urlopen", side_effect=[http_error(retry_after="invalid"), response()]), patch.object(localization.time, "sleep") as sleep:
            localization.translate_public_title("테스트")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 5])

    def test_permission_errors_are_not_retried(self):
        with patch.object(localization, "urlopen", side_effect=http_error(403)) as request, patch.object(localization.time, "sleep"):
            with self.assertRaises(HTTPError):
                localization.translate_public_title("테스트")
        self.assertEqual(request.call_count, 1)

    def test_temporary_network_and_server_errors_retry(self):
        for error in (URLError("temporary"), TimeoutError(), http_error(503)):
            with self.subTest(error=type(error).__name__), patch.object(localization, "urlopen", side_effect=[error, response()]), patch.object(localization.time, "sleep") as sleep:
                self.assertEqual(localization.translate_public_title("테스트"), "測試翻譯")
                self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 5])


class TranslationResumeTests(unittest.TestCase):
    def test_failed_generation_preserves_data_and_resumes_successful_translations(self):
        raw = {"events": [{"title": title, "kr": {"sources": []}, "tw": {"sources": []}}
                          for title in ("첫 번째", "두 번째")], "groups": [], "reviewQueue": []}
        calls = []
        def translator(text):
            calls.append(text)
            if text == "두 번째" and calls.count(text) == 1:
                raise http_error()
            return {"첫 번째": "第一項", "두 번째": "第二項"}[text]
        with TemporaryDirectory(dir=ROOT) as directory:
            root = Path(directory)
            cache = root / ".cache/timeline"
            originals = {"update-timeline.json": {"old": True},
                         "timeline/source-index.json": {"kr": [], "tw": []},
                         "timeline/translations.json": {}}
            for path, data in originals.items():
                timeline.write(root / path, data)
            before = {p: (root / p).read_bytes() for p in originals}
            factory = lambda *args, **kwargs: localization.Localizer(*args, translator=translator, **kwargs)
            with patch.object(timeline, "ROOT", root), patch.object(sys, "argv", ["update_timeline.py", "--cache-dir", str(cache), "--today", "2026-11-01"]), patch.object(timeline, "Client"), patch.object(timeline, "crawl_kr", return_value=[]), patch.object(timeline, "crawl_tw", return_value=[]), patch.object(timeline, "build", side_effect=lambda *args: copy.deepcopy(raw)), patch.object(timeline, "Localizer", side_effect=factory):
                with self.assertRaises(HTTPError):
                    timeline.main()
                self.assertTrue((cache / "translations.json").exists())
                self.assertEqual(len(timeline.read(cache / "translations.json", {})), 1)
                self.assertEqual({p: (root / p).read_bytes() for p in originals}, before)
                timeline.main()
            self.assertEqual(calls, ["첫 번째", "두 번째", "두 번째"])
            result = timeline.read(root / "update-timeline.json", {})
            self.assertEqual([e["title"] for e in result["events"]], ["第一項", "第二項"])
            self.assertEqual(len(timeline.read(root / "timeline/translations.json", {})), 2)


if __name__ == "__main__":
    unittest.main()
