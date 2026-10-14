# Tilbudshenter

Tilbudshenter scanner de danske tilbudsaviser (Netto, Rema 1000, Lidl, Føtex,
Bilka, Coop m.fl.), opdager når der udkommer nye, og laver en liste over de
bedste tilbud ud fra **dine** valg af butikker og typer af varer.

Data hentes fra [Tjek/eTilbudsavis](https://etilbudsavis.dk), der samler
kædernes aviser.

## Kom i gang

Kræver Python 3.11 eller nyere. Der er ingen andre afhængigheder.

### Appen (anbefalet)

**Windows (anbefalet):** hent zip-filen og pak den ud én gang, og dobbeltklik
på `Installer.bat`. Programmet lægges i `%LOCALAPPDATA%\Tilbudshenter`, og der
kommer en genvej **Tilbudshenter** på skrivebordet og i Start-menuen. Hver gang
du starter fra genvejen, henter programmet selv den nyeste udgave fra GitHub
(uden git). Dine indstillinger, hentede tilbud og rapporter ligger uden for
programmappen og bliver aldrig rørt af en opdatering. Har du brugt programmet
fra den udpakkede mappe før, flyttes indstillinger og data med.

Er repoet privat, beder installationen om en GitHub-nøgle. Lav den på
<https://github.com/settings/personal-access-tokens/new>, vælg
*Only select repositories* og Tilbudshenter under *Repository access* (standardvalget
*Public repositories* virker ikke), og sæt *Contents* til *Read-only*. Den gemmes i
`%LOCALAPPDATA%\Tilbudshenter\github-noegle.txt`. Uden net starter programmet
bare den udgave, der allerede er installeret.

**Windows uden installation:** dobbeltklik på `Tilbudshenter.bat` i den
udpakkede mappe. Filen kører altid programmet fra sin egen mappe, også hvis en
ældre udgave er installeret med `pip`.

**Andre systemer:**

```bash
pip install -e .
tilbudshenter app
```

I appen kan du:

- hente nye tilbud med knappen **Hent nye tilbud** (første gang sker det
  automatisk),
- søge og filtrere på butik og kategori, sortere efter rabat eller pris pr. kg,
- vælge mellem tilbud der gælder nu, og dem der starter senere,
- se hvilke tilbud der kræver Lidl Plus, kædens app eller medlemskab (og skjule dem),
- lægge tilbud og egne varer på en **indkøbsliste**, delt op efter butik, som
  kan kopieres, sendes som mail eller udskrives,
- vælge butikker, aviser, kategorier og din placering under **Indstillinger**.

Appen kører kun på din egen computer. Luk konsolvinduet for at stoppe den.
Vil du prøve med demodata uden internet: `tilbudshenter app --demo`.

### Kommandolinjen

```bash
pip install -e .
tilbudshenter init        # opretter tilbudshenter.toml, som du retter til
tilbudshenter scan        # henter nye aviser og laver rapport
```

Vil du prøve programmet uden internet, kan du bruge de indbyggede demodata:

```bash
tilbudshenter scan --demo
```

Demodata gemmes adskilt fra dine rigtige data (`tilbud.demo.db` og
`rapporter/demo/`).

## Kommandoer

| Kommando | Hvad den gør |
|---|---|
| `tilbudshenter app` | Åbner appen i browseren. |
| `tilbudshenter scan` | Finder nye aviser for dine butikker, henter tilbuddene og laver rapport. Aviser der allerede er scannet, springes over. |
| `tilbudshenter tilbud` | Viser de bedste aktuelle tilbud fra databasen. Kan filtreres ad hoc, se nedenfor. |
| `tilbudshenter butikker` | Viser hvilke butikker der har aviser i dit område, og hvilke du har valgt. |
| `tilbudshenter kategorier` | Viser de typer tilbud du kan vælge mellem. |
| `tilbudshenter overvaag` | Scanner automatisk hver 6. time (`--interval` ændrer det). |
| `tilbudshenter init` | Opretter en konfigurationsfil med forklaringer. |

Eksempler på `tilbud`:

```bash
tilbudshenter tilbud -b Netto -b Lidl            # kun Netto og Lidl
tilbudshenter tilbud -k koed -k fisk -n 10       # top 10 inden for kød og fisk
tilbudshenter tilbud -s kaffe --alle             # alle kaffetilbud, uanset dine valg
tilbudshenter tilbud --min-rabat 40 -f html -o tilbud.html
```

## Vælg butikker, aviser og typer af tilbud

Alt styres i `tilbudshenter.toml` (oprettes med `tilbudshenter init`):

```toml
[placering]
breddegrad = 55.6761
laengdegrad = 12.5683
radius_km = 15

[butikker]
vaelg = ["Netto", "REMA 1000", "Lidl", "føtex", "Kvickly", "SuperBrugsen"]   # tom liste = alle
fravaelg = []

[aviser]
vaelg = []                                        # fx ["uge"]; tom liste = alle
fravaelg = ["legetøj", "nonfood", "halloween"]

[kategorier]
vaelg = ["koed", "fisk", "mejeri", "frugt_og_groent"]  # tom liste = alle
fravaelg = []

[filtre]
min_rabat_procent = 0
kun_kendt_rabat = false
udelad_ord = ["øko"]
favoritter = ["kyllingebryst", "skyr"]
```

En ny konfiguration vælger Netto, REMA 1000, Lidl, føtex, Bilka,
365discount og Coops kæder (Kvickly, SuperBrugsen, Brugsen, MENY og SPAR).
Kør `tilbudshenter butikker` for at se de præcise navne på butikker og
aviser i dit område. Listen viser også, hvilke der er valgt med de nuværende
indstillinger. Butiksnavne matches uden hensyn til store/små bogstaver, og et
navn matcher også længere navne (`"365"` matcher `"365discount"`). Aviser
matches på en del af navnet, så `"legetøj"` fravælger både
"Legetøjskatalog" og "Billies Bedste Legetøjskatalog 2026".

Kategorier tildeles ud fra nøgleord i varens navn. Du kan lave dine egne
kategorier eller tilføje nøgleord til de eksisterende:

```toml
[kategorier.egne.morgenmad]
navn = "Morgenmad"
noegleord = ["havregryn", "müsli", "skyr"]

[kategorier.egne.koed]
noegleord = ["tatar"]          # ekstra nøgleord til en eksisterende kategori
```

## Sådan vurderes "bedste tilbud"

1. **Rabat ift. normalpris**: `(normalpris - pris) / normalpris`. Normalprisen
   tages fra avisens førpris-felt eller fra teksten, fx "Normalpris 219,-",
   "Spar 43,80" eller "Spar 25 %".
2. Mangler normalprisen, sammenlignes varens **enhedspris** (kr/kg, kr/l)
   med den typiske pris i tidligere aviser. Historikken opbygges automatisk,
   jo længere programmet har kørt.
3. Er der heller ingen historik, sammenlignes prisen pr. kg eller liter med
   **de andre valgte butikker** i de aktuelle aviser. Koster hakket oksekød
   75 kr/kg i Netto og typisk 100 kr/kg hos de andre, vises det som
   "ca. -25%". Det gælder almindelige basisvarer som hakket kød,
   kyllingebryst, bacon, laks, mælk, æg, kartofler og kaffe (se
   `comparison.py`). Tilbud på flere forskellige varer ("Hakket okse- eller
   grisekød"), færdigretter, pålæg og økologiske varer sammenlignes ikke.
4. **Laveste pris i X uger**: er prisen pr. kg/liter lavere end i alle
   tidligere aviser i mindst 3 uger, vises det på tilbuddet, og det rykker
   lidt op. Det kræver, at programmet har kørt i et par uger.
5. **Favoritter** får en bonus (`favorit_bonus`), og store besparelser i kroner
   giver et lille ekstra skub.

Mange kæder (fx Netto og REMA 1000) oplyser sjældent en normalpris, og
derfor er sammenligningen med andre butikker vigtig for dem. Anslåede
rabatter vises med "ca." og en ramme i stedet for fyldt mærke. Tilbud,
hvor rabatten ikke kendes, vises efter dem med kendt rabat, sorteret efter
kategori og enhedspris. Sæt `kun_kendt_rabat = true` for at skjule dem.
`min_rabat_procent` skjuler tilbud, hvis kendte rabat er lavere.

## Rapporter

Hver scanning med nye aviser skriver rapporter i `rapporter/`:

- `seneste.html`: oversigt med billeder og filterknapper for butik og kategori
- `seneste.md`: tabel, der kan læses overalt
- `seneste.json`: maskinlæsbar liste, tænkt som input til fx en madplan
- samt dateret kopi, fx `tilbud-2026-10-13.html`

## Kør automatisk

Aviserne udkommer typisk én gang om ugen (oftest fredag-søndag). Det er nok
at køre `scan` et par gange om dagen; der hentes kun noget, når der er nye
aviser.

**Linux/macOS (cron)**: `crontab -e` og tilføj fx

```
0 7,19 * * * cd /sti/til/mappen && /sti/til/tilbudshenter scan >> scan.log 2>&1
```

**Windows**: Opret en opgave i *Opgavestyring* (Task Scheduler), der kører
`tilbudshenter scan` i mappen med `tilbudshenter.toml`.

Alternativt kan `tilbudshenter overvaag` køre i baggrunden.

## Opbygning

```
src/tilbudshenter/
  cli.py          kommandolinjen
  webapp.py       appen (lokal webserver); brugerfladen ligger i data/app.html
  config.py       indlæsning af tilbudshenter.toml
  scanner.py      finder nye aviser og henter tilbud
  sources/        datakilder (tjek.py = eTilbudsavis, demo.py = demodata)
  categories.py   kategorisering ud fra nøgleord
  comparison.py   sammenligning af samme vare på tværs af butikker
  selection.py    filtrering og rangering
  storage.py      SQLite: aviser, tilbud og prishistorik
  report.py       HTML, Markdown, JSON og terminal
```

En ny datakilde skal blot implementere `list_catalogs()` og `list_offers()`
(se `sources/base.py`).

## Madplan (planlagt)

Programmet er bygget, så en madplan kan lægges ovenpå:

- `Storage.current_offers()` giver alle aktuelle tilbud med kategori,
  enhedspris og gyldighedsperiode.
- `select_offers()` giver de bedste af dem ud fra brugerens valg.
- `rapporter/seneste.json` indeholder det samme for programmer, der ikke er
  skrevet i Python.

En madplan kan fx vælge opskrifter, hvis hovedingredienser (kød, fisk,
grønt) er på tilbud i de valgte butikker i den pågældende uge.

## Udvikling

```bash
pip install -e ".[dev]"
pytest
```
