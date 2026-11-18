# Tilbudshenter

Tilbudshenter scanner de danske tilbudsaviser (Netto, Rema 1000, Lidl, Føtex,
Bilka, Coop m.fl.), opdager når der udkommer nye, og laver en liste over de
bedste tilbud ud fra **dine** valg af butikker og typer af varer.

Data hentes fra [Tjek/eTilbudsavis](https://etilbudsavis.dk), der samler
kædernes aviser.

føtex food vises som sin egen kæde med sine egne butikker, men har ingen egen
avis hos Tjek. Den får føtex' ugeavis, som også gælder i føtex food.

## Kom i gang

### Som hjemmeside (nemmest)

Åbn **<https://simonhansen8.github.io/Tilbudshenter/>** på computer eller
telefon. Der skal ikke installeres noget.

GitHub henter selv de nye aviser to gange om dagen (workflowen
`.github/workflows/side.yml`) og lægger tilbuddene på siden. Du kan også
hente med det samme under *Actions → Opdater siden → Run workflow*.
Indstillinger og indkøbsliste gemmes i din browser, så de følger ikke med
fra computeren til telefonen. Siden har de samme filtre, sammenligninger og
den samme indkøbsliste som appen. Under *Indstillinger → Hvor handler du?*
skriver du dit postnummer eller din by, eller bruger telefonens placering, og
vælger en afstand. Så ser du kun tilbud fra de kæder, der har en butik så
tæt på. Aviserne hentes fra hele landet, og butikkernes adresser kommer
fra Tjek.

Første gang skal GitHub Pages slås til: *Settings → Pages*, vælg
*Deploy from a branch*, grenen `gh-pages` og mappen `/ (root)`, og tryk
*Save*. Grenen oprettes af workflowen første gang, den kører.

Siden bygges med `tilbudshenter side --ud side`, som henter aviserne og
skriver `index.html`, `data.json` (tilbuddene) og `opskrifter.json` i mappen
`side`. Opskrifterne fylder det meste og hentes først, når madplanen eller
ugeplanen åbnes, så forsiden åbner hurtigt på telefonen.

Kræver Python 3.11 eller nyere. Der er ingen andre afhængigheder.

### Notifikationer på telefonen

Skriv de varer, du vil have besked om, i `notifikationer.txt` (ét søgeord pr.
linje, som i søgefeltet). Når siden opdateres, søges der efter dem med samme
regler som *Mine basisvarer*, og hvert nyt tilbud giver én push-besked
gennem den gratis app **ntfy**. Et tryk på beskeden åbner siden med søgningen.

1. Installér appen *ntfy* (App Store eller Google Play).
2. Tryk *+* og abonnér på et emne, som kun du kender, fx `tilbud-` efterfulgt
   af nogle tilfældige bogstaver og tal.
3. På GitHub: *Settings → Secrets and variables → Actions → New repository
   secret*, navn `NTFY_EMNE`, værdi det samme emne.

Uden `NTFY_EMNE` viser workflowen bare træffene i loggen. Hvilke tilbud der
er sendt besked om, huskes i `notifikationer.json` på `gh-pages`.

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
- søge og filtrere (se *Filtre* nedenfor) og sortere efter rabat eller pris pr. kg,
- trykke på et tilbud for at se et stort billede, hele siden i avisen med
  tilbuddet markeret og en knap til den rigtige tilbudsavis på eTilbudsavis,
- vise tilbuddene butik for butik i samme rækkefølge som i tilbudsavisen
  (sortering *Butik, som i avisen*),
- se hvilke tilbud der kræver Lidl Plus, kædens app eller medlemskab,
- se normalprisen ved hvert tilbud, og om tilbuddet faktisk er billigere: butikkens
  egen normalpris, når avisen oplyser den, ellers basisprisen (madplanens hyldepris
  uden tilbud, se nedenfor) for almindelige basisvarer som hakket oksekød, mælk og kartofler.
  For de fleste andre varer oplyser aviserne ingen normalpris, og så står der
  *Normalpris ukendt*,
- lægge tilbud og egne varer på en **indkøbsliste**, delt op efter butik og afdeling.
  Øverst står, hvor mange varer der mangler, og hvad de koster. Det, du sætter
  hak ved, flytter ned **I kurven**, så det, der mangler, står øverst. Hver vare
  fylder én linje (tryk på noten for at se mængder og retter), og "fra fre."
  eller "sidste dag i morgen" står ved tilbud, hvor det betyder noget. En vare,
  du fjerner, kan lægges tilbage med **Fortryd**, og samme egen vare kommer kun
  på én gang. Antallet rettes med **−** og **+** (under 1 fjernes varen). Egne
  varer kan få en butik, når de tilføjes (valget huskes), og flyttes til en
  anden butik bagefter; de kommer i den afdeling, hvor ordet oftest står blandt
  tilbuddene (toiletpapir under husholdning, tandpasta under personlig pleje). **Del listen** bruger telefonens deling (ellers kopieres den); den
  delte tekst er kort, kun det, der mangler, med en samlet pris. Listen kan også
  sendes som mail eller udskrives,
- lave en **madplan** ud fra ugens tilbud (se nedenfor),
- vælge kæder, aviser, favoritter og din placering under **Indstillinger**.

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
| `tilbudshenter side` | Henter tilbud og bygger den statiske side til GitHub Pages. |
| `tilbudshenter opskrifter` | Henter opskrifterne i `opskrifter.txt` fra madsiderne til madplanen. |

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
Alle kategorier er valgt. Står en ældre konfiguration stadig med det gamle
standardvalg (kød, fisk, mejeri, frugt og grønt, brød, kolonial, frost og
kaffe og te), vælges alle kategorier én gang; har du selv rettet listen,
beholdes den.
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

### Filtre

Som udgangspunkt vises alle tilbud fra dine kæder. Knappen **Filtre** over
tilbuddene åbner valgene:

- **Butik**, **Kategori** og **Gælder** (nu eller senere): tryk på det, du vil
  se, fx Netto. Så vises kun Netto, og et tryk mere på fx Lidl tager Lidl med.
  **Alle** slår filteret fra. **Kun mad og drikke** vælger alle kategorier
  undtagen husholdning, personlig pleje, baby, dyr og non-food.
- **Rabat**: alle tilbud, kun dem med kendt rabat, eller mindst 10-50 % rabat.
  Mange aviser oplyser ingen normalpris; de tilbud vises kun under *Alle tilbud*.
- **Højeste pris**, **Skjul medlems- og app-priser** og **Skjul varer**
  (tilbud der nævner fx "øl" eller "øko", med samme regler som søgningen).

Tallet ved hvert valg er, hvor mange tilbud man får med det. Hvert filter, der
er slået til, står som et mærke ved siden af knappen og fjernes med ét tryk, og
**Nulstil alle** viser alt igen. Under tilbuddene står, hvor mange filtrene
skjuler, og skjuler de alt, foreslås det, hvad man kan slå fra. Søgningen
bruger også filtrene. Filtrene huskes i browseren. Hvilke kæder og aviser der
hentes, vælges under *Indstillinger* (linket *Flere kæder og aviser*).

Har du `udelad_ord` eller `max_pris` i `tilbudshenter.toml`, bliver de til filtre
første gang, appen åbnes med de nye filtre, så de kan ses og fjernes. I
appen bruges `[kategorier]`, `min_rabat_procent`, `kun_kendt_rabat` og
`skal_indeholde` ikke;
de gælder kun rapporterne fra `tilbudshenter scan` og `tilbudshenter tilbud`.

### Mine basisvarer

Vælg **Mine basisvarer** over tilbuddene, og skriv de varer, du altid køber,
fx mælk, smør, kaffe og bananer. Så vises alle tilbud på dem samlet vare for
vare, med den billigste pr. kg eller liter først. Kategori og rabat gælder ikke
her (butik, periode, pris og skjulte varer gør), og varer uden tilbud nævnes over listen.
Varen skal stå i tilbuddets overskrift som et helt ord eller sidst i et
sammensat ord: "mælk" finder "letmælk", men ikke "mælkedrik" eller
"smørrebrød". Et minus udelader noget: `mælk -kakao`. Listen gemmes i
browseren.

## Sådan vurderes "bedste tilbud"

1. **Rabat ift. normalpris**: `(normalpris - pris) / normalpris`. Normalprisen
   tages fra avisens førpris-felt eller fra teksten, fx "Normalpris 219,-",
   "Spar 43,80" eller "Spar 25 %".
2. Mangler normalprisen, sammenlignes varens **enhedspris** (kr/kg, kr/l)
   med den typiske pris i tidligere aviser. Historikken opbygges automatisk,
   jo længere programmet har kørt. Samme tilbud i flere aviser fra samme kæde
   tæller én gang, og svinger prisen på varer med samme navn mere end det
   dobbelte (fx "Julekalender", "Kalenderlys" eller "Peter Larsen Kaffe" i
   100 g og 500 g), er det forskellige varer, og historikken bruges ikke. En
   rabat over 65 % ud fra historikken bruges heller ikke.
3. Er der heller ingen historik, sammenlignes prisen pr. kg eller liter med
   **de andre valgte butikker** i de aktuelle aviser. Koster hakket oksekød
   75 kr/kg i Netto og typisk 100 kr/kg hos de andre, vises det som
   "ca. -25%". Kæder med fælles avis (fx Kvickly og SuperBrugsen) tæller som
   én butik, og har de andre butikker kun dyre specialvarer på tilbud (fx
   gourmet-olivenolie til 300 kr/l), bruges medianen af alle tilbud på varen
   i stedet. Det gælder almindelige basisvarer som hakket kød,
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
kategori og enhedspris. I appen skjules de med filteret **Rabat**; i
rapporterne med `kun_kendt_rabat = true`. `min_rabat_procent` skjuler tilbud i
rapporterne, hvis kendte rabat er lavere.

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
  pages.py        den statiske udgave af appen til GitHub Pages
  notifikation.py besked til telefonen (ntfy) om tilbud på varerne i notifikationer.txt
  config.py       indlæsning af tilbudshenter.toml
  scanner.py      finder nye aviser og henter tilbud
  sources/        datakilder (tjek.py = eTilbudsavis, demo.py = demodata)
  categories.py   kategorisering ud fra nøgleord
  comparison.py   sammenligning af samme vare på tværs af butikker
  selection.py    filtrering og rangering
  mealplan.py     retter og ingredienser til madplanen
  opskrifter.py   opskrifter fra madsider (schema.org/Recipe)
  storage.py      SQLite: aviser, tilbud og prishistorik
  report.py       HTML, Markdown, JSON og terminal
```

En ny datakilde skal blot implementere `list_catalogs()` og `list_offers()`
(se `sources/base.py`).

## Madplan

Knappen **Madplan** på siden og i appen foreslår aftensmad, hvor
hovedingrediensen er på tilbud i dine butikker, fx spaghetti bolognese når
hakket oksekød er billigt.

En ret kommer kun med, når tilbuddene bærer den: hovedingrediensen er på
tilbud, mindst halvdelen af rettens varer er på tilbud (og mindst to, eller
den ene, hvis retten kun har én), mindst halvdelen af prisen kommer fra tilbud, og retten sparer mindst 10 %
mod basisvarerne (`OFFER_MIN_*` i `app.html`). Grønt tilbehør og det, du har
derhjemme, tæller ikke med. En ret med noget, du har derhjemme, som
hovedingrediens, og dine egne retter, du sætter på planen, kommer altid med.
En ret, hvis tilbud slutter tidligt i perioden, lægges på en dag, hvor
tilbuddet stadig gælder. Jo flere af rettens varer der er på tilbud, jo
højere kommer den. Retter, der har været på en madplan de sidste 14 dage,
kommer bagerst i køen (gemt i browseren), så **Ny madplan** og næste uges
plan giver nye retter.

- Retterne kommer fra en fast samling af omkring 40 danske hverdagsretter i
  `mealplan.py` og fra opskrifterne hentet fra madsiderne (se nedenfor).
  Kun rigtig aftensmad kommer med: ikke sovse, dressinger, syltede løg,
  pickles, tilbehør, madpakker og frokostretter (ud fra navnet og madsidens
  kategori), og en hentet opskrift skal mætte (mindst 120 kcal pr. person af
  de varer, der kan genkendes, 250 kcal for supper og salater) og have kød,
  fisk, æg, bælgfrugter, tofu eller ost (mindst 60 g til 4 personer).
  Desserter og bagværk (en ret uden kød med fx marcipan, vanilje, flormelis
  eller glasur), bagværk i stk ("6 boller") og morgenmad kommer heller ikke
  med, og det samme gælder brød og boller (hvidløgsbrød, briocheboller),
  småkager (klejner, brownies), pålæg (postej, rillettes, terrine),
  smørrebrød, pølsehorn, babymad, snacks i stk ("6 stk", "2 servinger") og
  HelloFresh' delevenlige retter (snackbrætter, crostini). Opskrifterne er
  også gennemgået i hånden: dem, madsiden kalder aftensmad, men som er
  tilbehør, dessert, snack, frokost eller en sovs eller dej, står i
  `src/tilbudshenter/data/ikke_retter.txt`. Danske opskrifter
  (madsider på .dk og samlingens hverdagsretter) får ekstra point, fordi de
  bruger varer og pakker fra danske butikker og er skrevet på dansk.
- Mangler en ret kartofler, ris, pasta, brød eller lignende, får den
  kartofler som tilbehør, eller ris til fx karry, wok og chili, så prisen er
  for et helt måltid.
- En kendt vare uden mængde i opskriften ("hakkede tomater", "kogte ris til
  servering") købes i en almindelig mængde (fx 300 g ris eller én dåse); kun
  det valgfrie ("evt. persille", "smør til stegning") regnes for at være
  derhjemme. "1 pakke grillpølser" er en hel pakke, og "10 cherrytomater" er
  10 tomater, ikke 10 bakker. Hver ingrediens genkendes i aviserne ud fra nøgleord, så
  hvert tilbud ved, hvilke ingredienser det kan bruges som. En bestemt vare
  går forud for en bred: parmesan er ikke revet ost, og rucola og
  romainesalat er ikke icebergsalat. Er et tilbud på to varer, fx "pasta
  eller hakkede tomater", står kun den del, retten bruger.
- Retterne får point for tre ting: lav pris pr. person, stor besparelse i
  forhold til normalprisen og meget grønt. Vælg **Lavest mulig pris** for at
  lægge mest vægt på prisen.
- Planen følger kostrådene: fisk hver uge (to gange ved 6-7 retter), en
  grøntsagsret ved 4 eller flere retter, højst halvdelen med rødt kød og højst
  to retter af samme slags. Samme hovedingrediens (fx hakket grisekød) eller
  samme hovedtilbud bruges ikke to gange, så ugen ikke bliver fire slags
  frikadeller. Retter med under 125 g grønt pr. person får grønt
  tilbehør, fx råkost, af det billigste grønt på tilbud.
- Under **Butik** er standardvalget **Højst 2 butikker**: madplanen prøver
  de butikker, hvor ugens bedste tilbudsretter har deres hovedtilbud, og
  vælger de to (eller **Kun 1 butik**: den ene), der giver flest
  tilbudsretter og de bedste point. Øverst står, hvor du skal handle. Ugen
  bliver lidt dyrere end med alle butikker, men skal kun købes ind ét eller
  to steder. Du kan også vælge **Alle mine butikker** eller én bestemt
  butik. Butikkerne vælges, når planen laves, og ændres ikke, når du bytter
  eller flytter retter.
- Er der ikke tilbudsretter nok (fx med kun én butik), fyldes ugen ud med
  billige hverdagsretter fra samlingen, så der er aftensmad alle dage. De
  er mærket, så du kan se, at hovedvaren ikke er på tilbud.
- For hver vare vises det billigste tilbud pr. kg, helst fra den butik, hvor
  hovedingrediensen købes, så en ret kan købes ind ét sted. Varerne står
  under **Varer** ved hver ret, som foldes ud med et tryk.
- Et tilbud bruges kun, når det er billigere end **basisvaren**: den
  rigtige hyldepris uden tilbud i REMA 1000 på den billigste almindelige (ikke
  økologiske) udgave af varen. Hele REMA 1000's sortiment hentes fra deres
  webshop med hver opdatering og gemmes i `normalpriser.json` (`shelf.py`);
  svarer webshoppen ikke, bruges de sidst hentede priser. Har REMA 1000 ikke
  varen, bruges en anslået pris (`NORMAL_PRICES` i `mealplan.py`), og koster
  varen typisk mere på tilbud i aviserne (medianen af mindst 6 tilbud i
  prishistorikken), bruges det i stedet, dog højst halvanden gang den
  anslåede pris. En stor rabat på et dyrt mærke er altså ikke nok. Under
  **Basispriser** kan du rette priserne til det, du selv giver; dine priser
  gemmes i browseren.
- Hver ret har en samlet pris og en pris pr. person. Den regnes for de
  mængder, retten bruger, med tilbuddets pris pr. kg, liter eller stk, og for
  varer uden tilbud med basisvarens pris. Besparelsen regnes også i forhold
  til basisvaren.
- Du køber hele pakker, også af varer uden tilbud (fx et net løg eller en
  bakke æg, `BASIS_PACK_G` i `mealplan.py`). Prisen på en ret er det, du
  betaler i butikken; under hver vare står, hvor mange pakker du køber, hvad
  retten bruger, og prisen pr. person. Bliver der nok tilbage af en pakke
  til en senere ret, står der "Resten af pakken fra …" og ingen pris, også
  når resten er af samme vare fra et andet tilbud. Et tilbud vælges efter
  prisen for de hele pakker, retten skal bruge, så en kæmpepakke til lav
  kilopris ikke vælges til 400 g, og retter, der kan dele en pakke,
  foretrækkes. Tryk på et tilbud
  for at se det hele med billede, avis og hvad det bruges til i planen; du
  kan bladre mellem planens tilbud.
- Et tilbud bruges kun på en dag, hvor det gælder. En ret, hvis tilbud først
  starter senere i perioden, lægges på en dag, hvor tilbuddet er startet.
- Øverst står, hvad du betaler i butikken for ugen, hvad retterne bruger
  (pr. dag og pr. person), hvad resten af pakkerne er værd, og hvor meget
  tilbuddene sparer. Varer, du har derhjemme, og varer uden kendt pris er ikke regnet
  med.
- Øverst står valgene på én linje (fx "5 dage fra i dag · 4 pers. · højst
  2 butikker"); tryk **Ret** for at vælge første dag, antal dage, antal
  personer (mængderne skaleres), kost (alt, uden svinekød, uden fisk eller
  vegetar), butik og hvor mange varer der skal være på tilbud. Hver ret får
  en dag: retter over 45 minutter lægges i weekenden og de hurtige på
  hverdagene. **↑** og **↓** flytter en ret, **Byt ret** viser fire andre
  retter, der passer ind i planen (pris pr. person, tid og hvor mange varer
  der er på tilbud), at vælge imellem, eller søg en hvilken som helst ret frem
  og vælg den selv (den bliver på planen, også uden tilbud). **Ny madplan**
  giver helt nye retter.
- Retterne står på deres dato. Åbner du planen senere på ugen, er de dage,
  der er gået, væk, og resten står, hvor de stod, så de passer til det, du
  har købt. Først når alle dagene er gået, laves en ny plan.
- Øverst står også, hvad der er tilovers af pakkerne efter ugen (fx "400 g
  ris, citron (ca. 4 stk)"), og hvilke tilbud der først kan købes senere. Er
  der meget tilovers af en vare, der ikke holder sig (fx kyllingebryst eller
  spinat for mindst 10 kr), foreslår **Brug resterne** en ret, der bruger det,
  som en dag mere på planen.
- Retterne vælges, så ugen som helhed bliver billigst: retter, der deler
  pakker (også ris, løg og andre varer uden tilbud), foretrækkes, og samme
  hovedvare må bruges i to forskellige retter, når den anden bruger resten
  af pakken (fx bolognese og chili af samme pakke hakket kød). Til 1-2
  personer kan **Lav dobbelte portioner** gøre ugen billigere; det
  beholdes kun, når det gør.
- Holdbare rester (ris, pasta, løg, kartofler, dåser ...) står i næste uges
  plan under **Det har jeg allerede** som "(rest)", så de bliver brugt.
- **Opskrift** (eller et tryk på rettens navn) viser det, du skal bruge,
  regnet om til planens antal personer, det, der skal være i skabet, og
  fremgangsmåden. For de hentede opskrifter står fremgangsmåden hos
  madsiden, som der linkes til (teksten er madsidens og gemmes ikke).
  Bladr mellem dagene med **Dagen før** og **Dagen efter**.
- På forsiden står dagens ret fra madplanen ("I aften: ..."; efter kl. 20
  morgendagens) med en knap til opskriften. Dagen efter en dobbelt portion
  står resten som "Rester fra i går", og der skal ikke købes noget til den.
- **Dobbelt portion** laver retten til to dage, så resten spises dagen efter.
- **Det har jeg allerede**: skriv, hvad du har i køleskabet eller skabet
  (eller tryk **har jeg** ved en vare). Retter, der bruger det, kommer
  først, det koster ikke noget i planen, og det kommer ikke på
  indkøbslisten.
- **Mine opskrifter**: tilføj dine egne retter ved at skrive eller kopiere
  ingredienslisten ind. Hver linje som "500 g hakket oksekød" genkendes som
  tilbuddene, og retten kommer på madplanen, når hovedingrediensen er på
  tilbud, eller når du trykker **Sæt på madplanen**. Du kan også indsætte
  et link til en opskrift (også fra **+ Egen opskrift fra link** i
  ugeplanen): navn, ingredienser og fremgangsmåde hentes fra madsiden, og
  du ser med det samme, hvilke varer der er på tilbud i ugen, og hvad retten
  koster. Er opskriften allerede i samlingen, hentes den derfra. På
  GitHub Pages kan siden ikke selv hente andre sider, så den prøver først
  direkte og ellers gennem den gratis tjeneste r.jina.ai, som kun får
  adressen på opskriften. Egne opskrifter
  gemmes i browseren.
- **Læg på indkøbslisten** lægger tilbuddene og de varer, der ikke er på
  tilbud, på indkøbslisten. Samme vare i flere retter lægges sammen, med en
  note om mængden og retterne, og antallet af pakker står på listen og
  ganges med i prisen. Varer uden tilbud lægges under den butik, hvor de
  fleste af ugens tilbud købes. Krydderier, olie og mel regnes som noget, man
  har derhjemme, men det, man ofte ikke har (fx harissa, kapers, pesto,
  nødder og friske krydderurter som dild og koriander), står ved retten som
  **Tjek om du har** og kommer på listen med en note. Varer uden tilbud får
  den anslåede pris for hele pakker, så listens sum passer med madplanens.
  Laver du en ny madplan og lægger den på listen, erstatter den den forrige
  madplans varer; det, du har sat hak ved, og det, du selv har lagt på,
  bliver. Listen åbnes, så du kan se den. Indkøbslisten er sorteret efter
  afdeling i butikken.

Under **På tilbud** vælger du, hvor mange af rettens varer der skal være på
tilbud: mindst halvdelen (standard), mindst 3 af 4 eller alle. Krydderier,
olie og det, du har derhjemme, tæller ikke med, og en vare uden kendt pris
tæller som ikke på tilbud. Uanset valget skal rettens hovedingredienser,
fx kødet, altid være på tilbud eller noget, du har derhjemme.

Madplanen huskes i browseren, ligesom indkøbslisten.

### Planlæg kommende uger (ugeplan)

Knappen **Planlæg kommende uger** nederst i madplanen viser alle
opskrifterne, så du selv kan vælge retter til denne og de kommende uger
(madplanen vælger dem for dig ud fra ugens tilbud). Ugerne har ugenummeret fra kalenderen (ISO-uger, som i
Danmark), og du bladrer fra denne uge og op til 12 uger frem. Søg efter en
ret eller ingrediens, vælg slags, og tryk **+ uge 42** for at gemme retten
i ugen. Retterne i ugen sættes i den rækkefølge, du har lyst til at spise
dem, med ↑ og ↓. **Læg på indkøbslisten** lægger ugens ingredienser på
listen, lagt sammen pr. vare til det valgte antal personer. Tryk på en ret i ugen for at åbne opskriften og lægge
netop dens ingredienser på listen. Under opskriften kan du også vælge
retten til en anden uge. Under hver vare står det billigste tilbud i ugen
fra dine butikker (tryk for at se tilbuddet), og ved retten står, hvor
mange varer der er på tilbud. For de kommende uger vises kun de tilbud,
der allerede er kendt. Som standard står retterne med den største andel
af varerne på tilbud først (kun retter med varer på tilbud i ugen); vælg
**Flest varer på tilbud** eller **Alfabetisk** for en anden rækkefølge. Hver ret kan åbnes, lægges i en uge og på
indkøbslisten. Ved hver ret står, hvad den koster til ugens antal
personer, og i den åbne ret står prisen for hver vare: hele pakker af
tilbuddet eller basisvaren, som i madplanen. I madplanen
kan en ret gemmes i sin uge med **Gem i uge 42**. Ugeplanen huskes i
browseren; uger, der er mere end fire uger gamle, ryddes væk.

### Flere opskrifter fra madsider

Næsten alle madsider beskriver deres opskrifter med
[schema.org/Recipe](https://schema.org/Recipe), så Google kan vise dem. Det
bruger Tilbudshenter til at hente opskrifter automatisk:

1. Skriv adressen på en opskrift, et sitemap eller bare en madside (fx
   `sitemap: https://www.valdemarsro.dk/`) i `opskrifter.txt` (én pr. linje;
   se eksemplerne i filen). For en madside findes sitemappet i dens
   robots.txt, og op til 2500 opskrifter hentes.
2. Hver gang siden bygges, henter GitHub op til 3000 nye sider, højst 150
   fra hver madside. Madsiderne hentes samtidig, men hver madside kun én
   side ad gangen med et sekunds pause. Opskrifterne gemmes i
   `src/tilbudshenter/data/opskrifter.json` og lægger dem ind i madplanen.
   Hver side hentes kun én gang.

Kun navn, antal personer, tid og ingredienser gemmes; madplanen linker til
madsiden for fremgangsmåden. Opskrifter med kød eller fisk, som ikke kan
genkendes i aviserne, eller med for mange ukendte varer, springes over, da
de ikke kan prissættes. Det samme gør opskrifter, der ikke er aftensmad (se
Madplan ovenfor). Reglerne bruges også på opskrifter, der allerede er hentet,
så de flyttes til listen over sprungne sider, når reglerne skærpes.

Opskrifter fra engelske madsider (fx BBC Good Food og RecipeTin Eats) gemmes
på engelsk og oversættes til dansk, når de bruges: navnet ("Chicken and leek
pie" bliver "Tærte med kylling og porrer"), mængderne (cups til dl, oz og lb
til g, tbsp til spsk) og ingredienserne, så de kan findes i tilbudsaviserne.
Oversættelsen er en ordliste i `src/tilbudshenter/oversaet.py`; en opskrift,
hvis navn ikke kan oversættes helt, springes over, og det samme gør en
opskrift med kød eller fisk, ordlisten ikke kender. Fremgangsmåden står på
engelsk på madsiden.

## Udvikling

```bash
pip install -e ".[dev]"
pytest
```

Søgningen og "Mine basisvarer" testes mod et øjebliksbillede af rigtige
aviser (`tests/data/`). `tests/test_search_cases.py` fejler, hvis et søgeord
mister et træf eller får nye. Nye træf godkendes med
`python tests/update_search_cases.py` (`--nyt ord` tilføjer et søgeord), og
træf kan kun fjernes med `--fjern-traef`, når Simon har sagt god for det.
