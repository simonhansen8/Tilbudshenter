import subprocess

from tilbudshenter.version import current


def test_from_version_file(tmp_path):
    (tmp_path / "VERSION.txt").write_text("d" * 40 + "\n", "utf-8")
    assert current(tmp_path, env={}) == {"sha": "d" * 40, "date": None, "dirty": False,
                                         "repo": "simonhansen8/Tilbudshenter", "source": "installeret"}


def test_unknown_or_actions(tmp_path):
    (tmp_path / "VERSION.txt").write_text("lokal\n", "utf-8")
    assert current(tmp_path, env={})["sha"] is None
    got = current(tmp_path / "ingen", env={"GITHUB_SHA": "e" * 40, "GITHUB_REPOSITORY": "a/b"})
    assert (got["sha"], got["repo"], got["source"]) == ("e" * 40, "a/b", "actions")


def test_from_git(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n")
    git("add", "-A")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x")
    got = current(tmp_path, env={})
    assert got["source"] == "git" and len(got["sha"]) == 40 and got["date"] and not got["dirty"]
    (tmp_path / "src" / "a.py").write_text("x = 2\n")
    (tmp_path / "tilbud.db").write_text("")  # data i mappen tæller ikke
    assert current(tmp_path, env={})["dirty"]
