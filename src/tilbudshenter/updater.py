"""Installation og automatisk opdatering af Tilbudshenter på Windows.

Filen kører som et selvstændigt script (kun standardbiblioteket og ingen
relative imports), så den kan kopieres ud som ``opdater.py`` og opdatere
programmet uden at holde fast i filerne i programmappen.

Mappen ser sådan ud efter installation (standard: %LOCALAPPDATA%\\Tilbudshenter):

    Tilbudshenter.bat    starter programmet (genvejene peger hertil)
    opdater.py           denne fil; henter nyeste udgave fra GitHub
    program\\             selve programmet; udskiftes ved hver opdatering
    tilbudshenter.toml   dine indstillinger  } røres aldrig af
    tilbud.db            hentede tilbud      } opdateringen
    rapporter\\
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

REPO = "simonhansen8/Tilbudshenter"
BRANCH = "main"
API = "https://api.github.com"
TIMEOUT = 15

PROGRAM_DIR = "program"
VERSION_FILE = "VERSION.txt"
TOKEN_FILE = "github-noegle.txt"
UPDATER_FILE = "opdater.py"
LAUNCHER_FILE = "Tilbudshenter.bat"
# Det der kopieres fra repoet ind i programmappen.
PROGRAM_PARTS = ("src", "pyproject.toml", "README.md")
# Brugerens data, som flyttes med fra en gammel udpakket mappe.
DATA_PARTS = ("tilbudshenter.toml", "tilbud.db", "tilbud.demo.db", "rapporter")

LAUNCHER = r"""@echo off
rem Starter Tilbudshenter. Programmet opdaterer sig selv fra GitHub foerst.
title Tilbudshenter
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Python blev ikke fundet. Installer Python fra https://www.python.org/downloads/
  pause
  exit /b 1
)
py "%~dp0opdater.py"
set "PYTHONPATH=%~dp0program\src"
py -m tilbudshenter app
if errorlevel 1 pause
"""

Fetch = Callable[[str, dict], bytes]


class UpdateError(Exception):
    pass


class NotFound(UpdateError):
    """Repoet kunne ikke ses, typisk fordi det er privat og nøglen mangler."""

    def __init__(self, message: str, code: int = 404) -> None:
        super().__init__(message)
        self.code = code


def default_home() -> Path:
    override = os.environ.get("TILBUDSHENTER_HJEM")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    return Path(base) / "Tilbudshenter"


# -- GitHub ---------------------------------------------------------------
def http_fetch(url: str, headers: dict) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "tilbudshenter-opdatering", **headers})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise NotFound(f"GitHub svarede {exc.code}", exc.code) from exc
        raise UpdateError(f"GitHub svarede {exc.code}") from exc
    except (urllib.error.URLError, OSError) as exc:
        raise UpdateError(f"Ingen forbindelse til GitHub ({exc})") from exc


def _headers(token: str | None, accept: str) -> dict:
    headers = {"Accept": accept}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def latest_sha(token: str | None, fetch: Fetch = http_fetch) -> str:
    raw = fetch(f"{API}/repos/{REPO}/commits/{BRANCH}", _headers(token, "application/vnd.github.sha"))
    sha = raw.decode("ascii", "replace").strip()
    if len(sha) != 40:
        raise UpdateError("Uventet svar fra GitHub")
    return sha


def download(sha: str, token: str | None, fetch: Fetch = http_fetch) -> bytes:
    return fetch(f"{API}/repos/{REPO}/zipball/{sha}", _headers(token, "application/vnd.github+json"))


def clean_token(raw: str) -> str:
    """Fjerner mellemrum, citationstegn og usynlige tegn, der kan komme med ved kopiering."""
    return "".join(ch for ch in raw if ch.isascii() and ch.isprintable() and ch not in " \"'")


def read_token(home: Path) -> str | None:
    try:
        return clean_token((home / TOKEN_FILE).read_text("utf-8-sig")) or None
    except OSError:
        return None


def installed_version(home: Path) -> str | None:
    try:
        return (home / PROGRAM_DIR / VERSION_FILE).read_text("utf-8").strip() or None
    except OSError:
        return None


# -- Udskiftning af programmappen -----------------------------------------
def _check_program(path: Path) -> None:
    if not (path / "src" / "tilbudshenter" / "__init__.py").is_file():
        raise UpdateError("Den hentede udgave ser ikke ud som Tilbudshenter")


def _swap_in(home: Path, staged: Path, version: str) -> None:
    """Gør ``staged`` til den nye programmappe og rydder den gamle væk."""
    _check_program(staged)
    (staged / VERSION_FILE).write_text(version + "\n", "utf-8")
    program = home / PROGRAM_DIR
    old = home / (PROGRAM_DIR + ".gammel")
    shutil.rmtree(old, ignore_errors=True)
    if program.exists():
        program.rename(old)
    try:
        staged.rename(program)
    except OSError:
        if old.exists() and not program.exists():
            old.rename(program)
        raise
    shutil.rmtree(old, ignore_errors=True)
    # Opdateringsscriptet uden for programmappen følger med den nye udgave.
    new_updater = program / "src" / "tilbudshenter" / "updater.py"
    if new_updater.is_file():
        shutil.copyfile(new_updater, home / UPDATER_FILE)


def _staging(home: Path) -> Path:
    staged = home / (PROGRAM_DIR + ".ny")
    shutil.rmtree(staged, ignore_errors=True)
    staged.mkdir(parents=True)
    return staged


def install_from_zip(home: Path, data: bytes, version: str) -> None:
    staged = _staging(home)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                # GitHub lægger alt i en topmappe som "ejer-repo-sha/".
                parts = Path(info.filename).parts[1:]
                if not parts or parts[0] not in PROGRAM_PARTS or ".." in parts:
                    continue
                target = staged.joinpath(*parts)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(zf.read(info))
        _swap_in(home, staged, version)
    except zipfile.BadZipFile as exc:
        raise UpdateError("Den hentede fil var ikke en gyldig zip") from exc
    finally:
        shutil.rmtree(staged, ignore_errors=True)


def install_from_folder(home: Path, source: Path, version: str) -> None:
    staged = _staging(home)
    try:
        for part in PROGRAM_PARTS:
            src = source / part
            if src.is_dir():
                shutil.copytree(src, staged / part, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.egg-info"))
            elif src.is_file():
                shutil.copyfile(src, staged / part)
        _swap_in(home, staged, version)
    finally:
        shutil.rmtree(staged, ignore_errors=True)


# -- Opdatering ved opstart -------------------------------------------------
def update(home: Path, fetch: Fetch = http_fetch, log: Callable[[str], None] = print) -> bool:
    """Henter nyeste udgave hvis der er en. Returnerer True hvis der blev opdateret.

    Fejler noget (ingen net, GitHub nede), køres den installerede udgave bare.
    """
    token = read_token(home)
    current = installed_version(home)
    try:
        sha = latest_sha(token, fetch)
        if sha == current:
            return False
        log("Henter ny udgave af Tilbudshenter …")
        install_from_zip(home, download(sha, token, fetch), sha)
    except NotFound:
        log("Kunne ikke se Tilbudshenter på GitHub, så der søges ikke efter opdateringer.")
        log(f"Hvis repoet er privat, så læg en GitHub-nøgle i {home / TOKEN_FILE}")
        return False
    except (UpdateError, OSError) as exc:
        log(f"Kunne ikke opdatere ({exc}). Starter den udgave der allerede er installeret.")
        return False
    log(f"Opdateret til udgave {sha[:7]}.")
    return True


# -- Installation -----------------------------------------------------------
def migrate_data(source: Path, home: Path) -> list[str]:
    """Kopierer indstillinger og data fra en gammel udpakket mappe, hvis de mangler."""
    moved = []
    for name in DATA_PARTS:
        src, dst = source / name, home / name
        if not src.exists() or dst.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
        moved.append(name)
    return moved


def create_shortcuts(home: Path) -> bool:
    """Lægger genveje på skrivebordet og i Start-menuen (kun Windows)."""
    if os.name != "nt":
        return False
    script = (
        "$ws = New-Object -ComObject WScript.Shell;"
        "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {"
        " $s = $ws.CreateShortcut((Join-Path $dir 'Tilbudshenter.lnk'));"
        " $s.TargetPath = $env:TH_TARGET; $s.WorkingDirectory = $env:TH_HOME;"
        " $s.Description = 'Find de bedste tilbud i tilbudsaviserne'; $s.Save() }"
    )
    env = {**os.environ, "TH_TARGET": str(home / LAUNCHER_FILE), "TH_HOME": str(home)}
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            env=env, capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0


def ask_token(home: Path, fetch: Fetch, ask: Callable[[str], str], log: Callable[[str], None]) -> None:
    """Sørger for at opdateringen kan se repoet; spørger efter en nøgle hvis det er privat."""
    try:
        latest_sha(read_token(home), fetch)
        return
    except NotFound:
        pass
    except UpdateError as exc:
        log(f"Kunne ikke nå GitHub lige nu ({exc}). Programmet prøver igen, når det starter.")
        return
    log("")
    log("Repoet på GitHub er privat, så programmet skal have en nøgle for at kunne hente opdateringer.")
    log("Sådan laver du den:")
    log("  1. Gå til https://github.com/settings/personal-access-tokens/new")
    log("  2. Skriv et navn, fx Tilbudshenter, og vælg en udløbsdato.")
    log("  3. Under 'Repository access' vælger du 'Only select repositories' og så Tilbudshenter.")
    log("     (Standardvalget 'Public repositories' virker IKKE, fordi repoet er privat.)")
    log("  4. Under 'Permissions' finder du 'Contents' og sætter den til 'Read-only'.")
    log("  5. Tryk 'Generate token' og kopiér nøglen (den starter med github_pat_).")
    log("Indsæt nøglen her med højreklik eller Ctrl+V og tryk Enter.")
    while True:
        token = clean_token(ask("GitHub-nøgle (tryk Enter for at springe over): "))
        if not token:
            log("Springer over. Programmet virker, men opdaterer sig ikke selv.")
            return
        try:
            latest_sha(token, fetch)
        except NotFound as exc:
            if exc.code == 401:
                log("GitHub kender ikke nøglen. Den er nok kopieret forkert eller udløbet. Prøv igen.")
            else:
                log(f"Nøglen er gyldig, men kan ikke se repoet {REPO} (GitHub svarede {exc.code}).")
                log("Ret nøglen på https://github.com/settings/personal-access-tokens så den har")
                log("'Only select repositories' med Tilbudshenter og 'Contents: Read-only', og prøv igen.")
            continue
        except UpdateError as exc:
            log(f"Kunne ikke afprøve nøglen: {exc}. Prøv igen.")
            continue
        (home / TOKEN_FILE).write_text(token + "\n", "utf-8")
        log("Nøglen virker og er gemt.")
        return


def install(
    source: Path,
    home: Path,
    fetch: Fetch = http_fetch,
    ask: Callable[[str], str] = input,
    log: Callable[[str], None] = print,
) -> int:
    log(f"Installerer Tilbudshenter i {home}")
    home.mkdir(parents=True, exist_ok=True)
    if installed_version(home) is None:
        # Den udpakkede mappe bruges som første udgave; opdateringen nedenfor
        # skifter den ud med den nyeste fra GitHub.
        install_from_folder(home, source, "lokal")
    else:
        shutil.copyfile(source / "src" / "tilbudshenter" / "updater.py", home / UPDATER_FILE)
    (home / LAUNCHER_FILE).write_bytes(LAUNCHER.replace("\r\n", "\n").replace("\n", "\r\n").encode("ascii"))

    moved = migrate_data(source, home)
    if moved:
        log("Dine indstillinger og data er flyttet med: " + ", ".join(moved))

    ask_token(home, fetch, ask, log)
    update(home, fetch, log)

    if create_shortcuts(home):
        log("Der er lagt en genvej 'Tilbudshenter' på skrivebordet og i Start-menuen.")
    log("")
    log("Færdig. Fremover starter du programmet fra genvejen, og det opdaterer sig selv.")
    log("Den udpakkede mappe og zip-filen kan du slette.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    home = default_home()
    if argv[:1] == ["installer"]:
        source = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parents[2]
        return install(source.resolve(), home)
    update(home)
    return 0


if __name__ == "__main__":
    sys.exit(main())
