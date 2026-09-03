# -*- coding: utf-8 -*-
"""Interfaccia a riga di comando: da audio/video a testo in un solo comando."""
import argparse
import os
import sys

from .audio import load_audio
from .cleaning import clean_segments, paragraphs_from_blob, to_paragraphs
from .config import load_dotenv
from .diarization import assign_speakers, check_diar_assets, diarize, format_dialogue
from .transcription import DOMAIN_PROMPT, transcribe

EXAMPLES = """\
Esempi d'uso:
  # Trascrizione semplice (italiano, iGPU Intel di default)
  audio-transcriber riunione.wav

  # Con "chi dice cosa" e 3 speaker noti (offline se c'e' pyannote-diar/config.yaml)
  audio-transcriber riunione.wav --diarize --speakers 3

  # Forza la CPU e un modello piu' leggero/veloce
  audio-transcriber riunione.wav --device CPU --model medium

  # Lingua diversa e file di uscita specifico
  audio-transcriber talk.mp4 --language en --out talk.txt

  # Diarizzazione online (repo HF) invece del config locale
  audio-transcriber riunione.wav --diarize --diar-model pyannote/speaker-diarization-3.1

  # Auto-detect della lingua e senza rimozione delle frasi-filler
  audio-transcriber audio.m4a --language "" --keep-fillers
"""


def build_parser():
    ap = argparse.ArgumentParser(
        prog="audio-transcriber",
        description="Da audio/video a testo (Whisper via OpenVINO su iGPU Intel) con diarizzazione opzionale.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("input", help="file audio o video")
    ap.add_argument("--out", default=None, help="file .txt di uscita (default: stesso nome)")
    ap.add_argument("--model", default="large-v3", help="tiny|base|small|medium|large-v3 (o id HF)")
    ap.add_argument("--language", default="it", help="es. it, en (default: it; '' per auto)")
    ap.add_argument("--device", default="GPU", help="GPU (iGPU Intel, default) | CPU | NPU")
    ap.add_argument("--model-dir", default=None,
                    help="cartella dei modelli OpenVINO "
                         "(default: sottocartella 'whisper-ov-models' nella cartella corrente)")
    ap.add_argument("--prompt", default=DOMAIN_PROMPT,
                    help="testo-guida coi termini di dominio ('' per disattivarlo)")
    ap.add_argument("--para-gap", type=float, default=1.2,
                    help="secondi di pausa oltre i quali iniziare un nuovo paragrafo (senza --diarize)")
    ap.add_argument("--para-max-chars", type=int, default=600,
                    help="lunghezza massima di un paragrafo (senza --diarize)")
    ap.add_argument("--keep-fillers", action="store_true",
                    help="NON rimuovere le frasi-allucinazione (Grazie a tutti, ecc.)")
    ap.add_argument("--diarize", action="store_true",
                    help="attiva la diarizzazione 'chi dice cosa' (pyannote, CPU)")
    ap.add_argument("--speakers", type=int, default=None,
                    help="numero di speaker se noto (migliora molto la resa)")
    ap.add_argument("--hf-token", default=None,
                    help="token Hugging Face per pyannote (o var. HUGGINGFACE_TOKEN)")
    ap.add_argument("--diar-model", default=None,
                    help="id HF (online, con token) o percorso a un config.yaml locale (offline). "
                         "Default: 'pyannote-diar/config.yaml' nella cartella corrente, con fallback al repo HF")
    return ap


def main(argv=None):
    ap = build_parser()
    if argv is None:
        argv = sys.argv[1:]
    if not argv:  # lanciato senza argomenti: mostra help + esempi
        ap.print_help(sys.stderr)
        sys.exit(1)
    a = ap.parse_args(argv)

    load_dotenv()  # carica HF_TOKEN/HUGGINGFACE_TOKEN da un .env nella cartella corrente

    if not os.path.exists(a.input):
        sys.exit(f"File non trovato: {a.input}")
    out = a.out or (os.path.splitext(a.input)[0] + ".txt")
    model_dir = a.model_dir or os.path.join(os.getcwd(), "whisper-ov-models")
    language = a.language or None

    audio = load_audio(a.input)

    # Pre-flight diarizzazione: verifica i file locali PRIMA della lunga trascrizione,
    # cosi' non aspetti l'intera trascrizione per scoprire che manca qualcosa.
    token = diar_model = None
    if a.diarize:
        token = a.hf_token or os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
        diar_model = a.diar_model or os.path.join(os.getcwd(), "pyannote-diar", "config.yaml")
        check_diar_assets(diar_model, token)

    segments, blob = transcribe(audio, a.model, language, a.device, model_dir, a.prompt)
    if not segments and not blob.strip():
        sys.exit("Nessun testo trascritto (audio vuoto o silenzioso?).")
    segments = clean_segments(segments, drop_fillers=not a.keep_fillers)

    if a.diarize:
        turns = diarize(audio, token, a.speakers, diar_model)
        if segments and turns:
            text = format_dialogue(assign_speakers(segments, turns)) + "\n"
        else:
            print("  ATTENZIONE: diarizzazione senza turni o senza segmenti: scrivo il testo semplice.")
            text = "\n\n".join(to_paragraphs(segments, a.para_gap, a.para_max_chars)
                               or paragraphs_from_blob(blob)) + "\n"
    else:
        paras = to_paragraphs(segments, a.para_gap, a.para_max_chars) if segments else paragraphs_from_blob(blob)
        text = "\n\n".join(paras) + "\n"

    with open(out, "w", encoding="utf-8") as f:
        f.write(text)

    print(f"\nOK: trascrizione -> {out}")
    print(f"   parole: {len(text.split())} | device trascr.: {a.device} | lingua: {language or 'auto'}"
          + (" | diarizzazione: ON" if a.diarize else ""))


if __name__ == "__main__":
    main()
