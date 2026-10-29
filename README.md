# Curated upcoming albums

Refreshes `upcoming-albums.txt` from [Pitchfork's maintained release calendar](https://pitchfork.com/news/new-album-releases/) **weekly (every 7 days)**, with daily removal of expired albums from saved data. Each line pairs one artist with one album in the RED IRC announce format. The existing gist remains the subscription endpoint:

**[Stable gist feed](https://gist.githubusercontent.com/elicstone/a04cecae2e6a2ada2b969e752831d332/raw/gistfile1.txt)**

The original URL contains `/raw/393d4cff10ff5f09a1ca00f819a6080fb134772f/`. That URL is an immutable revision. Change autobrr to the stable URL above once; the gist ID and `gistfile1.txt` filename are preserved. The repository also exposes [upcoming-albums.txt](https://raw.githubusercontent.com/elicstone/upcoming-albums/main/upcoming-albums.txt).

## Current verification

Deployment verified October 28, 2026: **gist publication is enabled**. The [first successful publication run](https://github.com/elicstone/upcoming-albums/actions/runs/40815940696) passed all tests and updated the existing gist. The public gist returned HTTP 200 with `text/plain`, matched the repository feed exactly, and autobrr imported all 111 patterns unchanged. Source refreshes now occur every 7 days; daily cleanup preserves the 14-day retention window. RED - Popular was left disabled pending the Test-only validation below.

- Verified October 28, 2026 (America/Los_Angeles): the calendar is accessible as HTML with a `NewsArticle` JSON-LD body, date headings and `Artist: Album [Label]` lines. No browser rendering or paid API is needed.
- Initial parse: **102 albums across 19 dates**, from October 30, 2026 through March 12, 2027. Pattern count is recorded in `data/status.json`.
- The article's modification date is October 1, 2026; its original publication date is 2022 and must not be used as the release year. The parser uses the current headline, modification date and ordered headings. It ignores a January caption carrying the wrong year.
- The stable gist endpoint was checked and returns `text/plain; charset=utf-8`.
- Parser, retention, matching and publication safeguards have local automated tests. A green GitHub Actions run additionally verifies source access from a GitHub runner. Neither establishes successful matching on your installed autobrr version: complete the Test-only procedure below.

## Weekly refresh and retention

The workflow checks at **14:17 UTC** daily (07:17 Pacific daylight time / 06:17 Pacific standard time), but fetches Pitchfork only when **7 days have elapsed since the last successful source refresh**. On other days it uses the saved album data only, removing expired entries. The gist is changed only when its content changes. The weekly interval continues across month/year boundaries. GitHub scheduling can be delayed. It uses Python 3.12's standard library and no installed scraping packages.

For example, a source refresh on October 29 is next due **November 5, 2026**. `data/status.json` records the actual `last_source_fetch`, `next_source_fetch`, and whether a run did a `source refresh` or `retention only`. Daily cleanup never moves the next fetch date. New announcements, cancellations and date changes are picked up on the next source refresh and can therefore lag by up to 7 days. For an immediate refresh, use **Actions → Update upcoming albums → Run workflow**; a manual run or relevant code change forces a fetch and starts a new 7-day interval. Change `source_refresh_days` in `config.json` to adjust this interval.

The feed includes upcoming albums within 365 days and releases dated at most **14 days before today**, inclusive. A release dated October 30 remains through November 13 and drops on November 14. Dates use America/Los_Angeles. `retain_days` can be set from 7 to 14 in `config.json`.

`data/albums.json` is committed history. When Pitchfork removes a past week, those albums remain until their retention cutoff. A removed future entry is dropped to avoid retaining a canceled release; changed dates replace earlier dates for the same artist/title. On the first run, releases already removed from Pitchfork cannot be reconstructed. A renamed album is treated as a new entry.

The source is editorially curated, not a popularity ranking. It includes albums, EPs, mixtapes, live recordings, compilations and reissues. Preserve the quality, format and category choices you want in your own filter.

## Enable updates to the existing gist

Repository generation runs on setup; subsequent scheduled runs follow the weekly source refresh and daily cleanup rules above. **Gist publication starts disabled** until the repository variable below is set. A preview run does not alter the existing gist or any autobrr filter.

1. Check the first **Update upcoming albums** run is green and inspect `upcoming-albums.txt` and `data/status.json`.
2. On GitHub, create a fine-grained personal access token for your own account with **Account permissions → Gists: Read and write**. No repository permissions are required for this token. If using a classic token, select only the `gist` scope. Give it a suitable expiration and renew it before expiry. The permission covers your gists, so keep the token private.
3. In **elicstone/upcoming-albums → Settings → Secrets and variables → Actions → Secrets**, create a repository secret named **`GIST_TOKEN`** and paste the token directly there. Do not put it in chat, code, or `config.json`.
4. Complete the Test-only autobrr setup below before changing its live list.
5. Under the same settings' **Variables** tab, add **`PUBLISH_GIST`** with value **`true`**. Run the workflow manually. Confirm the **Publish to the existing gist** step succeeds.
6. Open the stable gist feed and compare it with the repository's generated file. CDN caching may delay visible changes briefly. Then refresh the list in autobrr and verify its managed field.

The default workflow `GITHUB_TOKEN` commits repository state; it does not authorize updates to an account's gist. The extra token is only available to the publication step. No RED, seedbox, autobrr or torrent-client credentials belong in this repository.

The publisher checks the gist owner and existing filename, changes only `gistfile1.txt`, and verifies the returned content. It does not create a gist, rename a file, change visibility, or touch other gist files. [GitHub's update-gist reference](https://docs.github.com/en/rest/gists/gists#update-a-gist) documents the endpoint and Gists permission.

## Exact autobrr Plaintext settings

First export **RED - Popular** as a backup. Disable it while changing configuration. Create a separate **RED - Popular - TEST** filter with the same desired quality rules and **Redacted** indexer, and only a **Test** action. Do not copy enabled download actions into it.

Go to **Settings → Lists → Add new list**:

| Setting | Value |
| --- | --- |
| Name | RED upcoming albums |
| Type | Plaintext |
| URL | `https://gist.githubusercontent.com/elicstone/a04cecae2e6a2ada2b969e752831d332/raw/gistfile1.txt` |
| Match Release / Match Releases | **On** |
| Bypass cleanup and sanitization / Skip clean/sanitize | **On** |
| Target filter | **RED - Popular - TEST** during verification |
| Enabled, if shown | On |

In the target filter's **Advanced** tab, set **Use regex** for Match/Except releases **Off**. Save the list and inspect **Match releases**: it should contain the feed patterns joined by commas. The list owns that entire field; manual additions can be overwritten. Remove conflicting artist/album/title constraints if they were only remnants of the old list. Keep deliberate format, quality, category and size rules. Do not attach multiple competing lists to the same field.

Autobrr's Plaintext list expects HTTP 200 with a `text/plain` response. It reads one pattern per line. Current documentation says lists refresh on save and every six hours; use the list refresh control for immediate verification. Menu wording can vary by installed version. See [autobrr Lists](https://autobrr.com/filters/lists).

### Safe test procedure — no torrent snatching

1. Confirm **RED - Popular is disabled** and no other enabled RED filter can download the test releases. If you need a strict no-snatch session, disable every download-capable filter that could accept those RED announces.
2. In the test filter, keep **only Test enabled**. Remove or disable all download-client, *arr, watch-folder, Exec and webhook actions. Adding paused is not a dry run: it can still fetch a torrent and add it to a client.
3. Before gist publication, you can use the repository raw URL on the TEST list to validate the generated patterns. After publication, switch that same TEST list to the stable gist URL above.
4. Enable the TEST filter, refresh the list and inspect its Match releases field. Ensure it is nonempty and is not just `*`. Keep regex off.
5. Observe actual RED announcements and the filter's logs. For a listed album, the artist and album must both match. Check wrong-album/same-artist, wrong-artist/same-album, punctuation, accented names, EPs and reissues as available. Other quality conditions can legitimately reject a title match. Absence of new announces does not prove correctness.
6. Verify no torrent was added to any client and all successful actions are **Test**. The local checker below evaluates names without contacting any tracker. Do not use a UI retry button unless your version explicitly says it is a dry run.
7. Keep everything Test-only until you have reviewed actual matching results. Later, attach the list to **RED - Popular** while it is disabled, confirm the final field and restrictions, and remove the list from the TEST filter if no longer needed. Enabling a downloading action is a separate, deliberate step after verification; this project never does it.

The [Test action](https://autobrr.com/filters/actions#test) logs matches without downloading torrent files. Some filter predicates may fetch extra metadata before actions; for a strict zero-tracker-request test, use the offline name checker instead.

## Pattern behavior and limitations

Example:

```text
Ex*Re* - Save*As* [*] *
```

This matches a RED name such as `Ex:Re - Save As [2026] [Album] - FLAC / Lossless / WEB`. The exact ` - ` artist/title separator and literal ` [year] ` structure come from autobrr's RED IRC definition. The patterns target RED IRC names; unrelated RSS/title formats are not assumed compatible.

Each line contains both artist and album, preventing the cross-product caused by independent Artists and Albums lists. Punctuation becomes `*`; commas are never emitted because autobrr uses them to separate patterns. Accented and folded variants are included. Artist collaboration separators are relaxed; `Various Artists`, `Various`, and `VA` variants are included for compilations. Meaningful title parentheses are retained; terminal EP, OST, reissue and selected edition descriptors are removed.

The year is a wildcard because RED can label a reissue with its original release year. This can also match older uploads of the same album. The feed is not a new-upload guarantee or a duplicate detector. Wildcards permit extra text between tokens and may match expanded editions; unusual artist aliases and collaboration ordering may still be missed. Validate with actual names before downloading. Album editions, date changes and source mistakes can require review.

Matching semantics and RED structure were inspected at autobrr commit `f1979fffed8d4572a2ca4deb87fbfdb6428e390d`:

- [RED indexer definition](https://github.com/autobrr/autobrr/blob/f1979fffed8d4572a2ca4deb87fbfdb6428e390d/internal/indexer/definitions/red.yaml)
- [Plaintext processing](https://github.com/autobrr/autobrr/blob/f1979fffed8d4572a2ca4deb87fbfdb6428e390d/internal/list/process_list_plaintext.go)
- [Wildcard matcher](https://github.com/autobrr/autobrr/blob/f1979fffed8d4572a2ca4deb87fbfdb6428e390d/pkg/wildcard/match.go)

## Local verification

```sh
python -m unittest discover -s tests -v
python scripts/update_feed.py
python scripts/update_feed.py --scheduled
python scripts/check_name.py "Ex:Re - Save As [2026] [Album] - FLAC / Lossless / WEB"
```

The name checker uses only local files and checks the title pattern, not the complete autobrr filter. `update_feed.py` alone forces a source refresh; `--scheduled` fetches only when due and otherwise performs retention cleanup without contacting Pitchfork. On Windows, Python may need timezone data (`python -m pip install tzdata`); GitHub's Linux runner includes it. For an offline historical check, supply `--html path/to/calendar.html --today YYYY-MM-DD`. Do not use a historical override in the scheduled workflow.

## Failure handling and recovery

- HTTP failures, challenge pages, missing JSON-LD, malformed dates, stale source metadata, no upcoming releases, and a source-count drop of more than 50% fail the run. Generated files are only written after all checks pass. Gist publication never runs after a failed build or commit.
- A failed fetch leaves the last validated feed intact. **It does not magically expire entries in the already published gist.** Check failed Actions runs and source age; disable the receiving filter during an extended outage. A schema change needs a parser fix and tests. This project does not silently switch to an unverified source.
- `data/status.json` records validation time, counts and a checksum. A feed older than 48 hours or with an inconsistent checksum cannot be published by the publisher.
- If a legitimate source reset triggers the count-drop check, inspect the source and adjust the prior `source_count` in `data/albums.json` to the newly confirmed count, preserving its `albums` history. Commit the reviewed change and run the workflow again.
- Enable GitHub Actions failure notifications in your account. For public repositories GitHub can disable schedules after 60 days of inactivity; the daily status commit creates activity. Confirm the workflow remains enabled if it has been failing. See [GitHub scheduling behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).
- A write-permission or branch-protection failure stops before gist publication. Allow this workflow to commit to its repository's `main` branch or adapt it to the repository's existing review rules.
- To stop gist changes, set `PUBLISH_GIST` to `false`. To roll back, disable the autobrr filter, restore the desired gist revision in GitHub, and inspect the stable URL before re-testing. The original revision URL remains available as a read-only backup.
