#!/usr/bin/env python3
"""IAMRITA Arcade Zone generator.

Outputs (to dist/, published on the `output` branch):
  1. snake-grow.gif - snake eats contribution blocks and GROWS bigger each time
  2. pacman.gif     - Pac-Rita chomps the grind, ghosts = procrastination
  3. rhythm.png     - Coding Rhythm card (weekday bars + streak, real GitHub data)

Data: GitHub GraphQL contributionsCollection (needs GITHUB_TOKEN),
      falls back to no-auth scrape of /users/<login>/contributions.
"""
import os
import re
import json
import math
import datetime as dt

import requests
from PIL import Image, ImageDraw, ImageFont

USER = "iamrita-ai"
OUT_DIR = "dist"

# ---------- style ----------
BG = (13, 17, 23)          # github dark
PANEL = (22, 27, 34)
PURPLE = (139, 92, 246)
LIGHT_PURPLE = (167, 139, 250)
CYAN = (103, 232, 249)
WHITE = (240, 246, 252)
DIM = (139, 148, 158)
GOLD = (255, 213, 79)
RED = (255, 70, 85)
GREEN = (63, 185, 80)

LEVELS = [  # purple ramp, empty -> legendary
    (33, 38, 45),
    (76, 41, 149),
    (124, 58, 237),
    (167, 139, 250),
    (240, 230, 255),
]


def font(size: int):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
              "arialbd.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def level_of(count: int) -> int:
    if count <= 0:
        return 0
    if count <= 3:
        return 1
    if count <= 7:
        return 2
    if count <= 12:
        return 3
    return 4


# ---------- data ----------
def fetch_graphql(token: str):
    q = ('query{user(login:"%s"){contributionsCollection{'
         'contributionCalendar{totalContributions '
         'weeks{contributionDays{date contributionCount}}}}}}' % USER)
    r = requests.post("https://api.github.com/graphql",
                      headers={"Authorization": f"bearer {token}"},
                      json={"query": q}, timeout=25)
    r.raise_for_status()
    cal = r.json()["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [[(d["date"], d["contributionCount"]) for d in w["contributionDays"]]
             for w in cal["weeks"]]
    return weeks, cal["totalContributions"]


def fetch_scrape():
    today = dt.date.today()
    year_ago = today - dt.timedelta(days=370)
    url = (f"https://github.com/users/{USER}/contributions"
           f"?from={year_ago}&to={today}")
    html = requests.get(url, headers={"User-Agent": "Mozilla/5.0"},
                        timeout=25).text
    found = re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"[^>]*?data-level="(\d)"', html)
    pseudo = {0: 0, 1: 1, 2: 4, 3: 7, 4: 12}
    days = sorted((d, pseudo[int(l)]) for d, l in found)
    weeks, cur = [], []
    for d, c in days:
        cur.append((d, c))
        if len(cur) == 7:
            weeks.append(cur)
            cur = []
    if cur:
        weeks.append(cur)
    return weeks, sum(c for _, c in days)


def build_grid(weeks):
    """Full W x 7 grid of counts (None-padded), column-major snake path."""
    W = len(weeks)
    grid = [[0] * 7 for _ in range(W)]
    for wi, week in enumerate(weeks):
        # GraphQL partial weeks: first week may start mid-week (Sunday-first).
        # contributionDays include date; map by weekday (Mon=0..Sun=6 -> row Sun-first index).
        for datestr, count in week:
            d = dt.date.fromisoformat(datestr)
            row = (d.weekday() + 1) % 7  # Sunday -> 0
            grid[wi][row] = count
    # path: boustrophedon (down col 0, up col 1, ...)
    path = []
    for wi in range(W):
        rows = range(7) if wi % 2 == 0 else range(6, -1, -1)
        for ri in rows:
            path.append((wi, ri))
    # cut path at today (don't eat the future)
    today = dt.date.today().isoformat()
    last_real = None
    for wi, week in enumerate(weeks):
        for datestr, _ in week:
            if datestr <= today:
                d = dt.date.fromisoformat(datestr)
                last_real = (wi, (d.weekday() + 1) % 7)
    if last_real in path:
        path = path[:path.index(last_real) + 1]
    return grid, path


# ---------- drawing helpers ----------
def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def base_canvas(w, h):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, w - 3, h - 3], radius=16, outline=PURPLE, width=2)
    return img, d


def header(d, w, title, right_text, accent=GOLD):
    d.ellipse([18, 20, 34, 36], fill=RED)
    d.ellipse([40, 20, 56, 36], fill=GOLD)
    d.ellipse([62, 20, 78, 36], fill=GREEN)
    d.text((92, 16), title, font=font(21), fill=WHITE)
    d.text((w - 20, 16), right_text, font=font(17), fill=accent, anchor="ra")


def footer_bar(d, w, h, frac, label):
    y0, y1 = h - 34, h - 14
    d.rounded_rectangle([20, y0, w - 20, y1], radius=8, fill=PANEL)
    fw = int((w - 40) * max(0.0, min(1.0, frac)))
    if fw > 4:
        d.rounded_rectangle([20, y0, 20 + fw, y1], radius=8, fill=PURPLE)
    d.text((w // 2, y0 - 24), label, font=font(14), fill=DIM, anchor="ma")


# ---------- 1. growing snake ----------
def make_snake(grid, path, total):
    W = len(grid)
    cell, gap = 11, 3
    step = cell + gap
    gx, gy = 24, 84
    gw, gh = W * step - gap, 7 * step - gap
    w = gx * 2 + gw
    h = gy + gh + 66

    K = 3                     # cells eaten per frame
    n_frames = math.ceil(len(path) / K)
    body = list(range(min(6, len(path))))  # path indices, tail..head
    pending = 0
    score = 0
    max_len = 150
    f_title, f_small = font(21), font(14)
    frames = []

    for f in range(n_frames):
        img, d = base_canvas(w, h)
        head_idx = min(len(path) - 1, (f + 1) * K - 1)
        # grow for newly eaten cells
        prev_head = body[-1]
        for idx in range(prev_head + 1, head_idx + 1):
            wi, ri = path[idx]
            c = grid[wi][ri]
            if c > 0:
                pending += 1 + min(c, 5)
                score += c
        body = list(range(max(0, head_idx - max_len + 1), head_idx + 1))
        # apply growth by extending tail backwards
        want_len = min(max_len, 6 + pending)
        start = max(0, head_idx - want_len + 1)
        body = list(range(start, head_idx + 1))

        eaten = set(range(head_idx + 1))
        # grid
        for idx, (wi, ri) in enumerate(path):
            x, y = gx + wi * step, gy + ri * step
            if idx in eaten:
                d.rounded_rectangle([x, y, x + cell, y + cell], radius=3,
                                    fill=(20, 26, 36))
            else:
                d.rounded_rectangle([x, y, x + cell, y + cell], radius=3,
                                    fill=LEVELS[level_of(grid[wi][ri])])
        # snake body (tail -> head gradient purple -> cyan)
        n = len(body)
        for i, idx in enumerate(body):
            wi, ri = path[idx]
            x, y = gx + wi * step - 1, gy + ri * step - 1
            col = lerp(PURPLE, CYAN, i / max(1, n - 1)) if n > 1 else CYAN
            d.rounded_rectangle([x, y, x + cell + 2, y + cell + 2],
                                radius=4, fill=col)
        # head: eyes + tongue
        hwi, hri = path[head_idx]
        hx, hy = gx + hwi * step + cell / 2, gy + hri * step + cell / 2
        pwi, pri = path[max(0, head_idx - 1)]
        dx = (hwi - pwi) or 0
        dy = (hri - pri) or 0
        dx, dy = (dx and dx // abs(dx)), (dy and dy // abs(dy))
        px, py = -dy, dx  # perpendicular
        for s in (-1, 1):
            ex = hx + px * 3.4 * s + dx * 1.5
            ey = hy + py * 3.4 * s + dy * 1.5
            d.ellipse([ex - 2.4, ey - 2.4, ex + 2.4, ey + 2.4], fill=WHITE)
            d.ellipse([ex + dx - 1.2, ey + dy - 1.2,
                       ex + dx + 1.2, ey + dy + 1.2], fill=(10, 10, 20))
        if f % 6 < 3:  # tongue flick
            tx, ty = hx + dx * 8, hy + dy * 8
            d.line([hx + dx * 6, hy + dy * 6, tx, ty], fill=RED, width=2)
            d.line([tx, ty, tx + (px * 2 + dx * 2), ty + (py * 2 + dy * 2)],
                   fill=RED, width=2)
            d.line([tx, ty, tx + (-px * 2 + dx * 2), ty + (-py * 2 + dy * 2)],
                   fill=RED, width=2)

        header(d, w, "SNAKE 2.0 - EAT. GROW. REPEAT.",
               f"SCORE {score}  |  LEN {len(body)}")
        footer_bar(d, w, h, (head_idx + 1) / len(path),
                   f"BLOCKS EATEN {head_idx + 1}/{len(path)}  -  every bite makes it LONGER")
        frames.append(img)

    return frames


# ---------- 2. pacman ----------
def draw_ghost(d, cx, cy, r, color, dir_x, frightened):
    x0, x1 = cx - r, cx + r
    top = cy - r
    d.pieslice([x0, top, x1, top + 2 * r], 180, 360, fill=color)
    d.rectangle([x0, cy - 1, x1, cy + r], fill=color)
    # skirt
    teeth = 3
    tw = (2 * r) / teeth
    for i in range(teeth):
        tx = x0 + i * tw
        d.polygon([(tx, cy + r), (tx + tw / 2, cy + r - 4),
                   (tx + tw, cy + r)], fill=color)
    if frightened:
        d.ellipse([cx - 4, cy - 4, cx - 1, cy - 1], fill=WHITE)
        d.ellipse([cx + 1, cy - 4, cx + 4, cy - 1], fill=WHITE)
    else:
        for s in (-1, 1):
            ex = cx + s * r * 0.42
            d.ellipse([ex - 3, cy - 5, ex + 3, cy + 1], fill=WHITE)
            d.ellipse([ex + dir_x * 1.5 - 1.5, cy - 3.5,
                       ex + dir_x * 1.5 + 1.5, cy - 0.5], fill=(20, 20, 255))


def make_pacman(grid, path, total):
    W = len(grid)
    cell, gap = 11, 3
    step = cell + gap
    gx, gy = 24, 84
    gw, gh = W * step - gap, 7 * step - gap
    w = gx * 2 + gw
    h = gy + gh + 66

    K = 3
    n_frames = math.ceil(len(path) / K)
    score = 0
    fright = 0
    frames = []

    for f in range(n_frames):
        img, d = base_canvas(w, h)
        head_idx = min(len(path) - 1, (f + 1) * K - 1)
        for idx in range(max(0, head_idx - K + 1), head_idx + 1):
            wi, ri = path[idx]
            c = grid[wi][ri]
            if c > 0:
                score += c
                if c >= 8:
                    fright = 16  # power pellet!
        fright = max(0, fright - 1)
        eaten = set(range(head_idx + 1))

        # maze dots: small dot per cell, big pellet on rich cells
        for idx, (wi, ri) in enumerate(path):
            if idx in eaten:
                continue
            x = gx + wi * step + cell / 2
            y = gy + ri * step + cell / 2
            c = grid[wi][ri]
            if c >= 8:
                pr = 4.5 + math.sin(f * 0.6) * 1.2
                d.ellipse([x - pr, y - pr, x + pr, y + pr], fill=LIGHT_PURPLE)
            else:
                col = LEVELS[level_of(c)]
                d.ellipse([x - 1.8, y - 1.8, x + 1.8, y + 1.8], fill=col)

        # ghosts trailing behind
        hwi, hri = path[head_idx]
        pwi, pri = path[max(0, head_idx - 1)]
        dx = (hwi - pwi)
        dx = dx // abs(dx) if dx else 0
        for off, col in ((16, (255, 70, 120)), (30, (255, 80, 60))):
            gi = max(0, head_idx - off)
            if gi > head_idx - 4:
                continue  # don't stack ghosts on pac at the start
            gwi, gri = path[gi]
            gcx = gx + gwi * step + cell / 2
            gcy = gy + gri * step + cell / 2
            draw_ghost(d, gcx, gcy, 7.5,
                       (40, 40, 255) if fright else col, dx, bool(fright))

        # pac-rita
        cx = gx + hwi * step + cell / 2
        cy = gy + hri * step + cell / 2
        r = 8.5
        base_ang = {  # facing per direction
            (1, 0): 0, (-1, 0): 180, (0, 1): 90, (0, -1): 270}.get((dx, 0), 0)
        if dx == 0:
            dy = (hri - pri)
            dy = dy // abs(dy) if dy else 1
            base_ang = 90 if dy > 0 else 270
        mouth = (f % 4) * 9  # chomp animation
        d.pieslice([cx - r, cy - r, cx + r, cy + r],
                   base_ang + mouth, base_ang + 360 - mouth, fill=GOLD)

        title = "PAC-RITA - CHOMP THE GRIND" + ("  [POWER!]" if fright else "")
        header(d, w, title, f"SCORE {score}")
        footer_bar(d, w, h, (head_idx + 1) / len(path),
                   f"GHOSTS = PROCRASTINATION  -  STATUS: EATEN" if fright
                   else f"DOTS EATEN {head_idx + 1}/{len(path)}  -  ghosts are closing in...")
        frames.append(img)

    return frames


# ---------- 3. rhythm card ----------
def make_rhythm(grid, weeks, total):
    weekday_totals = [0] * 7
    best = 0
    active = 0
    flat = []
    for week in weeks:
        for datestr, c in week:
            d = dt.date.fromisoformat(datestr)
            if d > dt.date.today():
                continue
            flat.append((datestr, c))
            weekday_totals[d.weekday()] += c
            best = max(best, c)
            if c > 0:
                active += 1
    flat.sort()
    # current streak
    streak = 0
    for datestr, c in reversed(flat):
        if datestr == dt.date.today().isoformat() and c == 0:
            continue
        if c > 0:
            streak += 1
        else:
            break

    w, h = 780, 320
    img, d = base_canvas(w, h)
    d.text((30, 22), "CODING RHYTHM  -  REAL DATA, ZERO EMOTIONS",
           font=font(21), fill=WHITE)

    # weekday bars
    names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    bx0, bw, by1, bh_max = 50, 62, 218, 110
    mx = max(weekday_totals) or 1
    for i, (nm, v) in enumerate(zip(names, weekday_totals)):
        bh = max(6, int(bh_max * v / mx))
        x0 = bx0 + i * (bw + 34)
        col = lerp(PURPLE, CYAN, v / mx)
        d.rounded_rectangle([x0, by1 - bh, x0 + bw, by1], radius=8, fill=col)
        d.text((x0 + bw / 2, by1 - bh - 26), str(v), font=font(15),
               fill=WHITE, anchor="ma")
        d.text((x0 + bw / 2, by1 + 10), nm, font=font(14), fill=DIM, anchor="ma")

    # stat boxes
    stats = [("YEAR TOTAL", str(total), PURPLE),
             ("ACTIVE DAYS", str(active), CYAN),
             ("BEST DAY", str(best), GOLD),
             ("DAY STREAK", f"{streak} DAYS", GREEN)]
    sx0, sw, sy0, sh = 30, 168, 252, 0
    for i, (label, val, col) in enumerate(stats):
        x0 = sx0 + i * (sw + 12)
        # (drawn in footer zone)
    # enlarge canvas zone: stats row under bars
    d.text((w - 30, 24), "auto-refresh", font=font(13), fill=DIM, anchor="ra")
    img.save(f"{OUT_DIR}/rhythm.png")
    # second pass: extend canvas for stat boxes
    canvas = Image.new("RGB", (w, h + 78), BG)
    canvas.paste(img, (0, 0))
    d2 = ImageDraw.Draw(canvas)
    d2.rounded_rectangle([2, 2, w - 3, h + 78 - 3], radius=16,
                         outline=PURPLE, width=2)
    for i, (label, val, col) in enumerate(stats):
        x0 = 30 + i * (sw + 12)
        y0 = h + 8
        d2.rounded_rectangle([x0, y0, x0 + sw, y0 + 58], radius=10,
                             fill=PANEL, outline=col, width=2)
        d2.text((x0 + sw / 2, y0 + 6), label, font=font(12), fill=DIM, anchor="ma")
        d2.text((x0 + sw / 2, y0 + 24), val, font=font(19), fill=WHITE, anchor="ma")
    canvas.save(f"{OUT_DIR}/rhythm.png")
    return {"total": total, "active": active, "best": best, "streak": streak,
            "weekdays": weekday_totals}


def save_gif(frames, name, duration=90):
    pal = [f.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=128)
           for f in frames]
    pal[0].save(f"{OUT_DIR}/{name}", save_all=True, append_images=pal[1:],
                duration=duration, loop=0, optimize=True)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    token = os.environ.get("GITHUB_TOKEN", "")
    try:
        if not token:
            raise RuntimeError("no token")
        weeks, total = fetch_graphql(token)
        print(f"data: GraphQL OK, total={total}")
    except Exception as e:
        print(f"data: GraphQL failed ({e}), using scrape fallback")
        weeks, total = fetch_scrape()
        print(f"data: scrape OK, total={total}")
    grid, path = build_grid(weeks)
    print(f"grid: {len(grid)} weeks, path: {len(path)} cells")

    snake = make_snake(grid, path, total)
    save_gif(snake, "snake-grow.gif")
    print(f"snake-grow.gif: {len(snake)} frames")

    pac = make_pacman(grid, path, total)
    save_gif(pac, "pacman.gif")
    print(f"pacman.gif: {len(pac)} frames")

    info = make_rhythm(grid, weeks, total)
    print("rhythm.png:", json.dumps(info))


if __name__ == "__main__":
    main()
