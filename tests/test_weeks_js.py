"""Ugeplanens ugenumre (mellem "// <weeks>" og "// </weeks>" i app.html),
kørt i Node og tjekket mod Pythons ISO-kalender."""

import datetime
import json
import shutil
import subprocess
from importlib import resources

import pytest


def run_js(code: str) -> object:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <weeks>", 1)[1].split("\n", 1)[1].split("// </weeks>", 1)[0]
    script = f"process.env.TZ = 'Europe/Copenhagen';\n{block}\nconsole.log(JSON.stringify({code}));\n"
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def test_week_numbers_follow_iso_calendar():
    days = [datetime.date(2024, 12, 23) + datetime.timedelta(days=n) for n in range(0, 900, 3)]
    js = run_js(f"{json.dumps([d.isoformat() for d in days])}.map(s => {{"
                "const [y, m, d] = s.split('-').map(Number); const w = weekOf(new Date(y, m - 1, d, 12));"
                "return [w.key, w.monday.getFullYear(), w.monday.getMonth() + 1, w.monday.getDate()]; })")
    for day, (key, y, m, d) in zip(days, js):
        year, week, weekday = day.isocalendar()
        assert key == f"{year}-W{week:02d}", day
        assert datetime.date(y, m, d) == day - datetime.timedelta(days=weekday - 1), day


def test_week_dates_and_cleanup():
    got = run_js("[weekDates(weekOf(new Date(2026, 9, 16, 12))), weekDates(weekOf(new Date(2026, 8, 30, 12))),"
                 " weekOf(new Date(2026, 11, 31, 12)).key, weekOf(new Date(2027, 0, 3, 23, 30)).key,"
                 " cleanWeeks({'2026-W37': ['a'], '2026-W38': ['b'], '2026-W43': [], '2026-W44': ['c']}, new Date(2026, 9, 16, 12))]")
    assert got == ["12.–18. oktober", "28. september – 4. oktober", "2026-W53", "2026-W53",
                   {"2026-W38": ["b"], "2026-W44": ["c"]}]
