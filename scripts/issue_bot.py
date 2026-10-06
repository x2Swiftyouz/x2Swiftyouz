"""Handle profile issues: guestbook entries and tic-tac-toe moves.

Runs from .github/workflows/issues.yml when an issue is opened. Reads the event from
GITHUB_EVENT_PATH, updates guestbook.json / xo.json and re-renders their README sections.
The reply is only queued; the workflow posts it (and closes the issue) after the
change has been pushed, so a failed push never leaves a misleading answer.

Usage:
    python scripts/issue_bot.py                 # handle the issue in GITHUB_EVENT_PATH
    python scripts/issue_bot.py --send-reply    # post the queued reply, close the issue
    python scripts/issue_bot.py --render        # just re-render both README sections
"""
import datetime as dt
import html
import json
import os
import random
import re
import sys
from pathlib import Path
from urllib.parse import quote

import requests

ROOT = Path(__file__).resolve().parent.parent
CFG = json.loads((ROOT / "profile.json").read_text(encoding="utf-8"))
REPO = f"{CFG['username']}/{CFG['username']}"
NEW_ISSUE = f"https://github.com/{REPO}/issues/new"
GUESTBOOK = ROOT / "guestbook.json"
XO = ROOT / "xo.json"
REPLY = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "issue-bot-reply.json"
MAX_MESSAGE = 200
SHOW_ENTRIES = 10
LINES = [(0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6), (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6)]


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def fill_section(text, name, body):
    pattern = re.compile(rf"(<!--START_SECTION:{name}-->).*?(<!--END_SECTION:{name}-->)", re.S)
    return pattern.sub(lambda m: f"{m.group(1)}\n{body}\n{m.group(2)}", text)


# ---------------------------------------------------------------- github api
def api(method, path, **kw):
    r = requests.request(method, f"https://api.github.com/repos/{REPO}{path}", timeout=30,
                         headers={"Authorization": f"bearer {os.environ['GITHUB_TOKEN']}",
                                  "Accept": "application/vnd.github+json"}, **kw)
    r.raise_for_status()


def reply_and_close(number, text, completed=True):
    save(REPLY, {"number": number, "text": text, "completed": completed})


def send_reply():
    if not REPLY.exists():
        return
    r = json.loads(REPLY.read_text(encoding="utf-8"))
    footer = "\n\n<sub>🤖 This reply was posted automatically by the profile bot.</sub>"
    api("POST", f"/issues/{r['number']}/comments", json={"body": r["text"] + footer})
    api("PATCH", f"/issues/{r['number']}", json={
        "state": "closed", "state_reason": "completed" if r["completed"] else "not_planned"})


# ---------------------------------------------------------------- guestbook
def clean_message(body):
    """Visitor text is untrusted: one line, no HTML, no Markdown, no live links."""
    # issue-form layout: text under "### Message", up to the next heading or rule
    m = re.search(r"###\s*Message\s*\n(.*?)(?:\n###\s|\n-{3,}\s*(?:\n|$)|$)", body or "", re.S)
    text = (m.group(1) if m else body or "").replace("_No response_", "")
    text = " ".join(text.split())[:MAX_MESSAGE]
    text = html.escape(text, quote=False)
    text = re.sub(r"([\\`*_{}\[\]()#+\-.!|~:])", r"\\\1", text)
    # zero-width spaces stop GitHub from auto-linking http:// and www.
    text = text.replace("\\:/", "\\:\u200b/")
    text = re.sub(r"(?i)\b(www)\\\.", "\\1\u200b\\.", text)
    return text.replace("@", "@\u200b")                              # no mentions


def render_guestbook():
    entries = load(GUESTBOOK, [])
    sign = f"{NEW_ISSUE}?template=guestbook.yml"
    head = f"[**✍️ Sign the guestbook**]({sign}) — leave a message and it shows up here.\n"
    if not entries:
        return head + "\n_Be the first to sign!_"
    rows = [f"- **[{e['user']}](https://github.com/{e['user']})**: {e['message']}"
            f" · <sub>{e['date'][:10]}</sub>" for e in reversed(entries[-SHOW_ENTRIES:])]
    return head + "\n" + "\n".join(rows)


def handle_guestbook(issue):
    user, number = issue["user"]["login"], issue["number"]
    message = clean_message(issue.get("body"))
    if not message.strip():
        reply_and_close(number, "Your message was empty, so nothing was added. Try again! 🙂", False)
        return
    entries = load(GUESTBOOK, [])
    now = dt.datetime.now(dt.timezone.utc)
    recent = [e for e in entries if e["user"] == user
              and now - dt.datetime.fromisoformat(e["date"]) < dt.timedelta(days=1)]
    if recent:
        reply_and_close(number, "You already signed in the last 24 hours. Thanks for coming back! 💚", False)
        return
    entries.append({"user": user, "message": message, "date": now.isoformat(), "issue": number})
    save(GUESTBOOK, entries)
    reply_and_close(number, f"Thanks for signing, @{user}! 💚 Your message is now on "
                            f"[the profile](https://github.com/{CFG['username']}).")


# ---------------------------------------------------------------- tic-tac-toe
def winner(b):
    for x, y, z in LINES:
        if b[x] != " " and b[x] == b[y] == b[z]:
            return b[x]
    return "draw" if " " not in b else None


def bot_move(b):
    """Beatable on purpose: win, else block, else centre, else random."""
    free = [i for i, c in enumerate(b) if c == " "]
    for mark in ("O", "X"):
        for i in free:
            trial = b[:i] + mark + b[i + 1:]
            if winner(trial) == mark:
                return i
    if 4 in free:
        return 4
    return random.choice(free)


def ascii_board(b):
    c = [b[i] if b[i] != " " else str(i + 1) for i in range(9)]
    return "\n".join(" | ".join(c[r * 3:r * 3 + 3]) for r in range(3))


def render_xo():
    st = load(XO, {"board": " " * 9, "stats": {"you": 0, "bot": 0, "draw": 0}, "log": []})
    b = st["board"]
    keycaps = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
    body = quote("Just press **Create** — the bot plays back within a minute. 🎮")

    def cell(i):
        if b[i] == "X":
            return "❌"
        if b[i] == "O":
            return "⭕"
        return f'<a href="{NEW_ISSUE}?title={quote(f"xo: {i + 1}")}&body={body}">{keycaps[i]}</a>'

    rows = "\n".join("<tr>" + "".join(f'<td align="center" width="48">{cell(r * 3 + c)}</td>'
                                      for c in range(3)) + "</tr>" for r in range(3))
    s = st["stats"]
    out = ["You are ❌ — click a number to play your move. The bot answers as ⭕.", "",
           f"<table>\n{rows}\n</table>", "",
           f"🏆 Visitors **{s['you']}** · 🤖 Bot **{s['bot']}** · 🤝 Draws **{s['draw']}**"]
    if st.get("last_result"):
        out.append(f"<br>Last game: {st['last_result']}")
    if st["log"]:
        out.append("<br><sub>Recent moves: " + " · ".join(st["log"]) + "</sub>")
    return "\n".join(out)


def handle_xo(issue, cell):
    user, number = issue["user"]["login"], issue["number"]
    st = load(XO, {"board": " " * 9, "stats": {"you": 0, "bot": 0, "draw": 0}, "log": []})
    b = st["board"]
    if b[cell] != " ":
        reply_and_close(number, f"Square {cell + 1} is already taken — pick another one on "
                                f"[the profile](https://github.com/{CFG['username']}).", False)
        return
    b = b[:cell] + "X" + b[cell + 1:]
    result = winner(b)
    reply = f"You played **{cell + 1}**."
    if not result:
        o = bot_move(b)
        b = b[:o] + "O" + b[o + 1:]
        result = winner(b)
        reply += f" The bot answered **{o + 1}**."
    st["log"] = ([f"{user} → {cell + 1}"] + st["log"])[:5]
    if result:
        key, text = {"X": ("you", f"🎉 {user} beat the bot!"),
                     "O": ("bot", f"🤖 the bot beat {user}"),
                     "draw": ("draw", f"🤝 {user} and the bot drew")}[result]
        st["stats"][key] += 1
        st["last_result"] = text
        reply += f"\n\n```\n{ascii_board(b)}\n```\n\n{text}. A new game has started."
        b = " " * 9
    else:
        reply += f"\n\n```\n{ascii_board(b)}\n```\n\nYour turn again on " \
                 f"[the profile](https://github.com/{CFG['username']})!"
    st["board"] = b
    save(XO, st)
    reply_and_close(number, reply)


# ---------------------------------------------------------------- main
def render_readme():
    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    text = fill_section(text, "guestbook", render_guestbook())
    text = fill_section(text, "xo", render_xo())
    readme.write_text(text, encoding="utf-8")


def main():
    if "--send-reply" in sys.argv:
        send_reply()
        return
    if "--render" not in sys.argv:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        issue = event["issue"]
        title = issue["title"].strip()
        move = re.fullmatch(r"xo\s*:\s*([1-9])", title, re.I)
        if move:
            handle_xo(issue, int(move.group(1)) - 1)
        elif title.lower().startswith("guestbook"):
            handle_guestbook(issue)
        else:
            print("not a guestbook or xo issue; ignoring")
            return
    render_readme()


if __name__ == "__main__":
    main()
