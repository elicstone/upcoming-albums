"""Update exactly one existing gist file, preserving its name and identity."""
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from update_feed import ROOT, FeedError, validate_feed


def github_request(gist_id, token, payload=None):
    headers = {"Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "upcoming-albums-feed/1.0"}
    data = json.dumps(payload).encode() if payload is not None else None
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request("https://api.github.com/gists/" + gist_id, data=data, headers=headers, method="PATCH" if data is not None else "GET")
    try:
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        # Never emit request headers, the token, or an arbitrary server body.
        raise FeedError(f"GitHub gist request returned HTTP {exc.code}.") from None


def verify_generated(content, status, now):
    validate_feed(content)
    verified = datetime.fromisoformat(status["verified_at"])
    if not 0 <= (now - verified).total_seconds() < 48 * 3600:
        raise FeedError("Refusing to publish a feed not validated in the last 48 hours.")
    if hashlib.sha256(content.encode()).hexdigest() != status["feed_sha256"]:
        raise FeedError("Generated feed checksum does not match its validation report.")


def publish(config, content, token, request=github_request):
    old = request(config["gist_id"], token)
    if old.get("owner", {}).get("login", "").lower() != config["gist_owner"].lower():
        raise FeedError("Gist owner does not match configuration.")
    filename = config["gist_filename"]
    if filename not in old.get("files", {}):
        raise FeedError("Expected gist filename missing; refusing to create or rename files.")
    if old["files"][filename].get("truncated"):
        raise FeedError("Existing gist file is unexpectedly large.")
    if old["files"][filename].get("content") == content:
        return "Gist already matches the validated feed."
    result = request(config["gist_id"], token, {"files": {filename: {"content": content}}})
    if result.get("files", {}).get(filename, {}).get("content") != content:
        raise FeedError("Gist update response did not confirm the expected content.")
    return "Updated the existing gist file; other files and visibility preserved."


def main():
    token = os.environ.get("GIST_TOKEN")
    if not token:
        raise FeedError("Set the GIST_TOKEN Actions secret before enabling gist publishing.")
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    status = json.loads((ROOT / "data/status.json").read_text(encoding="utf-8"))
    content = (ROOT / "upcoming-albums.txt").read_text(encoding="utf-8")
    verify_generated(content, status, datetime.now(timezone.utc))
    print(publish(config, content, token))


if __name__ == "__main__":
    try:
        main()
    except (FeedError, KeyError, ValueError, OSError) as exc:
        sys.exit(f"Gist publication failed: {exc}")
