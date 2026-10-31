"""Render the contribution graph as a comet sweep, in the profile's palette.

A comet makes a raster pass over the year's contribution cells, one row at a
time, consuming each active cell as it crosses it. Its ion tail grows with the
share of cells eaten, so it starts as a bare head and ends a long streak.

Animation is SMIL (animateMotion + animate), which GitHub renders for SVGs
loaded through <img>; CSS offset-path is not as widely supported there.

    python scripts/comet.py --out dist            # real data, needs GITHUB_TOKEN
    python scripts/comet.py --out dist --demo     # synthetic data, for local preview

Writes contrib-comet-dark.svg and contrib-comet-light.svg.
"""
import argparse
import json
import math
import os
import urllib.request

PITCH = 14          # cell pitch in px
CELL = 11           # cell size in px
CANVAS = 830        # shared page width; every image on the profile is drawn against it
PAD_TOP = 22
PAD_BOTTOM = 36
SPEED = 520.0       # px per second along the path
TAIL = 64           # tail segments
TAIL_STEP = 5.5     # px between tail segments
PAUSE = 1.6         # seconds held at the end of each loop
R = 16

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

THEMES = {
    "dark": dict(card="#131b2b", top="#18223a", bot="#111a2d", edge="#2a3652", muted="#97a3b8", empty="#182238", eaten="#1c2740",
                 levels=["#1f4a5c", "#2f7f9a", "#52b0cf", "#8fdcf0"], head="#ffb020", ion="#78cce4"),
    "light": dict(card="#ffffff", top="#ffffff", bot="#f4f7fb", edge="#dde3ed", muted="#52607a", empty="#eceff4", eaten="#f2f4f8",
                  levels=["#cfe6ee", "#9ccfe0", "#4fa5c4", "#12799e"], head="#d98a06", ion="#12799e"),
}

LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}

QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { weekday contributionLevel } }
      }
    }
  }
}
"""


def blend(a, b, f):
    """Linear mix of two #rrggbb colours; f=0 gives a, f=1 gives b."""
    pa, pb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(f"{round(x + (y - x) * f):02x}" for x, y in zip(pa, pb))


def fetch(login, token):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        cal = json.load(r)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    weeks = [{d["weekday"]: LEVELS[d["contributionLevel"]] for d in w["contributionDays"]} for w in cal["weeks"]]
    return weeks, cal["totalContributions"]


def demo():
    weeks, total = [], 0
    for c in range(53):
        week = {}
        for r in range(7):
            v = (c * 7 + r) * 2654435761 % 1000 / 1000
            lvl = 0 if v < 0.45 or r in (0, 6) and v < 0.7 else 1 + int((v - 0.45) / 0.55 * 4)
            week[r] = min(lvl, 4)
            total += lvl * 3
        weeks.append(week)
    return weeks, total


def build(weeks, total, name, t):
    cols = len(weeks)
    grid_w = cols * PITCH - (PITCH - CELL)
    w = CANVAS
    PAD_X = (w - grid_w) / 2   # centred; leaves room for the U-turns
    h = PAD_TOP + 7 * PITCH - (PITCH - CELL) + PAD_BOTTOM
    xl = PAD_X + CELL / 2
    xr = PAD_X + grid_w - CELL / 2
    row_y = [PAD_TOP + r * PITCH + CELL / 2 for r in range(7)]
    span = xr - xl
    turn = math.pi * (PITCH / 2)

    # One raster pass per row, joined by half-circle turns at alternating ends.
    d = [f"M{xl:.1f},{row_y[0]:.1f}"]
    for r in range(7):
        d.append(f"H{(xr if r % 2 == 0 else xl):.1f}")
        if r < 6:
            sweep = 1 if r % 2 == 0 else 0
            d.append(f"A{PITCH/2} {PITCH/2} 0 0 {sweep} {(xr if r % 2 == 0 else xl):.1f},{row_y[r+1]:.1f}")
    path = " ".join(d)
    length = 7 * span + 6 * turn
    t0 = length / SPEED
    total_t = t0 + TAIL * TAIL_STEP / SPEED + PAUSE

    def arrival(c, r):
        along = (c * PITCH) if r % 2 == 0 else (span - c * PITCH)
        return (r * (span + turn) + along) / SPEED

    cells, eaten_times = [], []
    for c, week in enumerate(weeks):
        for r, lvl in sorted(week.items()):
            x = round(PAD_X + c * PITCH, 1)
            y = PAD_TOP + r * PITCH
            if lvl == 0:
                cells.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{t["empty"]}"/>')
                continue
            tc = arrival(c, r)
            eaten_times.append(tc)
            color = t["levels"][lvl - 1]
            a, b = tc / total_t, min((tc + 0.25) / total_t, 0.97)
            cells.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{color}">'
                f'<animate attributeName="fill" dur="{total_t:.2f}s" repeatCount="indefinite" '
                f'values="{color};{color};{t["eaten"]};{t["eaten"]};{color}" '
                f'keyTimes="0;{a:.4f};{b:.4f};0.985;1"/></rect>')
    eaten_times.sort()

    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
           f'aria-label="Contribution graph: a comet sweeps the year, consuming active days as its ion tail grows">',
           f'<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["top"]}"/>'
           f'<stop offset="1" stop-color="{t["bot"]}"/></linearGradient></defs>',
           f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="{R}" fill="url(#g)" stroke="{t["edge"]}"/>']
    out += cells

    # Tail segment i appears when the comet has eaten i/TAIL of its cells.
    for i in range(TAIL, 0, -1):
        f = i / TAIL
        q = eaten_times[min(int(f * (len(eaten_times) - 1)), len(eaten_times) - 1)] if eaten_times else 0
        lag = i * TAIL_STEP / SPEED
        s, e = lag / total_t, (lag + t0) / total_t
        fade_in = q / total_t
        alpha = 0.85 * (1 - f) ** 1.15
        rad = 0.9 + 3.9 * (1 - f) ** 0.8
        fill = blend(t["head"], t["ion"], min(i / 10, 1))
        out.append(
            f'<circle r="{rad:.2f}" fill="{fill}" opacity="0">'
            f'<animateMotion dur="{total_t:.2f}s" repeatCount="indefinite" calcMode="linear" path="{path}" '
            f'keyPoints="0;0;1;1" keyTimes="0;{s:.4f};{e:.4f};1"/>'
            f'<animate attributeName="opacity" dur="{total_t:.2f}s" repeatCount="indefinite" '
            f'values="0;0;{alpha:.2f};{alpha:.2f};0;0" '
            f'keyTimes="0;{fade_in:.4f};{min(fade_in + 0.01, e - 0.001):.4f};{e:.4f};{min(e + 0.02, 0.995):.4f};1"/></circle>')

    # Head: amber core in a soft halo.
    out.append(
        f'<g><circle r="10" fill="{t["head"]}" opacity=".22"/><circle r="5.2" fill="{t["head"]}"/>'
        f'<animateMotion dur="{total_t:.2f}s" repeatCount="indefinite" calcMode="linear" path="{path}" '
        f'keyPoints="0;1;1" keyTimes="0;{t0/total_t:.4f};1"/></g>')

    out.append(f'<text x="{PAD_X}" y="{h-13}" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="{t["muted"]}">'
               f'{total} CONTRIBUTIONS · PAST YEAR</text>')
    out.append('</svg>')
    return "".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="dist")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--user", default=os.environ.get("GITHUB_REPOSITORY_OWNER", "MatthewGoldsberry"))
    args = ap.parse_args()

    weeks, total = demo() if args.demo else fetch(args.user, os.environ["GITHUB_TOKEN"])
    os.makedirs(args.out, exist_ok=True)
    for name, t in THEMES.items():
        with open(os.path.join(args.out, f"contrib-comet-{name}.svg"), "w", encoding="utf-8") as f:
            f.write(build(weeks, total, name, t))


if __name__ == "__main__":
    main()
