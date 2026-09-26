#!/usr/bin/env python3
"""VL Ludwigstrasse 37 (Halle/Saale) -> Kalenderabo (iCalendar, .ics).

Liest das Programm von https://www.ludwigstrasse37.de/ und schreibt eine
.ics-Datei mit allen Terminen ausser KueFA, Plenum und Rote Hilfe. Nur Standardbibliothek.

Aufruf:   python vl_ics.py [ziel.ics] [--html seite.html]
Standard: docs/vl.ics, Seite live aus dem Netz.
Exit 1, wenn keine datierten Termine gefunden werden (Seite umgebaut?):
dann bleibt die alte Datei unangetastet und GitHub meldet den Fehlschlag.
"""
import argparse
import hashlib
import html
import re
import sys
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

QUELLE = "https://www.ludwigstrasse37.de/"
ORT = "VL, Ludwigstraße 37, 06110 Halle (Saale)"
PRAEFIX = "VL: "
AUSSCHLUSS = re.compile(r"k[üu]fa|plenum|roten?\s+hilfe", re.I)
DAUER = timedelta(hours=3)
TZID = "Europe/Berlin"
WOCHENTAGE = {"montag": 0, "dienstag": 1, "mittwoch": 2, "donnerstag": 3,
              "freitag": 4, "samstag": 5, "sonntag": 6}
ICAL_TAG = ["MO", "TU", "WE", "TH", "FR", "SA", "SU"]

VTIMEZONE = [
    "BEGIN:VTIMEZONE", "TZID:Europe/Berlin",
    "BEGIN:DAYLIGHT", "TZOFFSETFROM:+0100", "TZOFFSETTO:+0200", "TZNAME:CEST",
    "DTSTART:19700329T020000", "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=-1SU",
    "END:DAYLIGHT",
    "BEGIN:STANDARD", "TZOFFSETFROM:+0200", "TZOFFSETTO:+0100", "TZNAME:CET",
    "DTSTART:19701025T030000", "RRULE:FREQ=YEARLY;BYMONTH=10;BYDAY=-1SU",
    "END:STANDARD", "END:VTIMEZONE",
]

WT = r"[A-Za-zÄÖÜäöü]{2}"
ZEIT = (r"(?P<h>\d{1,2})(?:[:.](?P<mi>\d{2}))?"
        r"(?:\s*[-–]\s*(?P<h2>\d{1,2})(?:[:.](?P<mi2>\d{2}))?)?"
        r"\s*Uhr(?:\s*\([^)]*\))?")
DATIERT = re.compile(
    r"^" + WT + r",?\s*(?P<d>\d{1,2})\.(?P<m>\d{1,2})\.(?P<y>\d{4})"
    r"(?:\s*(?:[-–]|bis)\s*(?:" + WT + r",?\s*)?"
    r"(?P<d2>\d{1,2})\.(?P<m2>\d{1,2})\.(?P<y2>\d{4}))?"
    r"(?:,\s*" + ZEIT + r")?\s*[-–]\s*(?P<titel>.+)$")
REGEL = re.compile(
    r"^Jeden\s+(?P<was>[^,]+),\s*" + ZEIT + r"\s*[-–]\s*(?P<titel>.+)$", re.I)
IRGENDEIN_DATUM = re.compile(r"(\d{1,2})\.(\d{1,2})\.(\d{4})")


def laden():
    req = urllib.request.Request(QUELLE, headers={"User-Agent": "vl-kalender/1.0"})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")


def klartext(s):
    s = re.sub(r"<br\s*/?>|</p>|</li>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\s*\n\s*", "\n", s)
    return s.strip()


def bloecke(seite):
    """Liefert (Ueberschrift, Text) je <h3>; auskommentierte Termine fallen weg."""
    seite = re.sub(r"<!--.*?-->", "", seite, flags=re.S)
    teile = re.split(r"(<h[1-3][^>]*>.*?</h[1-3]>)", seite, flags=re.S | re.I)
    for i, teil in enumerate(teile):
        m = re.match(r"<h3[^>]*>(.*?)</h3>", teil, re.S | re.I)
        if not m:
            continue
        kopf = " ".join(klartext(m.group(1)).split())
        rumpf = klartext(teile[i + 1]) if i + 1 < len(teile) else ""
        rumpf = rumpf.split("[nach oben]")[0]
        rumpf = rumpf.split("Änderungen im Programm vorbehalten")[0].strip()
        yield kopf, rumpf[:1500]


def zeitraum(m, tag):
    """Beginn/Ende als datetime, oder (None, None) fuer ganztaegig."""
    if not m.group("h") or int(m.group("h")) > 23:
        return None, None
    beginn = datetime.combine(tag, time(int(m.group("h")), int(m.group("mi") or 0)))
    if m.group("h2") and int(m.group("h2")) <= 23:
        ende = datetime.combine(tag, time(int(m.group("h2")), int(m.group("mi2") or 0)))
        if ende <= beginn:
            ende += timedelta(days=1)
    else:
        ende = beginn + DAUER
    return beginn, ende


def regel(was):
    """'Mittwoch' / '2. und 4. Mittwoch im Monat' / 'letzten Freitag im Monat'."""
    w = was.lower()
    tag = next((n for name, n in WOCHENTAGE.items() if name in w), None)
    if tag is None:
        return None
    if "monat" in w:
        if "letzt" in w:
            return tag, [-1]
        nr = [int(x) for x in re.findall(r"(\d)\.", w)]
        return (tag, nr) if nr else None
    return tag, []


def passt(tag_datum, tag, nr):
    if tag_datum.weekday() != tag:
        return False
    if not nr:
        return True
    n = (tag_datum.day - 1) // 7 + 1
    letzter = (tag_datum + timedelta(days=7)).month != tag_datum.month
    return n in nr or (-1 in nr and letzter)


def uid(schluessel):
    return hashlib.sha1(schluessel.encode("utf-8")).hexdigest()[:20] + "@vl-kalender"


def termine(seite, heute):
    evs, zaehler = [], {"datiert": 0, "regel": 0, "ausgeschlossen": 0, "unklar": 0}
    for kopf, rumpf in bloecke(seite):
        if AUSSCHLUSS.search(kopf):
            zaehler["ausgeschlossen"] += 1
            continue
        m = REGEL.match(kopf)
        if m:
            r = regel(m.group("was"))
            if r is None:
                zaehler["unklar"] += 1
                print(f"  unklar (Regel): {kopf}", file=sys.stderr)
                continue
            tag, nr = r
            erster = next(heute + timedelta(days=i) for i in range(70)
                          if passt(heute + timedelta(days=i), tag, nr))
            beginn, ende = zeitraum(m, erster)
            byday = ",".join(f"{n}{ICAL_TAG[tag]}" for n in nr) if nr else ICAL_TAG[tag]
            freq = "MONTHLY" if nr else "WEEKLY"
            evs.append({"uid": uid("regel|" + kopf), "titel": m.group("titel"),
                        "text": rumpf, "beginn": beginn, "ende": ende, "tag": erster,
                        "rrule": f"FREQ={freq};BYDAY={byday}"})
            zaehler["regel"] += 1
            continue
        m = DATIERT.match(kopf)
        if m:
            tag = date(int(m.group("y")), int(m.group("m")), int(m.group("d")))
            bis = (date(int(m.group("y2")), int(m.group("m2")), int(m.group("d2")))
                   if m.group("d2") else tag)
            beginn, ende = zeitraum(m, tag)
            if beginn and bis > tag:
                ende = datetime.combine(bis, beginn.time()) + DAUER
            titel = m.group("titel")
        else:
            d = IRGENDEIN_DATUM.search(kopf)
            if not d:
                zaehler["unklar"] += 1
                print(f"  unklar (ohne Datum): {kopf}", file=sys.stderr)
                continue
            tag = bis = date(int(d.group(3)), int(d.group(2)), int(d.group(1)))
            beginn = ende = None
            titel = kopf
            print(f"  Format unbekannt, ganztaegig uebernommen: {kopf}", file=sys.stderr)
        evs.append({"uid": uid(f"{tag.isoformat()}|{titel}"), "titel": titel,
                    "text": rumpf, "beginn": beginn, "ende": ende, "tag": tag,
                    "bis": bis, "rrule": None})
        zaehler["datiert"] += 1
    return evs, zaehler


def esc(s):
    return (s.replace("\\", "\\\\").replace(";", "\\;")
             .replace(",", "\\,").replace("\n", "\\n"))


def falten(zeile):
    """RFC 5545: max. 75 Byte je Zeile, Folgezeilen beginnen mit Leerzeichen."""
    teile, akt, laenge, grenze = [], "", 0, 75
    for ch in zeile:
        n = len(ch.encode("utf-8"))
        if laenge + n > grenze:
            teile.append(akt)
            akt, laenge, grenze = ch, n, 74
        else:
            akt += ch
            laenge += n
    teile.append(akt)
    return [teile[0]] + [" " + t for t in teile[1:]]


def ics(evs):
    stempel = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    z = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//vl-kalender//DE",
         "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:VL Halle",
         "X-WR-CALDESC:" + esc("Programm VL Ludwigstraße 37, Halle (Saale) - "
                               "ohne KüfA, Plenum und Rote Hilfe. Quelle: " + QUELLE),
         "X-WR-TIMEZONE:" + TZID, "REFRESH-INTERVAL;VALUE=DURATION:P1D",
         "X-PUBLISHED-TTL:P1D"] + VTIMEZONE
    for e in evs:
        z += ["BEGIN:VEVENT", "UID:" + e["uid"], "DTSTAMP:" + stempel]
        if e["beginn"]:
            z.append(f"DTSTART;TZID={TZID}:" + e["beginn"].strftime("%Y%m%dT%H%M%S"))
            z.append(f"DTEND;TZID={TZID}:" + e["ende"].strftime("%Y%m%dT%H%M%S"))
        else:
            bis = e.get("bis") or e["tag"]
            z.append("DTSTART;VALUE=DATE:" + e["tag"].strftime("%Y%m%d"))
            z.append("DTEND;VALUE=DATE:" + (bis + timedelta(days=1)).strftime("%Y%m%d"))
        if e["rrule"]:
            z.append("RRULE:" + e["rrule"])
        text = (e["text"] + "\n\n" if e["text"] else "") + "Quelle: " + QUELLE
        z += ["SUMMARY:" + esc(PRAEFIX + e["titel"]), "LOCATION:" + esc(ORT),
              "DESCRIPTION:" + esc(text), "URL:" + QUELLE, "END:VEVENT"]
    z.append("END:VCALENDAR")
    return "".join(teil + "\r\n" for zeile in z for teil in falten(zeile))


def pruefen(pfad):
    roh = pfad.read_bytes()
    zeilen = roh.split(b"\r\n")
    assert roh.endswith(b"\r\n"), "Datei endet nicht mit CRLF"
    assert max(len(x) for x in zeilen) <= 75, "Zeile laenger als 75 Byte"
    assert roh.count(b"BEGIN:VEVENT") == roh.count(b"END:VEVENT"), "VEVENT unbalanciert"
    assert b"\n" not in roh.replace(b"\r\n", b""), "nacktes LF in der Datei"
    return roh.count(b"BEGIN:VEVENT")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("ziel", nargs="?", default="docs/vl.ics")
    ap.add_argument("--html", help="lokale HTML-Datei statt Abruf (Test)")
    a = ap.parse_args()
    seite = (Path(a.html).read_bytes().decode("utf-8", "replace")
             if a.html else laden())
    evs, zaehler = termine(seite, date.today())
    print("Zaehlung:", zaehler)
    if zaehler["datiert"] == 0:
        print("FEHLER: keine datierten Termine gefunden - Seite umgebaut? "
              "Alte Datei bleibt stehen.", file=sys.stderr)
        return 1
    ziel = Path(a.ziel)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(ics(evs).encode("utf-8"))
    n = pruefen(ziel)
    for e in evs:
        wann = e["beginn"].strftime("%a %d.%m.%Y %H:%M") if e["beginn"] else \
            e["tag"].strftime("%a %d.%m.%Y ganztaegig")
        print(f"  {wann}  {e['titel'][:70]}" + (f"  [{e['rrule']}]" if e["rrule"] else ""))
    print(f"OK: {n} Termine -> {ziel} ({ziel.stat().st_size} Byte)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
