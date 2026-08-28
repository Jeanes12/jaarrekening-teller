#!/usr/bin/env python3
"""
Teller "nog neer te leggen jaarrekeningen".

Haalt via de AdminPulse-API alle hoofdtaken (met hun subtaken) op, telt de
subtaken met de ingestelde naam (standaard "Neerlegging jaarrekening") die nog
niet op status "Afgewerkt" staan, en schrijft:

  site/index.html     de webpagina met het cijfer, de quote en de aftelklok
  site/data.json      dezelfde gegevens als data (de pagina ververst zich hiermee)
  geschiedenis.csv    één regel per keer dat het cijfer verandert

Instellingen staan in config.ini, de quotes in citaten.txt. De API-sleutel komt
uit de omgevingsvariabele ADMINPULSE_API_KEY (in GitHub: Settings > Secrets and
variables > Actions).

Gebruikt enkel de standaardbibliotheek van Python, dus niets te installeren.
"""

import configparser
import csv
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

API_URL = os.environ.get("ADMINPULSE_API_URL", "https://api.adminpulse.be").rstrip("/")
API_KEY = os.environ.get("ADMINPULSE_API_KEY", "").strip()

STATUS_TODO, STATUS_BEZIG, STATUS_AFGEWERKT = 0, 1, 2
STATUS_NAMEN = {0: "te doen", 1: "bezig", 2: "afgewerkt"}
PAGINAGROOTTE = 400          # maximum van de API
TIJDZONE = ZoneInfo("Europe/Brussels")

MAP = Path(__file__).resolve().parent
SITE_MAP = MAP / "site"
SJABLOON = MAP / "sjabloon.html"
CITATEN = MAP / "citaten.txt"
GESCHIEDENIS = MAP / "geschiedenis.csv"


# --------------------------------------------------------------------------- #
# Instellingen
# --------------------------------------------------------------------------- #
def lees_datum(tekst: str, naam: str):
    """dd/mm/jjjj -> date, of None als leeg."""
    tekst = (tekst or "").strip()
    if not tekst:
        return None
    try:
        return datetime.strptime(tekst, "%d/%m/%Y").date()
    except ValueError:
        sys.exit(f"FOUT: '{naam}' in config.ini moet het formaat dd/mm/jjjj hebben, niet '{tekst}'.")


def lees_instellingen() -> dict:
    cfg = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    cfg.read(MAP / "config.ini", encoding="utf-8")

    f = cfg["filter"] if "filter" in cfg else {}
    p = cfg["pagina"] if "pagina" in cfg else {}
    k = cfg["aftelklok"] if "aftelklok" in cfg else {}
    c = cfg["citaten"] if "citaten" in cfg else {}

    vandaag = date.today()
    deadline_van = lees_datum(f.get("deadline_van", ""), "deadline_van")
    deadline_tot = lees_datum(f.get("deadline_tot", ""), "deadline_tot")
    if deadline_van and deadline_tot and deadline_van > deadline_tot:
        sys.exit("FOUT: 'deadline_van' ligt na 'deadline_tot' in config.ini.")

    # Venster waarmee we bij AdminPulse ophalen: ruim rond de gevraagde periode,
    # omdat de API-filter op de hoofdtaak kan slaan en niet op de subtaak.
    ophalen_vanaf = f.get("ophalen_vanaf", "").strip().lower()
    if deadline_van:
        api_vanaf = deadline_van - timedelta(days=366)
    elif ophalen_vanaf in ("", None):
        api_vanaf = date(vandaag.year - 1, 1, 1)
    elif ophalen_vanaf == "alles":
        api_vanaf = None
    else:
        api_vanaf = lees_datum(ophalen_vanaf, "ophalen_vanaf")
    api_tot = deadline_tot + timedelta(days=366) if deadline_tot else None

    aftel_tot = None
    aftel_tekst = (k.get("tot", "") or "").strip()
    if aftel_tekst:
        try:
            aftel_tot = datetime.strptime(aftel_tekst, "%d/%m/%Y %H:%M:%S").replace(tzinfo=TIJDZONE)
        except ValueError:
            sys.exit("FOUT: 'tot' bij [aftelklok] moet het formaat dd/mm/jjjj uu:mm:ss hebben.")

    ref = (f.get("referentiejaar", "") or "").strip()
    return {
        "taaknaam": f.get("taaknaam", "Neerlegging jaarrekening").strip(),
        "vergelijking": f.get("vergelijking", "exact").strip().lower(),
        "referentiejaar": int(ref) if ref else None,
        "deadline_van": deadline_van,
        "deadline_tot": deadline_tot,
        "api_vanaf": api_vanaf,
        "api_tot": api_tot,
        "titel": p.get("titel", "Nog neer te leggen jaarrekeningen").strip(),
        "ondertitel": p.get("ondertitel", "").strip(),
        "nul_boodschap": p.get("nul_boodschap", "Alles is neergelegd.").strip(),
        "ververs_minuten": int(p.get("ververs_minuten", "5") or 5),
        "verouderd_na_uur": int(p.get("verouderd_na_uur", "3") or 3),
        "aftel_tot": aftel_tot,
        "aftel_tekst": k.get("tekst", "tot de deadline").strip(),
        "aftel_verstreken": k.get("verstreken_tekst", "De deadline is verstreken.").strip(),
        "citaat_bij_nul": c.get("bij_nul", "").strip(),
    }


def api_datum(d) -> str:
    """date -> ddMMyyyy zoals de API het wil; leeg als er geen datum is."""
    return d.strftime("%d%m%Y") if d else ""


# --------------------------------------------------------------------------- #
# AdminPulse-API
# --------------------------------------------------------------------------- #
def api_get(pad: str, params: dict) -> dict:
    """Eén GET-oproep naar de API, met herhaling bij tijdelijke fouten."""
    params = {k: v for k, v in params.items() if v not in ("", None)}
    url = f"{API_URL}{pad}?{urllib.parse.urlencode(params)}"
    verzoek = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {API_KEY}",
        "Accept": "application/json",
        "User-Agent": "jaarrekening-teller/1.1",
    })

    for poging in range(1, 6):
        try:
            with urllib.request.urlopen(verzoek, timeout=120) as antwoord:
                return json.loads(antwoord.read().decode("utf-8"))
        except urllib.error.HTTPError as fout:
            if fout.code == 401:
                sys.exit("FOUT: de API weigert de sleutel (401). Controleer de Secret "
                         "ADMINPULSE_API_KEY en of de sleutel de scope tasks.read heeft.")
            if fout.code == 429:
                print(f"  te veel oproepen (429), even wachten ... (poging {poging})")
                time.sleep(20)
                continue
            if 500 <= fout.code < 600 and poging < 5:
                print(f"  serverfout {fout.code}, opnieuw proberen ... (poging {poging})")
                time.sleep(10 * poging)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as fout:
            if poging < 5:
                print(f"  netwerkfout ({fout}), opnieuw proberen ... (poging {poging})")
                time.sleep(10 * poging)
                continue
            raise
    sys.exit("FOUT: de API bleef fouten geven; later opnieuw proberen.")


def haal_alle_taken(inst: dict) -> list:
    """Haalt alle pagina's van GET /tasks op en geeft één lijst hoofdtaken terug."""
    taken, pagina = [], 0
    while True:
        data = api_get("/tasks", {
            "page": pagina,
            "pageSize": PAGINAGROOTTE,
            "deadlineFrom": api_datum(inst["api_vanaf"]),
            "deadlineUntil": api_datum(inst["api_tot"]),
            "languageCode": "nl",
        })
        resultaten = data.get("results", []) if isinstance(data, dict) else data
        taken.extend(resultaten)
        print(f"  pagina {pagina + 1}: {len(resultaten)} hoofdtaken")

        pagina += 1
        aantal_paginas = data.get("pageCount") if isinstance(data, dict) else None
        if aantal_paginas is not None and pagina >= int(aantal_paginas):
            break
        if len(resultaten) < PAGINAGROOTTE:
            break
        if pagina > 2000:                      # noodrem
            break
    return taken


# --------------------------------------------------------------------------- #
# Tellen
# --------------------------------------------------------------------------- #
def normaliseer(tekst) -> str:
    return " ".join(str(tekst or "").lower().split())


def naam_past(taak: dict, inst: dict) -> bool:
    doel = normaliseer(inst["taaknaam"])
    kandidaten = {normaliseer(taak.get("templateName")), normaliseer(taak.get("name"))}
    if inst["vergelijking"] == "bevat":
        return any(doel in k for k in kandidaten if k)
    return doel in kandidaten


def deadline_van_taak(taak: dict):
    """De deadline van een taak als date, of None."""
    tekst = (taak.get("deadline") or "")[:10]
    try:
        return date.fromisoformat(tekst) if tekst else None
    except ValueError:
        return None


def binnen_periode(taak: dict, inst: dict) -> bool:
    if not inst["deadline_van"] and not inst["deadline_tot"]:
        return True
    d = deadline_van_taak(taak)
    if d is None:
        return False                          # zonder deadline kan ze niet in de periode vallen
    if inst["deadline_van"] and d < inst["deadline_van"]:
        return False
    if inst["deadline_tot"] and d > inst["deadline_tot"]:
        return False
    return True


def tel(taken: list, inst: dict) -> dict:
    open_taken, afgewerkt = [], 0
    per_jaar, per_status = {}, {0: 0, 1: 0, 2: 0}
    gezien_namen, buiten_periode = {}, 0

    for hoofdtaak in taken:
        if hoofdtaak.get("inapplicable"):
            continue
        jaar = hoofdtaak.get("referenceYear")
        if inst["referentiejaar"] and jaar != inst["referentiejaar"]:
            continue

        subtaken = hoofdtaak.get("subtasks") or []
        for s in subtaken:
            naam = s.get("templateName") or s.get("name") or ""
            gezien_namen[naam] = gezien_namen.get(naam, 0) + 1

        passend = [s for s in subtaken if naam_past(s, inst)]
        if not passend and naam_past(hoofdtaak, inst):
            passend = [hoofdtaak]              # de neerlegging is zelf een hoofdtaak

        for t in passend:
            if t.get("inapplicable"):
                continue
            if not binnen_periode(t, inst):
                buiten_periode += 1
                continue
            status = t.get("status")
            per_status[status] = per_status.get(status, 0) + 1
            if status == STATUS_AFGEWERKT:
                afgewerkt += 1
            else:
                open_taken.append({
                    "relatie": hoofdtaak.get("relationUniqueIdentifier"),
                    "deadline": (t.get("deadline") or "")[:10],
                    "status": STATUS_NAMEN.get(status, str(status)),
                    "jaar": jaar,
                })
                sleutel = str(jaar) if jaar is not None else "onbekend"
                per_jaar[sleutel] = per_jaar.get(sleutel, 0) + 1

    return {
        "aantal_open": len(open_taken),
        "aantal_afgewerkt": afgewerkt,
        "per_jaar": dict(sorted(per_jaar.items())),
        "per_status": {STATUS_NAMEN.get(k, str(k)): v for k, v in per_status.items()},
        "buiten_periode": buiten_periode,
        "open_taken": open_taken,
        "gezien_namen": gezien_namen,
    }


# --------------------------------------------------------------------------- #
# Geschiedenis en quotes
# --------------------------------------------------------------------------- #
def lees_geschiedenis() -> list:
    if not GESCHIEDENIS.exists():
        return []
    with GESCHIEDENIS.open(encoding="utf-8", newline="") as bestand:
        return list(csv.DictReader(bestand, delimiter=";"))


def bewaar_geschiedenis(telling: dict, nu: datetime) -> bool:
    """Voegt een regel toe als het cijfer veranderd is. Geeft terug of er iets geschreven is."""
    rijen = lees_geschiedenis()
    if not GESCHIEDENIS.exists():
        GESCHIEDENIS.write_text("tijdstip;aantal_open;aantal_afgewerkt\n", encoding="utf-8")

    laatste = rijen[-1] if rijen else None
    if laatste and laatste.get("aantal_open") == str(telling["aantal_open"]) \
            and laatste.get("aantal_afgewerkt") == str(telling["aantal_afgewerkt"]):
        return False

    with GESCHIEDENIS.open("a", encoding="utf-8", newline="") as bestand:
        csv.writer(bestand, delimiter=";").writerow([
            nu.astimezone(TIJDZONE).strftime("%d/%m/%Y %H:%M"),
            telling["aantal_open"],
            telling["aantal_afgewerkt"],
        ])
    return True


def aantal_dalingen() -> int:
    """Hoe vaak het cijfer in de geschiedenis gedaald is (bepaalt welke quote aan de beurt is)."""
    dalingen, vorige = 0, None
    for rij in lees_geschiedenis():
        try:
            huidig = int(rij.get("aantal_open", ""))
        except ValueError:
            continue
        if vorige is not None and huidig < vorige:
            dalingen += 1
        vorige = huidig
    return dalingen


def lees_citaten() -> list:
    citaten = []
    if CITATEN.exists():
        for regel in CITATEN.read_text(encoding="utf-8").splitlines():
            regel = regel.strip()
            if not regel or regel.startswith("#"):
                continue
            tekst, _, bron = regel.partition("|")
            citaten.append({"tekst": tekst.strip(), "bron": bron.strip()})
    # Vaste, gehusselde volgorde: elke daling geeft de volgende quote, zonder herhaling
    # tot de lijst rond is.
    random.Random(2026).shuffle(citaten)
    return citaten


def kies_citaat(telling: dict, inst: dict) -> dict:
    if telling["aantal_open"] == 0 and inst["citaat_bij_nul"]:
        return {"tekst": inst["citaat_bij_nul"], "bron": ""}
    citaten = lees_citaten()
    if not citaten:
        return {"tekst": "", "bron": ""}
    return citaten[aantal_dalingen() % len(citaten)]


# --------------------------------------------------------------------------- #
# Uitvoer
# --------------------------------------------------------------------------- #
DAGEN = ["maandag", "dinsdag", "woensdag", "donderdag", "vrijdag", "zaterdag", "zondag"]


def tekst_tijd(moment: datetime) -> str:
    lokaal = moment.astimezone(TIJDZONE)
    return f"{DAGEN[lokaal.weekday()]} {lokaal:%d/%m/%Y} om {lokaal:%H:%M}"


def ontsmet(tekst) -> str:
    """Maakt tekst veilig om in HTML te zetten."""
    return (str(tekst).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def schrijf_uitvoer(telling: dict, inst: dict, citaat: dict, nu: datetime) -> None:
    SITE_MAP.mkdir(exist_ok=True)

    gegevens = {
        "aantal_open": telling["aantal_open"],
        "aantal_afgewerkt": telling["aantal_afgewerkt"],
        "per_jaar": telling["per_jaar"],
        "bijgewerkt": nu.isoformat(timespec="seconds"),
        "bijgewerkt_tekst": tekst_tijd(nu),
        "citaat": citaat["tekst"],
        "citaat_bron": citaat["bron"],
        "aftel_tot": inst["aftel_tot"].isoformat() if inst["aftel_tot"] else None,
        "filter": {
            "taaknaam": inst["taaknaam"],
            "referentiejaar": inst["referentiejaar"],
            "deadline_van": inst["deadline_van"].strftime("%d/%m/%Y") if inst["deadline_van"] else None,
            "deadline_tot": inst["deadline_tot"].strftime("%d/%m/%Y") if inst["deadline_tot"] else None,
        },
    }
    (SITE_MAP / "data.json").write_text(json.dumps(gegevens, ensure_ascii=False, indent=2),
                                        encoding="utf-8")

    html = SJABLOON.read_text(encoding="utf-8")
    vervangingen = {
        "{{TITEL}}": inst["titel"],
        "{{ONDERTITEL}}": inst["ondertitel"],
        "{{AANTAL}}": str(telling["aantal_open"]),
        "{{NUL_BOODSCHAP}}": inst["nul_boodschap"],
        "{{CITAAT}}": citaat["tekst"],
        "{{CITAAT_BRON}}": citaat["bron"],
        "{{AFTEL_ISO}}": gegevens["aftel_tot"] or "",
        "{{AFTEL_TEKST}}": inst["aftel_tekst"],
        "{{AFTEL_VERSTREKEN}}": inst["aftel_verstreken"],
        "{{BIJGEWERKT_TEKST}}": gegevens["bijgewerkt_tekst"],
        "{{BIJGEWERKT_ISO}}": gegevens["bijgewerkt"],
        "{{VERVERS_MINUTEN}}": str(inst["ververs_minuten"]),
        "{{VEROUDERD_NA_UUR}}": str(inst["verouderd_na_uur"]),
        "{{TAAKNAAM}}": inst["taaknaam"],
    }
    for sleutel, waarde in vervangingen.items():
        html = html.replace(sleutel, ontsmet(waarde))
    (SITE_MAP / "index.html").write_text(html, encoding="utf-8")
    (SITE_MAP / ".nojekyll").write_text("", encoding="utf-8")


# --------------------------------------------------------------------------- #
def main() -> None:
    if not API_KEY:
        sys.exit("FOUT: omgevingsvariabele ADMINPULSE_API_KEY ontbreekt.")

    inst = lees_instellingen()
    periode = "alle deadlines"
    if inst["deadline_van"] or inst["deadline_tot"]:
        periode = (f"deadline van {inst['deadline_van'].strftime('%d/%m/%Y') if inst['deadline_van'] else '...'}"
                   f" tot {inst['deadline_tot'].strftime('%d/%m/%Y') if inst['deadline_tot'] else '...'}")
    print(f"Filter: taak '{inst['taaknaam']}' ({inst['vergelijking']}), "
          f"referentiejaar {inst['referentiejaar'] or 'alle'}, {periode}")
    print(f"Ophalen bij AdminPulse: deadline vanaf {api_datum(inst['api_vanaf']) or 'geen grens'} "
          f"tot {api_datum(inst['api_tot']) or 'geen grens'}")

    print("Taken ophalen uit AdminPulse ...")
    taken = haal_alle_taken(inst)
    print(f"{len(taken)} hoofdtaken opgehaald.")

    telling = tel(taken, inst)
    nu = datetime.now(timezone.utc)

    print(f"\nRESULTAAT: {telling['aantal_open']} nog niet neergelegd, "
          f"{telling['aantal_afgewerkt']} afgewerkt.")
    print(f"  per status: {telling['per_status']}")
    print(f"  open per referentiejaar: {telling['per_jaar']}")
    if telling["buiten_periode"]:
        print(f"  niet meegeteld omdat de deadline buiten de periode valt: {telling['buiten_periode']}")

    if telling["aantal_open"] + telling["aantal_afgewerkt"] == 0:
        print("\nFOUT: geen enkele taak past bij de ingestelde filter, dus de pagina wordt "
              "niet overschreven. Dit zijn de subtaaknamen die wél voorkomen (met aantal):")
        for naam, n in sorted(telling["gezien_namen"].items(), key=lambda x: -x[1])[:60]:
            print(f"    {n:5d}  {naam}")
        sys.exit("Pas 'taaknaam' in config.ini aan (of zet 'vergelijking = bevat'), "
                 "of verruim de periode ('deadline_van', 'deadline_tot', 'ophalen_vanaf').")

    veranderd = bewaar_geschiedenis(telling, nu)
    citaat = kies_citaat(telling, inst)
    schrijf_uitvoer(telling, inst, citaat, nu)
    print(f"\nQuote van dienst: \"{citaat['tekst']}\"")
    print(f"Pagina geschreven naar {SITE_MAP / 'index.html'}"
          + (" — geschiedenis.csv bijgewerkt." if veranderd else " — cijfer ongewijzigd."))


if __name__ == "__main__":
    main()
