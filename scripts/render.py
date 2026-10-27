"""Render the profile README images as SVG, styled as psql sessions.

Every image comes in a dark and a light variant that use GitHub's own
Primer colors, so the README matches the theme the visitor picked.

Usage: GITHUB_TOKEN=... python scripts/render.py [login]
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

LOGIN = sys.argv[1] if len(sys.argv) > 1 else "jayeuse"
OUT = Path(__file__).resolve().parent.parent / "assets"

MONO = "ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace"
SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans', Helvetica, Arial, sans-serif"

# Primer canvas/border/fg tokens plus GitHub's code-highlight colors.
THEMES = {
    "dark": {
        "canvas": "#0d1117", "inset": "#161b22", "border": "#30363d",
        "fg": "#e6edf3", "muted": "#7d8590", "prompt": "#3fb950",
        "keyword": "#ff7b72", "number": "#79c0ff", "string": "#a5d6ff",
        "func": "#d2a8ff",
        "dots": ("#ff5f57", "#febc2e", "#28c840"),
    },
    "light": {
        "canvas": "#ffffff", "inset": "#f6f8fa", "border": "#d0d7de",
        "fg": "#1f2328", "muted": "#656d76", "prompt": "#1a7f37",
        "keyword": "#cf222e", "number": "#0550ae", "string": "#0a3069",
        "func": "#8250df",
        "dots": ("#ff5f57", "#febc2e", "#28c840"),
    },
}

# What the hero record and the "now" card say. Edit these by hand.
PROFILE = [
    ("name", "Ceejay Feruelo", "fg"),
    ("role", "Backend Developer & Database Engineer", "string"),
    ("stack", "FastAPI · PostgreSQL · Docker", "fg"),
    ("award", "Champion, Database Programming · IT Skills Olympics 2025", "fg"),
    ("based_in", "Pasig City, PH · UTC+8", "fg"),
    ("status", "open to backend internships & junior roles", "prompt"),
]
NOW = [
    ("building", "OpenSlate, a no-code workspace"),
    ("running", "Shorekeeper, an LLM + RAG bot"),
    ("studying", "query tuning & indexing"),
    ("learning", "CI/CD, monitoring, backups"),
    ("school", "BSIT @ PLP, class of 2027"),
]

QUERY = """
query($login: String!) {
  user(login: $login) {
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch(token: str) -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": LOGIN}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "User-Agent": f"{LOGIN}-profile"},
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        payload = json.load(res)
    if payload.get("errors"):
        raise SystemExit(f"GraphQL error: {payload['errors']}")
    return payload["data"]["user"]


def calendar_days(user: dict) -> list[dict]:
    weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    return sorted((d for w in weeks for d in w["contributionDays"]), key=lambda d: d["date"])


def streaks(days: list[dict]) -> tuple[int, int]:
    """Return (current, longest) streak in days. Today may still be empty."""
    counts = [d["contributionCount"] for d in days]
    longest = run = 0
    for c in counts:
        run = run + 1 if c else 0
        longest = max(longest, run)
    current = 0
    tail = counts[:-1] if counts and counts[-1] == 0 else counts
    for c in reversed(tail):
        if not c:
            break
        current += 1
    return current, longest


# ---------------------------------------------------------------- drawing


def window(t: dict, width: int, height: int, title: str, body: str, label: str) -> str:
    dots = "".join(
        f'<circle cx="{20 + i * 18}" cy="18" r="5.5" fill="{c}"/>' for i, c in enumerate(t["dots"])
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(label)}">
<title>{escape(label)}</title>
<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="10" fill="{t['canvas']}" stroke="{t['border']}"/>
<path d="M0.5 36V10.5a10 10 0 0 1 10-10h{width - 21}a10 10 0 0 1 10 10V36z" fill="{t['inset']}"/>
<line x1="0.5" y1="36" x2="{width - 0.5}" y2="36" stroke="{t['border']}"/>
{dots}
<text x="{width / 2}" y="22.5" text-anchor="middle" font-family="{SANS}" font-size="12" fill="{t['muted']}">{escape(title)}</text>
{body}
</svg>
"""


def span(text: str, fill: str, weight: str = "normal") -> str:
    w = f' font-weight="{weight}"' if weight != "normal" else ""
    return f'<tspan fill="{fill}"{w}>{escape(text)}</tspan>'


def sql(t: dict, query: list[tuple[str, str]]) -> str:
    """query is a list of (kind, text); kind picks the highlight color."""
    colors = {"kw": t["keyword"], "id": t["fg"], "fn": t["func"], "num": t["number"], "str": t["string"]}
    return "".join(span(text, colors[kind], "600" if kind == "kw" else "normal") for kind, text in query)


def prompt(t: dict) -> str:
    return span("jayeuse=# ", t["prompt"], "600")


def line(x: float, y: float, content: str, extra: str = "") -> str:
    return f'<text x="{x}" y="{y}" xml:space="preserve"{extra}>{content}</text>'


def record_header(t: dict, key_w: int, value_w: int) -> str:
    return span("-[ RECORD 1 ]" + "-" * (key_w - 13) + "+" + "-" * value_w, t["muted"])


def hero(t: dict) -> str:
    width, fs, lh, x = 840, 17, 30, 28
    char = fs * 0.62
    # psql widens the key column to fit the record header.
    key_w = max(max(len(k) for k, _, _ in PROFILE) + 1, 14)
    parts: list[str] = []
    clock = 0.4

    def typed(y: float, prefix: str, text: str, styled: str, idx: int) -> str:
        """The prefix shows at once; the rest types out one character at a time.

        The clip starts at full width, so renderers without SMIL show the whole line.
        """
        nonlocal clock
        start, n, step = clock, len(text), 0.03
        end = start + n * step
        prefix_w = len(prefix) * char
        widths = [prefix_w] + [prefix_w + i * char for i in range(1, n + 1)] + [width]
        times = [0.0] + [(start + i * step) / end for i in range(1, n + 1)] + [1.0]
        clock = end + 0.25
        return (
            f'<clipPath id="c{idx}"><rect x="{x - 2}" y="{y - fs}" height="{lh}" width="{width}">'
            f'<animate attributeName="width" dur="{end:.2f}s" calcMode="discrete" fill="freeze" '
            f'values="{";".join(f"{w:.1f}" for w in widths)}" keyTimes="{";".join(f"{k:.4f}" for k in times)}"/>'
            f"</rect></clipPath>" + line(x, y, styled, f' clip-path="url(#c{idx})"')
        )

    def hold(at: float) -> str:
        """Keep an element hidden until `at` seconds; visible by default without SMIL."""
        return f'<animate attributeName="opacity" values="0;1" keyTimes="0;1" dur="{at:.2f}s" calcMode="discrete" fill="freeze"/>'

    def shown(y: float, styled: str, at: float) -> str:
        return line(x, y, styled + hold(at))

    y = 36 + 40
    parts.append(typed(y, "$ ", "psql jayeuse", span("$ ", t["muted"]) + span("psql jayeuse", t["fg"]), 0))
    y += lh
    query = [("kw", "SELECT"), ("id", " * "), ("kw", "FROM"), ("id", " engineer "), ("kw", "WHERE"),
             ("id", " handle = "), ("str", "'jayeuse'"), ("id", ";")]
    parts.append(typed(y, "jayeuse=# ", "".join(s for _, s in query), prompt(t) + sql(t, query), 1))
    reveal = clock
    y += lh
    parts.append(shown(y, record_header(t, key_w, 44), reveal))
    for i, (key, value, tone) in enumerate(PROFILE):
        y += lh
        weight = "600" if key == "name" else "normal"
        row = span(key.ljust(key_w), t["muted"]) + span("| ", t["muted"]) + span(value, t[tone], weight)
        parts.append(shown(y, row, reveal + 0.07 * (i + 1)))
    end = reveal + 0.07 * (len(PROFILE) + 1)
    y += lh
    parts.append(shown(y, span("(1 row)", t["muted"]), end))
    y += lh * 1.25
    parts.append(shown(y, prompt(t), end + 0.15))
    cursor_x = x + len("jayeuse=# ") * char
    parts.append(
        f'<rect x="{cursor_x:.1f}" y="{y - fs + 3}" width="{char:.1f}" height="{fs + 2}" fill="{t["fg"]}">'
        + hold(end + 0.15)
        + f'<animate attributeName="opacity" values="1;0" dur="1.1s" begin="{end + 0.15:.2f}s" '
        f'calcMode="discrete" repeatCount="indefinite"/></rect>'
    )
    body = f'<g font-family="{MONO}" font-size="{fs}">' + "".join(parts) + "</g>"
    label = ". ".join(v for _, v, _ in PROFILE)
    return window(t, width, int(y + 30), "jayeuse — psql — 84×24", body, label)


def kv_card(t: dict, title: str, query: list[tuple[str, str]], rows: list[tuple[str, str, str, str]],
            footer: str, label: str, height: int | None = None) -> str:
    """A psql expanded-display card. rows are (key, value, value_color, unit)."""
    width, fs, lh, x = 410, 13, 25, 20
    key_w = max(max(len(k) for k, *_ in rows) + 1, 14)
    y = 36 + 30
    out = [line(x, y, prompt(t) + sql(t, query))]
    y += lh
    out.append(line(x, y, record_header(t, key_w, 30 - key_w)))
    for key, value, color, unit in rows:
        y += lh
        weight = "600" if color == "number" else "normal"
        out.append(line(x, y, span(key.ljust(key_w), t["muted"]) + span("| ", t["muted"])
                        + span(value, t[color], weight) + span(unit, t["muted"])))
    y += lh
    out.append(line(x, y, span("(1 row)", t["muted"])))
    out.append(f'<text x="{width - x}" y="{y}" text-anchor="end">{span(footer, t["muted"])}</text>')
    body = f'<g font-family="{MONO}" font-size="{fs}">' + "".join(out) + "</g>"
    return window(t, width, height or int(y + 22), title, body, label)


def activity(t: dict, user: dict, days: list[dict]) -> str:
    cc = user["contributionsCollection"]
    current, longest = streaks(days)
    rows = [
        ("contributions", f'{cc["contributionCalendar"]["totalContributions"]:,}', "number", ""),
        ("commits", f'{cc["totalCommitContributions"]:,}', "number", ""),
        ("pull_requests", f'{cc["totalPullRequestContributions"]:,}', "number", ""),
        ("current_streak", f"{current:,}", "number", " days"),
        ("longest_streak", f"{longest:,}", "number", " days"),
    ]
    query = [("kw", "SELECT"), ("id", " * "), ("kw", "FROM"), ("id", " activity_last_year;")]
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    label = "GitHub activity in the last year: " + ", ".join(f"{k.replace('_', ' ')} {v}{u}" for k, v, _, u in rows)
    return kv_card(t, "activity — psql", query, rows, f"-- as of {stamp}", label)


def now_card(t: dict, height: int) -> str:
    rows = [(k, v, "fg" if k != "building" else "string", "") for k, v in NOW]
    query = [("kw", "SELECT"), ("id", " * "), ("kw", "FROM"), ("id", " "), ("fn", "now"), ("id", "();")]
    label = "Right now: " + "; ".join(f"{k} {v}" for k, v in NOW)
    return kv_card(t, "now — psql", query, rows, "-- updated by hand", label, height)


def main() -> None:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("Set GITHUB_TOKEN.")
    user = fetch(token)
    days = calendar_days(user)
    OUT.mkdir(exist_ok=True)
    for name, t in THEMES.items():
        act = activity(t, user, days)
        act_h = int(act.split('height="', 1)[1].split('"', 1)[0])
        (OUT / f"hero-{name}.svg").write_text(hero(t))
        (OUT / f"activity-{name}.svg").write_text(act)
        (OUT / f"now-{name}.svg").write_text(now_card(t, act_h))
    print(f"Wrote {len(THEMES) * 3} images to {OUT}")


if __name__ == "__main__":
    main()
