# Music license — replay video

The replay video (`site/media/demo-replay.webm`) has one background music track. No narration, no other
audio.

| Field | Value |
|---|---|
| Track | **Clean Soul** |
| Creator | **Kevin MacLeod** |
| Publisher / source | incompetech.com (Incompetech Inc.) |
| ISRC | USUAN1300033 (incompetech catalogue: "Very clean soft piece with a lot of space in it." — feel: Calming, Mysterious, Relaxed; electric piano, bass; 5:07) |
| Source file URL | https://incompetech.com/music/royalty-free/mp3-royaltyfree/Clean%20Soul.mp3 |
| Downloaded file | `Clean Soul.mp3`, 12,271,405 bytes, 320 kbps MP3, sha256 `458868c225cf8f6dbaf17300aa2e0839386991be8581d0218554699297d7581c` (kept in the gitignored `.cache/music/`, **not** committed) |
| License | **Creative Commons Attribution 4.0 International (CC BY 4.0)** — https://creativecommons.org/licenses/by/4.0/ |
| Required attribution (publisher's format) | Clean Soul Kevin MacLeod (incompetech.com)<br>Licensed under Creative Commons: By Attribution 4.0<br>https://creativecommons.org/licenses/by/4.0/ |
| Changes made (disclosure required by CC BY 4.0 and the publisher) | Excerpt from the start of the track, trimmed to 76 s, volume set to background level (+7.2 dB gain from a quiet master, body ≈ −23 dBFS RMS, peaks −6 dBFS), 3 s fade-in and 5 s fade-out, re-encoded to Opus 128 kb/s and muxed with the video. |
| Verified on | **2026-09-27** |

## Why this use is permitted

- **Publisher terms** — incompetech's FAQ (https://incompetech.com/music/royalty-free/faq.html), on using the
  music in videos: "Yes, AND you can monetize the videos. Be sure to credit me." Credit may be "in the
  video description or in the video itself", placed so "a person who wants to know where the music came
  from should have no difficulty in finding it". Edits are allowed if the credits make clear "which parts
  are yours, and which parts are mine". The credit format above is quoted from the same FAQ.
- **Licensing page** — https://incompetech.com/music/royalty-free/licenses/ offers "Creative Commons — Free",
  which "Requires that you credit the music".
- **License text** — CC BY 4.0 lets anyone "copy and redistribute the material in any medium or format for
  any purpose, even commercially" and "remix, transform, and build upon the material", on condition that
  you "give appropriate credit, provide a link to the license, and indicate if changes were made". This
  covers embedding the edited excerpt in a video on a public portfolio site and redistributing it as part
  of that video.
- **Catalogue entry** — the track is listed in incompetech's own catalogue data
  (https://incompetech.com/music/royalty-free/pieces.json, `isrc` USUAN1300033) and the file is served from
  incompetech.com. The MP3's ID3 tags name the title, the artist and "Royalty Free".

## Where the credit appears

- On the site under the video and in the footer (rendered from `site/data/replay-captions.js`).
- In `README.md` (Credits).
- In the video manifest `site/media/demo-replay.json` (`audio.track`).

## Notes and residual risk

- The track-level page on the publisher's licensing platform (`incompetech.filmmusic.io/song/3514-clean-soul/`)
  redirected to a page that returned 404 on the verification date, so the license was verified from the
  publisher's FAQ, licensing page, catalogue data and the CC legal code instead.
- The 2013 announcement post predates the site's move to CC BY 4.0; earlier releases were offered under
  CC BY 3.0. Both versions permit this use with the same attribution.
- Only the mixed video is distributed. The source MP3 is not committed or offered for download.
- Some platforms run automated content matching; if a re-upload (e.g. to YouTube) is flagged, the credit
  above is the basis for disputing it. This does not affect hosting the file on the portfolio site.

## Reproduce

```powershell
New-Item -ItemType Directory -Force .cache\music | Out-Null
Invoke-WebRequest "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Clean%20Soul.mp3" -OutFile ".cache\music\Clean Soul.mp3"
node tools/mix_soundtrack.mjs      # refuses a file whose sha256 differs from the one above
```
