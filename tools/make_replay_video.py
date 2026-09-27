"""Render the replay video of the recorded demo run.

    python tools/make_replay_video.py                 # encode site/media/demo-replay.webm
    python tools/make_replay_video.py --preview DIR   # stills per scene, no encoding

Method: every frame is drawn with Pillow from site/data/demo-run.js (itself generated from
demo-workspace/), then piped as JPEG into ffmpeg and encoded as VP8/WebM. It is a *replay
rendered from run artifacts* — not a screen recording — and says so on screen.

Story (each beat is a state change taken from the run data):
  initial graph -> new source -> staged proposal -> human decisions -> revised page ->
  expanded graph -> validation + audit log

Captions are burned into the frames (useful when muted) and also written as WebVTT, together
with a timed narration script for an optional voiceover. No audio track is produced.

Needs: Pillow and an ffmpeg with libvpx ($FFMPEG, PATH, or Playwright's bundled copy).
Writes: site/media/demo-replay.webm, demo-replay-poster.png, demo-replay.en.vtt,
        demo-replay.json (manifest), site/data/replay-captions.js, docs/video-narration-script.md
"""
from __future__ import annotations

import glob
import hashlib
import io
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from demo import read_site_data  # noqa: E402

MEDIA = REPO / "site" / "media"
SCRIPT_DOC = REPO / "docs" / "video-narration-script.md"
W, H, FPS, S = 1280, 720, 30, 2  # layout in 1280x720 units, rendered at S x for anti-aliasing

# Palette (matches the AI Systems Portfolio "Midnight AI" tokens)
BG = (8, 17, 31)
CARD = (18, 35, 58)
BORDER = (36, 56, 82)
TEXT = (248, 250, 252)
TEXT2 = (169, 184, 204)
MUTED = (116, 134, 158)
CYAN = (34, 211, 238)
VIOLET = (139, 92, 246)
BLUE = (59, 130, 246)
GREEN = (34, 197, 94)
AMBER = (245, 158, 11)
RED = (248, 113, 113)
SLATE = (120, 140, 168)


# ------------------------------------------------------------------ fonts
@lru_cache(maxsize=None)
def font(kind: str, size: int):
    names = {
        "bold": ["seguibl.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"],
        "semi": ["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"],
        "reg": ["segoeui.ttf", "DejaVuSans.ttf"],
        "mono": ["CascadiaMono.ttf", "consola.ttf", "DejaVuSansMono.ttf"],
    }[kind]
    for name in names:
        for folder in ("C:/Windows/Fonts", "/usr/share/fonts/truetype/dejavu", "/Library/Fonts"):
            path = os.path.join(folder, name)
            if os.path.exists(path):
                return ImageFont.truetype(path, size * S)
    return ImageFont.load_default(size * S)


# ------------------------------------------------------------------ easing
def clamp(x, a=0.0, b=1.0):
    return max(a, min(b, x))


def seg(t, a, b):
    """Progress of t through [a, b], 0..1."""
    return clamp((t - a) / (b - a)) if b > a else float(t >= b)


def ease(x):
    return 1 - (1 - clamp(x)) ** 3


def ease_io(x):
    x = clamp(x)
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def spring(x):
    x = clamp(x)
    return 1 + 2.7 * (x - 1) ** 3 + 1.7 * (x - 1) ** 2 if x < 1 else 1.0


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    return tuple(int(lerp(a, b, t)) for a, b in zip(c1, c2))


def rgba(c, a):
    return (c[0], c[1], c[2], int(255 * clamp(a)))


# ------------------------------------------------------------------ canvas
class Canvas:
    """Drawing in 1280x720 layout units on an S-times larger RGBA image."""

    def __init__(self, base: Image.Image):
        # RGB target + RGBA draw mode => Pillow alpha-blends translucent fills (it would not on RGBA).
        self.img = base.convert("RGB")
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def text(self, xy, s, f, fill, a=1.0, anchor="la"):
        if a > 0.01:
            self.d.text((xy[0] * S, xy[1] * S), s, font=f, fill=rgba(fill, a), anchor=anchor)

    def tlen(self, s, f):
        return self.d.textlength(s, font=f) / S

    def rrect(self, box, r, fill=None, outline=None, width=1, a=1.0, oa=None):
        x0, y0, x1, y1 = (v * S for v in box)
        self.d.rounded_rectangle((x0, y0, x1, y1), r * S, fill=rgba(fill, a) if fill else None,
                                 outline=rgba(outline, a if oa is None else oa) if outline else None,
                                 width=int(width * S))

    def line(self, p, q, color, width=2, a=1.0):
        if a > 0.01:
            self.d.line((p[0] * S, p[1] * S, q[0] * S, q[1] * S), fill=rgba(color, a), width=int(width * S))

    def dashed(self, p, q, color, width=2, a=1.0, dash=10, gap=8, progress=1.0):
        full = math.hypot(q[0] - p[0], q[1] - p[1])
        length = full * progress
        if length <= 0 or a <= 0.01:
            return
        ux, uy = (q[0] - p[0]) / full, (q[1] - p[1]) / full
        pos = 0.0
        while pos < length:
            e = min(pos + dash, length)
            self.line((p[0] + ux * pos, p[1] + uy * pos), (p[0] + ux * e, p[1] + uy * e), color, width, a)
            pos += dash + gap

    def circle(self, c, r, fill=None, outline=None, width=2, a=1.0):
        if a <= 0.01 or r <= 0:
            return
        x, y = c
        self.d.ellipse(((x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S),
                       fill=rgba(fill, a) if fill else None, outline=rgba(outline, a) if outline else None,
                       width=int(width * S))

    def glow(self, c, color, radius, a=1.0):
        if a <= 0.02:
            return
        spr = glow_sprite(color, int(radius), int(a * 10))
        self.img.paste(spr, (int(c[0] * S - spr.width / 2), int(c[1] * S - spr.height / 2)), spr)


@lru_cache(maxsize=None)
def glow_sprite(color, radius, level):
    size = radius * 2 * S
    spr = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(spr)
    peak = 110 * level / 10
    for i in range(18, 0, -1):
        r = size / 2 * i / 18
        d.ellipse((size / 2 - r, size / 2 - r, size / 2 + r, size / 2 + r), fill=color + (int(peak * (1 - i / 18) ** 2),))
    return spr.filter(ImageFilter.GaussianBlur(radius * S / 6))


def wrap(canvas, text, f, width):
    lines, line = [], ""
    for word in str(text).split():
        test = (line + " " + word).strip()
        if canvas.tlen(test, f) <= width:
            line = test
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def plain(md: str) -> str:
    md = re.sub(r"\[\[([^\]]+)\]\]", r"\1", md)
    md = md.replace("**", "").replace("*", "").replace("`", "")
    return re.sub(r"\s+", " ", md).strip()


def section(text: str, heading_prefix: str) -> str:
    """Plain text of the first Markdown section whose heading starts with heading_prefix."""
    m = re.search(r"^## " + re.escape(heading_prefix) + r".*?\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return plain(m.group(1)) if m else ""


def changed_lines(a: str, b: str) -> list[str]:
    """Lines of a that are not in b (ignoring the engine's `updated:` field)."""
    other = set(b.splitlines())
    return [ln for ln in a.splitlines() if ln.strip() and ln not in other and not ln.startswith("updated:")]


# ------------------------------------------------------------------ background
def make_background():
    img = Image.new("RGBA", (W * S, H * S), BG + (255,))
    over = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(over)
    for (cx, cy, r, col, a) in ((1080, 60, 480, VIOLET, 40), (120, 700, 520, CYAN, 22), (640, 360, 640, BLUE, 10)):
        d.ellipse(((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S), fill=col + (a,))
    img.alpha_composite(over.filter(ImageFilter.GaussianBlur(80 * S)))
    rnd = random.Random(7)
    d = ImageDraw.Draw(img)
    for _ in range(150):  # faint fixed star field
        x, y, r = rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(0.5, 1.2)
        d.ellipse(((x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S), fill=TEXT2 + (rnd.randint(16, 50),))
    return img


class Drift:
    """Slow drifting fragments — the ambient motion layer."""

    def __init__(self, n=44, seed=3):
        rnd = random.Random(seed)
        self.p = [(rnd.uniform(0, W), rnd.uniform(0, H), rnd.uniform(-7, 7), rnd.uniform(-4, 4),
                   rnd.uniform(1.0, 2.0), rnd.choice((CYAN, VIOLET, TEXT2))) for _ in range(n)]

    def draw(self, c, time):
        for x, y, vx, vy, r, col in self.p:
            c.circle(((x + vx * time) % W, (y + vy * time) % H), r, fill=col, a=0.32)


# ------------------------------------------------------------------ graph
def layout(data):
    g = data["graph"]
    nodes = [dict(n) for n in g["after"]["nodes"]]
    for i, n in enumerate(nodes):
        ang = 2 * math.pi * i / len(nodes)
        n.update(x=math.cos(ang) * 200, y=math.sin(ang) * 150, vx=0.0, vy=0.0)
    by = {n["id"]: n for n in nodes}
    pairs = {tuple(sorted(e)): e for e in g["after"]["edges"] + g["rejected_edges"]}
    for _ in range(600):
        for p in nodes:
            for q in nodes:
                if p is q:
                    continue
                dx, dy = p["x"] - q["x"], p["y"] - q["y"]
                d2 = max(dx * dx + dy * dy, 1)
                p["vx"] += dx / math.sqrt(d2) * 9000 / d2
                p["vy"] += dy / math.sqrt(d2) * 9000 / d2
        for a, b in pairs.values():
            p, q = by[a], by[b]
            dx, dy = q["x"] - p["x"], q["y"] - p["y"]
            dist = math.hypot(dx, dy) or 1
            f = (dist - 170) * 0.01
            p["vx"] += dx / dist * f; p["vy"] += dy / dist * f
            q["vx"] -= dx / dist * f; q["vy"] -= dy / dist * f
        for p in nodes:
            p["vx"] -= p["x"] * 0.004; p["vy"] -= p["y"] * 0.006
            p["x"] += p["vx"] * 0.5; p["y"] += p["vy"] * 0.5
            p["vx"] *= 0.6; p["vy"] *= 0.6
    xs, ys = [n["x"] for n in nodes], [n["y"] for n in nodes]
    for n in nodes:  # normalise to 0..1 so any box can host the graph
        n["u"] = (n["x"] - min(xs)) / ((max(xs) - min(xs)) or 1)
        n["v"] = (n["y"] - min(ys)) / ((max(ys) - min(ys)) or 1)
    return by, pairs


def short_title(title):
    t = title.replace("SAMPLE: ", "")
    return t if len(t) <= 24 else t[:22].rstrip(" —-") + "…"


class Graph:
    def __init__(self, data):
        g = data["graph"]
        self.by, self.pairs = layout(data)
        self.before_nodes = {n["id"] for n in g["before"]["nodes"]}
        self.before_pairs = {tuple(sorted(e)) for e in g["before"]["edges"]}
        self.after_pairs = {tuple(sorted(e)) for e in g["after"]["edges"]}
        self.rejected_pairs = {tuple(sorted(e)) for e in g["rejected_edges"]}
        self.touched = g["touched"]

    def pos(self, nid, box):
        x0, y0, x1, y1 = box
        n = self.by[nid]
        return (lerp(x0, x1, n["u"]), lerp(y0, y1, n["v"]))

    def draw(self, c, box, *, alpha=1.0, grow=None, edge_progress=None, rejected=0.0, highlight=None,
             labels=True, pulse=0.0, ring=None, show_state=False):
        """grow: node id -> 0..1 scale (default: before-state nodes only).
        edge_progress: pair -> 0..1 draw progress for edges added by the run.
        show_state: colour nodes by what the run did to them."""
        grow = grow or {}
        edge_progress = edge_progress or {}
        for key, (a, b) in self.pairs.items():
            pa, pb = self.pos(a, box), self.pos(b, box)
            if key in self.before_pairs:
                c.line(pa, pb, SLATE, 1.6, 0.45 * alpha)
            elif key in self.after_pairs:
                p = edge_progress.get(key, 0.0)
                if p > 0:
                    c.line(pa, (lerp(pa[0], pb[0], p), lerp(pa[1], pb[1], p)), CYAN, 2.4, 0.85 * alpha)
            elif key in self.rejected_pairs and rejected > 0:
                c.dashed(pa, pb, RED, 2, 0.8 * alpha * rejected)
        for nid, n in self.by.items():
            s = grow.get(nid, 1.0 if nid in self.before_nodes else 0.0)
            if s <= 0.01:
                continue
            x, y = self.pos(nid, box)
            state = self.touched.get(nid) if show_state else None
            col = CYAN if state == "created" else VIOLET if state == "updated" else BLUE if n["type"] == "source" else SLATE
            r = (11 if n["type"] == "source" else 14) * s
            if highlight == nid or state:
                c.glow((x, y), col if state else VIOLET, 44 + 10 * pulse, alpha * (0.75 + 0.25 * pulse))
            c.circle((x, y), r + 3, fill=BG, a=alpha)
            c.circle((x, y), r, fill=VIOLET if highlight == nid and not state else col, a=alpha)
            if ring and nid in ring:
                c.circle((x, y), r + 7, outline=ring[nid], width=2, a=alpha)
            if labels and s > 0.6:
                c.text((x, y + r + 10), short_title(n["title"]), font("semi", 15), TEXT, alpha * seg(s, 0.6, 1), anchor="ma")


# ------------------------------------------------------------------ chrome
STEPS = ["Knowledge", "Source", "Proposal", "Human review", "Revision", "Graph", "Audit"]


def chrome(c, step, mode_label):
    c.text((40, 30), "Second Brain Ingest Lab", font("semi", 17), TEXT, 0.9)
    pill = f"REPLAY · {mode_label} RUN"
    pw = c.tlen(pill, font("mono", 13)) + 26
    c.rrect((W - 40 - pw, 24, W - 40, 52), 14, fill=AMBER, a=0.14, outline=AMBER, oa=0.7)
    c.text((W - 40 - pw / 2, 38), pill, font("mono", 13), AMBER, anchor="mm")
    # process rail: where we are in the ingest (the graph is one stage, not the process)
    x0, x1, y = 330, W - 330, 38
    for i, name in enumerate(STEPS):
        x = lerp(x0, x1, i / (len(STEPS) - 1))
        active, done = i == step, i < step
        if i:
            px = lerp(x0, x1, (i - 1) / (len(STEPS) - 1))
            c.line((px + 7, y), (x - 7, y), CYAN if (done or active) else BORDER, 2, 0.8)
        c.circle((x, y), 5.5 if active else 4, fill=CYAN if (active or done) else BORDER)
        if active:
            c.glow((x, y), CYAN, 18, 0.9)
            c.text((x, y + 13), name, font("semi", 13), CYAN, anchor="ma")


def caption(c, text, a):
    if not text or a <= 0:
        return
    f = font("semi", 25)
    lines = wrap(c, text, f, 980)
    h = 38 * len(lines) + 22
    y0 = H - 28 - h
    widest = max(c.tlen(line, f) for line in lines)
    c.rrect((W / 2 - widest / 2 - 26, y0, W / 2 + widest / 2 + 26, H - 28), 14, fill=(4, 9, 18), a=0.9 * a,
            outline=(51, 80, 122), oa=0.9 * a)
    for i, line in enumerate(lines):
        c.text((W / 2, y0 + 11 + i * 38), line, f, TEXT, a, anchor="ma")


def card(c, box, a=1.0, accent=None):
    if a <= 0.01:
        return
    c.rrect(box, 14, fill=CARD, a=0.92 * a, outline=BORDER, oa=a)
    if accent:
        x0, y0, x1, y1 = box
        c.rrect((x0, y0 + 14, x0 + 4, y1 - 14), 2, fill=accent, a=a)


def chip(c, xy, label, color, a=1.0, size=14):
    f = font("mono", size)
    w = c.tlen(label, f) + 22
    if a > 0.01:
        c.rrect((xy[0], xy[1], xy[0] + w, xy[1] + size + 14), 8, fill=color, a=0.16 * a, outline=color, oa=0.8 * a)
        c.text((xy[0] + 11, xy[1] + 6), label, f, color, a)
    return w


# ------------------------------------------------------------------ scenes
class Scene:
    def __init__(self, key, step, seconds, cues, draw):
        self.key, self.step, self.seconds, self.cues, self.draw = key, step, seconds, cues, draw


def build(data):
    run = data["run"]
    mock = run["mode"] == "mock"
    graph = Graph(data)
    drift = Drift()
    changes = data["changes"]
    con = data["proposal"]["contradictions"][0]
    approved = [c for c in changes if c["decision"] == "approve"]
    edited = [c for c in approved if c["edited_by_reviewer"]]
    rejected = [c for c in changes if c["decision"] == "reject"]
    created = [c for c in approved if c["action"] == "create"]
    plain_ok = len(approved) - len(edited)
    sb, sa = data["before"]["validation"]["stats"], data["after"]["validation"]["stats"]
    va = data["after"]["validation"]
    target = con["page"]
    before_concl = section(data["before"]["pages"][target]["text"], "Current conclusion")
    after_concl = section(data["after"]["pages"][target]["text"], "Current conclusion")
    status_before = data["before"]["pages"][target]["status"]
    status_after = data["after"]["pages"][target]["status"]
    source_title = data["proposal"]["source_title"].replace("SAMPLE: ", "")
    flag_phrases = [re.sub(r"^.*?'(.*)'$", r"\1", f) for f in data["source"]["flags"]]
    new_pairs = sorted(graph.after_pairs - graph.before_pairs)
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight"}
    num = lambda n: words.get(n, str(n))  # noqa: E731
    right_box = (600, 160, 1170, 500)
    center_box = (270, 170, 1010, 500)
    chip_y = [150 + i * 70 for i in range(len(changes))]
    scenes = []

    # 1 — intro: scattered fragments coalesce into the existing knowledge graph
    rnd = random.Random(11)
    frags = [(rnd.uniform(40, W - 40), rnd.uniform(90, H - 140), rnd.choice(sorted(graph.before_nodes)),
              rnd.choice((CYAN, VIOLET)), rnd.uniform(0.0, 1.6), rnd.uniform(0, 2 * math.pi), rnd.uniform(14, 34))
             for _ in range(90)]

    def s_intro(c, t, T):
        drift.draw(c, T)
        for x, y, nid, col, delay, ang, orbit in frags:
            k = ease_io(seg(t, 0.3 + delay, 3.2 + delay))
            tx, ty = graph.pos(nid, right_box)
            # approach a loose orbit around the node, then collapse into it
            o = orbit * (1 - seg(t, 3.6, 4.8)) * k
            ox, oy = tx + math.cos(ang + T * 0.8) * o, ty + math.sin(ang + T * 0.8) * o
            c.circle((lerp(x, ox, k), lerp(y, oy, k)), 2.2, fill=col, a=0.85 * (1 - seg(t, 4.4, 5.2)))
        graph.draw(c, right_box, alpha=seg(t, 3.8, 5.0), labels=t > 4.6)
        a = ease(seg(t, 0.2, 1.4))
        c.text((70, 180), "A second brain", font("bold", 50), TEXT, a)
        c.text((70, 240), "that asks before", font("bold", 50), TEXT, a)
        c.text((70, 300), "it learns.", font("bold", 50), CYAN, a)
        c.text((72, 382), "Human-guided ingest into a linked Markdown wiki", font("reg", 21), TEXT2, ease(seg(t, 0.8, 2.0)))
        chip(c, (72, 424), f"Replay of a recorded {run['mode']} run", AMBER, ease(seg(t, 1.2, 2.4)), 15)

    scenes.append(Scene("intro", 0, 7.5, [
        (0.2, f"A replay of a recorded {run['mode']} run of the ingest pipeline."),
        (3.8, "A small wiki learns from one new source, but only with a human's approval."),
    ], s_intro))

    # 2 — the knowledge before: the conclusion that will be contradicted
    def s_before(c, t, T):
        drift.draw(c, T)
        pulse = 0.5 + 0.5 * math.sin(T * 3)
        graph.draw(c, right_box, highlight=target if t > 1.5 else None, pulse=pulse)
        a = ease(seg(t, 0.3, 1.2))
        c.text((70, 130), f"{sb['pages']} pages · {sb['links']} links", font("bold", 34), TEXT, a)
        c.text((70, 176), "The wiki before the ingest", font("reg", 19), TEXT2, a)
        ca = ease(seg(t, 1.6, 2.6))
        card(c, (60, 230, 530, 470), ca, accent=VIOLET)
        c.text((86, 252), f"{target} · current conclusion", font("mono", 14), VIOLET, ca)
        for i, line in enumerate(wrap(c, "“" + con["existing_claim"] + "”", font("semi", 25), 410)[:5]):
            c.text((86, 288 + i * 36), line, font("semi", 25), TEXT, ca)
        x, y = graph.pos(target, right_box)
        c.dashed((530, 350), (x - 24, y), VIOLET, 1.6, 0.7 * ca, progress=ease(seg(t, 2.2, 3.2)))

    scenes.append(Scene("before", 0, 7.0, [
        (0.2, f"The wiki starts with {num(sb['pages'])} linked pages about evaluating RAG systems."),
        (3.4, "One page concludes that a high faithfulness score means the answer is correct."),
    ], s_before))

    # 3 — new source: key facts, the flagged instruction, fragments flowing toward the wiki
    def s_source(c, t, T):
        drift.draw(c, T)
        graph.draw(c, right_box, alpha=0.35, labels=False)
        x0 = lerp(-560, 60, ease(seg(t, 0.0, 0.9)))
        card(c, (x0, 100, x0 + 580, 560), 1.0, accent=BLUE)
        c.text((x0 + 28, 122), "raw/ · new source · immutable, hashed", font("mono", 14), BLUE)
        tl = wrap(c, source_title, font("bold", 25), 520)[:2]
        for i, line in enumerate(tl):
            c.text((x0 + 28, 152 + i * 34), line, font("bold", 25), TEXT)
        y = 160 + 34 * len(tl) + 10
        fa = ease(seg(t, 1.2, 2.2))
        for line in wrap(c, con["new_evidence"], font("semi", 23), 520)[:4]:
            c.text((x0 + 28, y), line, font("semi", 23), TEXT, fa)
            y += 33
        y += 16
        ia = ease(seg(t, 4.2, 5.0))
        c.rrect((x0 + 20, y, x0 + 560, y + 140), 10, fill=RED, a=0.10 * ia, outline=RED, oa=0.7 * ia)
        c.text((x0 + 36, y + 14), "instruction hidden in the source", font("mono", 14), RED, ia)
        for i, ph in enumerate(flag_phrases[:2]):
            line = wrap(c, f"“{ph}”", font("semi", 20), 500)[0]
            c.text((x0 + 36, y + 42 + i * 30), line, font("semi", 20), TEXT, ia)
        chip(c, (x0 + 36, y + 102), "flagged · treated as data · model has no tools", RED, ease(seg(t, 5.2, 6.0)), 13)
        rnd2 = random.Random(5)
        for _ in range(28):
            st, sx, sy = rnd2.uniform(1.8, 6.8), x0 + rnd2.uniform(60, 540), rnd2.uniform(180, 380)
            nid = rnd2.choice(sorted(graph.before_nodes))
            k = ease_io(seg(t, st, st + 1.6))
            if 0 < k < 1:
                tx, ty = graph.pos(nid, right_box)
                c.circle((lerp(sx, tx, k), lerp(sy, ty, k)), 2.4, fill=CYAN, a=0.9 * math.sin(k * math.pi))

    scenes.append(Scene("source", 1, 8.5, [
        (0.2, "A new source arrives: a fictional incident review."),
        (2.6, "An answer scored high on faithfulness, yet it relied on a superseded policy."),
        (5.4, "A hidden instruction to AI assistants is flagged and treated as data."),
    ], s_source))

    # 4 — proposal: change cards with dashed "proposed" links to their target pages
    def s_proposal(c, t, T):
        drift.draw(c, T)
        graph.draw(c, right_box, alpha=0.9)
        chip(c, (60, 102), "MOCK FIXTURE · hand-authored, not model output" if mock else "LLM proposal",
             AMBER if mock else CYAN, ease(seg(t, 0.2, 0.9)), 13)
        for i, ch in enumerate(changes):
            a = ease(seg(t, 0.6 + i * 0.45, 1.3 + i * 0.45))
            if a <= 0:
                continue
            y = chip_y[i]
            col = CYAN if ch["action"] == "create" else VIOLET
            card(c, (60, y, 480, y + 56), a)
            c.text((78, y + 9), f"{ch['change_id']} · {ch['action']}", font("mono", 14), col, a)
            c.text((78, y + 28), short_title(ch["page_id"].replace("src-", "source: ")), font("semi", 19), TEXT, a)
            tx, ty = graph.pos(ch["page_id"], right_box)
            c.dashed((480, y + 28), (tx, ty), col, 1.6, 0.7 * a, progress=ease(seg(t, 1.0 + i * 0.45, 2.0 + i * 0.45)))
            if ch["action"] == "create":
                c.circle((tx, ty), 13, outline=CYAN, width=2, a=0.9 * a)
                c.text((tx, ty + 24), "proposed", font("mono", 13), CYAN, a, anchor="ma")
        c.text((70, 516), "Staged in proposals/ — nothing written to the wiki yet", font("semi", 19), TEXT2,
               ease(seg(t, 4.2, 5.0)))

    scenes.append(Scene("proposal", 2, 8.0, [
        (0.2, f"The ingest compares the source with the wiki and stages {num(len(changes))} proposed changes."),
        (3.6, ("In this run the proposal is a hand-authored fixture, not live model output. " if mock else "")
         + "Nothing is written yet."),
    ], s_proposal))

    # 5 — human review: decisions stamped one by one; then the reviewer's correction
    def s_review(c, t, T):
        drift.draw(c, T)
        c.text((60, 108), "Decisions replayed from a pre-recorded decisions file" if mock else "Reviewer decisions",
               font("semi", 16), TEXT2, ease(seg(t, 0.1, 0.8)))
        rej_visible = 1.0
        for i, ch in enumerate(changes):
            y = chip_y[i]
            stamp = ease(seg(t, 1.0 + i * 1.0, 1.4 + i * 1.0))
            kind = "reject" if ch["decision"] == "reject" else "edited" if ch["edited_by_reviewer"] else "approve"
            col = {"approve": GREEN, "edited": VIOLET, "reject": RED}[kind]
            fade = 1 - 0.5 * stamp if kind == "reject" else 1.0
            card(c, (60, y, 480, y + 56), fade)
            if stamp > 0:
                c.rrect((60, y, 480, y + 56), 14, outline=col, width=2, oa=stamp * fade)
            c.text((78, y + 9), f"{ch['change_id']} · {ch['action']}", font("mono", 14), MUTED, fade)
            c.text((78, y + 28), short_title(ch["page_id"].replace("src-", "source: ")), font("semi", 19), TEXT, fade)
            label = {"approve": "APPROVED", "edited": "EDITED + APPROVED", "reject": "REJECTED"}[kind]
            if stamp > 0:
                lw = c.tlen(label, font("mono", 13)) + 20
                c.rrect((468 - lw, y + 15, 468, y + 41), 8, fill=col, a=0.18 * stamp, outline=col, oa=stamp)
                c.text((468 - lw / 2, y + 28), label, font("mono", 13), col, stamp, anchor="mm")
            if kind == "reject":
                rej_visible = 1 - stamp
        ea = ease(seg(t, 6.4, 7.2)) if edited else 0.0
        graph.draw(c, right_box, alpha=0.9 * (1 - ea) + 0.2 * ea, rejected=rej_visible, labels=ea < 0.5)
        if ea > 0:
            ch = edited[0]
            removed = plain(" ".join(changed_lines(ch["proposed_text"], ch["final_text"])))
            added = plain(" ".join(changed_lines(ch["final_text"], ch["proposed_text"])))
            card(c, (530, 140, 1230, 530), ea, accent=VIOLET)
            c.text((556, 162), f"{ch['change_id']} · {ch['page_id']} · reviewer's correction", font("mono", 14), VIOLET, ea)
            y = 200
            strike = ease(seg(t, 7.2, 8.0))
            for line in wrap(c, removed, font("semi", 23), 630)[:3]:
                c.text((556, y), line, font("semi", 23), RED, ea)
                c.line((556, y + 17), (556 + c.tlen(line, font("semi", 23)) * strike, y + 17), RED, 2, ea)
                y += 34
            y += 14
            for line in wrap(c, added, font("semi", 23), 630)[:3]:
                c.text((556, y), line, font("semi", 23), GREEN, ea * ease(seg(t, 7.8, 8.6)))
                y += 34
            y += 14
            for line in wrap(c, "Reviewer note: " + ch["note"], font("reg", 18), 630)[:3]:
                c.text((556, y), line, font("reg", 18), TEXT2, ea * ease(seg(t, 8.4, 9.2)))
                y += 26

    scenes.append(Scene("review", 3, 11.5, [
        (0.2, "A human decides each change." + (" Here the decisions are replayed from a pre-recorded file." if mock else "")),
        (3.8, f"{num(plain_ok).capitalize()} approved as proposed; {num(len(rejected))} misreading rejected, so it never reaches the wiki."),
        (7.2, f"{num(len(edited)).capitalize()} overreach is corrected by the reviewer, then approved."),
    ], s_review))

    # 6 — the revised existing page
    def s_revision(c, t, T):
        drift.draw(c, T)
        c.text((70, 100), f"wiki/concepts/{target}.md", font("mono", 18), CYAN, ease(seg(t, 0.0, 0.6)))
        a1 = ease(seg(t, 0.2, 1.0))
        card(c, (60, 136, 620, 540), a1, accent=RED)
        c.text((86, 158), "BEFORE · current conclusion", font("mono", 14), MUTED, a1)
        chip(c, (500, 152), status_before, SLATE, a1, 13)
        strike = ease(seg(t, 2.0, 3.4))
        y = 198
        for line in wrap(c, before_concl, font("semi", 24), 500)[:7]:
            c.text((86, y), line, font("semi", 24), mix(TEXT, MUTED, strike), a1)
            c.line((86, y + 18), (86 + c.tlen(line, font("semi", 24)) * strike, y + 18), RED, 2, a1)
            y += 36
        a2 = ease(seg(t, 2.8, 3.6))
        card(c, (660, 136, 1220, 540), a2, accent=GREEN)
        c.text((686, 158), "AFTER · current conclusion (revised)", font("mono", 14), MUTED, a2)
        chip(c, (1076, 152), status_after, AMBER if status_after == "needs-review" else GREEN, ease(seg(t, 6.2, 7.0)), 13)
        lines = wrap(c, after_concl, font("semi", 24), 500)[:9]
        budget = int(sum(len(line) for line in lines) * seg(t, 3.4, 6.6))
        y = 198
        for line in lines:
            c.text((686, y), line[: max(0, budget)], font("semi", 24), TEXT, a2)
            budget -= len(line)
            y += 36

    scenes.append(Scene("revision", 4, 9.5, [
        (0.2, "The existing conclusion is narrowed, not silently overwritten."),
        (4.2, "Faithfulness becomes necessary but not sufficient, and the page is flagged for review."),
    ], s_revision))

    # 7 — the expanded graph (the effect of the ingest)
    def s_graph(c, t, T):
        drift.draw(c, T)
        grow = {nid: 1.0 for nid in graph.before_nodes}
        for i, ch in enumerate(created):
            grow[ch["page_id"]] = spring(seg(t, 0.8 + i * 0.6, 1.8 + i * 0.6))
        ep = {p: ease(seg(t, 2.0 + i * 0.25, 3.0 + i * 0.25)) for i, p in enumerate(new_pairs)}
        ring = {target: AMBER} if status_after == "needs-review" and t > 4.5 else None
        graph.draw(c, center_box, grow=grow, edge_progress=ep, pulse=0.5 + 0.5 * math.sin(T * 3.2), ring=ring,
                   rejected=0.4 * seg(t, 4.0, 5.0), show_state=True)
        k = ease(seg(t, 2.0, 5.0))
        c.text((70, 100), f"{round(lerp(sb['pages'], sa['pages'], k))} pages", font("bold", 30), TEXT)
        c.text((70, 138), f"{round(lerp(sb['links'], sa['links'], k))} links", font("bold", 30), CYAN)
        for i, (lab, col) in enumerate((("created page", CYAN), ("updated page", VIOLET), ("needs review", AMBER),
                                        ("rejected link", RED))):
            la = ease(seg(t, 4.6 + i * 0.2, 5.2 + i * 0.2))
            c.circle((1050, 108 + i * 26), 6, fill=col, a=la)
            c.text((1066, 108 + i * 26), lab, font("reg", 16), TEXT2, la, anchor="lm")

    scenes.append(Scene("graph", 5, 8.5, [
        (0.2, f"The graph shows the effect: {num(len(created))} new pages, revised pages and new links."),
        (4.4, f"{num(sa['pages']).capitalize()} pages and {sa['links']} links, up from {num(sb['pages'])} and {sb['links']}."),
    ], s_graph))

    # 8 — validation and audit
    checks = ["Every [[link]] resolves", "Cited sources exist", "Raw source unchanged (sha256)",
              "No duplicate pages or titles", "Index matches the pages"]
    log = data["after"]["log"]
    entry = log[log.rfind("\n## [") + 1:].strip().splitlines()
    log_lines = [ln for ln in entry if ln.startswith(("- approved", "- rejected"))]

    def s_audit(c, t, T):
        drift.draw(c, T)
        card(c, (60, 100, 600, 530), ease(seg(t, 0.0, 0.6)), accent=GREEN)
        c.text((86, 122), "VALIDATION", font("mono", 14), MUTED)
        for i, chk in enumerate(checks):
            a = ease(seg(t, 0.6 + i * 0.35, 1.0 + i * 0.35))
            c.circle((100, 176 + i * 44), 12, fill=GREEN, a=0.2 * a)
            cy = 176 + i * 44
            c.line((94, cy), (99, cy + 5), GREEN, 2.4, a)
            c.line((99, cy + 5), (107, cy - 5), GREEN, 2.4, a)
            c.text((126, 176 + i * 44), chk, font("semi", 21), TEXT, a, anchor="lm")
        ra = ease(seg(t, 2.6, 3.2))
        c.text((86, 408), "PASSED" if va["ok"] else "FAILED", font("bold", 30), GREEN if va["ok"] else RED, ra)
        for i, w in enumerate(va["warnings"][:2]):
            c.text((86, 454 + i * 26), "warning · " + w.replace(": status is ", " is "), font("reg", 18), AMBER, ra)
        la = ease(seg(t, 3.4, 4.0))
        card(c, (640, 100, 1220, 410), la, accent=CYAN)
        c.text((666, 122), "wiki/log.md · appended entry", font("mono", 14), MUTED, la)
        for i, line in enumerate(log_lines[:5]):
            a = ease(seg(t, 3.8 + i * 0.3, 4.2 + i * 0.3))
            txt = plain(line[2:].split(" — ")[0])
            txt = txt if len(txt) <= 50 else txt[:48] + "…"
            c.text((666, 164 + i * 46), txt, font("mono", 18), RED if line.startswith("- rejected") else TEXT, a)
        na = ease(seg(t, 6.0, 6.8))
        card(c, (640, 430, 1220, 530), na, accent=SLATE)
        c.text((666, 452), "Repeat ingest of the same source", font("semi", 21), TEXT, na)
        c.text((666, 488), "no-op · no new run, page or log entry", font("mono", 17), CYAN, na)

    warn_line = (f"Validation passes with {num(len(va['warnings']))} warning: the revised page needs review."
                 if va["ok"] and len(va["warnings"]) == 1 else
                 "Validation checks links, cited sources, raw hashes and duplicates.")
    scenes.append(Scene("audit", 6, 9.0, [
        (0.2, warn_line),
        (3.6, "An append-only log records what was approved and what was rejected."),
        (6.0, "Ingesting the same source again changes nothing."),
    ], s_audit))

    # 9 — outro
    def s_outro(c, t, T):
        drift.draw(c, T)
        graph.draw(c, (720, 170, 1190, 470), alpha=0.5, grow={nid: 1.0 for nid in graph.by},
                   edge_progress={p: 1 for p in new_pairs}, labels=False, show_state=True)
        a = ease(seg(t, 0.2, 1.0))
        c.text((70, 150), "Knowledge changes only", font("bold", 40), TEXT, a)
        c.text((70, 200), "after a human says yes.", font("bold", 40), CYAN, a)
        for i, (big, small) in enumerate(((str(len(changes)), "proposed"),
                                          (str(len(approved)), f"approved ({len(edited)} edited)"),
                                          (str(len(rejected)), "rejected"))):
            ba = ease(seg(t, 0.8 + i * 0.3, 1.4 + i * 0.3))
            c.text((70 + i * 200, 280), big, font("bold", 44), TEXT, ba)
            c.text((70 + i * 200, 338), small, font("reg", 18), TEXT2, ba)
        foot = f"Replay rendered from the artifacts of recorded {run['mode']} run {run['run_id']}."
        if mock:
            foot += " Proposal: hand-authored fixture. Decisions: pre-recorded file."
        for i, line in enumerate(wrap(c, foot, font("reg", 16), 600)):
            c.text((70, 400 + i * 24), line, font("reg", 16), MUTED, ease(seg(t, 2.0, 2.8)))

    scenes.append(Scene("outro", 6, 6.5, [
        (0.3, "The same review and apply path serves a live Claude run." + (" This replay shows the recorded mock run." if mock else "")),
    ], s_outro))
    return scenes


# ------------------------------------------------------------------ output helpers
def find_ffmpeg() -> str:
    for cand in (os.environ.get("FFMPEG"), shutil.which("ffmpeg")):
        if cand:
            return cand
    home = Path.home()
    for pattern in ("AppData/Local/ms-playwright/ffmpeg-*/ffmpeg-*.exe", ".cache/ms-playwright/ffmpeg-*/ffmpeg-*"):
        hits = sorted(glob.glob(str(home / pattern)))
        if hits:
            return hits[-1]
    sys.exit("ffmpeg not found: set FFMPEG=path/to/ffmpeg (needs the libvpx encoder)")


def timeline(scenes):
    """Absolute caption cues: (start, end, text)."""
    cues, start = [], 0.0
    for sc in scenes:
        rel = sc.cues + [(sc.seconds, None)]
        for (a, text), (b, _) in zip(rel, rel[1:]):
            cues.append((round(start + a, 2), round(start + b - 0.2, 2), text))
        start += sc.seconds
    return cues


def ts(x):
    m, s = divmod(x, 60)
    return f"00:{int(m):02d}:{s:06.3f}"


def write_vtt(cues, path):
    out = ["WEBVTT", "", "NOTE Captions for the replay of the recorded demo run. Also burned into the video.", ""]
    for i, (a, b, text) in enumerate(cues, 1):
        out += [str(i), f"{ts(a)} --> {ts(b)}", text, ""]
    path.write_text("\n".join(out), encoding="utf-8")


def write_script(cues, scenes, data, path):
    words = sum(len(t.split()) for _, _, t in cues)
    total = sum(sc.seconds for sc in scenes)
    lines = [
        "# Narration script — replay video",
        "",
        "GENERATED by `python tools/make_replay_video.py` from the recorded run data. Edit the cue text in",
        "that script, not here. The same lines are burned into the video as captions and written to",
        "`site/media/demo-replay.en.vtt`.",
        "",
        f"- Run: `{data['run']['run_id']}` (mode: **{data['run']['mode']}**)",
        f"- Length: {total:.1f} s · {words} words (~{words / total * 60:.0f} words per minute; "
        + ("comfortable for voiceover)" if words / total * 60 <= 160 else
           "brisk for a voiceover — typical narration is ~150 wpm, so trim lines or lengthen scenes before recording)"),
        "- Status: **ready for review — not recorded.** The published video has burned-in captions and no narration;",
        "  background music is added separately by `node tools/mix_soundtrack.mjs` (see `docs/music-license.md`).",
        "",
        "Why no voiceover yet: the only local English voice on the build machine is the legacy Windows SAPI",
        "voice (\"Microsoft Zira Desktop\"), which sounds robotic, and the available ffmpeg build cannot encode",
        "audio. After approval, record these lines (own voice or an approved TTS service), mix them over the",
        "existing music bed with the music ducked a few dB (e.g. ffmpeg `amix`/`sidechaincompress` with libopus),",
        "and keep the music credit in place.",
        "",
        "| Time | Line |",
        "|---|---|",
    ]
    lines += [f"| {ts(a)[3:8]}–{ts(b)[3:8]} | {text} |" for a, b, text in cues]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_frame(bg, sc, t, T, cues_abs, mode_label):
    c = Canvas(bg)
    sc.draw(c, t, T)
    chrome(c, sc.step, mode_label)
    for a, b, txt in cues_abs:
        if a <= T <= b:
            caption(c, txt, min(seg(T, a, a + 0.25), 1 - seg(T, b - 0.25, b)))
            break
    img = c.img.resize((W, H), Image.LANCZOS)
    fade = min(seg(t, 0, 0.35), 1 - seg(t, sc.seconds - 0.3, sc.seconds))
    return Image.blend(Image.new("RGB", (W, H), BG), img, clamp(fade)) if fade < 1 else img


def main(preview: str | None = None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    data = read_site_data()
    scenes = build(data)
    cues = timeline(scenes)
    bg = make_background().convert("RGB")
    mode_label = data["run"]["mode"].upper()

    if preview:
        out = Path(preview)
        out.mkdir(parents=True, exist_ok=True)
        start = 0.0
        for i, sc in enumerate(scenes):
            for frac in (0.5, 0.97):
                t = sc.seconds * frac
                render_frame(bg, sc, t, start + t, cues, mode_label).save(out / f"{i + 1:02d}-{sc.key}-{int(frac * 100)}.png")
            start += sc.seconds
        print(f"wrote previews to {out}")
        return

    MEDIA.mkdir(parents=True, exist_ok=True)
    out = MEDIA / "demo-replay.webm"
    cmd = [find_ffmpeg(), "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(FPS),
           "-i", "pipe:0", "-c:v", "libvpx", "-b:v", "1800k", "-crf", "10", "-qmin", "2", "-qmax", "30", "-an", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    frames, start, poster, manifest_scenes = 0, 0.0, None, []
    for i, sc in enumerate(scenes):
        n = int(round(sc.seconds * FPS))
        for f in range(n):
            t = f / FPS
            img = render_frame(bg, sc, t, start + t, cues, mode_label)
            if sc.key == "graph" and f == n - int(FPS * 0.6):
                poster = img.copy()
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=93)
            proc.stdin.write(buf.getvalue())
            frames += 1
        manifest_scenes.append({"key": sc.key, "stage": STEPS[sc.step], "start_s": round(start, 2), "seconds": sc.seconds})
        start += sc.seconds
        print(f"  scene {i + 1}/{len(scenes)}: {sc.key}")
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed")
    poster.save(MEDIA / "demo-replay-poster.png")
    write_vtt(cues, MEDIA / "demo-replay.en.vtt")
    captions_js = REPO / "site" / "data" / "replay-captions.js"
    captions_js.write_text(
        "// GENERATED by `python tools/make_replay_video.py`. Caption cues of media/demo-replay.webm.\n"
        "window.REPLAY_CAPTIONS = " + json.dumps({
            "run_id": data["run"]["run_id"], "duration_s": round(frames / FPS, 1),
            "cues": [{"start": a, "end": b, "text": text} for a, b, text in cues]}, indent=1, ensure_ascii=False) + ";\n",
        encoding="utf-8")
    write_script(cues, scenes, data, SCRIPT_DOC)
    site_js = REPO / "site" / "data" / "demo-run.js"
    manifest = {
        "method": "replay rendered with Pillow from site/data/demo-run.js (generated from demo-workspace/); "
                  "encoded with ffmpeg (VP8/WebM). Not a screen recording.",
        "run_id": data["run"]["run_id"],
        "mode": data["run"]["mode"],
        "proposal_origin": "hand-authored mock fixture" if data["run"]["mode"] == "mock" else "LLM",
        "reviewer": data["honesty"]["reviewer"],
        "captions": {"burned_in": True, "vtt": "demo-replay.en.vtt", "cues": len(cues)},
        "audio": None,
        "audio_note": "Silent render. Background music is muxed in by tools/mix_soundtrack.mjs; narration script: docs/video-narration-script.md.",
        "source_data_sha256": hashlib.sha256(site_js.read_bytes()).hexdigest(),
        "sha256": hashlib.sha256(out.read_bytes()).hexdigest(),
        "fps": FPS, "frames": frames, "duration_s": round(frames / FPS, 1), "size": [W, H],
        "scenes": manifest_scenes,
    }
    (MEDIA / "demo-replay.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(REPO)} ({out.stat().st_size // 1024} KiB, {manifest['duration_s']} s)")


if __name__ == "__main__":
    main(sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == "--preview" else None)
