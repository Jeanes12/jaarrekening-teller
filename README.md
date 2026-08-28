# Teller: nog neer te leggen jaarrekeningen

Een kleine webpagina die elk uur automatisch toont hoeveel jaarrekeningen nog
niet neergelegd zijn, geteld op basis van de taken in AdminPulse. De pagina
draait gratis op GitHub Pages; het tellen gebeurt door een geplande GitHub
Action. Er is geen eigen server nodig.

**Hoe het werkt, in één zin:** elk uur haalt `teller.py` via de AdminPulse-API
alle taken op, telt de subtaken "Neerlegging jaarrekening" die niet op
*Afgewerkt* staan, en publiceert dat cijfer als webpagina.

De pagina toont daarnaast een aftelklok (op de seconde) tot de deadline, en een
quote die verandert telkens het cijfer daalt. Het uiterlijk volgt de huisstijl
van adp-accountants.be (blauw, goud, Merriweather en Montserrat).

## Wat je nodig hebt

- Een GitHub-account (gratis volstaat).
- Beheerdersrechten in AdminPulse, om een API-sleutel te kunnen aanmaken.
- Een kwartiertje. Er hoeft niets geïnstalleerd te worden.

## Installatie, stap voor stap

### 1. API-sleutel aanmaken in AdminPulse

1. Open in AdminPulse **Mijn profiel > API-sleutels**
   (rechtstreekse link: https://app.adminpulse.be/#/profile/accesstokens).
2. Maak een nieuwe sleutel aan. Kies bij het type voor **eigen kantoorintegratie**
   en geef enkel de scope **tasks.read** (lezen van taken). Meer is niet nodig.
3. Kopieer de sleutel. Je plakt hem straks één keer in GitHub en nergens anders.
   Behandel hem als een wachtwoord.

### 2. Repository aanmaken op GitHub

1. Ga naar https://github.com/new.
2. Naam: bijvoorbeeld `jaarrekening-teller`. Kies **Public** (gratis GitHub Pages
   werkt enkel bij publieke repositories; er komen geen klantgegevens in, enkel
   deze bestanden, het cijfer en de geschiedenis van het cijfer).
3. Klik op **Create repository**.

### 3. Bestanden uploaden

1. Klik in de nieuwe repository op **Add file > Upload files**.
2. Sleep de **inhoud** van de zip in het venster, mappen inbegrepen. Controleer
   dat de lijst ook `.github/workflows/teller.yml` bevat; zonder dat bestand
   loopt er niets automatisch.
3. Klik onderaan op **Commit changes**.

### 4. API-sleutel als geheime instelling bewaren

1. Ga naar **Settings > Secrets and variables > Actions**.
2. Klik op **New repository secret**.
3. Naam: `ADMINPULSE_API_KEY` (exact zo). Waarde: de sleutel uit stap 1.
4. Klik op **Add secret**. De sleutel is daarna voor niemand meer leesbaar, ook
   niet voor jou; enkel het script kan hem gebruiken.

### 5. GitHub Pages inschakelen

1. Ga naar **Settings > Pages**.
2. Zet bij **Build and deployment > Source** de keuze op **GitHub Actions**.
   (De workflow probeert dit ook zelf te doen bij de eerste run; even
   controleren kan geen kwaad.)

### 6. Eerste keer laten lopen

1. Ga naar het tabblad **Actions** en kies links **Teller jaarrekeningen bijwerken**.
2. Klik op **Run workflow > Run workflow**. (Een eerdere run die automatisch
   startte bij het uploaden is mogelijk mislukt omdat de sleutel er toen nog
   niet was; dat is normaal.)
3. Na een paar minuten staat er een groen vinkje. De link naar de pagina vind je
   bij de stap **Pagina publiceren** of onder **Settings > Pages**. Ze ziet er
   zo uit: `https://<jouw-gebruikersnaam>.github.io/jaarrekening-teller/`

Vanaf nu loopt het elk uur vanzelf.

## Controleren of het cijfer klopt

Vergelijk het cijfer op de pagina met je filter in AdminPulse. Open in GitHub
de laatste run (tabblad **Actions**) en klik op de stap
**Aantal ophalen uit AdminPulse en pagina maken**. Daar staat precies wat geteld
is: per status (te doen / bezig / afgewerkt) en per referentiejaar.

Komt het cijfer niet overeen, dan zit het verschil bijna altijd in een van deze
instellingen in `config.ini`:

| Instelling | Standaard | Wanneer aanpassen |
|---|---|---|
| `taaknaam` | Neerlegging jaarrekening | Heet de subtaak bij jullie anders, zet hier de juiste naam. |
| `vergelijking` | exact | Zet op `bevat` als de naam een toevoeging heeft (bv. "Neerlegging jaarrekening NBB"). |
| `referentiejaar` | leeg (alle jaren) | Wil je enkel boekjaar 2025 tellen, zet `2025`. |
| `deadline_van` en `deadline_tot` | leeg (alle deadlines) | Enkel neerleggingen tellen met een deadline in een periode, bv. `deadline_van = 01/01/2026` en `deadline_tot = 31/12/2026`. Het gaat om de deadline van de subtaak zelf; één van beide mag leeg blijven. |
| `ophalen_vanaf` | 1 januari van vorig jaar | Hoe ver terug het script taken ophaalt bij AdminPulse (enkel voor de snelheid). Telt jouw filter ook oudere jaren mee, zet hier een vroegere datum (dd/mm/jjjj) of het woord `alles`. |

Past geen enkele taak bij de ingestelde filter, dan stopt het script bewust met
een foutmelding (de pagina blijft dan op het vorige cijfer staan) en toont het
in het logboek welke subtaaknamen wél bestaan, zodat je de juiste kunt kiezen.

**Iets aanpassen:** open `config.ini` op GitHub, klik op het potloodje, wijzig,
en klik op **Commit changes**. De teller loopt daarna meteen opnieuw.

## Aftelklok, quotes en uiterlijk

- **Aftelklok.** In `config.ini` onder `[aftelklok]` staat `tot = 31/08/2026 23:59:59`
  (Belgische tijd). De klok telt af op de seconde; is het moment voorbij, dan
  verschijnt de tekst uit `verstreken_tekst`. Laat `tot` leeg om de klok te
  verbergen. Volgend jaar volstaat het de datum aan te passen.
- **Quotes.** De quotes staan in `citaten.txt`, één per regel; een bron zet je
  erachter na een `|`. Telkens het cijfer daalt, verschijnt de volgende quote
  (in een vaste, gehusselde volgorde; de lijst begint opnieuw als ze rond is).
  Stijgt het cijfer, dan blijft de quote staan. Bij nul verschijnt de quote uit
  `bij_nul` in `config.ini`. Voeg gerust eigen quotes toe: opslaan op GitHub
  volstaat.
- **Uiterlijk.** De kleuren en lettertypes staan bovenaan in `sjabloon.html`
  (blauw `#22559a`, navy `#16163f`, goud `#d3b574`, lichtblauw `#a3c6cf`).
  De lettertypes Merriweather, Montserrat en Open Sans worden van Google Fonts
  geladen; zonder internet valt de pagina terug op een gewoon lettertype.
  Op een tv-scherm (breder dan 1600 pixels) wordt alles automatisch wat groter.

## Goed om te weten

- **Tijdstip.** De teller loopt elk uur, 7 minuten na het uur. GitHub kan een
  geplande run bij drukte enkele minuten uitstellen. Wil je een ander ritme,
  pas dan de regel `cron:` aan in `.github/workflows/teller.yml` (daar staat
  een voorbeeld bij).
- **Verversen.** De pagina zelf haalt om de 5 minuten het nieuwste cijfer op;
  je hoeft ze niet te herladen. Handig voor een scherm op kantoor.
- **Waarschuwing.** Is het cijfer meer dan 3 uur oud (bijvoorbeeld omdat een run
  mislukte), dan verschijnt een gele melding op de pagina. GitHub stuurt je bij
  een mislukte run ook een e-mail; het logboek zegt dan wat er misging.
- **60-dagenregel.** GitHub zet geplande workflows in een publieke repository
  uit als er 60 dagen geen activiteit was. De teller bewaart zelf een regel in
  `geschiedenis.csv` telkens het cijfer verandert, wat als activiteit telt. Stopt
  het toch (je krijgt daar een mail over), klik dan in **Actions** op de workflow
  en op **Enable workflow**.
- **Geschiedenis.** `geschiedenis.csv` bevat per wijziging het tijdstip, het
  aantal open en het aantal afgewerkte neerleggingen. Handig om later de
  voortgang van het seizoen te bekijken, bijvoorbeeld in Excel.
- **Privacy.** Op de pagina staan enkel een cijfer en een tijdstip. In de
  repository staan geen klantnamen en nooit de API-sleutel.
- **Sleutel intrekken.** Verwijder de sleutel in AdminPulse en maak een nieuwe;
  zet die als nieuwe waarde bij de secret `ADMINPULSE_API_KEY`.
- **Stoppen.** Tabblad **Actions > Teller jaarrekeningen bijwerken > ... > Disable workflow**.

## Bestanden

| Bestand | Wat het doet |
|---|---|
| `teller.py` | Haalt de taken op, telt, kiest de quote en maakt de pagina. |
| `config.ini` | Instellingen: taaknaam, filter, aftelklok, teksten op de pagina. |
| `citaten.txt` | De quotes, één per regel. |
| `sjabloon.html` | Het uiterlijk van de pagina (kleuren, lettertypes, aftelklok). |
| `.github/workflows/teller.yml` | De uurlijkse planning en de publicatie naar GitHub Pages. |
| `geschiedenis.csv` | Wordt automatisch aangemaakt: verloop van het cijfer. |
| `.gitignore` | Zorgt dat tijdelijke bestanden niet in de repository komen. |

De AdminPulse-API die gebruikt wordt: `GET https://api.adminpulse.be/tasks`
(documentatie op https://developer.adminpulse.be). Statussen: 0 = te doen,
1 = bezig, 2 = afgewerkt. Subtaken met de markering "niet van toepassing"
worden niet meegeteld.
