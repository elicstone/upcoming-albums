import copy
import hashlib
import json
import re
import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from update_feed import FeedError, build, clean_title, merge_rows, parse_calendar, patterns_for, validate_feed
from publish_gist import publish, verify_generated

CONFIG = json.loads((Path(__file__).resolve().parents[1] / 'config.json').read_text())
TODAY = date(2026, 10, 28)


def source(body, modified='2026-10-01T10:35:03-04:00', headline='New Music Releases and Upcoming Albums in 2026'):
    return '<script type="application/ld+json">' + json.dumps({'@type':'NewsArticle', 'headline':headline, 'articleBody':body, 'dateModified':modified, 'url':CONFIG['source_url']}) + '</script>'


def calendar():
    # Deliberately invented metadata. No copied article fixture required.
    return source('October 30\n' + '\n'.join(f'Artist {i}: Record {i} [Label]' for i in range(10)) + '\nDecember 11\nEx:Re: Save As [Label]\nJanuary 8\nNext Artist: Next Record [Label]\nNew music releases for Friday, January 8, 2026, include: Fake: Caption [Label]')


def matches(pattern, release):
    # autobrr's wildcard matcher treats brackets literally; Python fnmatch does not.
    regex = re.escape(pattern.lower()).replace(r'\*', '.*').replace(r'\?', '.')
    return re.fullmatch(regex, release.lower()) is not None


def row(artist='Test Artist', title='Test Album', released='2026-10-30'):
    return {'artist':artist, 'title':title, 'release_date':released}


class CalendarTests(unittest.TestCase):
    def test_live_shape_and_year_rollover(self):
        rows, meta = parse_calendar(calendar(), TODAY, CONFIG)
        self.assertEqual(len(rows), 12)
        self.assertEqual(rows[-1]['release_date'], '2027-01-08')
        self.assertEqual(rows[-2]['artist'], 'Ex:Re')
        self.assertFalse(any(r['artist'] == 'Fake' for r in rows))

    def test_january_page_can_begin_with_previous_december(self):
        body = 'December 25\n' + '\n'.join(f'A {i}: B {i} [Label]' for i in range(10)) + '\nJanuary 8\nNext: Future [Label]'
        rows, _ = parse_calendar(source(body, '2027-01-01T00:00:00Z', 'Upcoming Albums in 2027'), date(2027,1,2), CONFIG)
        self.assertEqual(rows[0]['release_date'], '2026-12-25')
        self.assertEqual(rows[-1]['release_date'], '2027-01-08')

    def test_literal_backslash_n_body(self):
        rows, _ = parse_calendar(calendar().replace('\\n', '\\\\n'), TODAY, CONFIG)
        self.assertEqual(len(rows), 12)

    def test_block_page_rejected(self):
        with self.assertRaises(FeedError): parse_calendar('<html>Access denied</html>', TODAY, CONFIG)

    def test_stale_source_rejected(self):
        with self.assertRaises(FeedError): parse_calendar(calendar(), date(2027,5,1), CONFIG)

    def test_out_of_order_rejected(self):
        with self.assertRaises(FeedError): parse_calendar(calendar().replace('December 11','September 11'), TODAY, CONFIG)

    def test_drop_guard(self):
        with self.assertRaises(FeedError): build(CONFIG, calendar(), {'source_count':100}, TODAY)

    def test_removed_and_expired_releases(self):
        prior = [row('Day14', released='2026-10-14'), row('Day15', released='2026-10-13'), row('Canceled', released='2026-11-01')]
        result = merge_rows([row()], prior, TODAY, CONFIG)
        self.assertEqual({r['artist'] for r in result}, {'Day14','Test Artist'})

    def test_rescheduled_album_replaces_old_date(self):
        result = merge_rows([row(released='2026-11-20')], [row(released='2026-10-20')], TODAY, CONFIG)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['release_date'],'2026-11-20')

    def test_invalid_retention(self):
        config = dict(CONFIG, retain_days=30)
        with self.assertRaises(FeedError): build(config, calendar(), {}, TODAY)


class PatternTests(unittest.TestCase):
    def assert_matches(self, artist, title, announce):
        self.assertTrue(any(matches(p, announce) for p in patterns_for(row(artist,title))), announce)

    def test_red_announce(self):
        self.assert_matches('Test Artist','Test Album','Test Artist - Test Album [2026] [Album] - FLAC / Lossless / WEB')

    def test_wrong_artist_and_wrong_album_fail(self):
        patterns = patterns_for(row())
        for name in ('Other Artist - Test Album [2026] [Album] - FLAC', 'Test Artist - Other Album [2026] [Album] - FLAC', 'Test Artist Tribute - Another Test Album [2026] [Album] - FLAC'):
            self.assertFalse(any(matches(p,name) for p in patterns))

    def test_punctuation_commas_and_accents(self):
        self.assert_matches('Björk','One, Two','Bjork - One, Two [2026] [Album] - FLAC')
        self.assert_matches('Ex:Re','Save As','Ex:Re - Save As [2026] [Album] - FLAC')
        self.assert_matches('Dawuna','Love’s Arp',"Dawuna - Love's Arp [2026] [Album] - FLAC")
        validate_feed('\n'.join(patterns_for(row('Example','One, Two'))) + '\n')

    def test_collaboration_separators(self):
        self.assert_matches('First and Second','Album Title','First & Second - Album Title [2026] [Album] - FLAC')

    def test_ep_reissue_and_meaningful_parentheses(self):
        self.assertEqual(clean_title('Title EP'),'Title')
        self.assertEqual(clean_title('Title (25th Anniversary Edition)'),'Title')
        self.assertEqual(clean_title('Title (Take Out or Delivery)'),'Title (Take Out or Delivery)')
        self.assert_matches('Example','Old Record (reissue)','Example - Old Record [1999] [Album] - FLAC')

    def test_various_artists(self):
        self.assert_matches('Various Artists','Compilation','VA - Compilation [2026] [Album] - FLAC')

    def test_empty_or_dangerous_feed(self):
        for content in ('','*\n','artist,album\n','Artist*\n'):
            with self.assertRaises(FeedError): validate_feed(content)


class PublishTests(unittest.TestCase):
    def test_only_target_file_is_changed(self):
        calls = []
        content = '\n'.join(patterns_for(row())) + '\n'
        def request(gist_id, token, payload=None):
            calls.append(payload)
            if payload is None:
                return {'owner':{'login':'elicstone'},'files':{'gistfile1.txt':{'content':'old'},'other.txt':{'content':'keep'}}}
            return {'files':{'gistfile1.txt':{'content':content}}}
        publish(CONFIG, content, 'test-token', request)
        self.assertEqual(calls[-1], {'files':{'gistfile1.txt':{'content':content}}})

    def test_owner_guard(self):
        with self.assertRaises(FeedError):
            publish(CONFIG,'feed','test',lambda *args: {'owner':{'login':'someone-else'}})

    def test_no_op(self):
        def request(*args):
            self.assertEqual(len(args),2)
            return {'owner':{'login':'elicstone'},'files':{'gistfile1.txt':{'content':'same'}}}
        self.assertIn('already',publish(CONFIG,'same','test',request))

    def test_checksum_and_staleness(self):
        content = '\n'.join(patterns_for(row())) + '\n'
        now = datetime.now(timezone.utc)
        status = {'verified_at':now.isoformat(),'feed_sha256':hashlib.sha256(content.encode()).hexdigest()}
        verify_generated(content,status,now)
        with self.assertRaises(FeedError): verify_generated(content,status,now+timedelta(days=3))
        with self.assertRaises(FeedError): verify_generated(content+'\n',status,now)


if __name__ == '__main__':
    unittest.main()
