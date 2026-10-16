"""Søgeord i rigtige aviser skal blive ved med at finde de samme tilbud.

tests/data/search_offers.json er et øjebliksbillede af tilbuddene på siden, og
tests/data/search_cases.json siger for hvert søgeord, hvilke tilbud søgningen
finder: "find" er de rigtige træf (de vises først og under "Mine basisvarer"),
"sidst" er træf, der kun vises nederst i søgningen (fx is med smag af banan).

Ændres søgereglerne, så et søgeord mister et træf, fejler testen og viser
hvilke. Nye træf skal også godkendes: kør

    python tests/update_search_cases.py

som skriver dem ind i filen. Den nægter at fjerne træf fra "find" uden
--fjern-traef, og det må kun bruges, når Simon har sagt god for det.
"""

import json
import shutil
import subprocess
from importlib import resources
from pathlib import Path

import pytest

DATA = Path(__file__).parent / "data"


def current_hits(terms: list[str]) -> dict[str, dict[str, list[str]]]:
    """Kører søgningen fra app.html i Node på øjebliksbilledet."""
    node = shutil.which("node")
    if not node:
        pytest.skip("Node er ikke installeret")
    html = resources.files("tilbudshenter.data").joinpath("app.html").read_text(encoding="utf-8")
    block = html.split("// <search>", 1)[1].split("\n", 1)[1].split("// </search>", 1)[0]
    script = (f"{block}\n"
              f"const offers = JSON.parse(require('fs').readFileSync({json.dumps(str(DATA / 'search_offers.json'))}, 'utf8'));\n"
              "const idx = searchIndex(offers), out = {};\n"
              f"for (const t of {json.dumps(terms, ensure_ascii=False)}) {{\n"
              "  const m = searchMatcher(t, idx), find = new Set(), last = new Set();\n"
              "  for (const o of offers) { const tier = m(o), name = `${o.heading.replace(/\\s+/g, ' ').trim()} · ${o.dealer}`;\n"
              "    if (tier === 0 || tier === 1) find.add(name); else if (tier === 2) last.add(name); }\n"
              "  out[t] = {find: [...find].sort(), sidst: [...last].sort()};\n"
              "}\n"
              "console.log(JSON.stringify(out));\n")
    res = subprocess.run([node, "-"], input=script, capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(res.stdout)


def load_cases() -> dict[str, dict[str, list[str]]]:
    return json.loads((DATA / "search_cases.json").read_text(encoding="utf-8"))


def test_search_terms_keep_their_hits():
    cases = load_cases()
    got = current_hits(list(cases))
    problems = []
    for term, want in cases.items():
        now = got[term]
        lost = sorted(set(want["find"]) - set(now["find"]))
        if lost:
            problems.append(f"'{term}' finder ikke længere: {lost}")
        hidden = sorted(set(want["sidst"]) - set(now["find"]) - set(now["sidst"]))
        if hidden:
            problems.append(f"'{term}' viser ikke længere nederst: {hidden}")
        new = sorted((set(now["find"]) | set(now["sidst"])) - set(want["find"]) - set(want["sidst"]))
        moved = sorted(set(now["find"]) & set(want["sidst"]))
        if new or moved:
            problems.append(f"'{term}' har nye træf, der skal godkendes med tests/update_search_cases.py: {new + moved}")
    assert not problems, "\n".join(problems)
