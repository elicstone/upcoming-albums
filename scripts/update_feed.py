"""Refresh the calendar fortnightly and expire old albums daily. Python 3.12+."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "AUTOBRR_NO_CURATED_ALBUMS_7f4bd530c23b4e0b9af2"
MONTHS = {m: i for i, m in enumerate(("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"), 1)}
DATE_HEADING = re.compile(r"^(" + "|".join(MONTHS) + r") (\d{1,2})(?:,? (20\d{2}))?$")
ENTRY = re.compile(r"^(.+?):\s+(.+?)\s+\[([^\[\]]+)\]$")
EDITION = re.compile(r"\s*\((?:reissue|(?:\d+(?:st|nd|rd|th)\s+)?anniversary(?:\s+expanded)?\s+edition|deluxe(?:\s+edition)?|expanded(?:\s+edition)?|remaster(?:ed)?(?:\s+edition)?|OST)\)\s*$", re.I)


class FeedError(ValueError):
    pass


class ArticleScripts(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.active = False
        self.parts = []
        self.documents = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("type") == "application/ld+json":
            self.active = True
            self.parts = []

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)

    def handle_endtag(self, tag):
        if tag == "script" and self.active:
            self.documents.append(json.loads("".join(self.parts)))
            self.active = False


def objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from objects(child)


def key(row):
    return unicodedata.normalize("NFC", row["artist"]).lower(), unicodedata.normalize("NFC", row["title"]).lower()


def parse_calendar(html, today, config):
    parser = ArticleScripts()
    parser.feed(html)
    articles = [item for doc in parser.documents for item in objects(doc)
                if isinstance(item.get("articleBody"), str)
                and "Upcoming Albums" in item.get("headline", "")
                and item.get("url", "").rstrip("/") == config["source_url"].rstrip("/")]
    if len(articles) != 1:
        raise FeedError("Expected one Pitchfork calendar article in JSON-LD; source format changed.")
    article = articles[0]
    year_match = re.search(r"\b(20\d{2})\b", article["headline"])
    if not year_match:
        raise FeedError("Calendar headline has no explicit year.")
    headline_year = int(year_match[1])
    modified = datetime.fromisoformat(article["dateModified"].replace("Z", "+00:00")).date()
    if not -2 <= (today - modified).days <= config["maximum_source_age_days"]:
        raise FeedError("Calendar modification date is stale or in the future; preserving previous feed.")
    rows = {}
    current = None
    first = None
    headings = 0
    for raw in article["articleBody"].replace("\\n", "\n").splitlines():
        line = " ".join(raw.split())
        heading = DATE_HEADING.fullmatch(line)
        if heading:
            month, day = MONTHS[heading[1]], int(heading[2])
            if heading[3]:
                year = int(heading[3])
            elif current is None:
                # A January update may still begin with December from the previous year.
                candidates = [date(y, month, day) for y in (headline_year - 1, headline_year, headline_year + 1)]
                year = min(candidates, key=lambda d: abs((d - modified).days)).year
            else:
                year = current.year
                if month < current.month:
                    if current.month < 10 or month > 3:
                        raise FeedError("Unexpected backwards date heading.")
                    year += 1
            next_date = date(year, month, day)
            if current and next_date <= current:
                raise FeedError("Calendar headings are not strictly chronological.")
            first = first or next_date
            if (next_date - first).days > 550:
                raise FeedError("Calendar spans more than 550 days; check year inference.")
            current = next_date
            headings += 1
            continue
        if any(line.startswith(prefix) for prefix in ("New music releases for", "Image may contain")):
            continue
        if any(line.startswith(m + " ") for m in MONTHS) and current:
            raise FeedError("Unrecognized date heading: " + line)
        match = ENTRY.fullmatch(line) if current else None
        if not match:
            if current and ": " in line and "[" in line:
                raise FeedError("Unrecognized album row; source layout may have changed.")
            continue
        artist, title = match[1].strip(), match[2].strip()
        if any(c in artist + title for c in ("\ufffd", "\x00")):
            raise FeedError("Invalid text encoding in an album row.")
        row = {"artist": artist, "title": title, "release_date": current.isoformat()}
        if key(row) in rows and rows[key(row)]["release_date"] != row["release_date"]:
            raise FeedError("Conflicting dates for the same album.")
        rows[key(row)] = row
    if headings < 2 or not config["minimum_source_albums"] <= len(rows) <= 2000:
        raise FeedError(f"Unexpected source size: {len(rows)} albums, {headings} dates.")
    if not any(today <= date.fromisoformat(r["release_date"]) <= today + timedelta(days=config["lookahead_days"]) for r in rows.values()):
        raise FeedError("Source has no upcoming releases inside the configured window.")
    return list(rows.values()), {"headline": article["headline"], "modified": article["dateModified"], "date_headings": headings}


def clean_title(title):
    previous = None
    while title != previous:
        previous = title
        title = EDITION.sub("", title).strip()
    return re.sub(r"\s+EP$", "", title, flags=re.I).strip()


def variants(text):
    text = unicodedata.normalize("NFC", text)
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    folded = folded.translate(str.maketrans({"ø": "o", "Ø": "O", "ł": "l", "Ł": "L", "æ": "ae", "Æ": "AE", "œ": "oe", "Œ": "OE", "ß": "ss"}))
    return sorted({text, folded})


def component(text):
    # Only letters and digits are literals. Commas must never reach autobrr's
    # comma-delimited field; *, ?, | and all punctuation become separators.
    return re.sub(r"\*+", "*", "".join(c if c.isalnum() else "*" for c in text)).strip("*")


def patterns_for(row):
    title = clean_title(row["title"])
    artists = variants(re.sub(r"\s+(?:and|&|/|\+)\s+", " ", row["artist"], flags=re.I))
    if row["artist"].lower() == "various artists":
        artists += ["Various", "VA"]
    patterns = set()
    for artist in artists:
        for album in variants(title):
            a, b = component(artist), component(album)
            if not a or not b or len(a.replace("*", "") + b.replace("*", "")) < 6:
                raise FeedError("Album name too short to generate a safe automatic pattern.")
            # RED's documented announce has an artist/title delimiter followed
            # by a literal space + [year]. Keep both boundaries in each pattern.
            patterns.add(f"{a}* - {b}* [*] *")
    return sorted(patterns, key=str.lower)


def merge_rows(current, previous, today, config):
    cutoff = today - timedelta(days=config["retain_days"])
    horizon = today + timedelta(days=config["lookahead_days"])
    merged = {key(r): r for r in current}
    # Keep recently released albums when the rolling source drops old dates.
    # Missing future albums are removed: a cancellation should not remain live.
    for row in previous:
        released = date.fromisoformat(row["release_date"])
        if cutoff <= released <= today and key(row) not in merged:
            merged[key(row)] = row
    return sorted((r for r in merged.values() if cutoff <= date.fromisoformat(r["release_date"]) <= horizon), key=lambda r: (r["release_date"], *key(r)))


def validate_feed(content):
    lines = content.splitlines()
    if not lines or len(lines) > 10000:
        raise FeedError("Refusing an empty or oversized feed.")
    if lines == [SENTINEL]:
        return
    if len(lines) != len(set(lines)):
        raise FeedError("Duplicate patterns.")
    for line in lines:
        if not line or line != line.strip() or any(c in line for c in (",", "|", "\x00", "\r", "\ufffd")):
            raise FeedError("Invalid plaintext pattern.")
        if " - " not in line or not line.endswith("* [*] *") or len(line) > 1000:
            raise FeedError("Pattern is missing the required artist/title/year structure.")


def http_get(url):
    for attempt in range(3):
        try:
            req = Request(url, headers={"User-Agent": "upcoming-albums-feed/1.0 (+https://github.com/elicstone)", "Accept": "text/html"})
            with urlopen(req, timeout=30) as response:
                if response.status != 200 or response.headers.get_content_type() != "text/html":
                    raise FeedError("Calendar did not return HTTP 200 text/html.")
                raw = response.read(5_000_001)
                if len(raw) > 5_000_000:
                    raise FeedError("Calendar response too large.")
                return raw.decode("utf-8")
        except (HTTPError, URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(content, encoding="utf-8", newline="\n")
    temp.replace(path)


def validate_timing(config):
    if not 7 <= config["retain_days"] <= 14:
        raise FeedError("retain_days must be between 7 and 14.")
    if not 1 <= config.get("source_refresh_days", 14) <= 30:
        raise FeedError("source_refresh_days must be between 1 and 30.")


def source_refresh_due(previous, today, config):
    validate_timing(config)
    last_fetch = previous.get("last_source_fetch") or previous.get("as_of")
    if not last_fetch:
        return True
    elapsed = (today - date.fromisoformat(last_fetch)).days
    if elapsed < 0:
        raise FeedError("Saved source-fetch date is in the future.")
    return elapsed >= config.get("source_refresh_days", 14)


def render_feed(config, rows, source_count, metadata, today, last_fetch, mode):
    patterns = sorted({p for r in rows for p in patterns_for(r)}, key=str.lower)
    content = "\n".join(patterns or [SENTINEL]) + "\n"
    validate_feed(content)
    next_fetch = date.fromisoformat(last_fetch) + timedelta(days=config.get("source_refresh_days", 14))
    result = {"schema_version": 1, "as_of": today.isoformat(), "source_url": config["source_url"], "source_count": source_count, "retain_days": config["retain_days"], "last_source_fetch": last_fetch, "source_metadata": metadata, "albums": rows}
    status = {"as_of": today.isoformat(), "source": metadata, "source_count": source_count, "album_count": len(rows), "pattern_count": len(patterns), "feed_sha256": hashlib.sha256(content.encode()).hexdigest(), "verified_at": datetime.now(timezone.utc).isoformat(), "last_source_fetch": last_fetch, "next_source_fetch": next_fetch.isoformat(), "update_mode": mode, "gist_raw_url": f"https://gist.githubusercontent.com/{config['gist_owner']}/{config['gist_id']}/raw/{config['gist_filename']}"}
    return content, result, status


def build(config, html, previous, today):
    validate_timing(config)
    current, metadata = parse_calendar(html, today, config)
    old_count = previous.get("source_count", 0)
    if old_count >= 20 and len(current) < old_count * (1 - config["maximum_drop_fraction"]):
        raise FeedError("Source lost more than half its albums; review before publishing.")
    rows = merge_rows(current, previous.get("albums", []), today, config)
    return render_feed(config, rows, len(current), metadata, today, today.isoformat(), "source refresh")


def build_cached(config, previous, today):
    if source_refresh_due(previous, today, config):
        raise FeedError("A fresh source fetch is due; refusing to extend the cache.")
    metadata = previous.get("source_metadata")
    if not metadata or not isinstance(previous.get("albums"), list):
        raise FeedError("Cached source metadata or albums are missing.")
    last_fetch = previous.get("last_source_fetch") or previous["as_of"]
    rows = merge_rows(previous["albums"], [], today, config)
    return render_feed(config, rows, previous["source_count"], metadata, today, last_fetch, "retention only")


def prepare_update(config, previous, today, *, scheduled=False, html=None, fetch=http_get):
    if scheduled and html is None and not source_refresh_due(previous, today, config):
        return build_cached(config, previous, today)
    return build(config, html if html is not None else fetch(config["source_url"]), previous, today)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--html", type=Path, help="Local source snapshot, for verification only")
    parser.add_argument("--today", type=date.fromisoformat, help="Explicit test date")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--scheduled", action="store_true", help="Fetch only when the source refresh interval is due; otherwise expire old albums from saved data")
    args = parser.parse_args()
    config = json.loads((args.root / "config.json").read_text(encoding="utf-8"))
    today = args.today or datetime.now(ZoneInfo(config["timezone"])).date()
    history = args.root / "data/albums.json"
    previous = json.loads(history.read_text(encoding="utf-8")) if history.exists() else {}
    # Migrate the existing daily feed without pretending today's cleanup is a fetch.
    old_status_path = args.root / "data/status.json"
    if previous and not previous.get("source_metadata") and old_status_path.exists():
        old_status = json.loads(old_status_path.read_text(encoding="utf-8"))
        previous["source_metadata"] = old_status.get("source")
    html = args.html.read_text(encoding="utf-8") if args.html else None
    content, state, status = prepare_update(config, previous, today, scheduled=args.scheduled, html=html)
    # Nothing is touched until all parsing, retention and pattern checks pass.
    atomic_write(args.root / "upcoming-albums.txt", content)
    atomic_write(history, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
    atomic_write(args.root / "data/status.json", json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    print(f"{status['update_mode']}: validated {status['album_count']} albums / {status['pattern_count']} patterns for {today}. Next source fetch: {status['next_source_fetch']}.")


if __name__ == "__main__":
    try:
        main()
    except (FeedError, KeyError, ValueError, OSError) as exc:
        sys.exit(f"Feed update failed; do not publish: {exc}")
