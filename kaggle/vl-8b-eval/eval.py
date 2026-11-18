"""Etappe 3+7: Adapter messen — 24 Textfaelle und 10 Bildfaelle.

Laeuft als Kaggle-Kernel, weil der Adapter aus dem Trainings-Kernel eingebunden
wird (kernel_sources) und die Basis auf der Gratis-GPU liegt. Lokal waeren 17 GB
Download und 4-Bit-Quantisierung auf 8 GB VRAM noetig — hier ist beides schon da.

Bewertung wie im Projekt ueblich: ein "muss"-Feld ist eine ODER-Liste; getroffen
heisst, mindestens ein Eintrag steht in der Antwort. Zusaetzlich wird die
Antwortlaenge protokolliert, weil "richtig durch Zufall" sonst unsichtbar bleibt.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import zipfile
import urllib.request
from pathlib import Path

WORK = Path("/kaggle/working") if Path("/kaggle").exists() else Path.home() / "omx-eval"
WORK.mkdir(parents=True, exist_ok=True)
OUT = WORK / "results.json"
ZIP_URL = "https://api.github.com/repos/openamer-max/openamer-os/zipball/main"
BASE_NAME = "max_full_sft.jsonl"
MODEL_ID = "Qwen/Qwen3-VL-8B-Instruct"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def deps() -> None:
    log("Installiere Bibliotheken ...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-U",
                    "transformers>=4.57.0", "accelerate", "peft", "bitsandbytes",
                    "pillow", "torchvision"], check=True)


def fetch_repo() -> Path:
    root = WORK / "src"
    if not any(root.glob(f"*/model/openamer-max-one/data/{BASE_NAME}")):
        zp = WORK / "repo.zip"
        log("Lade Repo-Archiv ...")
        req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "openamer-eval"})
        with urllib.request.urlopen(req, timeout=300) as r, open(zp, "wb") as f:
            f.write(r.read())
        with zipfile.ZipFile(zp) as z:
            z.extractall(root)
    hits = list(root.glob(f"*/model/openamer-max-one/data/{BASE_NAME}"))
    if not hits:
        raise FileNotFoundError("Repo-Archiv ohne Datensatz")
    return hits[0].parent.parent


def find_adapter() -> Path | None:
    """Adapter aus dem eingebundenen Trainings-Kernel (/kaggle/input/...)."""
    for p in Path("/kaggle/input").rglob("adapter_config.json"):
        log(f"Adapter gefunden: {p.parent}")
        return p.parent
    return None


def passe(antwort: str, muss: list) -> tuple[bool, str | None]:
    """Projektbewertung: ein "muss"-Feld ist eine ODER-Liste, Gross/Klein egal.

    Modul-Ebene statt in main(), damit die Bewertung ohne GPU pruefbar ist —
    eine Bewertung, die nur im Kernel laeuft, kann still falsch sein.
    """
    a = (antwort or "").lower()
    for w in muss or []:
        if str(w).strip().lower() in a:
            return True, str(w)
    return False, None


def systemprompt(base: Path) -> str:
    """Systemprompt aus dem 7B-Modelfile — Quelle statt Kopie.

    Ohne diesen Prompt ist der Vergleich unfair: das 7B wird im Betrieb mit
    "Du bist OpenAmer ..." gestartet, eine Messung ohne Prompt antwortet anders
    (am 19.11.2026 als Verdacht aufgefallen, nachdem 14/24 gegen 22/24 stand).
    """
    p = base / "Modelfile.max-7b"
    if not p.is_file():
        log("kein Modelfile.max-7b — Messung ohne Systemprompt")
        return ""
    t = p.read_text(encoding="utf-8", errors="replace")
    m = re.search(r'SYSTEM\s+"""(.*?)"""', t, re.S)
    return m.group(1).strip() if m else ""


def bildpfad(base: Path, wert: str) -> Path | None:
    """Bildpfade im Pruefsatz sind relativ zum REPO-HAUPTORDNER, nicht zum Modell.

    Vorher wurde nur base/<pfad> geprueft -> 0/0 Bildfaelle "gemessen"
    (Fund 19.11.2026).
    """
    for kand in (base, base.parent, base.parent.parent):
        p = kand / wert
        if p.is_file():
            return p
    return None


def main() -> int:
    t0 = time.time()
    deps()
    base = fetch_repo()
    adapter = find_adapter()
    log(f"Adapter: {adapter or 'KEINER — Auswertung der Basis ohne Adapter'}")

    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoProcessor, BitsAndBytesConfig
    from PIL import Image

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID, quantization_config=bnb, device_map={"": 0}, torch_dtype=dtype,
        trust_remote_code=True)
    if adapter:
        model = PeftModel.from_pretrained(model, str(adapter))
        log("Adapter geladen")
    model = model.merge_and_unload() if hasattr(model, "merge_and_unload") and adapter else model
    model.eval()
    proc = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    sys_prompt = systemprompt(base)
    log(f"Systemprompt: {len(sys_prompt)} Zeichen" if sys_prompt else "Systemprompt: keiner")

    @torch.no_grad()
    def frage(frage_text: str, bild: Path | None, max_neu: int = 96) -> str:
        inhalt = ([{"type": "image"}] if bild else []) + [{"type": "text", "text": frage_text}]
        msgs = ([{"role": "system", "content": sys_prompt}] if sys_prompt else []) \
            + [{"role": "user", "content": inhalt}]
        prompt = proc.apply_chat_template(msgs,
                                          tokenize=False, add_generation_prompt=True)
        imgs = [Image.open(bild).convert("RGB")] if bild else None
        enc = proc(text=[prompt], images=imgs, return_tensors="pt").to(0)
        ids = model.generate(**enc, max_new_tokens=max_neu, do_sample=False,
                             temperature=None, top_p=None)
        neu = ids[0][enc["input_ids"].shape[1]:]
        return proc.tokenizer.decode(neu, skip_special_tokens=True).strip()

    ergebnis = {"modell": MODEL_ID, "adapter": str(adapter) if adapter else None,
                "pruefungen": {}}

    for name, datei, bild_spalte in (("text", "testset_tasks.json", None),
                                     ("vision", "testset_vision.json", "bild")):
        p = base / datei
        if not p.is_file():
            log(f"{datei} fehlt — uebersprungen")
            continue
        cases = json.loads(p.read_text(encoding="utf-8"))["cases"]
        treffer, details = 0, []
        for c in cases:
            zeig = bildpfad(base, c[bild_spalte]) if bild_spalte and c.get(bild_spalte) else None
            if bild_spalte and zeig is None:
                log(f"  {name} {c.get('id')}: Bild fehlt ({c.get(bild_spalte)})")
                continue
            try:
                antwort = frage(c["frage"], zeig)
            except Exception as exc:
                antwort = f"FEHLER {type(exc).__name__}: {exc}"
            ok, wort = passe(antwort, c.get("muss") or [])
            treffer += ok
            details.append({"id": c.get("id"), "treffer": ok, "wort": wort,
                            "laenge": len(antwort), "antwort": antwort[:200]})
            log(f"  {name} {c.get('id')}: {'OK' if ok else '--'} {wort or ''} "
                f"({len(antwort)} Zeichen)")
        ergebnis["pruefungen"][name] = {"getroffen": treffer, "gesamt": len(details),
                                        "details": details}
        log(f"{name}: {treffer}/{len(details)}")

    ergebnis["dauer_min"] = round((time.time() - t0) / 60, 1)
    ergebnis["vram_spitze_gib"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
    OUT.write_text(json.dumps(ergebnis, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"Bericht: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
