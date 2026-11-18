"""Mærket ved navnet (mellem "// <version>" og "// </version>" i app.html):
udgave, ny udgave og hentning af aviser."""

import json
import re
import shutil
import subprocess
from importlib import resources
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = {"sha": "a" * 40}
NEW = {"sha": "b" * 40}


def run(expr: str):
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <version>", 1)[1].split("\n", 1)[1].split("// </version>", 1)[0]
    script = f"{block}\nconsole.log(JSON.stringify({expr}));\n"
    out = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(out.stdout)


def status(**v):
    return run(f"versionStatus({json.dumps(v)})")


def test_site_latest():
    assert status(static=True, page=PAGE, generated="2026-11-18T04:20:00Z",
                  deployed={**PAGE, "generated": "2026-11-18T04:20:00Z"},
                  run={"status": "completed", "conclusion": "success", "head_sha": PAGE["sha"]}) \
        == {"kind": "ok", "text": "Seneste udgave"}
    # Uden svar fra GitHub og version.json siges det stadig, ud fra hvad siden ved
    assert status(static=True, page=PAGE)["kind"] == "ok"


def test_site_new_version_or_offers():
    assert status(static=True, page=PAGE, deployed=NEW) == {"kind": "new", "text": "Ny udgave klar", "reload": True}
    got = status(static=True, page=PAGE, generated="2026-11-18T04:20:00Z",
                 deployed={**PAGE, "generated": "2026-11-18T15:20:00Z"})
    assert got["text"] == "Nye tilbud klar" and got["reload"]
    # En ny udgave går forud for, at der hentes igen
    assert status(static=True, page=PAGE, deployed=NEW, run={"status": "in_progress"})["kind"] == "new"


def test_site_fetching():
    assert status(static=True, page=PAGE, run={"status": "in_progress", "head_sha": PAGE["sha"]}) \
        == {"kind": "busy", "text": "Henter tilbudsaviser…"}
    assert status(static=True, page=PAGE, run={"status": "queued", "head_sha": NEW["sha"]})["text"] \
        == "Henter aviser og ny udgave…"


def test_site_failed_or_stale():
    assert status(static=True, page=PAGE, run={"status": "completed", "conclusion": "failure"})["kind"] == "error"
    assert status(static=True, page=PAGE, run={"status": "completed", "conclusion": "cancelled"})["kind"] == "ok"
    assert status(static=True, page=PAGE, stale=True)["kind"] == "warn"


def test_local():
    sha = PAGE["sha"]
    assert status(local={"sha": sha, "latest": sha}) == {"kind": "ok", "text": "Seneste udgave"}
    assert status(local={"sha": sha})["text"] == "Udgave aaaaaaa"
    assert status(local={"sha": sha, "latest": NEW["sha"]})["kind"] == "new"
    assert status(local={"sha": sha, "latest": sha, "dirty": True})["kind"] == "warn"
    assert status(local={})["kind"] == "unknown"
    assert status(local={"sha": sha, "latest": NEW["sha"]}, scanning=True)["kind"] == "busy"


def test_next_scheduled_matches_workflow():
    workflow = (ROOT / ".github" / "workflows" / "side.yml").read_text("utf-8")
    minute, hours = re.search(r'cron: "(\d+) ([\d,]+) \* \* \*"', workflow).groups()
    assert run("SCHEDULE_UTC") == [[int(h), int(minute)] for h in hours.split(",")]
    assert run('nextScheduled(new Date("2026-11-18T10:00:00Z"))') == "2026-11-18T15:17:00.000Z"
    assert run('nextScheduled(new Date("2026-11-18T20:00:00Z"))') == "2026-11-19T04:17:00.000Z"
