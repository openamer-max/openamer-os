"""OpenAmer-Max VL-8B — QLoRA-Training (Kaggle, Gratis-GPU).

Ziel: Qwen3-VL-8B-Instruct (Text + Vision + Denken + Werkzeuge in einer Basis)
mit eigenen Daten nachtrainieren. Dieser Lauf ist ein **Smoke-Test**: wenige
Schritte, volle Pipeline, damit ein Formatfehler nicht 9 GPU-Stunden kostet.

Robustheitsregeln:
  * Jeder Abschnitt in try/except und mit Ausgabe — ein Absturz soll lesbar sein.
  * Vision-Zeilen werden versucht; scheitert die Bildaufbereitung, laeuft der Lauf
    text-only weiter und sagt das.
  * Kein lokaler Pfad: Daten und Bilder kommen aus dem GitHub-Archiv (ein Request).

DRY_RUN=1 baut nur Beispiele und beendet sich (lokal testbar ohne GPU).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback
import urllib.request
import zipfile
from pathlib import Path

REPO = "openamer-max/openamer-os"
ZIP_URL = f"https://api.github.com/repos/{REPO}/zipball/main"
WORK = Path("/kaggle/working") if Path("/kaggle").is_dir() else Path.home() / "omx-work"
BASE_NAME = "max_full_sft.jsonl"
MODEL_ID = os.environ.get("OM_BASE", "Qwen/Qwen3-VL-8B-Instruct")
MAX_STEPS = int(os.environ.get("OM_STEPS", "25"))
EPOCHS = float(os.environ.get("OM_EPOCHS", "0"))
SEQ = int(os.environ.get("OM_SEQ", "1024"))
# Smoke-Laeufe sollen den Bild-Pfad GARANTIERT treffen, nicht zufaellig: mit
# 40 Bild-Zeilen in 682 Beispielen und 25 Schritten kann ein Lauf sonst ohne
# ein einziges Bild durchlaufen und den Vision-Fehler erst spaeter zeigen.
VISION_FIRST = os.environ.get("OM_VISION_FIRST", "0") == "1"
DRY = os.environ.get("DRY_RUN") == "1"


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(cmd: str) -> None:
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    out = (p.stdout or "").strip().splitlines()
    print("\n".join(out[-6:]), flush=True)
    if p.returncode != 0:
        print("FEHLER:", (p.stderr or "").strip()[-500:], flush=True)


# ---------------------------------------------------------------- 1. Umgebung
def deps() -> None:
    log("Installiere Bibliotheken ...")
    # torchvision ist Pflicht: Qwen3VLVideoProcessor wirft sonst ImportError
    # ("requires the Torchvision library") — im Dry-Run am 18.11.2026 aufgefallen.
    sh(f"{sys.executable} -m pip install -q -U 'transformers>=4.57.0' accelerate peft "
       f"bitsandbytes pillow torchvision")
    import torch, transformers
    log(f"torch {torch.__version__} · CUDA {torch.version.cuda} · "
        f"verfuegbar={torch.cuda.is_available()}")
    log(f"transformers {transformers.__version__}")
    if torch.cuda.is_available():
        p = torch.cuda.get_device_properties(0)
        log(f"GPU: {p.name} · {p.total_memory/2**30:.1f} GiB · bf16={torch.cuda.is_bf16_supported()}")


# ---------------------------------------------------------------- 2. Daten
def fetch_repo() -> Path:
    WORK.mkdir(parents=True, exist_ok=True)
    zp = WORK / "repo.zip"
    if not zp.is_file() or zp.stat().st_size < 1_000_000:
        log("Lade Repository-Archiv (Daten + Bilder) ...")
        req = urllib.request.Request(ZIP_URL, headers={"User-Agent": "openamer-kaggle"})
        with urllib.request.urlopen(req, timeout=300) as r, open(zp, "wb") as f:
            f.write(r.read())
    log(f"Archiv: {zp.stat().st_size/1e6:.1f} MB")
    root = WORK / "src"
    if not root.is_dir():
        with zipfile.ZipFile(zp) as z:
            z.extractall(root)
    hits = list(root.glob(f"*/model/openamer-max-one/data/{BASE_NAME}"))
    if not hits:
        raise FileNotFoundError(f"{BASE_NAME} nicht im Archiv")
    return hits[0].parent.parent          # .../model/openamer-max-one


def load_rows(base: Path) -> tuple[list[dict], dict]:
    rows = []
    for line in (base / "data" / BASE_NAME).read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    kinds: dict[str, int] = {}
    for r in rows:
        kinds[r.get("kind", "?")] = kinds.get(r.get("kind", "?"), 0) + 1
    log(f"Datensatz: {len(rows)} Zeilen · {len(kinds)} Arten")
    for k, v in sorted(kinds.items(), key=lambda x: -x[1]):
        log(f"   {k:16s} {v}")
    if len(rows) < 400:
        raise ValueError(f"zu wenige Zeilen: {len(rows)}")
    return rows, kinds


# ---------------------------------------------------------------- 3. Prompt-Bau
def serialize_tool_row(row: dict) -> tuple[str, str] | None:
    """Werkzeug-Zeile (user -> tool_calls -> tool -> assistant) als zwei Nachrichten.

    Warum als Text: der Trainer arbeitet mit einfachen user/assistant-Paaren. Ohne
    diese Serialisierung wurden die 40 Werkzeug-Zeilen **verworfen** — dann gibt es
    keinen einzigen Lernreiz fuer Werkzeug-Nutzung. Der Preis ist ehrlich: das Modell
    lernt das Muster, nicht die native function-calling-Schnittstelle.
    """
    msgs = row.get("messages") or []
    if len(msgs) < 3:
        return None
    user = (msgs[0].get("content") or "").strip()
    calls = [m for m in msgs if m.get("tool_calls")]
    results = [m for m in msgs if m.get("role") == "tool"]
    final = (msgs[-1].get("content") or "").strip()
    if not user or not calls or not results or not final:
        return None
    fn = calls[0]["tool_calls"][0].get("function", {})
    name, args = fn.get("name", "?"), fn.get("arguments", "{}")
    antwort = (f"Werkzeug: {name}\n"
               f"Eingabe: {args}\n"
               f"Ergebnis: {(results[0].get('content') or '').strip()}\n\n"
               f"Antwort: {final}")
    return user, antwort


def _encode(proc, prompt: str, full: str, images: list, max_len: int) -> dict:
    """Tokenisiert Prompt und Ziel; maskiert alles bis zum Ziel (-100)."""
    enc = proc(text=[full], images=images or None, return_tensors="pt",
               padding=False, truncation=True, max_length=max_len)
    pre = proc(text=[prompt], images=images or None, return_tensors="pt",
               padding=False, truncation=True, max_length=max_len)
    labels = enc["input_ids"].clone()
    cut = min(pre["input_ids"].shape[1], labels.shape[1])
    labels[:, :cut] = -100
    return _felder(enc, labels)


def _felder(enc, labels) -> dict:
    """Nur die TOKEN-Felder haben eine fuehrende Batch-Dimension (1, L)."""
    # Nur die TOKEN-Felder haben eine fuehrende Batch-Dimension (1, L) und
    # brauchen v[0]. Die Bild-Felder NICHT anfassen — gemessene Rohformen:
    #   pixel_values   (744, 1536)   744 Patches x 1536 Dimensionen
    #   image_grid_thw (1, 3)
    # Mit v[0] auf alles wurde aus pixel_values (1536,) — also EIN Patch von 744,
    # und aus image_grid_thw (3,), was den Lauf mit
    # "too many indices for tensor of dimension 1" killte
    # (Smoke-Lauf 18.11.2026: 23 Text-Schritte liefen, das erste Bild starb).
    keep_as_is = {"image_grid_thw", "pixel_values"}
    out = {}
    for k, v in enc.items():
        if not hasattr(v, "shape"):
            continue
        out[k] = v if k in keep_as_is else v[0]
    out["labels"] = labels[0]
    return out


def build_examples(proc, row: dict, base: Path, max_len: int) -> list[dict]:
    """Ein oder zwei Trainingsbeispiele fuer eine Zeile.

    Einfache Zeilen ergeben eins (Frage -> Antwort). Werkzeug-Zeilen ergeben ZWEI,
    weil beides gelernt werden muss:
      A) den Aufruf erzeugen            (Frage -> <tool_call>...</tool_call>)
      B) nach dem Ergebnis antworten    (Frage+Aufruf+<tool_response> -> Antwort)
    Die Qwen-Vorlage rendert dafuer nativ <tool_call> und <tool_response>; am
    18.11.2026 am Processor geprueft. Vorher wurde das Werkzeug-Format als Fliesstext
    gelehrt ("Werkzeug: ... Ergebnis: ...") — das lernt Muster, keine Schnittstelle.
    """
    from PIL import Image

    msgs = row.get("messages") or []
    images = []
    if row.get("image"):
        p = base / row["image"]
        if not p.is_file():
            return []
        images.append(Image.open(p).convert("RGB"))

    def rendern(teil: list[dict], gen: bool) -> str:
        ms = [dict(m) for m in teil]
        if images and ms and ms[0].get("role") == "user":
            ms[0]["content"] = [{"type": "image"},
                               {"type": "text", "text": ms[0].get("content") or ""}]
        return proc.apply_chat_template(ms, tokenize=False, add_generation_prompt=gen)

    eos = proc.tokenizer.eos_token or ""
    hat_call = any(m.get("tool_calls") for m in msgs)

    if not hat_call:
        if len(msgs) == 2 and msgs[1].get("role") == "assistant" and (msgs[1].get("content") or "").strip():
            prompt = rendern(msgs[:1], True)
            return [_encode(proc, prompt, rendern(msgs, False) + eos, images, max_len)]
        paar = serialize_tool_row(row)         # Altform als Rueckfall
        if paar is None:
            return []
        frage, antwort = paar
        prompt = rendern([{"role": "user", "content": frage}], True)
        return [_encode(proc, prompt, prompt + antwort + eos, images, max_len)]

    i_call = next(i for i, m in enumerate(msgs) if m.get("tool_calls"))
    out = [_encode(proc, rendern(msgs[:i_call], True),
                   rendern(msgs[:i_call + 1], False) + eos, images, max_len)]
    if len(msgs) > i_call + 2 and msgs[-1].get("role") == "assistant" \
            and (msgs[-1].get("content") or "").strip():
        out.append(_encode(proc, rendern(msgs[:-1], True),
                           rendern(msgs, False) + eos, images, max_len))
    return out


def build_dataset(proc, rows: list[dict], base: Path, max_len: int) -> tuple[list[dict], dict]:
    built, stats = [], {"text": 0, "vision": 0, "werkzeug": 0, "verworfen": 0, "fehler": 0}
    for r in rows:
        try:
            exs = build_examples(proc, r, base, max_len)
        except Exception:
            stats["fehler"] += 1
            if stats["fehler"] <= 2:
                traceback.print_exc()
            continue
        if not exs:
            stats["verworfen"] += 1
            continue
        built.extend(exs)
        if any(m.get("tool_calls") for m in (r.get("messages") or [])):
            stats["werkzeug"] += len(exs)
        else:
            stats["vision" if r.get("image") else "text"] += len(exs)
    if VISION_FIRST:
        built.sort(key=lambda ex: 0 if ex.get("pixel_values") is not None else 1)
        log("Reihenfolge: Bild-Beispiele zuerst (OM_VISION_FIRST=1)")
    log(f"Beispiele: {len(built)} · {stats}")
    return built, stats


def collate_batch(batch: list[dict], pad_id: int):
    """Macht aus Beispielen ein Batch. Modul-Ebene, damit es ohne GPU pruefbar ist.

    Vertrag, der am 18.11.2026 verletzt war: `image_grid_thw` muss 2-dimensional
    bleiben (n, 3). Der Vision-Teil rechnet grid_thw[:, 0] * [:, 1] * [:, 2].
    """
    import torch

    mx = max(x["input_ids"].shape[0] for x in batch)
    out = {}
    for key in ("input_ids", "attention_mask", "labels"):
        out[key] = torch.stack([
            torch.nn.functional.pad(x[key], (0, mx - x[key].shape[0]),
                                    value=(pad_id if key != "labels" else -100))
            for x in batch])
    # Qwen-VL: 0=Text, 1=Bild. Ohne dieses Feld keine Bild-Token-Zuordnung.
    if batch[0].get("mm_token_type_ids") is not None:
        out["mm_token_type_ids"] = torch.stack([
            torch.nn.functional.pad(x["mm_token_type_ids"],
                                    (0, mx - x["mm_token_type_ids"].shape[0]), value=0)
            for x in batch])
    # Nur die vorhandenen Bild-Felder zusammenfuehren. Frueher stand hier
    # all(v is not None ...): lag EIN Text-Beispiel im Batch, fielen die Bilder
    # fuer den ganzen Batch weg — bei batch_size=1 unsichtbar, sonst stiller
    # Datenverlust (am 18.11.2026 im Misch-Batch-Test aufgefallen).
    for key in ("pixel_values", "image_grid_thw"):
        vals = [x[key] for x in batch if x.get(key) is not None]
        if vals:
            out[key] = torch.cat(vals, dim=0)
    return out


# ---------------------------------------------------------------- 4. Training
def train(base: Path) -> None:
    import torch
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForImageTextToText, AutoProcessor,
                             BitsAndBytesConfig, Trainer, TrainingArguments)

    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    log(f"Lade {MODEL_ID} in 4 Bit ({dtype}) ...")
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                             bnb_4bit_compute_dtype=dtype, bnb_4bit_use_double_quant=True)
    proc = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL_ID, quantization_config=bnb, device_map={"": 0}, torch_dtype=dtype,
        trust_remote_code=True)
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    cfg = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, bias="none",
                     task_type="CAUSAL_LM",
                     target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                                     "gate_proj", "up_proj", "down_proj"])
    model = get_peft_model(model, cfg)
    model.print_trainable_parameters()

    rows, _ = load_rows(base)
    data, stats = build_dataset(proc, rows, base, SEQ)
    if len(data) < 20:
        raise RuntimeError(f"zu wenige Beispiele: {len(data)} ({stats})")

    pad_id = proc.tokenizer.pad_token_id or proc.tokenizer.eos_token_id

    def collate(batch):
        return collate_batch(batch, pad_id)

    # OM_EPOCHS>0 schlaegt OM_STEPS: fuer den echten Lauf will man Epochen,
    # fuer den Smoke-Test harte Schritte.
    steps_kw = {"num_train_epochs": EPOCHS} if EPOCHS > 0 else {"max_steps": MAX_STEPS}
    args = TrainingArguments(
        output_dir=str(WORK / "out"), per_device_train_batch_size=1,
        gradient_accumulation_steps=4, learning_rate=2e-4, **steps_kw,
        logging_steps=1, save_steps=MAX_STEPS, save_total_limit=1,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        fp16=dtype == torch.float16, bf16=dtype == torch.bfloat16,
        optim="paged_adamw_8bit", lr_scheduler_type="cosine", warmup_steps=5,
        report_to=[], remove_unused_columns=False, dataloader_pin_memory=False)
    trainer = Trainer(model=model, args=args, train_dataset=data, data_collator=collate)
    modus = f"{EPOCHS} Epochen" if EPOCHS > 0 else f"{MAX_STEPS} Schritte"
    log(f"Training startet: {modus}, seq {SEQ}, {len(data)} Beispiele")
    t0 = time.time()
    res = trainer.train()
    dt = time.time() - t0
    log(f"Training fertig in {dt/60:.1f} min · loss {res.training_loss:.4f}")
    if torch.cuda.is_available():
        log(f"VRAM-Spitze: {torch.cuda.max_memory_allocated()/2**30:.1f} GiB")

    out = WORK / "adapter"
    model.save_pretrained(str(out))
    proc.save_pretrained(str(out))
    files = sorted(p.name for p in out.iterdir())
    log(f"Adapter gespeichert: {out} · {files}")

    # Bericht als Datei: die Ausgabedateien des Kernels sind abholbar, das
    # Lauf-Protokoll nicht. Ohne diesen Bericht muesste man im Browser nachsehen.
    report = {
        "modell": MODEL_ID,
        "modus": modus,
        "seq": SEQ,
        "schritte": int(res.global_step) if hasattr(res, "global_step") else None,
        "loss": round(float(res.training_loss), 4),
        "dauer_min": round(dt / 60, 1),
        "vram_spitze_gib": round(torch.cuda.max_memory_allocated() / 2**30, 2)
        if torch.cuda.is_available() else None,
        "beispiele": len(data),
        "daten_stats": stats,
        "adapter_dateien": files,
        "lr": 2e-4,
        "lora_r": 16,
    }
    (WORK / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1),
                                      encoding="utf-8")
    log("report.json geschrieben")
    log("BERICHT: " + json.dumps(report, ensure_ascii=False))


def dry_run() -> None:
    base = fetch_repo()
    rows, kinds = load_rows(base)
    from transformers import AutoProcessor
    proc = AutoProcessor.from_pretrained(MODEL_ID, trust_remote_code=True)
    data, stats = build_dataset(proc, rows, base, SEQ)
    for ex in data[:2]:
        log(f"Beispiel: input_ids {tuple(ex['input_ids'].shape)} · "
            f"labels != -100: {(ex['labels'] != -100).sum().item()} · "
            f"pixel_values {None if ex.get('pixel_values') is None else tuple(ex['pixel_values'].shape)}")
    # Bildformen pruefen: image_grid_thw muss 2-dimensional bleiben (n, 3),
    # sonst stirbt der Vision-Teil mit "too many indices for tensor of dimension 1".
    bilder = [ex for ex in data if ex.get("pixel_values") is not None]
    for ex in bilder[:2]:
        g = ex["image_grid_thw"]
        log(f"Bild-Beispiel: grid_thw {tuple(g.shape)} (ndim={g.ndim}) · "
            f"pixel_values {tuple(ex['pixel_values'].shape)}")
    # Zwei Vertraege, die am 18.11.2026 beide verletzt waren:
    #   grid_thw 2-dimensional (n,3) — sonst IndexError im Vision-Teil
    #   pixel_values 2-dimensional (patches, dim) — sonst nur EIN Patch statt 744
    if bilder and any(ex["image_grid_thw"].ndim != 2 for ex in bilder):
        raise RuntimeError("image_grid_thw ist nicht (n,3) — Beispielbau pruefen")
    if bilder and any(ex["pixel_values"].dim() != 2 for ex in bilder):
        raise RuntimeError("pixel_values ist nicht (patches, dim) — Beispielbau pruefen")
    if bilder:
        n_patch = bilder[0]["pixel_values"].shape[0]
        log(f"Bild-Beispiel: {n_patch} Patches (muss > 1 sein, nicht 1)")
        if n_patch <= 1:
            raise RuntimeError(f"nur {n_patch} Patch — Bild waere unbrauchbar")
    log(f"DRY_RUN ok · {len(data)} Beispiele · {stats}")


if __name__ == "__main__":
    try:
        if DRY:
            dry_run()
        else:
            deps()
            train(fetch_repo())
        log("ENDE: ok")
    except Exception:
        traceback.print_exc()
        log("ENDE: FEHLER (siehe Traceback oben)")
        sys.exit(1)
