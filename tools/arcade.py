#!/usr/bin/env python3
"""IAMRITA profile animation generator.

Outputs (to dist/, published on the `output` branch):
  1. github-contribution-grid-snake.svg      - classic snake, light mode
  2. github-contribution-grid-snake-dark.svg - classic snake, dark mode
     Both: the snake eats the contribution grid and its TAIL GROWS +1
     for every block eaten (SMIL-animated SVG, snk-style look).
  3. rhythm.png - Coding Rhythm card (weekday bars + streak, real data).

Data: GitHub GraphQL contributionsCollection (needs GITHUB_TOKEN),
      falls back to no-auth scrape of /users/<login>/contributions.
"""
import os
import re
import json
import datetime as dt

import requests
from PIL import Image, ImageDraw, ImageFont

USER = "iamrita-ai"
OUT_DIR = "dist"

# ---------- style ----------
BG = (13, 17, 23)
PANEL = (22, 27, 34)
PURPLE = (139, 92, 246)
CYAN = (103, 232, 249)
WHITE = (240, 246, 252)
DIM = (139, 148, 158)
GOLD = (255, 213, 79)
GREEN = (63, 185, 80)


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


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


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
    """Full W x 7 grid of counts + column-major boustrophedon eating path."""
    W = len(weeks)
    grid = [[0] * 7 for _ in range(W)]
    for wi, week in enumerate(weeks):
        for datestr, count in week:
            d = dt.date.fromisoformat(datestr)
            row = (d.weekday() + 1) % 7  # Sunday -> 0
            grid[wi][row] = count
    path = []
    for wi in range(W):
        rows = range(7) if wi % 2 == 0 else range(6, -1, -1)
        for ri in rows:
            path.append((wi, ri))
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


# ---------- 1. classic growing snake (SMIL SVG, snk-style) ----------
def make_grow_svg(grid, path, dark=True):
    W = len(grid)
    cell, gap, pad = 10, 3, 8
    step = cell + gap
    w = pad * 2 + W * step - gap
    h = pad * 2 + 7 * step - gap
    dur = 28.0
    n = len(path)
    T_END = 0.90   # cells appear over [0, 0.90], hold, fade [0.95, 0.99]
    if dark:
        lv = [(33, 38, 45), (76, 41, 149), (124, 58, 237),
              (167, 139, 250), (240, 230, 255)]
        tail, head_c = (124, 58, 237), (103, 232, 249)
        pupil = (10, 10, 20)
    else:
        lv = [(235, 237, 240), (216, 204, 245), (183, 157, 240),
              (139, 92, 246), (109, 40, 217)]
        tail, head_c = (168, 85, 247), (76, 29, 149)
        pupil = (30, 20, 60)

    def hx(c):
        return '#%02x%02x%02x' % c

    L = []
    A = L.append
    A(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
      f'viewBox="0 0 {w} {h}">')
    # base contribution grid (static)
    A('<g>')
    for wi in range(W):
        for ri in range(7):
            x = pad + wi * step
            y = pad + ri * step
            A(f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" '
              f'fill="{hx(lv[level_of(grid[wi][ri])])}"/>')
    A('</g>')
    # snake layer: fades out at loop end, then regrows from zero
    A('<g><animate attributeName="opacity" values="1;1;0;0" '
      f'keyTimes="0;0.95;0.99;1" dur="{dur:g}s" repeatCount="indefinite"/>')
    e = 0.0004
    for i, (wi, ri) in enumerate(path):
        # tail grows +1 every block: cell i appears at its time and STAYS
        t = T_END * i / n
        col = lerp(tail, head_c, i / max(1, n - 1))
        x = pad + wi * step - 1
        y = pad + ri * step - 1
        s = cell + 2
        A(f'<rect x="{x}" y="{y}" width="{s}" height="{s}" rx="3.5" '
          f'fill="{hx(col)}" opacity="0">'
          f'<animate attributeName="opacity" values="0;0;1;1" '
          f'keyTimes="0;{t:.6f};{t + e:.6f};1" dur="{dur:g}s" '
          f'repeatCount="indefinite"/></rect>')
    # head eyes: visible only while the head sits on that cell
    for i, (wi, ri) in enumerate(path):
        if i == 0:
            nxt = path[1]
            dx, dy = nxt[0] - wi, nxt[1] - ri
        else:
            prv = path[i - 1]
            dx, dy = wi - prv[0], ri - prv[1]
        px, py = -dy, dx
        cx = pad + wi * step + cell / 2
        cy = pad + ri * step + cell / 2
        t0 = T_END * i / n
        t1 = T_END * (i + 1) / n
        A('<g opacity="0"><animate attributeName="opacity" '
          f'values="0;0;1;1;0;0" '
          f'keyTimes="0;{t0:.6f};{t0 + e:.6f};{t1:.6f};{t1 + e:.6f};1" '
          f'dur="{dur:g}s" repeatCount="indefinite"/>')
        for sgn in (-1, 1):
            ex0 = cx + px * 2.4 * sgn + dx * 1.2
            ey0 = cy + py * 2.4 * sgn + dy * 1.2
            A(f'<circle cx="{ex0:.1f}" cy="{ey0:.1f}" r="1.7" fill="#fff"/>'
              f'<circle cx="{ex0 + dx:.1f}" cy="{ey0 + dy:.1f}" r="0.8" '
              f'fill="{hx(pupil)}"/>')
        A('</g>')
    A('</g></svg>')
    return '\n'.join(L)


# ---------- 2. rhythm card ----------
def base_canvas(w, h):
    img = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([2, 2, w - 3, h - 3], radius=16, outline=PURPLE, width=2)
    return img, d


def make_rhythm(weeks, total):
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

    stats = [("YEAR TOTAL", str(total), PURPLE),
             ("ACTIVE DAYS", str(active), CYAN),
             ("BEST DAY", str(best), GOLD),
             ("DAY STREAK", f"{streak} DAYS", GREEN)]
    sw = 168
    d.text((w - 30, 24), "auto-refresh", font=font(13), fill=DIM, anchor="ra")
    img.save(f"{OUT_DIR}/rhythm.png")
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

    for dark, name in ((False, "github-contribution-grid-snake.svg"),
                       (True, "github-contribution-grid-snake-dark.svg")):
        svg = make_grow_svg(grid, path, dark=dark)
        with open(f"{OUT_DIR}/{name}", "w") as f:
            f.write(svg)
        print(f"{name}: {len(svg) // 1024} KB")

    info = make_rhythm(weeks, total)
    print("rhythm.png:", json.dumps(info))


if __name__ == "__main__":
    main()
