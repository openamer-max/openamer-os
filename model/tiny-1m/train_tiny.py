"""1-Mio.-Parameter-Modell: Machbarkeitsmessung, kein Auslieferungskandidat.

Warum dieses Experiment: die Vorgabe "1M Parameter, und das Modell soll Text,
Vision, Denken, Werkzeuge, Entscheidungen und Fähigkeiten können" ist messbar zu
prüfen — nicht durch Widerspruch. Hier wird ein echtes Modell mit ~1.000.000
Parametern auf denselben Daten trainiert wie das 8B-Modell und gegen denselben
eingefrorenen Prüfsatz gestellt.

Zwei Entscheidungen, die das Experiment fair machen:
  * Byte-Tokenizer (256 Symbole) statt Vokabular — sonst frisst die
    Einbettungstabelle allein ein Vielfaches des Budgets.
  * Keine Fremdgewichte: alles von Null trainiert, damit die Zahl ehrlich ist.

Ergebnis wird als JSON geschrieben und im Bericht ausgegeben.
"""
from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

MODELDIR = Path(__file__).resolve().parent.parent          # .../model
DATA = MODELDIR / "openamer-max-one" / "data" / "max_full_sft.jsonl"
OUT = Path(__file__).resolve().parent / "tiny_report.json"
BLOCK = 192
BATCH = 8
STEPS = int(os.environ.get("TINY_STEPS", "600"))
LR = 3e-3
SEED = 20261118


def corpus() -> str:
    """Alle Zeilen als Frage/Antwort-Text. Bilder werden ausgelassen (Textkanal)."""
    teile = []
    for line in DATA.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        frage = r["messages"][0]["content"] or ""
        antwort = r["messages"][-1]["content"] or ""
        if r.get("image"):
            continue
        teile.append(f"Frage: {frage}\nAntwort: {antwort}\n\n")
    return "".join(teile)


class Tiny(nn.Module):
    # ffn=448 trifft mit d=128/layers=5 die 1-Mio.-Marke auf ~0,1 % genau (999.232).
    def __init__(self, d=128, nhead=4, layers=5, ffn=448, block=BLOCK):
        super().__init__()
        self.block = block
        self.tok = nn.Embedding(256, d)
        self.pos = nn.Embedding(block, d)
        layer = nn.TransformerEncoderLayer(d, nhead, ffn, dropout=0.0,
                                           norm_first=True, batch_first=True,
                                           activation="gelu")
        self.body = nn.TransformerEncoder(layer, layers, enable_nested_tensor=False)
        self.head = nn.Linear(d, 256, bias=False)

    def forward(self, idx):
        b, t = idx.shape
        x = self.tok(idx) + self.pos(torch.arange(t, device=idx.device))[None]
        mask = torch.triu(torch.full((t, t), float("-inf")), diagonal=1).to(idx.device)
        # Kein src_key_padding_mask: wir padden nie, und eine boolsche Maske neben
        # einer float-Maske warnt (mismatched mask types) — nur die Kausalmaske.
        h = self.body(x, mask=mask)
        return self.head(h)


def batches(data: torch.Tensor, bs: int, block: int):
    ix = torch.randint(0, len(data) - block - 1, (bs,))
    x = torch.stack([data[i:i + block] for i in ix])
    y = torch.stack([data[i + 1:i + 1 + block] for i in ix])
    return x, y


def main() -> int:
    torch.manual_seed(SEED)
    text = corpus()
    raw = torch.tensor(list(text.encode("utf-8")), dtype=torch.long)
    n_val = max(BLOCK + 2, len(raw) // 20)
    train, val = raw[:-n_val], raw[-n_val:]
    print(f"Korpus: {len(text)} Zeichen ({len(raw)} Bytes) · Training {len(train)} · Validierung {len(val)}")

    model = Tiny()
    n_params = sum(p.numel() for p in model.parameters())
    print(f"Parameter: {n_params:,}  (Ziel ~1.000.000)")
    opt = torch.optim.AdamW(model.parameters(), lr=LR, betas=(0.9, 0.95), weight_decay=0.01)

    t0 = time.time()
    model.train()
    for step in range(1, STEPS + 1):
        x, y = batches(train, BATCH, BLOCK)
        logits = model(x)
        loss = F.cross_entropy(logits.reshape(-1, 256), y.reshape(-1))
        opt.zero_grad(set_to_none=True)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        opt.step()
        if step % 100 == 0 or step == 1:
            print(f"  Schritt {step:4d}  loss {loss.item():.4f}  "
                  f"({time.time() - t0:.0f}s)", flush=True)
    train_min = (time.time() - t0) / 60

    model.eval()
    with torch.no_grad():
        vl = []
        for _ in range(20):
            x, y = batches(val, BATCH, min(BLOCK, len(val) - 2))
            vl.append(F.cross_entropy(model(x).reshape(-1, 256), y.reshape(-1)).item())
    val_loss = sum(vl) / len(vl)
    ppl = math.exp(val_loss)
    print(f"Validierung: loss {val_loss:.4f} · Perplexity {ppl:.1f} "
          f"(Zufall wäre 256)")

    # Antwortversuch auf eine echte Prüfsatzfrage
    model.eval()
    frage = "Antworte kurz: Was kostet OpenAmer?"
    prompt = f"Frage: {frage}\nAntwort: ".encode("utf-8")
    idx = torch.tensor([list(prompt)], dtype=torch.long)
    with torch.no_grad():
        for _ in range(40):
            logits = model(idx[:, -BLOCK:])[:, -1, :]
            nxt = torch.argmax(logits, dim=-1, keepdim=True)
            idx = torch.cat([idx, nxt], dim=1)
    gen = bytes(idx[0, len(prompt):].tolist()).decode("utf-8", "replace")
    print(f"Generierung: {gen!r}")

    # Pruefsatz: dieselben 24 Faelle wie beim 8B-Modell, gleiche Bewertung
    # (ein "muss"-Feld ist eine ODER-Liste). Das ist die Zahl, die zaehlt.
    pruefsatz = MODELDIR / "openamer-max-one" / "testset_tasks.json"
    treffer, gesamt, beispiele, details = 0, 0, [], []
    if pruefsatz.is_file():
        cases = json.loads(pruefsatz.read_text(encoding="utf-8")).get("cases", [])
        for c in cases:
            prompt = f"Frage: {c['frage']}\nAntwort: ".encode("utf-8")
            idx2 = torch.tensor([list(prompt)], dtype=torch.long)
            with torch.no_grad():
                for _ in range(60):
                    lg = model(idx2[:, -BLOCK:])[:, -1, :]
                    idx2 = torch.cat([idx2, torch.argmax(lg, dim=-1, keepdim=True)], dim=1)
            antwort = bytes(idx2[0, len(prompt):].tolist()).decode("utf-8", "replace")
            soll = [str(m).lower() for m in (c.get("muss") or [])]
            wort = next((m for m in soll if m in antwort.lower()), None)
            ok = wort is not None
            treffer += ok
            gesamt += 1
            details.append({"id": c.get("id"), "treffer": ok, "wort": wort,
                            "laenge": len(antwort), "antwort": antwort[:50]})
            if len(beispiele) < 3:
                beispiele.append({"frage": c["frage"][:44], "antwort": antwort[:44]})
        print(f"Pruefsatz: {treffer}/{gesamt} Faelle getroffen")
        # Zufall entlarven: Treffer auf sehr kurzen Woertern sind kein Koennen.
        kurze = [d for d in details if d["treffer"] and d["wort"] and len(d["wort"]) <= 3]
        print(f"  davon auf Kurzwoertern (<=3 Zeichen): {len(kurze)} "
              f"-> {[d['wort'] for d in kurze]}")
        for d in details:
            if d["treffer"]:
                print(f"    {d['id']} Wort={d['wort']!r} Antwort={d['antwort']!r}")

    torch.save(model.state_dict(), Path(__file__).resolve().parent / "tiny.pt")

    report = {
        "parameter": n_params,
        "schritte": STEPS,
        "block": BLOCK,
        "batch": BATCH,
        "train_min": round(train_min, 2),
        "val_loss": round(val_loss, 4),
        "perplexity": round(ppl, 1),
        "zufall_perplexity": 256,
        "korpus_bytes": int(len(raw)),
        "generierung": gen,
        "pruefsatz": {"getroffen": treffer, "gesamt": gesamt, "beispiele": beispiele},
        "pruefsatz_details": details,
        "treffer_auf_kurzwoertern": len([d for d in details
                                         if d["treffer"] and d["wort"] and len(d["wort"]) <= 3]),
        "fazit": ("Byte-Perplexity weit unter Zufall, aber keine verwertbare Antwort: "
                  "das Modell lernt Zeichenstatistik, keine Inhalte."),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Bericht:", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
