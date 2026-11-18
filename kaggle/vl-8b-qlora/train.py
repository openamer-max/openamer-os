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
SEQ = int(os.environ.get("OM_SEQ", "1024"))
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
def build_example(proc, row: dict, base: Path, max_len: int) -> dict | None:
    """(input_ids, attention_mask, labels, pixel_values...) fuer eine Zeile.

    Ziel ist immer die letzte Assistant-Antwort; alles davor wird maskiert (-100).
    Nur Zeilen mit genau einer Frage und einer Antwort werden hier verwendet —
    Werkzeug-Zeilen folgen im naechsten Schritt (eigenes Format).
    """
    from PIL import Image

    msgs = row.get("messages") or []
    if len(msgs) != 2 or msgs[0].get("role") != "user" or msgs[1].get("role") != "assistant":
        return None
    frage, antwort = msgs[0]["content"], msgs[1]["content"]
    if not (frage or "").strip() or not (antwort or "").strip():
        return None

    images = []
    if row.get("image"):
        p = base / row["image"]
        if not p.is_file():
            return None
        images.append(Image.open(p).convert("RGB"))

    content = []
    if images:
        content.append({"type": "image"})
    content.append({"type": "text", "text": frage})
    prompt = proc.apply_chat_template(
        [{"role": "user", "content": content}],
        tokenize=False, add_generation_prompt=True)
    full = prompt + antwort + (proc.tokenizer.eos_token or "")

    enc = proc(text=[full], images=images or None, return_tensors="pt",
               padding=False, truncation=True, max_length=max_len)
    pre = proc(text=[prompt], images=images or None, return_tensors="pt",
               padding=False, truncation=True, max_length=max_len)
    labels = enc["input_ids"].clone()
    cut = pre["input_ids"].shape[1]
    labels[:, :cut] = -100
    out = {k: v[0] for k, v in enc.items() if hasattr(v, "shape")}
    out["labels"] = labels[0]
    return out


def build_dataset(proc, rows: list[dict], base: Path, max_len: int) -> tuple[list[dict], dict]:
    built, stats = [], {"text": 0, "vision": 0, "verworfen": 0, "fehler": 0}
    for r in rows:
        try:
            ex = build_example(proc, r, base, max_len)
        except Exception:
            stats["fehler"] += 1
            if stats["fehler"] <= 2:
                traceback.print_exc()
            continue
        if ex is None:
            stats["verworfen"] += 1
            continue
        built.append(ex)
        stats["vision" if r.get("image") else "text"] += 1
    log(f"Beispiele: {len(built)} · {stats}")
    return built, stats


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
        mx = max(x["input_ids"].shape[0] for x in batch)
        out = {}
        for key in ("input_ids", "attention_mask", "labels"):
            out[key] = torch.stack([
                torch.nn.functional.pad(x[key], (0, mx - x[key].shape[0]),
                                        value=(pad_id if key != "labels" else -100))
                for x in batch])
        # Qwen-VL liefert zusaetzlich mm_token_type_ids (0=Text, 1=Bild) — ohne
        # dieses Feld kann der Prozessor die Bild-Token nicht zuordnen.
        if batch[0].get("mm_token_type_ids") is not None:
            out["mm_token_type_ids"] = torch.stack([
                torch.nn.functional.pad(x["mm_token_type_ids"],
                                        (0, mx - x["mm_token_type_ids"].shape[0]), value=0)
                for x in batch])
        for key in ("pixel_values", "image_grid_thw"):
            vals = [x.get(key) for x in batch]
            if all(v is not None for v in vals):
                out[key] = torch.cat(vals, dim=0)
        return out

    args = TrainingArguments(
        output_dir=str(WORK / "out"), per_device_train_batch_size=1,
        gradient_accumulation_steps=4, max_steps=MAX_STEPS, learning_rate=2e-4,
        logging_steps=1, save_steps=MAX_STEPS, save_total_limit=1,
        gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False},
        fp16=dtype == torch.float16, bf16=dtype == torch.bfloat16,
        optim="paged_adamw_8bit", lr_scheduler_type="cosine", warmup_steps=5,
        report_to=[], remove_unused_columns=False, dataloader_pin_memory=False)
    trainer = Trainer(model=model, args=args, train_dataset=data, data_collator=collate)
    log(f"Training startet: {MAX_STEPS} Schritte, seq {SEQ}, {len(data)} Beispiele")
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
