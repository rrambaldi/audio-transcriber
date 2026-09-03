# -*- coding: utf-8 -*-
"""Diarizzazione "chi dice cosa" con pyannote (su CPU) e assegnazione
degli speaker ai segmenti trascritti."""
import os
import re
import sys

from .cleaning import clean_text


def check_diar_assets(model, token):
    """Pre-flight: verifica che tutto il necessario per la diarizzazione ci sia
    PRIMA di avviare la (lunga) trascrizione. Esce con un messaggio chiaro se
    manca qualcosa. Non scarica e non carica nulla di pesante."""
    try:
        import pyannote.audio  # noqa: F401
    except ImportError:
        sys.exit("Diarizzazione: manca pyannote. Esegui: pip install pyannote.audio")

    is_local = os.path.exists(model)
    looks_local = (os.sep in model or "/" in model
                   or model.lower().endswith((".yaml", ".yml")))

    if not is_local:
        if looks_local:
            print(f"  Pre-flight: config locale non trovato ({model}); userei il repo HF.")
        if not token:
            sys.exit("Diarizzazione: manca sia un config locale sia un token HF.\n"
                     "  Metti i file offline (pyannote-diar/config.yaml) oppure imposta HF_TOKEN\n"
                     "  con il permesso 'Read access to public gated repos'.")
        print("  Pre-flight: uso online (repo HF) con token presente.")
        return

    # Config locale presente: controllo i modelli referenziati (embedding/segmentation)
    try:
        with open(model, encoding="utf-8") as f:
            text = f.read()
    except Exception as e:
        sys.exit(f"Diarizzazione: impossibile leggere il config {model}: {e}")

    refs = re.findall(r"^\s*(embedding|segmentation)\s*:\s*(.+?)\s*$", text, re.M)
    base = os.path.dirname(os.path.abspath(model))
    missing, warn = [], []
    for key, val in refs:
        val = val.strip().strip('"').strip("'")
        is_path = (os.sep in val or "/" in val
                   or val.lower().endswith((".bin", ".pt", ".ckpt", ".onnx", ".safetensors")))
        if not is_path:
            continue  # e' un id HF: lo scarichera' pyannote (serve token, gia' gestito)
        if os.path.exists(val):
            continue
        if os.path.exists(os.path.join(base, val)):
            warn.append((key, val))
            continue
        missing.append((key, val))

    if missing:
        lines = "\n".join(f"    - {k}: {v}" for k, v in missing)
        sys.exit("Diarizzazione: nel config mancano file locali (non trovati):\n"
                 + lines + f"\n  Controlla i percorsi in {model}")
    for key, val in warn:
        print(f"  ATTENZIONE: '{key}' ({val}) esiste relativo al config ma pyannote lo risolve\n"
              f"  rispetto alla cartella di lancio: lancia dallo stesso folder o usa un percorso assoluto.")
    print(f"  Pre-flight diarizzazione OK: config e modelli locali presenti ({model}).")


def diarize(audio, token, num_speakers, model="pyannote/speaker-diarization-3.1"):
    """Restituisce i turni di parola come lista di (start, end, speaker_label).
    `model` puo' essere l'id HF (scarica online, richiede token) oppure il
    percorso a un config.yaml LOCALE (uso offline, nessun token)."""
    try:
        import torch
        from pyannote.audio import Pipeline
    except ImportError:
        sys.exit("Manca pyannote. Esegui: pip install pyannote.audio")
    is_local = os.path.exists(model)
    if not is_local and (os.sep in model or "/" in model or model.lower().endswith((".yaml", ".yml"))):
        # sembrava un config locale ma non c'e': ripiego sul repo HF
        fallback = "pyannote/speaker-diarization-3.1"
        print(f"  (config locale non trovato: {model} --> uso il repo HF {fallback})")
        model = fallback
    if not is_local and not token:
        sys.exit(
            "Per --diarize serve un token Hugging Face (o un config.yaml locale via --diar-model).\n"
            "  - Passa --hf-token TOKEN oppure imposta HUGGINGFACE_TOKEN.\n"
            "  - Il token deve avere il permesso 'Read access to public gated repos'.\n"
            "  - Accetta le condizioni su huggingface.co dei modelli:\n"
            "      pyannote/speaker-diarization-3.1, pyannote/segmentation-3.0,\n"
            "      pyannote/wespeaker-voxceleb-resnet34-LM"
        )
    print(f"Carico la pipeline di diarizzazione pyannote (CPU) da: {model}")
    if is_local:
        pl = Pipeline.from_pretrained(model)  # config locale: nessun token
    else:
        try:
            pl = Pipeline.from_pretrained(model, use_auth_token=token)
        except TypeError:
            pl = Pipeline.from_pretrained(model, token=token)
    if pl is None:
        sys.exit("Diarizzazione non inizializzata: token non valido o condizioni dei modelli non accettate.")

    pl.to(torch.device("cpu"))
    waveform = torch.from_numpy(audio).unsqueeze(0)  # (1, campioni)
    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers
    print("Diarizzazione in corso (puo' richiedere qualche minuto)...")
    diar = pl({"waveform": waveform, "sample_rate": 16000}, **kwargs)
    turns = [(t.start, t.end, lab) for t, _, lab in diar.itertracks(yield_label=True)]
    n_spk = len({l for _, _, l in turns})
    print(f"   turni rilevati: {len(turns)} | speaker: {n_spk}")
    return turns


def assign_speakers(segments, turns):
    """Assegna a ogni segmento trascritto lo speaker col maggior overlap
    temporale; se il segmento non ha timestamp usa lo speaker precedente."""
    out, last = [], (turns[0][2] if turns else "SPEAKER_00")
    for s in segments:
        st, en = s.get("start"), s.get("end")
        spk = None
        if st is not None and en is not None and turns:
            best = 0.0
            for ts, te, lab in turns:
                ov = min(en, te) - max(st, ts)
                if ov > best:
                    best, spk = ov, lab
        if spk is None:
            spk = last
        last = spk
        out.append({**s, "speaker": spk})
    return out


def format_dialogue(seg_spk):
    """Unisce i segmenti consecutivi dello stesso speaker in un turno leggibile."""
    blocks, cur_spk, buf = [], None, []
    for s in seg_spk:
        if s["speaker"] != cur_spk:
            if buf:
                blocks.append((cur_spk, clean_text(" ".join(buf))))
            cur_spk, buf = s["speaker"], [s["text"]]
        else:
            buf.append(s["text"])
    if buf:
        blocks.append((cur_spk, clean_text(" ".join(buf))))
    return "\n\n".join(f"[{spk}] {txt}" for spk, txt in blocks if txt)
