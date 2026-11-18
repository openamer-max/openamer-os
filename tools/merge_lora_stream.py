#!/usr/bin/env python
"""Rechnet einen LoRA-Adapter stromweise in eine HF-Basis ein (Platte statt RAM).

Warum: ein normaler Merge laedt die 8B-Basis in bf16 (16 GB) und braucht mit
Delta und Ergebnis ~20 GB RAM. Hier sind nur ~17 GB frei (31 GB gesamt, Windows
und Desktop belegen den Rest). Deshalb Tensor fuer Tensor:

    W' = W + (B @ A) * (alpha / r)

Jeder Basistensor wird einzeln gelesen, bei Bedarf korrigiert und sofort wieder
geschrieben. Spitzenbedarf: der groesste Einzeltensor (~0,5 GB) plus der Adapter
(0,16 GB). Ergebnis ist ein vollstaendiges HF-Verzeichnis, das der GGUF-Konverter
versteht — kein transformers, kein peft.

Aufruf:
    python tools/merge_lora_stream.py <basis_hf> <adapter_dir> <ziel_hf>
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import torch
from safetensors import safe_open
from safetensors.torch import save_file




def adapter_lesen(adapter: Path) -> tuple[dict[str, tuple[torch.Tensor, torch.Tensor]], float]:
    """(Modulpfad -> (A, B), Skalierung alpha/r)."""
    cfg = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
    skalierung = float(cfg["lora_alpha"]) / float(cfg["r"])
    datei = next((adapter / n for n in ("adapter_model.safetensors", "adapter_model.bin")
                  if (adapter / n).is_file()), None)
    if datei is None:
        raise FileNotFoundError("adapter_model.safetensors fehlt")
    roh = {}
    if datei.suffix == ".safetensors":
        with safe_open(str(datei), framework="pt") as f:
            for k in f.keys():
                roh[k] = f.get_tensor(k)
    else:
        roh = torch.load(str(datei), map_location="cpu")

    paare: dict[str, dict[str, torch.Tensor]] = {}
    for k, v in roh.items():
        # Keys sehen so aus:
        # base_model.model.model.layers.0.self_attn.q_proj.lora_A.weight
        teil = k.replace("base_model.model.", "")
        for art in ("lora_A.weight", "lora_B.weight"):
            if teil.endswith(art):
                modul = teil[: -len(art)].rstrip(".")
                paare.setdefault(modul, {})["A" if art.startswith("lora_A") else "B"] = v
    fertig = {m: (d["A"], d["B"]) for m, d in paare.items() if "A" in d and "B" in d}
    return fertig, skalierung


def merge(basis: Path, adapter: Path, ziel: Path) -> int:
    deltas, skala = adapter_lesen(adapter)
    print(f"Adapter: {len(deltas)} Module · Skalierung alpha/r = {skala:.3f}", flush=True)

    index_datei = basis / "model.safetensors.index.json"
    if index_datei.is_file():
        weight_map = json.loads(index_datei.read_text(encoding="utf-8"))["weight_map"]
        pro_shard: dict[str, list[str]] = {}
        for tensor, shard in weight_map.items():
            pro_shard.setdefault(shard, []).append(tensor)
    else:
        dateien = sorted(basis.glob("*.safetensors"))
        if not dateien:
            raise FileNotFoundError("keine .safetensors in der Basis")
        pro_shard = {d.name: [] for d in dateien}      # [] = alle Tensoren der Datei

    ziel.mkdir(parents=True, exist_ok=True)
    for datei in basis.iterdir():                      # config, tokenizer, ...
        if datei.is_file() and datei.name != "model.safetensors.index.json":
            shutil.copy2(datei, ziel / datei.name)

    neu_index: dict[str, str] = {}
    getroffen = 0

    for shard, namen in pro_shard.items():
        puffer = {}
        with safe_open(str(basis / shard), framework="pt") as f:
            schluessel = namen or list(f.keys())
            for name in schluessel:
                w = f.get_tensor(name)
                modul = name[: -len(".weight")] if name.endswith(".weight") else name
                if modul in deltas:
                    a, b = deltas[modul]
                    # Delta in der Ziel-Dtype rechnen, dann addieren
                    delta = (b.to(torch.float32) @ a.to(torch.float32)) * skala
                    w = (w.to(torch.float32) + delta).to(w.dtype)
                    getroffen += 1
                puffer[name] = w.contiguous()
                neu_index[name] = shard
        save_file(puffer, str(ziel / shard), metadata={"format": "pt"})
        del puffer
        print(f"  {shard}: {len(schluessel)} Tensoren, {getroffen} bisher korrigiert", flush=True)

    (ziel / "model.safetensors.index.json").write_text(
        json.dumps({"metadata": {"total_size": 0}, "weight_map": neu_index}, indent=1),
        encoding="utf-8")
    print(f"Fertig: {getroffen} Tensoren mit Adapter-Delta -> {ziel}", flush=True)
    return 0 if getroffen else 3


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(merge(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])))
