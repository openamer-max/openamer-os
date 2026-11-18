# 20 Etappen zum Modell, das alles kann

Ein Modell soll Text, Vision, Denken, Werkzeuge, Entscheidungen und Fähigkeiten
abdecken; Einbetten kommt aus einem eigenen Modell (technisch nicht anders möglich).
Jede Etappe hat **eine** messbare Schranke. Ohne grüne Schranke beginnt die nächste
nicht — sonst weiß am Ende niemand, welche Stufe das Ergebnis verbessert hat.

**Regel für alle Etappen:** gemessen wird auf den eingefrorenen Sätzen
(`testset_tasks.json` 24 Fälle, `testset_vision.json` 10 Fälle) mit `--repeat 4`.
Eine einzelne Zahl ist kein Ergebnis.

| # | Etappe | Was entsteht | Schranke (muss grün sein) | Rechner |
|---|---|---|---|---|
| 1 | Datenbasis | `max_full_sft.jsonl` aus Grundsatz + Werkzeug + Denk + Bild | 4 Schranken in `tools/build_dataset.py`: Kontamination 0, Prüfwerte 0, Struktur 0, Abdeckung erfüllt | lokal |
| 2 | Pipeline-Beweis | QLoRA-Smoke (25 Schritte, Bilder zuerst) | `report.json` vorhanden, Vision-Beispiel gelesen (≥1 Patch), kein Absturz | Kaggle T4 |
| 3 | Text-Basis | Lauf über Text-Zeilen | 24 Fälle ≥ Ausgangswert (19/24) | Kaggle |
| 4 | Werkzeug-Spuren | 35 `tool_calls`-Zeilen im Training | Modell gibt bei 10 Werkzeug-Fragen das Format `Werkzeug/Eingabe/Ergebnis/Antwort` aus (≥8/10) | Kaggle |
| 5 | Entscheidungen | 25 Entscheidungs-Zeilen | bei 10 Grenz-Fällen (löschen, senden, deployen) fragt es nach oder lehnt ab (≥9/10) | Kaggle |
| 6 | Formtreue | kurze Antworten | „Antworte in einem Wort/Satz" wird eingehalten (≥8/10) | Kaggle |
| 7 | Bild-Lesen | 40 gerenderte Konsolen-Abbilder | 10 Vision-Fälle: ≥7/10 (Ausgangswert des 3B war 7/10) | Kaggle |
| 8 | Bild-Ausbau | 200+ Abbilder (mehr Schriftgrößen, Fehlercodes, Tabellen) | ≥8/10 auf dem Prüfsatz, kein Rückgang bei Text | Kaggle |
| 9 | Echte Screenshots | Desktop-/TUI-/Browser-Aufnahmen | ≥8/10, zusätzlich 10 neue eigene Aufnahmen | Kaggle |
| 10 | Gemischte Batches | Text + Bild in einem Schritt | `pixel_values` = Summe der Patches, `grid_thw` = Anzahl Bilder (Test `collate_batch`) | lokal |
| 11 | Denk-Spuren | 14 → 150 gerechnete Spuren | 10 Rechen-/Logikfälle: ≥9 richtig **mit** nachvollziehbaren Zwischenschritten | Kaggle |
| 12 | Denken ohne Schaden | Denk-Modus vs. direkt | Faktenantworten dürfen nicht schlechter werden (≥ Ausgang) | Kaggle |
| 13 | Denken messbar | Gedankenlänge | mittlere Antwortlänge steigt, Trefferquote steigt ebenfalls — sonst Denken abschalten | Kaggle |
| 14 | Fähigkeiten | 328 Skills als Kurztexte | „welcher Skill für X" trifft 8/10 | Kaggle |
| 15 | Sprache | Deutsch + Bosnisch/Kroatisch/Serbisch | je 5 Fragen in beiden Sprachen korrekt | Kaggle |
| 16 | Werkzeug-Entscheidung | Werkzeug ja/nein | 10 Fälle: richtig entschieden (kein Werkzeug, wenn unnötig) ≥9/10 | Kaggle |
| 17 | Einbetten (getrennt) | `Qwen3-Embedding-0.6B` + Hybrid-RAG | Top-1 ≥ 14/16 auf den Umschreibungen (Ist: 14/16, BM25 allein 9/16) | lokal |
| 18 | RAG im Alltag | Fakten aus dem RAG statt aus Gewichten | 10 Faktenfragen: richtig **mit** Belegstelle | lokal |
| 19 | Zusammenführen | GGUF aus Basis + Adapter | Datei lädt in Ollama, antwortet auf 5 Fragen, `sha256` dokumentiert | lokal/Kaggle |
| 20 | Abschluss und Veröffentlichung | Vergleich alt gegen neu | **jede** der sieben Fähigkeiten ≥ Ausgangswert, mindestens drei messbar besser — sonst bleibt der alte Stand online | Kaggle |

## Was „1 Mio. Parameter" bedeutet — jetzt mit echtem Modell gemessen

Ein Modell mit **999.232 Parametern** wurde gebaut, trainiert und gegen denselben
Prüfsatz gestellt (`model/tiny-1m/`, 43 s CPU, reproduzierbar):

| Kennzahl | 1M-Modell | 8B-VL-Basis |
|---|---|---|
| Prüfsatz 24 Fälle | **5/24 (21 %)** | **19/24 (79 %)** |
| davon echte Treffer | 0 — Korpusfetzen mit Zufallswort | 19 |
| Vision / Werkzeuge / Denken | **nicht möglich** | vorhanden bzw. im Training |
| Val-Perplexity | 14,8 (Zufall 256) | – |

| Größe | Wert |
|---|---|
| 1 Mio. Parameter in fp16 | 2 MB |
| Einbettungstabelle allein (151.936 × 3.584) | 545 Mio. = **545×** |
| kleinstes brauchbares Bildmodell (`SmolVLM-256M`) | 256 Mio. = **256×** |
| kleinste eigene Stufe (`openamer-max-watch`) | 596 Mio. = **596×** |

Damit ist die Frage nicht mehr theoretisch: 1 Mio. Parameter lernen
Zeichenstatistik (Perplexity 14,8 gegen 256 Zufall), aber keine der sieben
Fähigkeiten. „1M" ist realistisch als **1 Mio. Token Kontext**
(`Qwen2.5-7B-Instruct-1M` existiert) oder als **1 Mrd. Parameter** (Text-only).

## Takt

Etappen 1–6 sind heute/morgen erreichbar (Text, Werkzeuge, Entscheidungen).
7–13 brauchen je einen Kaggle-Lauf (Gratis-GPU, 9 h Sitzung). 14–18 sind Daten- und
Verdrahtungsarbeit ohne GPU. 19–20 erst, wenn 1–13 stabil grün sind.

**Nicht verhandelbar:** keine Veröffentlichung vor Etappe 20. Ein Modell, das auf
keinem Satz gemessen wurde, wird nicht ausgeliefert.
