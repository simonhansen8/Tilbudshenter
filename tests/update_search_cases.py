"""Skriver søgningens nuværende træf ind i tests/data/search_cases.json.

    python tests/update_search_cases.py              # godkend nye træf
    python tests/update_search_cases.py --nyt kaffe  # tilføj et søgeord
    python tests/update_search_cases.py --fjern-traef

Træf, der forsvinder fra "find", bliver kun fjernet med --fjern-traef, og det må
kun bruges, når Simon har sagt god for det. Ellers stopper scriptet og viser dem.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_search_cases import DATA, current_hits, load_cases  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nyt", nargs="*", default=[], help="nye søgeord at tage med")
    ap.add_argument("--fjern-traef", action="store_true", help="tillad at træf forsvinder (kun med Simons ok)")
    args = ap.parse_args()
    cases = load_cases() if (DATA / "search_cases.json").exists() else {}
    for t in args.nyt:
        cases.setdefault(t, {"find": [], "sidst": []})
    got = current_hits(list(cases))
    lost = {t: sorted(set(c["find"]) - set(got[t]["find"])) for t, c in cases.items()}
    lost = {t: v for t, v in lost.items() if v}
    if lost and not args.fjern_traef:
        for t, v in lost.items():
            print(f"'{t}' mister: {v}")
        print("Ret søgningen, eller brug --fjern-traef hvis Simon har godkendt det.")
        return 1
    for t in cases:
        added = sorted(set(got[t]["find"]) - set(cases[t]["find"]))
        if added:
            print(f"'{t}' nye træf: {added}")
    (DATA / "search_cases.json").write_text(json.dumps(got, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
