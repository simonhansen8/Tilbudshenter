import io
import shutil
import zipfile
from pathlib import Path

import pytest

from tilbudshenter import updater

REPO_ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 40
SHA_B = "b" * 40


def make_zip(marker: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        top = "simonhansen8-Tilbudshenter-abc1234/"
        zf.writestr(top, "")
        zf.writestr(top + "src/tilbudshenter/__init__.py", f'__version__ = "{marker}"\n')
        zf.writestr(top + "src/tilbudshenter/updater.py", f"# opdatering {marker}\n")
        zf.writestr(top + "README.md", marker)
        zf.writestr(top + "tests/test_x.py", "")
    return buf.getvalue()


class FakeGitHub:
    def __init__(self, sha=SHA_A, zips=None, token=None, offline=False):
        self.sha, self.zips, self.token, self.offline = sha, zips or {}, token, offline
        self.downloads = []

    def __call__(self, url, headers):
        if self.offline:
            raise updater.UpdateError("Ingen forbindelse")
        if self.token and headers.get("Authorization") != f"Bearer {self.token}":
            raise updater.NotFound("404")
        if url.endswith("/commits/main"):
            return self.sha.encode()
        sha = url.rsplit("/", 1)[1]
        self.downloads.append(sha)
        return self.zips[sha]


def program_marker(home):
    return (home / "program" / "src" / "tilbudshenter" / "__init__.py").read_text()


def test_update_replaces_program_and_keeps_data(tmp_path):
    home = tmp_path / "hjem"
    gh = FakeGitHub(SHA_A, {SHA_A: make_zip("A"), SHA_B: make_zip("B")})
    (home).mkdir()
    (home / "tilbudshenter.toml").write_text("mine indstillinger")
    (home / "tilbud.db").write_bytes(b"data")

    assert updater.update(home, gh, log=lambda _: None)
    assert '"A"' in program_marker(home)
    assert updater.installed_version(home) == SHA_A
    assert (home / "opdater.py").read_text() == "# opdatering A\n"
    assert not (home / "program" / "tests").exists()

    # Samme udgave: intet hentes.
    assert not updater.update(home, gh, log=lambda _: None)
    assert gh.downloads == [SHA_A]

    gh.sha = SHA_B
    assert updater.update(home, gh, log=lambda _: None)
    assert '"B"' in program_marker(home)
    assert sorted(p.name for p in home.iterdir()) == ["opdater.py", "program", "tilbud.db", "tilbudshenter.toml"]
    assert (home / "tilbudshenter.toml").read_text() == "mine indstillinger"
    assert (home / "tilbud.db").read_bytes() == b"data"


def test_update_offline_keeps_installed_version(tmp_path):
    home = tmp_path
    updater.update(home, FakeGitHub(SHA_A, {SHA_A: make_zip("A")}), log=lambda _: None)
    messages = []
    assert not updater.update(home, FakeGitHub(offline=True), log=messages.append)
    assert '"A"' in program_marker(home)
    assert "Starter den udgave" in messages[0]


def test_bad_download_keeps_installed_version(tmp_path):
    home = tmp_path
    updater.update(home, FakeGitHub(SHA_A, {SHA_A: make_zip("A")}), log=lambda _: None)
    assert not updater.update(home, FakeGitHub(SHA_B, {SHA_B: b"ikke en zip"}), log=lambda _: None)
    assert '"A"' in program_marker(home)
    assert sorted(p.name for p in home.iterdir()) == ["opdater.py", "program"]


def test_private_repo_uses_saved_token(tmp_path):
    gh = FakeGitHub(SHA_A, {SHA_A: make_zip("A")}, token="hemmelig")
    messages = []
    assert not updater.update(tmp_path, gh, log=messages.append)
    assert "github-noegle.txt" in messages[1]
    (tmp_path / "github-noegle.txt").write_text("hemmelig\n")
    assert updater.update(tmp_path, gh, log=lambda _: None)


def test_install_from_unzipped_folder(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "create_shortcuts", lambda home: True)
    source = tmp_path / "udpakket"
    for part in ("src", "pyproject.toml", "README.md"):
        src = REPO_ROOT / part
        if src.is_dir():
            shutil.copytree(src, source / part)
        else:
            source.mkdir(exist_ok=True)
            (source / part).write_bytes(src.read_bytes())
    (source / "tilbudshenter.toml").write_text("gamle indstillinger")
    (source / "rapporter").mkdir()
    (source / "rapporter" / "seneste.html").write_text("rapport")
    home = tmp_path / "hjem"
    gh = FakeGitHub(SHA_A, {SHA_A: make_zip("A")}, token="hemmelig")
    answers = iter(["forkert", "hemmelig"])
    messages = []

    assert updater.install(source, home, gh, ask=lambda _: next(answers), log=messages.append) == 0
    assert (home / "github-noegle.txt").read_text().strip() == "hemmelig"
    assert updater.installed_version(home) == SHA_A
    assert (home / "tilbudshenter.toml").read_text() == "gamle indstillinger"
    assert (home / "rapporter" / "seneste.html").exists()
    launcher = (home / "Tilbudshenter.bat").read_bytes()
    assert b"\r\n" in launcher and b"opdater.py" in launcher and b"program\\src" in launcher
    assert any("Nøglen virkede ikke" in m for m in messages)

    # Data i den nye mappe overskrives ikke ved en ny installation.
    (home / "tilbudshenter.toml").write_text("nye indstillinger")
    assert updater.install(source, home, gh, ask=lambda _: "", log=lambda _: None) == 0
    assert (home / "tilbudshenter.toml").read_text() == "nye indstillinger"


def test_install_without_network_uses_local_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "create_shortcuts", lambda home: False)
    home = tmp_path / "hjem"
    assert updater.install(REPO_ROOT, home, FakeGitHub(offline=True), ask=pytest.fail, log=lambda _: None) == 0
    assert updater.installed_version(home) == "lokal"
    assert (home / "program" / "src" / "tilbudshenter" / "cli.py").exists()
    assert not list((home / "program").rglob("__pycache__"))
