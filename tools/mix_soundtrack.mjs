// Add the licensed background music to the replay video.
//
//   node tools/mix_soundtrack.mjs
//
// Why this route: the ffmpeg build available here encodes video only. Headless Chrome decodes the
// MP3, applies gain + fades (Web Audio, offline render) and encodes Opus (MediaRecorder); ffmpeg then
// stream-copies that audio next to the existing VP8 video. The video stream is copied bit-for-bit, so
// frames, captions and timing are unchanged.
//
// Inputs:  site/media/demo-replay.webm (from make_replay_video.py) and the music file below, which is
//          NOT stored in the repo: download it once (see docs/music-license.md) into .cache/music/.
// Writes:  site/media/demo-replay.webm (replaced, now with an audio stream), updates
//          site/media/demo-replay.json and site/data/replay-captions.js with the audio details.
// Needs:   Node 18+, Google Chrome/Chromium, ffmpeg with the webm muxer ($FFMPEG, PATH or Playwright's).
import { spawn, spawnSync } from "node:child_process";
import { createServer } from "node:http";
import { createHash } from "node:crypto";
import { existsSync, readFileSync, writeFileSync, renameSync, mkdtempSync, rmSync, readdirSync } from "node:fs";
import { tmpdir, homedir } from "node:os";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const REPO = join(dirname(fileURLToPath(import.meta.url)), "..");
const VIDEO = join(REPO, "site", "media", "demo-replay.webm");
const MANIFEST = join(REPO, "site", "media", "demo-replay.json");
const CAPTIONS_JS = join(REPO, "site", "data", "replay-captions.js");

export const TRACK = {
  title: "Clean Soul",
  artist: "Kevin MacLeod",
  publisher: "incompetech.com",
  isrc: "USUAN1300033",
  source_url: "https://incompetech.com/music/royalty-free/mp3-royaltyfree/Clean%20Soul.mp3",
  source_sha256: "458868c225cf8f6dbaf17300aa2e0839386991be8581d0218554699297d7581c",
  license: "Creative Commons Attribution 4.0 International (CC BY 4.0)",
  license_url: "https://creativecommons.org/licenses/by/4.0/",
  attribution: "Clean Soul Kevin MacLeod (incompetech.com) Licensed under Creative Commons: By Attribution 4.0 https://creativecommons.org/licenses/by/4.0/",
  changes: "Excerpt from the start of the track, trimmed to the video length, volume lowered, fade-in and fade-out added, re-encoded to Opus.",
  details: "docs/music-license.md",
};
const MUSIC = process.env.MUSIC_FILE || join(REPO, ".cache", "music", "Clean Soul.mp3");
const MIX = { target_rms_dbfs: -23, peak_ceiling_dbfs: -6, fade_in_s: 3.0, fade_out_s: 5.0, start_offset_s: 0, opus_kbps: 128 };

function fail(msg) { console.error("mix_soundtrack: " + msg); process.exit(1); }
const sha256 = (p) => createHash("sha256").update(readFileSync(p)).digest("hex");

function findFfmpeg() {
  if (process.env.FFMPEG) return process.env.FFMPEG;
  const which = spawnSync(process.platform === "win32" ? "where" : "which", ["ffmpeg"], { encoding: "utf8" });
  if (which.status === 0 && which.stdout.trim()) return which.stdout.trim().split(/\r?\n/)[0];
  for (const base of [join(homedir(), "AppData/Local/ms-playwright"), join(homedir(), ".cache/ms-playwright")]) {
    if (!existsSync(base)) continue;
    for (const d of readdirSync(base).filter((d) => d.startsWith("ffmpeg")).sort().reverse()) {
      const exe = readdirSync(join(base, d)).find((f) => f.startsWith("ffmpeg"));
      if (exe) return join(base, d, exe);
    }
  }
  fail("ffmpeg not found (set FFMPEG=...)");
}

function findChrome() {
  const cands = [process.env.CHROME, "C:/Program Files/Google/Chrome/Application/chrome.exe",
    "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/usr/bin/google-chrome", "/usr/bin/chromium"];
  const hit = cands.find((c) => c && existsSync(c));
  if (!hit) fail("Chrome not found (set CHROME=...)");
  return hit;
}

// ------------------------------------------------------------------ checks
if (!existsSync(VIDEO) || !existsSync(MANIFEST)) fail("render the video first: python tools/make_replay_video.py");
if (!existsSync(MUSIC)) {
  fail(`music file not found: ${MUSIC}\n  Download it once (license: ${TRACK.license}; see ${TRACK.details}):\n` +
    `  PowerShell: Invoke-WebRequest "${TRACK.source_url}" -OutFile ".cache/music/Clean Soul.mp3"\n` +
    `  sh:         curl -L -o ".cache/music/Clean Soul.mp3" "${TRACK.source_url}"`);
}
if (sha256(MUSIC) !== TRACK.source_sha256) fail("music file checksum differs from the verified download; refusing to use it");
const manifest = JSON.parse(readFileSync(MANIFEST, "utf8"));
const DURATION = manifest.duration_s;

// --------------------------------------------------- serve + drive Chrome
const PAGE = "<!doctype html><meta charset=utf-8><title>mix</title>";
const server = createServer((req, res) => {
  if (req.url === "/music.mp3") { res.writeHead(200, { "content-type": "audio/mpeg" }); res.end(readFileSync(MUSIC)); }
  else { res.writeHead(200, { "content-type": "text/html" }); res.end(PAGE); }
}).listen(0, "127.0.0.1");
await new Promise((r) => server.once("listening", r));
const origin = `http://127.0.0.1:${server.address().port}`;
const work = mkdtempSync(join(tmpdir(), "mix-"));
const port = 9400 + Math.floor(Math.random() * 400);
const chrome = spawn(findChrome(), ["--headless=new", `--remote-debugging-port=${port}`, `--user-data-dir=${join(work, "profile")}`,
  "--autoplay-policy=no-user-gesture-required", `${origin}/`], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
let target;
for (let i = 0; i < 60 && !target; i++) {
  await sleep(250);
  try { target = (await (await fetch(`http://127.0.0.1:${port}/json`)).json()).find((t) => t.type === "page" && t.url.startsWith(origin)); } catch {}
}
if (!target) fail("could not connect to headless Chrome");
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => (ws.onopen = r));
let msgId = 0; const pending = new Map();
ws.onmessage = (m) => { const d = JSON.parse(m.data); if (d.id && pending.has(d.id)) { pending.get(d.id)(d); pending.delete(d.id); } };
const send = (method, params = {}) => new Promise((r) => { const i = ++msgId; pending.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });

await send("Page.enable");
await send("Page.navigate", { url: `${origin}/` });
for (let i = 0; i < 40; i++) {
  await sleep(150);
  const r = await send("Runtime.evaluate", { expression: "location.origin + '|' + document.readyState", returnByValue: true });
  if (r.result?.result?.value === `${origin}|complete`) break;
}
const script = `(async () => {
  const P = ${JSON.stringify({ ...MIX, duration: DURATION })};
  const SR = 48000;
  const data = await (await fetch(location.origin + '/music.mp3')).arrayBuffer();
  const src0 = await new OfflineAudioContext(2, SR, SR).decodeAudioData(data);
  const stats = (buf, a, b) => { let peak = 0, sum = 0, n = 0;
    for (let c = 0; c < buf.numberOfChannels; c++) { const d = buf.getChannelData(c);
      for (let i = Math.floor(a * buf.sampleRate); i < Math.min(d.length, Math.floor(b * buf.sampleRate)); i++) { const v = Math.abs(d[i]); if (v > peak) peak = v; sum += v * v; n++; } }
    const db = (x) => 20 * Math.log10(Math.max(x, 1e-9));
    return { peak_dbfs: +db(peak).toFixed(1), rms_dbfs: +db(Math.sqrt(sum / Math.max(n, 1))).toFixed(1) }; };
  const before = stats(src0, P.start_offset_s, P.start_offset_s + P.duration);
  const gainDb = Math.min(P.target_rms_dbfs - before.rms_dbfs, P.peak_ceiling_dbfs - before.peak_dbfs);
  const g = Math.pow(10, gainDb / 20);
  const off = new OfflineAudioContext(2, Math.ceil(P.duration * SR), SR);
  const s = off.createBufferSource(); s.buffer = src0;
  const gain = off.createGain();
  const curve = (from, to, n = 256) => Float32Array.from({ length: n }, (_, i) => { const x = i / (n - 1); const e = x * x * (3 - 2 * x); return from + (to - from) * e; });
  gain.gain.setValueAtTime(0, 0);
  gain.gain.setValueCurveAtTime(curve(0, g), 0, P.fade_in_s);
  gain.gain.setValueAtTime(g, P.duration - P.fade_out_s - 0.01);
  gain.gain.setValueCurveAtTime(curve(g, 0), P.duration - P.fade_out_s, P.fade_out_s);
  s.connect(gain).connect(off.destination);
  s.start(0, P.start_offset_s);
  const mixed = await off.startRendering();
  const after = stats(mixed, P.fade_in_s, P.duration - P.fade_out_s);
  const edges = { first_100ms: stats(mixed, 0, 0.1).peak_dbfs, last_100ms: stats(mixed, P.duration - 0.1, P.duration).peak_dbfs };
  // Encode in real time to Opus/WebM.
  const ac = new AudioContext({ sampleRate: SR }); await ac.resume();
  const dest = ac.createMediaStreamDestination();
  const play = ac.createBufferSource(); play.buffer = mixed; play.connect(dest);
  const rec = new MediaRecorder(dest.stream, { mimeType: 'audio/webm;codecs=opus', audioBitsPerSecond: P.opus_kbps * 1000 });
  const chunks = []; rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const done = new Promise((r) => (rec.onstop = r));
  rec.start(1000); play.start(); await new Promise((r) => (play.onended = r)); await new Promise((r) => setTimeout(r, 400));
  rec.stop(); await done;
  const blob = new Blob(chunks, { type: 'audio/webm' });
  const b64 = await new Promise((r) => { const fr = new FileReader(); fr.onload = () => r(fr.result.split(',')[1]); fr.readAsDataURL(blob); });
  return { b64, gain_db: +gainDb.toFixed(1), source_segment: before, mixed_body: after, edges, sample_rate: SR };
})()`;
console.log(`mix_soundtrack: rendering and encoding ${DURATION}s of audio in headless Chrome (real time)…`);
const res = await send("Runtime.evaluate", { expression: script, awaitPromise: true, returnByValue: true, timeout: (DURATION + 60) * 1000 });
ws.close(); chrome.kill(); server.close();
const out = res.result?.result?.value;
if (!out || !out.b64) fail("audio render failed: " + JSON.stringify(res.result?.exceptionDetails || res).slice(0, 500));

// ----------------------------------------------------------------- mux
const audioFile = join(work, "music.webm");
writeFileSync(audioFile, Buffer.from(out.b64, "base64"));
const ffmpeg = findFfmpeg();
const muxed = join(work, "demo-replay.webm");
const mux = spawnSync(ffmpeg, ["-y", "-loglevel", "error", "-i", VIDEO, "-i", audioFile, "-map", "0:v:0", "-map", "1:a:0",
  "-c", "copy", "-t", String(DURATION), muxed], { encoding: "utf8" });
if (mux.status !== 0) fail("ffmpeg mux failed: " + mux.stderr);
const probe = spawnSync(ffmpeg, ["-hide_banner", "-i", muxed], { encoding: "utf8" }).stderr;
const hasVideo = /Stream #0:0.*Video: vp8/.test(probe), hasAudio = /Stream #0:1.*Audio: opus/.test(probe);
if (!hasVideo || !hasAudio) fail("muxed file lacks the expected streams:\n" + probe);
renameSync(muxed, VIDEO);
rmSync(work, { recursive: true, force: true });

// ------------------------------------------------------------ metadata
const audio = {
  track: TRACK,
  codec: "opus", bitrate_kbps: MIX.opus_kbps, sample_rate: out.sample_rate, channels: 2,
  mix: { ...MIX, gain_db: out.gain_db, source_segment: out.source_segment, mixed_body: out.mixed_body, edges: out.edges },
  encoded_with: "Chrome Web Audio + MediaRecorder; muxed with ffmpeg stream copy (video stream unchanged)",
};
manifest.audio = audio;
manifest.audio_note = "Background music only; no narration. Credit: " + TRACK.attribution;
manifest.sha256 = sha256(VIDEO);
writeFileSync(MANIFEST, JSON.stringify(manifest, null, 2) + "\n");
const capText = readFileSync(CAPTIONS_JS, "utf8");
const cap = JSON.parse(capText.slice(capText.indexOf("= ") + 2).trim().replace(/;$/, ""));
cap.audio = { title: TRACK.title, artist: TRACK.artist, publisher: TRACK.publisher, license: TRACK.license,
  license_url: TRACK.license_url, source_url: TRACK.source_url, changes: TRACK.changes, attribution: TRACK.attribution };
writeFileSync(CAPTIONS_JS, capText.slice(0, capText.indexOf("window.REPLAY_CAPTIONS")) + "window.REPLAY_CAPTIONS = " + JSON.stringify(cap, null, 1) + ";\n");
console.log(`mix_soundtrack: done — gain ${out.gain_db} dB, body RMS ${out.mixed_body.rms_dbfs} dBFS, peak ${out.mixed_body.peak_dbfs} dBFS; streams: vp8 + opus`);
process.exit(0);
