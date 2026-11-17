# Dokumentation — Index

| Datei | Inhalt |
|---|---|
| `../README.md` | Projektübersicht, vier Ebenen, Messwerte, offene Punkte |
| `../START.md` | Startanleitung, Fehlerbehebung, was noch fehlt |
| `../ARCHITEKTUR.md` | Aufbau, Datenfluss, Sicherheitsentscheidungen, Messregeln |
| `../CHANGELOG.md` | Änderungen mit Datum und gemessenen Werten |
| `../NOTICE` | Lizenzschichten (Upstream, eigene Teile, Gewichte, Firmware) |
| `MESSUNGEN.md` | alle Messreihen mit Streuung und Aussagekraft |

## Die Messregeln in Kurzform

1. **Erst messen, dann ändern.** `verify.py` vor und nach jeder Änderung.
2. **Wiederholen.** Temperatur 0 ist nicht deterministisch: dasselbe Modell
   lieferte 22/24 und 20/24. Vergleiche nur mit `--repeat 4`.
3. **Messfehler ≠ Modellfehler.** Fehlendes Modell, HTTP-Fehler, leere Antwort
   → `error`, nicht `fail`. Bericht `valid: false`.
4. **Erst den Prüfer prüfen.** Ein `muss`-Feld ist eine ODER-Liste; fehlt ein
   Synonym, wird eine richtige Antwort als falsch gewertet.
5. **Nichts als Erfolg melden, was nicht im Log steht.** Ein Timeout ist kein
   Erfolg; gewertet wird der Marker.
