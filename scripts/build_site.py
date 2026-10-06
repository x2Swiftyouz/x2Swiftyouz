"""Build the portfolio site (GitHub Pages) from the same data as the profile card.

Output goes to _site/: index.html, one page per dev log post, and the portrait.

Usage:
    GITHUB_TOKEN=xxx python scripts/build_site.py      # live data
    python scripts/build_site.py --mock                # fake data, for local preview
"""
import datetime as dt
import html
import shutil
import sys

import markdown

import generate as gen

OUT = gen.ROOT / "_site"
E = html.escape

CSS = """
:root{--bg:#ffffff;--panel:#f6f8fa;--border:#d0d7de;--fg:#24292f;--dim:#57606a;
  --accent:#1a7f37;--accent2:#0969da;--accent3:#8250df;
  --c0:#ebedf0;--c1:#9be9a8;--c2:#40c463;--c3:#30a14e;--c4:#216e39}
@media (prefers-color-scheme:dark){:root{--bg:#0d1117;--panel:#161b22;--border:#30363d;--fg:#c9d1d9;
  --dim:#8b949e;--accent:#7ee787;--accent2:#79c0ff;--accent3:#d2a8ff;
  --c0:#161b22;--c1:#0e4429;--c2:#006d32;--c3:#26a641;--c4:#39d353}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
  font:16px/1.6 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
code,.mono{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
a{color:var(--accent2);text-decoration:none}a:hover{text-decoration:underline}
main{max-width:960px;margin:0 auto;padding:48px 16px 64px}
.hero{display:flex;gap:28px;align-items:center;flex-wrap:wrap}
.hero img{width:132px;height:132px;border-radius:50%;object-fit:cover;border:3px solid var(--accent)}
.hero h1{margin:0;font-size:2.2rem;line-height:1.2}
.hero h1 span{background:linear-gradient(90deg,var(--accent),var(--accent2),var(--accent3));
  -webkit-background-clip:text;background-clip:text;color:transparent}
.tag{color:var(--dim);margin:6px 0 12px}
.links a{display:inline-block;margin:0 8px 8px 0;padding:4px 12px;border:1px solid var(--border);
  border-radius:999px;color:var(--fg);font-size:.9rem}
h2{margin:48px 0 16px;font-size:1.25rem}
h2::before{content:"$ ";color:var(--accent);font-family:ui-monospace,monospace}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px}
.stat{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:14px}
.stat b{display:block;font-size:1.6rem;color:var(--accent)}
.stat span{color:var(--dim);font-size:.85rem}
.bar{display:flex;height:10px;border-radius:5px;overflow:hidden;background:var(--panel);margin-bottom:8px}
.legend span{margin-right:16px;font-size:.9rem;white-space:nowrap}
.dot{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}
.card{display:block;background:var(--panel);border:1px solid var(--border);border-left:4px solid var(--accent);
  border-radius:10px;padding:16px;color:var(--fg);transition:transform .15s,border-color .15s}
.card:hover{transform:translateY(-3px);border-color:var(--accent2);text-decoration:none}
.card h3{margin:0 0 6px;color:var(--accent);font-family:ui-monospace,monospace;font-size:1rem}
.card p{margin:0 0 12px;color:var(--fg);font-size:.92rem}
.meta{color:var(--dim);font-size:.82rem;display:flex;gap:14px;flex-wrap:wrap}
ul.list{list-style:none;padding:0;margin:0}
ul.list li{padding:8px 0;border-bottom:1px solid var(--border)}
ul.list li:last-child{border:0}
.when{color:var(--dim);font-size:.82rem;margin-left:6px}
.heat{display:grid;grid-auto-flow:column;grid-template-rows:repeat(7,11px);gap:3px;overflow-x:auto;padding-bottom:4px}
.heat i{width:11px;height:11px;border-radius:2px;background:var(--c0)}
.l1{background:var(--c1)!important}.l2{background:var(--c2)!important}
.l3{background:var(--c3)!important}.l4{background:var(--c4)!important}
blockquote{margin:0;padding:12px 16px;border-left:3px solid var(--accent3);background:var(--panel);
  border-radius:0 8px 8px 0;color:var(--dim);font-style:italic}
article h1{font-size:1.9rem}article pre{background:var(--panel);padding:12px;border-radius:8px;overflow-x:auto}
footer{margin-top:56px;color:var(--dim);font-size:.85rem;text-align:center}
"""


def page(title, body):
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(tagline())}">
<style>{CSS}</style>
<script>addEventListener("load",()=>{{const h=document.querySelector(".heat");if(h)h.scrollLeft=h.scrollWidth}})</script>
</head>
<body><main>{body}
<footer>Built automatically from <a href="https://github.com/{gen.CFG['username']}/{gen.CFG['username']}">my
profile repo</a> · updated {dt.datetime.now(dt.timezone.utc):%Y-%m-%d %H:%M} UTC</footer>
</main></body></html>
"""


def tagline():
    info = dict(i for i in gen.CFG["info"] if i)
    parts = [info.get("Languages.Programming"), info.get("Currently.Building")]
    return " · ".join(p for p in parts if p) or "Developer"


def info_value(key):
    return dict(i for i in gen.CFG["info"] if i).get(key, "")


def hero(user):
    c = gen.CFG
    links = [f'<a href="https://github.com/{c["username"]}">GitHub</a>']
    if str(c.get("discord_id") or "").isdigit():
        links.append(f'<a href="https://discord.com/users/{c["discord_id"]}">Discord</a>')
    if c.get("codewars_user"):
        links.append(f'<a href="https://www.codewars.com/users/{E(c["codewars_user"])}">Codewars</a>')
    img = '<img src="portrait.jpg" alt="">' if (gen.ROOT / c["portrait"]).exists() else ""
    return f"""<section class="hero">{img}<div>
<h1>Hi, I'm <span>{E(c['display'])}</span> 👋</h1>
<p class="tag">{E(tagline())} · {E(info_value('Host'))}</p>
<div class="links">{''.join(links)}</div></div></section>"""


def stats(user):
    cc = user["contributionsCollection"]
    cur, best = gen.streaks(cc["contributionCalendar"]["weeks"])
    items = [(user["repositories"]["totalCount"], "public repos"),
             (cc["totalCommitContributions"], "commits this year"),
             (cc["contributionCalendar"]["totalContributions"], "contributions"),
             (f"{cur}d", "current streak"), (f"{best}d", "best streak")]
    tiles = "".join(f'<div class="stat"><b>{E(str(v))}</b><span>{E(k)}</span></div>' for v, k in items)
    return f"<h2>whoami --stats</h2><div class='stats'>{tiles}</div>"


def languages(user):
    langs = gen.top_languages(user)
    if not langs:
        return ""
    # the page follows the viewer's theme, so lighten very dark colours for both
    langs = [(n, p, gen.readable(c, "dark")) for n, p, c in langs]
    bar = "".join(f'<span style="width:{p:.2f}%;background:{E(c)}"></span>' for _, p, c in langs)
    legend = "".join(f'<span><i class="dot" style="background:{E(c)}"></i>{E(n)} {p:.1f}%</span>'
                     for n, p, c in langs)
    return f"<h2>languages</h2><div class='bar'>{bar}</div><div class='legend'>{legend}</div>"


def heatmap(user):
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    first = (dt.date.fromisoformat(weeks[0]["contributionDays"][0]["date"]).weekday() + 1) % 7
    cells = ['<i style="visibility:hidden"></i>'] * first      # Sunday-first rows, like GitHub
    for w in weeks:
        for d in w["contributionDays"]:
            n = d["contributionCount"]
            lvl = 0 if n == 0 else 1 if n < 3 else 2 if n < 6 else 3 if n < 10 else 4
            cells.append(f'<i class="l{lvl}" title="{d["date"]}: {n}"></i>')
    return f"<h2>git log --graph</h2><div class='heat'>{''.join(cells)}</div>"


def projects(user):
    cards = []
    for r in gen.own_repos(user)[:gen.CFG.get("projects_max", 6)]:
        lang = r.get("primaryLanguage")
        dot = (f'<span><i class="dot" style="background:{E(lang["color"] or "#8b949e")}"></i>'
               f'{E(lang["name"])}</span>') if lang else ""
        cards.append(f"""<a class="card" href="{E(r['url'])}"><h3>{E(r['name'])}</h3>
<p>{E(r.get('description') or 'No description yet')}</p>
<div class="meta">{dot}<span>★ {r['stargazerCount']}</span><span>⑂ {r['forkCount']}</span>
<span>updated {gen.rel_time(r['pushedAt'])}</span></div></a>""")
    return f"<h2>ls ~/projects</h2><div class='grid'>{''.join(cards)}</div>" if cards else ""


def commits(user):
    found = []
    for repo in gen.own_repos(user):
        target = (repo.get("defaultBranchRef") or {}).get("target") or {}
        for c in (target.get("history") or {}).get("nodes") or []:
            if not c["messageHeadline"].startswith("Merge "):
                found.append((c["committedDate"], repo["name"], c))
    found.sort(key=lambda f: f[0], reverse=True)
    rows = "".join(f'<li><a class="mono" href="{E(c["url"])}">{c["oid"][:7]}</a> '
                   f'<b>{E(name)}</b> — {E(c["messageHeadline"])}<span class="when">{gen.rel_time(d)}</span></li>'
                   for d, name, c in found[:8])
    return f"<h2>git log --oneline</h2><ul class='list'>{rows}</ul>" if rows else ""


def devlog(posts):
    if not posts:
        return ""
    rows = "".join(f'<li><a href="posts/{p["file"][:-3]}.html">{E(p["title"])}</a>'
                   f'<span class="when">{p["date"]}</span></li>' for p in posts)
    return f"<h2>cat ~/devlog</h2><ul class='list'>{rows}</ul>"


def quote():
    q = gen.pick_quote()
    return f"<h2>fortune</h2><blockquote>“{E(q['text'])}” — {E(q['by'])}</blockquote>" if q else ""


def build(user):
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "posts").mkdir(parents=True)
    portrait = gen.ROOT / gen.CFG["portrait"]
    if portrait.exists():
        shutil.copy(portrait, OUT / "portrait.jpg")

    posts = gen.devlog_posts()
    body = "".join([hero(user), stats(user), languages(user), heatmap(user), projects(user),
                    commits(user), devlog(posts), quote()])
    (OUT / "index.html").write_text(page(f"{gen.CFG['display']} · portfolio", body), encoding="utf-8")

    for p in posts:
        src = (gen.ROOT / "devlog" / p["file"]).read_text(encoding="utf-8")
        article = markdown.markdown(src, extensions=["fenced_code", "tables"])
        body = (f'<p><a href="../index.html">← back</a></p><article>{article}</article>'
                f'<p class="when">{p["date"]}</p>')
        (OUT / "posts" / f"{p['file'][:-3]}.html").write_text(
            page(f"{p['title']} · {gen.CFG['display']}", body), encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    print(f"built {OUT} ({len(posts)} posts)")


if __name__ == "__main__":
    build(gen.fetch_mock() if "--mock" in sys.argv else gen.fetch_live())
