import json

from tilbudshenter.cli import main


def test_demo_end_to_end(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert main(["scan", "--demo"]) == 0
    out = capsys.readouterr().out
    assert "5 nye aviser" in out and "Kyllingebryst" in out

    reports = tmp_path / "rapporter" / "demo"
    assert (reports / "seneste.html").exists()
    data = json.loads((reports / "seneste.json").read_text("utf-8"))
    assert data["offers"] and all(o["category"] != "oel_og_vin" for o in data["offers"])

    assert main(["scan", "--demo"]) == 0
    assert "Ingen nye aviser" in capsys.readouterr().out

    assert main(["tilbud", "--demo", "--alle", "-b", "lidl", "-f", "json"]) == 0
    offers = json.loads(capsys.readouterr().out)["offers"]
    assert offers and {o["dealer"] for o in offers} == {"Lidl"}


def test_offers_without_scan(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["tilbud"]) == 1
    assert "Kør først" in capsys.readouterr().out
