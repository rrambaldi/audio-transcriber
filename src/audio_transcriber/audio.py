# -*- coding: utf-8 -*-
"""Decodifica audio a 16 kHz mono float32 via ffmpeg (incluso con imageio-ffmpeg)."""
import subprocess
import sys

import numpy as np


def ffmpeg_exe():
    """Percorso di ffmpeg: usa quello incluso da 'imageio-ffmpeg' (binario
    statico e autonomo, nessuna DLL esterna); se il pacchetto manca ripiega su
    un ffmpeg di sistema, che pero' su alcuni env conda e' rotto (errori tipo
    'libintl_dgettext' / fontconfig-1.dll)."""
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        print("  ATTENZIONE: 'imageio-ffmpeg' non installato: uso il ffmpeg di sistema.\n"
              "  Se vedi errori di DLL (libintl/fontconfig) esegui: pip install imageio-ffmpeg",
              file=sys.stderr)
        return "ffmpeg"


def load_audio(path, sr=16000):
    """Decodifica l'audio a 16 kHz mono float32 invocando ffmpeg (integrato via
    imageio-ffmpeg). Funziona con wav/mp3/m4a/mp4/mkv ecc."""
    exe = ffmpeg_exe()
    cmd = [exe, "-nostdin", "-loglevel", "error", "-i", path,
           "-f", "f32le", "-acodec", "pcm_f32le", "-ac", "1", "-ar", str(sr), "-"]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError:
        sys.exit("ffmpeg non trovato. Esegui: pip install imageio-ffmpeg")
    if proc.returncode != 0:
        sys.exit("Errore ffmpeg nel decodificare l'audio:\n"
                 + proc.stderr.decode(errors="ignore")[-1000:])
    # .copy() rende l'array scrivibile (serve poi a torch.from_numpy per pyannote)
    return np.frombuffer(proc.stdout, dtype=np.float32).copy()
