# -*- coding: utf-8 -*-
"""Trascrizione con Whisper via OpenVINO su device Intel (GPU/CPU/NPU)."""
import os
import re
import sys

# Vocabolario di dominio: guida il modello sui termini tecnici ricorrenti cosi'
# non li storpia. Sostituiscilo/svuotalo con --prompt se cambi argomento.
DOMAIN_PROMPT = (
    "Analisi dei rischi, asset, controllo, maturita', minaccia, scenario, "
    "matrice, soglia di accettabilita', piano di trattamento dei rischi (PTR), "
    "piano di remediation, ACM, CMDB, NIS, ISO 27001, assessment, propagazione, "
    "tenant, campagna, control set, wizard, simulazione."
)

# Scorciatoie modello --> id Hugging Face
MODEL_MAP = {
    "tiny": "openai/whisper-tiny",
    "base": "openai/whisper-base",
    "small": "openai/whisper-small",
    "medium": "openai/whisper-medium",
    "large-v3": "openai/whisper-large-v3",
}


def transcribe(audio, model_name, language, device, model_dir, prompt):
    """Trascrive con Whisper via OpenVINO su device Intel (GPU/CPU/NPU) e
    restituisce (segmenti [{"text","start","end"}], testo_grezzo)."""
    try:
        from optimum.intel import OVModelForSpeechSeq2Seq
        from transformers import AutoProcessor, pipeline
    except ImportError:
        sys.exit('Manca optimum-intel. Esegui: pip install "optimum-intel[openvino]" transformers')

    hf_id = MODEL_MAP.get(model_name, model_name)
    os.makedirs(model_dir, exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", hf_id) + "-ov"
    local = os.path.join(model_dir, safe)

    if os.path.isdir(local) and os.listdir(local):
        print(f"Uso il modello OpenVINO gia' convertito: {local}")
        model = OVModelForSpeechSeq2Seq.from_pretrained(local, device=device)
        processor = AutoProcessor.from_pretrained(local)
    else:
        print(f"Scarico e converto '{hf_id}' in OpenVINO (solo la prima volta)...")
        model = OVModelForSpeechSeq2Seq.from_pretrained(hf_id, export=True, device=device)
        processor = AutoProcessor.from_pretrained(hf_id)
        model.save_pretrained(local)
        processor.save_pretrained(local)
        print(f"Modello salvato in: {local}")

    print(f"Compilazione per il device '{device}'...")
    try:
        model.to(device)
        model.compile()
    except Exception as e:
        print(f"  (compile: {e})")

    pipe = pipeline(
        "automatic-speech-recognition",
        model=model,
        tokenizer=processor.tokenizer,
        feature_extractor=processor.feature_extractor,
        chunk_length_s=30,
        stride_length_s=5,
    )

    base_kwargs = {"task": "transcribe"}
    if language:
        base_kwargs["language"] = language
    prompt_ids = None
    if prompt:
        try:
            # tensore torch: Whisper fa torch.cat() sui prompt_ids (numpy non va bene)
            prompt_ids = processor.get_prompt_ids(prompt, return_tensors="pt")
        except Exception:
            prompt_ids = None

    def _run(with_prompt):
        gk = dict(base_kwargs)
        if with_prompt and prompt_ids is not None:
            gk["prompt_ids"] = prompt_ids
        # Audio gia' decodificato a 16 kHz: lo passo come {"raw","sampling_rate"}
        # cosi' il pipeline non tenta decodifiche (niente torchcodec). NB: il
        # pipeline "consuma" (pop) le chiavi del dict, quindi ne creo uno NUOVO
        # ad ogni chiamata.
        return pipe({"raw": audio, "sampling_rate": 16000},
                    return_timestamps=True, generate_kwargs=gk)

    print("Trascrizione in corso...")
    try:
        res = _run(with_prompt=True)
    except Exception as e:
        print(f"  (initial_prompt non applicato: {e}\n   riprovo senza prompt)")
        res = _run(with_prompt=False)

    segments = []
    for ch in res.get("chunks", []):
        t = (ch.get("text") or "").strip()
        ts = ch.get("timestamp") or (None, None)
        if t:
            segments.append({"text": t, "start": ts[0], "end": ts[1]})
    return segments, (res.get("text") or "")
