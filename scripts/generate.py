"""Generate the animated profile: neofetch-style card, project cards and README sections.

Outputs:
    dark_mode.svg / light_mode.svg        main terminal card
    cards/<repo>_{dark,light}.svg         one card per recent project
    README.md                             fills the projects + activity sections

Usage:
    GITHUB_TOKEN=xxx python scripts/generate.py          # live data
    python scripts/generate.py --mock                    # fake data, for local preview
"""
import datetime as dt
import html
import io
import json
import os
import re
import sys
from pathlib import Path

import requests
from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
API = "https://api.github.com"

FONT = 14            # px
CW = FONT * 0.6      # monospace char width
LH = 18              # line height
PAD = 28
TB = 34              # window title bar height
INFO_COLS = 58       # width of right column in characters
RAMP = " .,:;-=+*#%@"
MONO = "ui-monospace, SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace"

THEMES = {
    "dark": dict(bg="#0d1117", bar="#161b22", border="#30363d", fg="#c9d1d9", key="#ffa657",
                 val="#a5d6ff", dim="#6e7681", title="#7ee787",
                 grad=["#7ee787", "#79c0ff", "#d2a8ff"],
                 cell=["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]),
    "light": dict(bg="#ffffff", bar="#f6f8fa", border="#d0d7de", fg="#24292f", key="#953800",
                  val="#0a3069", dim="#8c959f", title="#116329",
                  grad=["#1a7f37", "#0969da", "#8250df"],
                  cell=["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"]),
}

QUERY = """
query($login: String!) {
  user(login: $login) {
    name createdAt avatarUrl(size: 400)
    followers { totalCount }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, first: 100,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes {
        name description url stargazerCount forkCount isFork pushedAt
        primaryLanguage { name color }
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } } }
      }
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
    headers = {"Authorization": f"bearer {token}"}
    r = requests.post(f"{API}/graphql", headers=headers, timeout=30,
                      json={"query": QUERY, "variables": {"login": CFG["username"]}})
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        sys.exit(f"GraphQL error: {body['errors']}")
    user = body["data"]["user"]
    r = requests.get(f"{API}/users/{CFG['username']}/events/public", headers=headers,
                     params={"per_page": 50}, timeout=30)
    user["events"] = r.json() if r.ok else []
    return user


def fetch_mock():
    import random
    random.seed(7)
    today = dt.date.today()
    now = dt.datetime.now(dt.timezone.utc)
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

    def ago(**kw):
        return (now - dt.timedelta(**kw)).isoformat().replace("+00:00", "Z")

    py = {"name": "Python", "color": "#3572A5"}
    ps = {"name": "PowerShell", "color": "#012456"}
    repos = [
        {"name": "Bot-Ai-Discord", "description": "AI chat bot for Discord", "isFork": False,
         "url": "https://github.com/x2Swiftyouz/Bot-Ai-Discord", "stargazerCount": 2,
         "forkCount": 1, "pushedAt": ago(hours=5), "primaryLanguage": py,
         "languages": {"edges": [{"size": 48000, "node": py}]}},
        {"name": "Bot-Music", "description": "Music bot for Discord with queue, loop and "
         "playlist support, built on discord.py", "isFork": False,
         "url": "https://github.com/x2Swiftyouz/Bot-Music", "stargazerCount": 1,
         "forkCount": 0, "pushedAt": ago(days=3), "primaryLanguage": py,
         "languages": {"edges": [{"size": 30000, "node": py}]}},
        {"name": "Akati-Os", "description": None, "isFork": False,
         "url": "https://github.com/x2Swiftyouz/Akati-Os", "stargazerCount": 0,
         "forkCount": 0, "pushedAt": ago(days=12), "primaryLanguage": ps,
         "languages": {"edges": [{"size": 21000, "node": ps}]}},
        {"name": "x2Swiftyouz", "description": "profile", "isFork": False,
         "url": "https://github.com/x2Swiftyouz/x2Swiftyouz", "stargazerCount": 0,
         "forkCount": 0, "pushedAt": ago(hours=1), "primaryLanguage": py,
         "languages": {"edges": [{"size": 12000, "node": py}]}},
    ]
    events = [
        {"type": "PushEvent", "repo": {"name": "x2Swiftyouz/Bot-Ai-Discord"},
         "payload": {"size": 2}, "created_at": ago(hours=5)},
        {"type": "PushEvent", "repo": {"name": "x2Swiftyouz/Bot-Ai-Discord"},
         "payload": {"size": 1}, "created_at": ago(hours=6)},
        {"type": "PullRequestEvent", "repo": {"name": "x2Swiftyouz/Bot-Music"},
         "payload": {"action": "closed", "number": 4,
                     "pull_request": {"merged": True, "title": "Add loop command"}},
         "created_at": ago(days=3)},
        {"type": "CreateEvent", "repo": {"name": "x2Swiftyouz/Akati-Os"},
         "payload": {"ref_type": "repository"}, "created_at": ago(days=12)},
        {"type": "WatchEvent", "repo": {"name": "Platane/snk"}, "payload": {"action": "started"},
         "created_at": ago(days=14)},
    ]
    return {
        "name": "x2swiftz_z", "createdAt": "2025-08-14T00:00:00Z", "avatarUrl": "",
        "followers": {"totalCount": 4},
        "repositories": {"totalCount": len(repos), "nodes": repos},
        "contributionsCollection": {
            "totalCommitContributions": 77, "totalPullRequestContributions": 2,
            "totalIssueContributions": 1,
            "contributionCalendar": {"totalContributions": 80, "weeks": weeks}},
        "events": events,
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


def local_now():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=CFG.get("utc_offset", 0))))


def greeting():
    h = local_now().hour
    where = CFG.get("greeting_from", "")
    if 5 <= h < 12:
        g = "☀️ Good morning"
    elif 12 <= h < 17:
        g = "🌤️ Good afternoon"
    elif 17 <= h < 21:
        g = "🌆 Good evening"
    else:
        g = "🌙 Good night"
    return f"{g} from {where}" if where else g


def pick_quote():
    quotes = CFG.get("quotes") or []
    if not quotes:
        return None
    now = local_now()
    slot = now.toordinal() * 4 + now.hour // 6      # changes with every 6h refresh
    return quotes[slot % len(quotes)]


def own_repos(user):
    me = CFG["username"].lower()
    return [n for n in user["repositories"]["nodes"]
            if not n["isFork"] and n["name"].lower() != me]


def top_languages(user, limit=5):
    totals, colors = {}, {}
    for repo in own_repos(user):
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            totals[name] = totals.get(name, 0) + e["size"]
            colors[name] = e["node"]["color"] or "#8b949e"
    total = sum(totals.values())
    if not total:
        return []
    ranked = sorted(totals.items(), key=lambda kv: -kv[1])
    langs = [(n, s / total * 100, colors[n]) for n, s in ranked[:limit]]
    rest = sum(s for _, s in ranked[limit:])
    if rest:
        langs.append(("Other", rest / total * 100, "#8b949e"))
    return langs


def readable(color, theme_name):
    """Lighten very dark language colours (e.g. PowerShell #012456) on the dark theme."""
    if theme_name != "dark" or not color:
        return color
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if lum >= 90:
        return color
    k = 0.55                                       # mix with white
    r, g, b = (round(c + (255 - c) * k) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def rel_time(iso):
    then = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    secs = (dt.datetime.now(dt.timezone.utc) - then).total_seconds()
    for unit, size in (("y", 31536000), ("mo", 2592000), ("d", 86400), ("h", 3600), ("m", 60)):
        if secs >= size:
            return f"{int(secs // size)}{unit} ago"
    return "just now"


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
    lines = [("title", head), ("dim", "-" * INFO_COLS), ("greet", greeting()), ("blank", "")]

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

    langs = top_languages(user)
    if langs:
        lines += [("blank", ""), ("section", "- Top Languages " + "-" * (INFO_COLS - 16)),
                  ("bar", langs)]
        # legend: two entries per line
        for i in range(0, len(langs), 2):
            lines.append(("legend", langs[i:i + 2]))
    return lines, cc["contributionCalendar"]


def render(user, theme_name):
    t = THEMES[theme_name]
    rows = ascii_rows(load_portrait(user), CFG["portrait_cols"])
    lines, cal = build_lines(user)
    quote = pick_quote()

    left_w = CFG["portrait_cols"] * CW
    info_x = PAD + left_w + 32
    width = int(info_x + INFO_COLS * CW + PAD)
    prompt_y = TB + 18 + FONT
    top = prompt_y + int(LH * 1.8)
    body_rows = max(len(rows), len(lines) + 2)

    weeks = cal["weeks"]
    cell, gap = 11, 3
    graph_w = len(weeks) * (cell + gap) - gap
    quote_y = top + body_rows * LH + 10
    graph_y = quote_y + (34 if quote else 0) + 18
    height = int(graph_y + 7 * (cell + gap) + 30 + PAD)

    s = []
    a = s.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
      f'viewBox="0 0 {width} {height}" font-family="{MONO}" font-size="{FONT}">')
    a(f"""<style>
.p{{fill:url(#pg);white-space:pre}} .f{{fill:{t['fg']}}} .k{{fill:{t['key']}}}
.v{{fill:{t['val']}}} .d{{fill:{t['dim']}}} .h{{fill:{t['title']};font-weight:700}}
text{{white-space:pre}}
.p,.ty,.c{{opacity:0;animation:on .01s forwards}}
.ty{{opacity:1;clip-path:inset(0 100% 0 0);animation:type .45s steps(24) forwards}}
.cmd{{clip-path:inset(0 100% 0 0);animation:type .7s steps(8) .3s forwards}}
.bar{{transform:scaleX(0);transform-box:fill-box;animation:grow .6s ease-out forwards}}
.cur{{fill:{t['title']};animation:blink 1s steps(1) infinite}}
@keyframes on{{to{{opacity:1}}}}
@keyframes type{{to{{clip-path:inset(0 0 0 0)}}}}
@keyframes grow{{to{{transform:scaleX(1)}}}}
@keyframes blink{{50%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{.p,.ty,.c,.cmd,.bar{{animation:none;opacity:1;clip-path:none;transform:none}}.cur{{animation:none}}}}
</style>""")
    g0, g1, g2 = t["grad"]
    port_h = len(rows) * LH
    a(f'<defs><linearGradient id="pg" gradientUnits="userSpaceOnUse" x1="{PAD}" y1="{top}" '
      f'x2="{PAD + left_w:.0f}" y2="{top + port_h}"><stop offset="0" stop-color="{g0}"/>'
      f'<stop offset=".5" stop-color="{g1}"/><stop offset="1" stop-color="{g2}"/>'
      f'</linearGradient>'
      f'<clipPath id="barclip"><rect x="{info_x}" y="0" width="{INFO_COLS * CW:.1f}" '
      f'height="{height}" rx="0"/></clipPath></defs>')

    # window frame + title bar
    a(f'<rect x=".5" y=".5" width="{width-1}" height="{height-1}" rx="10" '
      f'fill="{t["bg"]}" stroke="{t["border"]}"/>')
    a(f'<path d="M.5 {TB}V10.5a10 10 0 0 1 10-10h{width-21}a10 10 0 0 1 10 10V{TB}Z" '
      f'fill="{t["bar"]}"/>')
    a(f'<line x1=".5" y1="{TB}" x2="{width-.5}" y2="{TB}" stroke="{t["border"]}"/>')
    for i, c in enumerate(["#ff5f57", "#febc2e", "#28c840"]):
        a(f'<circle cx="{20 + i*20}" cy="{TB/2}" r="6" fill="{c}"/>')
    a(f'<text class="d" x="{width/2}" y="{TB/2 + 4}" font-size="12" text-anchor="middle">'
      f'{esc(CFG["display"])}@github: ~</text>')

    # prompt: "$ neofetch" typed before anything else shows up
    a(f'<text x="{PAD}" y="{prompt_y}"><tspan class="h">{esc(CFG["display"])}@github</tspan>'
      f'<tspan class="f">:</tspan><tspan class="v">~</tspan><tspan class="f">$ </tspan></text>')
    cmd_x = PAD + (len(CFG["display"]) + 11) * CW
    a(f'<text class="cmd f" x="{cmd_x:.1f}" y="{prompt_y}">neofetch</text>')
    start = 1.1

    # portrait: rows appear top to bottom
    for i, r in enumerate(rows):
        a(f'<text class="p" x="{PAD}" y="{top + i*LH}" style="animation-delay:{start + i*0.04:.2f}s">'
          f'{esc(r)}</text>')

    # info: typed line by line after portrait
    delay = start + len(rows) * 0.04 + 0.2
    y = top
    bar_w = INFO_COLS * CW
    for ln in lines:
        kind = ln[0]
        st = f'style="animation-delay:{delay:.2f}s"'
        if kind == "title":
            a(f'<text class="ty h" x="{info_x}" y="{y}" {st}>{esc(ln[1])}</text>')
        elif kind == "dim":
            a(f'<text class="ty d" x="{info_x}" y="{y}" {st}>{esc(ln[1])}</text>')
        elif kind == "greet":
            a(f'<text class="ty v" x="{info_x}" y="{y}" {st}>{esc(ln[1])}</text>')
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
        elif kind == "bar":
            x = info_x
            a(f'<g clip-path="url(#barclip)"><rect x="{info_x}" y="{y - 11}" '
              f'width="{bar_w:.1f}" height="10" rx="5" fill="{t["bar"]}"/>')
            a(f'<g class="bar" {st}>')
            for _, pct, color in ln[1]:
                w = bar_w * pct / 100
                a(f'<rect x="{x:.1f}" y="{y - 11}" width="{w + 0.5:.1f}" height="10" fill="{readable(color, theme_name)}"/>')
                x += w
            a('</g></g>')
        elif kind == "legend":
            parts = []
            for name, pct, color in ln[1]:
                label = f"{name} {pct:.1f}%"
                parts.append(f'<tspan fill="{readable(color, theme_name)}">●</tspan>'
                             f'<tspan class="v"> {esc(label):<{INFO_COLS // 2 - 4}}</tspan>')
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

    # quote of the moment
    if quote:
        q = f'"{quote["text"]}" — {quote["by"]}'
        a(f'<text class="ty d" x="{width/2}" y="{quote_y + 12}" font-size="13" font-style="italic" '
          f'text-anchor="middle" style="animation-delay:{delay:.2f}s">{esc(q)}</text>')

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


# ---------------------------------------------------------------- project cards
REPO_ICON = ("M2 2.5A2.5 2.5 0 0 1 4.5 0h8.75a.75.75 0 0 1 .75.75v12.5a.75.75 0 0 1-.75.75h-2.5"
             "a.75.75 0 0 1 0-1.5h1.75v-2h-8a1 1 0 0 0-.714 1.7.75.75 0 1 1-1.072 1.05A2.495 "
             "2.495 0 0 1 2 11.5Zm10.5-1h-8a1 1 0 0 0-1 1v6.708A2.486 2.486 0 0 1 4.5 9h8ZM5 "
             "12.25a.25.25 0 0 1 .25-.25h3.5a.25.25 0 0 1 .25.25v3.25a.25.25 0 0 1-.4.2l-1.45"
             "-1.087a.249.249 0 0 0-.3 0L5.4 15.7a.25.25 0 0 1-.4-.2Z")


def wrap(text, cols, max_lines):
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + (1 if cur else 0) <= cols:
            cur = f"{cur} {w}" if cur else w
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    if len(out) > max_lines:
        out = out[:max_lines]
        out[-1] = out[-1][:cols - 1].rstrip() + "…"
    return out


def render_project(repo, theme_name, index):
    t = THEMES[theme_name]
    W, H, fs = 420, 130, 12
    cw = fs * 0.6
    delay = index * 0.15
    s = []
    a = s.append
    a(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
      f'font-family="{MONO}" font-size="{fs}">')
    a(f"""<style>
.in{{opacity:0;animation:in .5s ease-out {delay:.2f}s forwards}}
@keyframes in{{from{{opacity:0;transform:translateY(6px)}}to{{opacity:1;transform:none}}}}
@media (prefers-reduced-motion:reduce){{.in{{animation:none;opacity:1}}}}
</style>""")
    a(f'<defs><clipPath id="card"><rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="8"/>'
      f'</clipPath></defs>')
    a(f'<g class="in"><rect x=".5" y=".5" width="{W-1}" height="{H-1}" rx="8" '
      f'fill="{t["bg"]}" stroke="{t["border"]}"/>')
    a(f'<rect x="0" y="0" width="4" height="{H}" fill="{t["title"]}" clip-path="url(#card)"/>')
    a(f'<path transform="translate(20 18)" d="{REPO_ICON}" fill="{t["dim"]}"/>')
    a(f'<text x="44" y="31" font-size="15" font-weight="700" fill="{t["title"]}">'
      f'{esc(repo["name"])}</text>')
    desc = repo.get("description") or "No description yet"
    for i, line in enumerate(wrap(desc, int((W - 40) / cw), 2)):
        a(f'<text x="20" y="{58 + i*17}" fill="{t["fg"]}">{esc(line)}</text>')
    y = H - 20
    x = 20
    lang = repo.get("primaryLanguage")
    if lang:
        a(f'<circle cx="{x + 5}" cy="{y - 4}" r="5" fill="{readable(lang["color"], theme_name) or t["dim"]}"/>')
        a(f'<text x="{x + 15}" y="{y}" fill="{t["fg"]}">{esc(lang["name"])}</text>')
        x += 15 + len(lang["name"]) * cw + 16
    a(f'<text x="{x:.0f}" y="{y}" fill="{t["dim"]}">★ {repo["stargazerCount"]}   '
      f'⑂ {repo["forkCount"]}</text>')
    a(f'<text x="{W - 16}" y="{y}" fill="{t["dim"]}" text-anchor="end">'
      f'updated {rel_time(repo["pushedAt"])}</text>')
    a("</g></svg>")
    return "\n".join(s)


def write_project_cards(user):
    repos = own_repos(user)[:CFG.get("projects_max", 6)]
    out = ROOT / "cards"
    out.mkdir(exist_ok=True)
    keep = set()
    for i, repo in enumerate(repos):
        for name in THEMES:
            f = out / f"{repo['name']}_{name}.svg"
            f.write_text(render_project(repo, name, i), encoding="utf-8")
            keep.add(f.name)
    for f in out.glob("*.svg"):
        if f.name not in keep:
            f.unlink()

    cells = []
    for repo in repos:
        n = repo["name"]
        cells.append(
            f'<a href="{repo["url"]}"><picture>'
            f'<source media="(prefers-color-scheme: dark)" srcset="cards/{n}_dark.svg">'
            f'<img alt="{html.escape(n)}" src="cards/{n}_light.svg" width="49%">'
            f'</picture></a>')
    if not cells:
        return "_No public projects yet._"
    return '<p align="center">\n' + "\n".join(cells) + "\n</p>"


# ---------------------------------------------------------------- activity feed
def describe(ev):
    repo = ev["repo"]["name"]
    link = f"[{repo}](https://github.com/{repo})"
    p = ev.get("payload") or {}
    kind = ev["type"]
    if kind == "PushEvent":
        n = p.get("size") or len(p.get("commits") or [])
        what = f"{n} commit{'s' * (n != 1)}" if n else "code"
        return "⬆️", f"Pushed {what} to {link}", ("push", repo), n
    if kind == "CreateEvent":
        ref = p.get("ref_type")
        if ref == "repository":
            return "🎉", f"Created repository {link}", None, 0
        if ref in ("branch", "tag"):
            icon = "🌿" if ref == "branch" else "🏷️"
            return icon, f"Created {ref} `{p.get('ref')}` in {link}", None, 0
    if kind == "PullRequestEvent":
        pr = p.get("pull_request") or {}
        num = p.get("number") or pr.get("number")
        pr_link = f"[#{num}](https://github.com/{repo}/pull/{num})"
        action = p.get("action")
        if action == "opened":
            return "🔀", f"Opened PR {pr_link} in {link}", None, 0
        if action == "closed":
            if pr.get("merged"):
                return "✅", f"Merged PR {pr_link} in {link}", None, 0
            return "❌", f"Closed PR {pr_link} in {link}", None, 0
    if kind == "IssuesEvent":
        num = (p.get("issue") or {}).get("number")
        issue = f"[#{num}](https://github.com/{repo}/issues/{num})"
        if p.get("action") == "opened":
            return "🐛", f"Opened issue {issue} in {link}", None, 0
        if p.get("action") == "closed":
            return "✔️", f"Closed issue {issue} in {link}", None, 0
    if kind == "IssueCommentEvent":
        num = (p.get("issue") or {}).get("number")
        return "💬", f"Commented on [#{num}](https://github.com/{repo}/issues/{num}) in {link}", None, 0
    if kind == "WatchEvent":
        return "⭐", f"Starred {link}", None, 0
    if kind == "ForkEvent":
        return "🍴", f"Forked {link}", None, 0
    if kind == "ReleaseEvent":
        tag = (p.get("release") or {}).get("tag_name", "")
        return "🚀", f"Released `{tag}` in {link}", None, 0
    if kind == "PublicEvent":
        return "📢", f"Made {link} public", None, 0
    return None


def activity_markdown(user, limit=6):
    items = []
    for ev in user.get("events") or []:
        d = describe(ev)
        if not d:
            continue
        icon, text, group, count = d
        prev = items[-1] if items else None
        if group and prev and prev["group"] == group:
            # merge consecutive pushes to the same repo into one line
            prev["count"] += count
            n = prev["count"]
            what = f"{n} commit{'s' * (n != 1)}" if n else "code"
            prev["text"] = f"Pushed {what} to [{group[1]}](https://github.com/{group[1]})"
            continue
        items.append({"icon": icon, "text": text, "group": group, "count": count,
                      "when": rel_time(ev["created_at"])})
        if len(items) > limit:
            break
    items = items[:limit]
    if not items:
        return "_No public activity yet._"
    return "\n".join(f"- {i['icon']} {i['text']} · <sub>{i['when']}</sub>" for i in items)


def fill_section(text, name, body):
    pattern = re.compile(rf"(<!--START_SECTION:{name}-->).*?(<!--END_SECTION:{name}-->)", re.S)
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", text)


# ---------------------------------------------------------------- main
def main():
    user = fetch_mock() if "--mock" in sys.argv else fetch_live()
    for name in THEMES:
        (ROOT / f"{name}_mode.svg").write_text(render(user, name), encoding="utf-8")
        print(f"wrote {name}_mode.svg")

    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = fill_section(text, "projects", write_project_cards(user))
    text = fill_section(text, "activity", activity_markdown(user))
    readme.write_text(text, encoding="utf-8")
    print("updated README.md")


if __name__ == "__main__":
    main()
