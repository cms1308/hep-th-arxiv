"""Delayed announcement regressions; no network or real waiting."""
import contextlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / 'scripts'))
import fetch_arxiv as fetch


def listing(day=20, count=1):
    return f'''<h3>Showing new listings for Tuesday, {day} October 2026</h3>
<h3>New submissions (showing {count} of {count} entries)</h3>
<dt>arXiv:2610.24062</dt><dd>
<div class="list-title">Light EFT Strings</div>
<div class="list-authors">A. Author</div>
<div class="list-subjects">High Energy Physics - Theory (hep-th)</div>
<p class="mathjax">{'A complete abstract about EFT strings. ' * 10}</p></dd>
<h3>Cross submissions (showing 1 of 1 entries)</h3>
<dt>arXiv:2610.99999</dt><dd>Cross-listed paper</dd>'''


class ListingTests(unittest.TestCase):
    def setUp(self):
        self.capture = contextlib.redirect_stdout(io.StringIO())
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def run_fetch(self, directory, pages, retries=0):
        args = ['fetch_arxiv.py', '--expect', '2026-10-20', '--outdir', directory,
                '--retries', str(retries), '--retry-wait', '1800']
        with patch.object(sys, 'argv', args), patch.object(
                fetch, 'get', side_effect=[p.encode() for p in pages]), patch.object(
                fetch.time, 'sleep') as sleep, patch.dict(fetch.os.environ, {}, clear=True):
            fetch.main()
        return sleep

    def test_today_only_includes_new_submissions(self):
        papers = fetch.parse_new_listing(listing(), '2026-10-20')
        self.assertEqual([p['id'] for p in papers], ['2610.24062'])
        self.assertEqual(papers[0]['categories'], 'hep-th')

    def test_old_or_future_page_is_rejected_without_archive(self):
        for day in (19, 21):
            with self.subTest(day=day):
                self.assertEqual(fetch.parse_new_listing(listing(day), '2026-10-20'), [])

    def test_broken_date_or_section_or_count_fails_loudly(self):
        for page in (listing().replace('Showing new listings for', 'Listing'),
                     listing().replace('New submissions', 'Changed section'),
                     listing(count=2)):
            with self.subTest(page=page[:80]), self.assertRaises(ValueError):
                fetch.parse_new_listing(page, '2026-10-20')

    def test_pending_check_writes_nothing_and_next_check_can_publish(self):
        with tempfile.TemporaryDirectory() as directory:
            self.run_fetch(directory, [listing(19)])
            self.assertEqual(list(pathlib.Path(directory).iterdir()), [])
            self.run_fetch(directory, [listing(20)])
            result = json.loads((pathlib.Path(directory) / '2026-10-20.json').read_text('utf-8'))
            self.assertEqual(result['date'], '2026-10-20')
            self.assertEqual(result['count'], 1)

    def test_manual_retry_waits_then_uses_new_page(self):
        with tempfile.TemporaryDirectory() as directory:
            sleep = self.run_fetch(directory, [listing(19), listing(20)], retries=1)
            sleep.assert_called_once_with(1800)
            self.assertTrue((pathlib.Path(directory) / '2026-10-20.json').exists())

    def test_retry_exhaustion_does_not_mislabel_old_papers(self):
        with tempfile.TemporaryDirectory() as directory:
            sleep = self.run_fetch(directory, [listing(19), listing(19)], retries=1)
            sleep.assert_called_once_with(1800)
            self.assertEqual(list(pathlib.Path(directory).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
