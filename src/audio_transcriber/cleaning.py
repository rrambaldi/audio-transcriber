# -*- coding: utf-8 -*-
"""Pulizia del testo trascritto: normalizzazione, rimozione delle frasi
"allucinate" da Whisper sul silenzio e raggruppamento in paragrafi."""
import re

# Frasi che Whisper "alluccina" tipicamente sul silenzio/non-parlato (IT).
HALLUCINATION_PHRASES = {
    "grazie", "grazie a tutti", "grazie mille", "grazie a te", "grazie a voi",
    "grazie per l'attenzione", "grazie per la visione", "grazie di cuore",
    "sottotitoli e revisione a cura di qtss",
    "sottotitoli creati dalla comunita amara.org",
    "ciao", "buongiorno a tutti", "buona giornata",
}


def clean_text(t):
    """Normalizza spazi e spazi prima della punteggiatura."""
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"\s+([,.;:!?…])", r"\1", t)
    return t


def _key(t):
    """Forma normalizzata (minuscola, senza punteggiatura) per confronti."""
    return re.sub(r"[^\w\s]", "", (t or "").lower()).strip()


def clean_segments(segments, drop_fillers=True):
    """Rimuove i segmenti-allucinazione e collassa i duplicati consecutivi
    generati dalla sovrapposizione dei chunk."""
    out = []
    for s in segments:
        t = (s.get("text") or "").strip()
        if not t:
            continue
        k = _key(t)
        if drop_fillers and k in HALLUCINATION_PHRASES:
            continue
        if out:
            pk = _key(out[-1]["text"])
            # duplicato esatto, oppure uno contenuto nell'altro (per segmenti lunghi)
            if k and (k == pk or (len(k) > 40 and (k in pk or pk in k))):
                if len(t) > len(out[-1]["text"]):
                    out[-1] = {**s, "text": t}
                continue
        out.append({**s, "text": t})
    return out


def to_paragraphs(segments, gap_break, max_chars):
    """Raggruppa i segmenti in paragrafi: nuovo paragrafo dopo una pausa lunga
    del parlato (gap_break secondi) o quando il paragrafo diventa troppo lungo."""
    paras, cur = [], ""
    for i, s in enumerate(segments):
        t = (s.get("text") or "").strip()
        if not t:
            continue
        cur = (cur + " " + t).strip() if cur else t
        nxt = segments[i + 1] if i + 1 < len(segments) else None
        end, nstart = s.get("end"), (nxt.get("start") if nxt else None)
        gap = (nstart - end) if (end is not None and nstart is not None) else 999
        if gap > gap_break or len(cur) >= max_chars:
            paras.append(clean_text(cur))
            cur = ""
    if cur:
        paras.append(clean_text(cur))
    return [p for p in paras if p]


def paragraphs_from_blob(text, sentences_per_para=5):
    """Fallback quando mancano i timestamp: divide in frasi e le raggruppa."""
    text = clean_text(text)
    sents = re.split(r"(?<=[.!?…])\s+", text)
    paras = []
    for i in range(0, len(sents), sentences_per_para):
        chunk = " ".join(sents[i:i + sentences_per_para]).strip()
        if chunk:
            paras.append(chunk)
    return paras
