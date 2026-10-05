"""Generate animated neofetch-style profile cards (dark + light SVG).

Usage:
    GITHUB_TOKEN=xxx python scripts/generate.py          # live data
    python scripts/generate.py --mock                    # fake data, for local preview
"""
import datetime as dt
import html
import io
import json
import os
import sys
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))

FONT = 14            # px
CW = FONT * 0.6      # monospace char width
LH = 18              # line height
PAD = 28
INFO_COLS = 58       # width of right column in characters
RAMP = " .,:;-=+*#%@"

THEMES = {
    "dark": dict(bg="#0d1117", border="#30363d", fg="#c9d1d9", key="#ffa657",
                 val="#a5d6ff", dim="#6e7681", title="#7ee787", portrait="#8b949e",
                 cell=["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]),
    "light": dict(bg="#ffffff", border="#d0d7de", fg="#24292f", key="#953800",
                  val="#0a3069", dim="#8c959f", title="#116329", portrait="#57606a",
                  cell=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]),
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    name createdAt avatarUrl(size: 400)
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, first: 100) {
      totalCount nodes { stargazerCount }
    }
    contributionsCollection {
      totalCommitContributions totalPullRequestContributions totalIssueContributions
      contributionCalendar { totalContributions
        weeks { contributionDays { contributionCount date } } }
    }
  }
}"""


# ---------------------------------------------------------------- data
def fetch_live():
    token = os.environ["GITHUB_TOKEN"]
    r = requests.post("https://api.github.com/graphql",
                      json={"query": QUERY, "variables": {"login": CFG["username"]}},
                      headers={"Authorization": f"bearer {token}"}, timeout=30)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def fetch_mock():
    import random
    random.seed(7)
    today = dt.date.today()
    start = today - dt.timedelta(days=today.weekday() + 1 + 52 * 7)
    weeks, day = [], start
    while day <= today:
        week = []
        for _ in range(7):
            if day > today:
                break
            n = random.choice([0, 0, 0, 1, 2, 4, 7]) if day > today - dt.timedelta(days=60) else 0
            week.append({"date": day.isoformat(), "contributionCount": n})
            day += dt.timedelta(days=1)
        weeks.append({"contributionDays": week})
    return {
        "name": "x2swiftz_z", "createdAt": "2025-08-14T00:00:00Z", "avatarUrl": "",
        "followers": {"totalCount": 4},
        "repositories": {"totalCount": 3, "nodes": [{"stargazerCount": 1}] * 3},
        "contributionsCollection": {
            "totalCommitContributions": 77, "totalPullRequestContributions": 2,
            "totalIssueContributions": 1,
            "contributionCalendar": {"totalContributions": 80, "weeks": weeks}},
    }


def streaks(weeks):
    days = [d for w in weeks for d in w["contributionDays"]]
    best = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] else 0
        best = max(best, run)
    cur = 0
    for i, d in enumerate(reversed(days)):
        if d["contributionCount"]:
            cur += 1
        elif i == 0:
            continue           # today may still be empty
        else:
            break
    return cur, best


def uptime(created):
    start = dt.datetime.fromisoformat(created.replace("Z", "+00:00")).date()
    days = (dt.date.today() - start).days
    y, rem = divmod(days, 365)
    m, d = divmod(rem, 30)
    parts = [f"{y} year{'s' * (y != 1)}"] if y else []
    parts += [f"{m} month{'s' * (m != 1)}", f"{d} day{'s' * (d != 1)}"]
    return ", ".join(parts)


# ---------------------------------------------------------------- portrait
def load_portrait(user):
    p = ROOT / CFG["portrait"]
    if p.exists():
        return Image.open(p)
    if user.get("avatarUrl"):
        return Image.open(io.BytesIO(requests.get(user["avatarUrl"], timeout=30).content))
    # placeholder: soft radial blob
    img = Image.radial_gradient("L").resize((200, 200))
    return ImageOps.invert(img)


def ascii_rows(img, cols):
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (0, 0, 0, 255))   # transparent area -> blank
        img = Image.alpha_composite(bg, img)
    img = img.convert("L")
    img = ImageOps.autocontrast(img, cutoff=2)
    w, h = img.size
    rows = max(1, int(h / w * cols * 0.5))  # chars are ~2x taller than wide
    img = img.resize((cols, rows))
    px = img.load()
    out = []
    for y in range(rows):
        out.append("".join(RAMP[px[x, y] * (len(RAMP) - 1) // 255] for x in range(cols)))
    return out


# ---------------------------------------------------------------- svg
def esc(s):
    return html.escape(s, quote=False)


def dotted(key, val, width=INFO_COLS):
    """'Key: ....... value' padded to fixed width."""
    left = f"{key}: "
    dots = max(2, width - len(left) - len(val) - 1)
    return left, "." * dots + " ", val


def build_lines(user):
    cc = user["contributionsCollection"]
    cur, best = streaks(cc["contributionCalendar"]["weeks"])
    stars = sum(n["stargazerCount"] for n in user["repositories"]["nodes"])
    up = uptime(user["createdAt"])

    head = f"{CFG['display']}@github"
    lines = [("title", head), ("dim", "-" * INFO_COLS)]

    def kv(k, v):
        lines.append(("kv",) + dotted(k, v.replace("{uptime}", up)))

    for item in CFG["info"]:
        if item:
            kv(*item)
        else:
            lines.append(("blank", ""))
    lines += [("blank", ""), ("section", "- Contact " + "-" * (INFO_COLS - 10))]
    for k, v in CFG["contact"]:
        kv(k, v)
    lines += [("blank", ""), ("section", "- GitHub Stats " + "-" * (INFO_COLS - 15))]
    pairs = [
        (("Repos", str(user["repositories"]["totalCount"])), ("Stars", str(stars))),
        (("Commits (1y)", str(cc["totalCommitContributions"])),
         ("Followers", str(user["followers"]["totalCount"]))),
        (("Pull requests", str(cc["totalPullRequestContributions"])),
         ("Issues", str(cc["totalIssueContributions"]))),
        (("Streak", f"{cur}d"), ("Best", f"{best}d")),
    ]
    half = INFO_COLS // 2 - 2
    for a, b in pairs:
        lines.append(("pair", dotted(*a, width=half), dotted(*b, width=INFO_COLS - half - 3)))
    return lines, cc["contributionCalendar"]


def render(user, theme_name):
    t = THEMES[theme_name]
    rows = ascii_rows(load_portrait(user), CFG["portrait_cols"])
    lines, cal = build_lines(user)

    left_w = CFG["portrait_cols"] * CW
    info_x = PAD + left_w + 32
    width = int(info_x + INFO_COLS * CW + PAD)
    body_rows = max(len(rows), len(lines) + 2)
    top = PAD + FONT

    weeks = cal["weeks"]
    cell, gap = 11, 3
    graph_w = len(weeks) * (cell + gap) - gap
    graph_y = top + body_rows * LH + 18
    height = int(graph_y + 7 * (cell + gap) + 30 + PAD)

    s = []
    a = s.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
      f'viewBox="0 0 {width} {height}" font-family="ui-monospace, SFMono-Regular, '
      f'Consolas, \'Liberation Mono\', Menlo, monospace" font-size="{FONT}">')
    a(f"""<style>
.p{{fill:{t['portrait']};white-space:pre}} .f{{fill:{t['fg']}}} .k{{fill:{t['key']}}}
.v{{fill:{t['val']}}} .d{{fill:{t['dim']}}} .h{{fill:{t['title']};font-weight:700}}
text{{white-space:pre}}
.p,.ty,.c{{opacity:0;animation:on .01s forwards}}
.ty{{opacity:1;clip-path:inset(0 100% 0 0);animation:type .45s steps(24) forwards}}
.cur{{fill:{t['title']};animation:blink 1s steps(1) infinite}}
@keyframes on{{to{{opacity:1}}}}
@keyframes type{{to{{clip-path:inset(0 0 0 0)}}}}
@keyframes blink{{50%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.p,.ty,.c{{animation:none;opacity:1;clip-path:none}}.cur{{animation:none}}}}
</style>""")
    a(f'<rect x=".5" y=".5" width="{width-1}" height="{height-1}" rx="10" '
      f'fill="{t["bg"]}" stroke="{t["border"]}"/>')

    # portrait: rows appear top to bottom
    for i, r in enumerate(rows):
        a(f'<text class="p" x="{PAD}" y="{top + i*LH}" style="animation-delay:{i*0.04:.2f}s">'
          f'{esc(r)}</text>')

    # info: typed line by line after portrait
    delay = len(rows) * 0.04 + 0.2
    y = top
    for ln in lines:
        kind = ln[0]
        st = f'style="animation-delay:{delay:.2f}s"'
        if kind == "title":
            a(f'<text class="ty h" x="{info_x}" y="{y}" {st}>{esc(ln[1])}</text>')
        elif kind in ("dim",):
            a(f'<text class="ty d" x="{info_x}" y="{y}" {st}>{esc(ln[1])}</text>')
        elif kind == "section":
            a(f'<text class="ty f" x="{info_x}" y="{y}" {st}>{esc(ln[1])}</text>')
        elif kind == "kv":
            k, dots, v = ln[1:]
            a(f'<text class="ty" x="{info_x}" y="{y}" {st}><tspan class="k">{esc(k)}</tspan>'
              f'<tspan class="d">{dots}</tspan><tspan class="v">{esc(v)}</tspan></text>')
        elif kind == "pair":
            parts = []
            for j, (k, dots, v) in enumerate(ln[1:]):
                if j:
                    parts.append('<tspan class="d"> | </tspan>')
                parts.append(f'<tspan class="k">{esc(k)}</tspan><tspan class="d">{dots}</tspan>'
                             f'<tspan class="v">{esc(v)}</tspan>')
            a(f'<text class="ty" x="{info_x}" y="{y}" {st}>{"".join(parts)}</text>')
        if kind != "blank":
            delay += 0.12
        y += LH
    # neofetch colour swatch + blinking cursor
    y += LH * 0.3
    for i, c in enumerate(["#f85149", "#ffa657", "#e3b341", "#7ee787", "#79c0ff", "#d2a8ff", t["fg"]]):
        a(f'<rect class="c" x="{info_x + i*26}" y="{y - FONT}" width="22" height="14" rx="2" '
          f'fill="{c}" style="animation-delay:{delay:.2f}s"/>')
    a(f'<rect class="cur" x="{info_x + 7*26 + 6}" y="{y - FONT}" width="{CW:.1f}" height="16"/>')

    # contribution graph: sweeps in column by column
    gx = (width - graph_w) / 2
    a(f'<text class="ty d" x="{gx}" y="{graph_y - 6}" style="animation-delay:{delay:.2f}s">'
      f'{cal["totalContributions"]} contributions in the last year</text>')
    gy = graph_y + 4
    delay += 0.2
    for wi, w in enumerate(weeks):
        for d in w["contributionDays"]:
            n = d["contributionCount"]
            lvl = 0 if n == 0 else 1 if n < 3 else 2 if n < 6 else 3 if n < 10 else 4
            di = dt.date.fromisoformat(d["date"]).weekday()
            row = (di + 1) % 7            # Sunday first, like GitHub
            a(f'<rect class="c" x="{gx + wi*(cell+gap):.0f}" y="{gy + row*(cell+gap)}" '
              f'width="{cell}" height="{cell}" rx="2" fill="{t["cell"][lvl]}" '
              f'style="animation-delay:{delay + wi*0.02:.2f}s"><title>{d["date"]}: {n}</title></rect>')
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    a(f'<text class="d" x="{width - PAD}" y="{height - PAD/2}" font-size="11" '
      f'text-anchor="end">updated {stamp}</text>')
    a("</svg>")
    return "\n".join(s)


def main():
    user = fetch_mock() if "--mock" in sys.argv else fetch_live()
    for name in THEMES:
        (ROOT / f"{name}_mode.svg").write_text(render(user, name), encoding="utf-8")
        print(f"wrote {name}_mode.svg")


if __name__ == "__main__":
    main()
