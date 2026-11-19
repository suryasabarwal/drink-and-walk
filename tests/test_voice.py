import re
from pathlib import Path

from dw import notes, voice

ROOT = Path(__file__).resolve().parent.parent
BANNED = ["delve", "tapestry", "vibrant", "bustling", "hidden gem", "unforgettable", "elevate", "embark", "journey",
          "nestled", "curated", "seamless", "foodie", "whether you're", "look no further", "game-changer", "unlock",
          "dive into", "let's", "!", "—", "–", "in conclusion", "ultimate", "perfect for", "explore"]


def check(text, where):
    low = text.lower()
    for b in BANNED:
        assert b not in low, f"{where}: stiff phrase {b!r} in {text[:60]!r}"


def test_every_voice_line_is_clean_and_short():
    for line in voice.all_text():
        check(line, "voice")
        assert len(line) <= 130, line


def test_page_and_script_copy_is_clean():
    for f in ("templates/index.html", "static/app.js"):
        text = (ROOT / f).read_text()
        text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        for lit in re.findall(r"'((?:[^'\\\n]|\\.)*)'", text):
            if " " in lit and not lit.startswith(("http", "/api")):
                check(lit, f)


def test_banners_are_clean():
    from datetime import date
    for d in (date(2026, 12, 31), date(2026, 11, 25), date(2026, 5, 22), date(2026, 3, 17), date(2026, 12, 25)):
        for b in notes.banners([d], "US", {d.isoformat(): {"rain_pct": 80, "lo_c": -5, "hi_c": 35}}):
            check(b["text"], "banner")


def test_every_line_bank_has_variety():
    assert all(len(v) >= 3 for v in voice.LINES.values())
