# VL-Kalender

Wandelt das Programm des VL (Ludwigstraße 37, Halle/Saale) von
https://www.ludwigstrasse37.de/ einmal pro Woche in einen abonnierbaren
Kalender um: `docs/vl.ics`. Enthalten ist alles außer KüfA und Plenum.

- Skript: `vl_ics.py` (nur Python-Standardbibliothek)
- Zeitplan: `.github/workflows/vl-kalender.yml`, montags früh, plus Handstart
- Findet das Skript keine datierten Termine (Seite umgebaut), bricht es ab,
  die alte Datei bleibt stehen und GitHub schickt eine Fehlermail.

Nur öffentliche Programmdaten des VL, keine persönlichen Daten.
