"""
Genera i riassunti di riferimento (ground truth) dal dataset CLIPS tramite Claude.

Serve:
    pip install anthropic python-dotenv

e un file .env in questa cartella (è già in .gitignore):
    ANTHROPIC_API_KEY=sk-ant-...
    CLIPS_DIR=/percorso/del/dataset/CLIPS

In CLIPS_DIR ogni .txt è una trascrizione; la durata viene letta dal .wav con lo
stesso nome, nella stessa cartella. Le sottocartelle vengono lette tutte.
"""
import os
import argparse
import random
import wave
from datetime import datetime
from anthropic import Anthropic
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def read_transcription(path):
    # I corpora italiani più vecchi sono spesso in latin-1, non in utf-8
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1")

def wav_duration(path):
    """
    Durata in secondi del .wav, o None se manca o non è un wav PCM leggibile.
    """
    try:
        with wave.open(str(path)) as w:
            return round(w.getnframes() / w.getframerate())
    except (FileNotFoundError, wave.Error, EOFError):
        return None

def load_clips(clips_dir):
    """
    Legge le trascrizioni vere del dataset CLIPS da clips_dir.
    """
    clips = []
    for txt in sorted(clips_dir.rglob("*.txt")):
        clips.append({
            # Il percorso relativo tiene distinti due file con lo stesso nome in cartelle diverse
            "id": "__".join(txt.relative_to(clips_dir).with_suffix("").parts),
            "duration": wav_duration(txt.with_suffix(".wav")),
            "transcription": read_transcription(txt),
        })
    return clips

def ask_first_action(output_dir):
    """
    La primissima domanda: se ci sono sommari, vogliamo "Rifare" o "Aggiungere"?
    """
    existing_files = list(output_dir.glob("*_summary.txt"))
    existing_ids = [f.name.replace("_summary.txt", "") for f in existing_files]

    if not existing_ids:
        return "add", []

    print(f"\n[!] Trovati {len(existing_ids)} sommari già esistenti nella cartella results.")
    print("Qual è il tuo obiettivo principale?")
    print("  1) RIFACCIAMO: Rielabora i sommari già esistenti (i vecchi andranno nello storico)")
    print("  2) AGGIUNGIAMO: Pesca un nuovo set di audio, scartando matematicamente quelli già fatti")

    scelta = input("Inserisci 1 o 2 [default: 2]: ").strip()
    if scelta == "1":
        return "redo", existing_ids
    else:
        return "add", existing_ids

def filter_by_duration(clips):
    """
    Filtra gli audio in base alla lunghezza (durata) desiderata, calibrata su audio lunghi (1-2 ore).
    """
    print("\nQual è la durata degli audio su cui vuoi lavorare?")
    print("  1) Corti (< 30 minuti)")
    print("  2) Medi (30 minuti - 1 ora)")
    print("  3) Lunghi (1 ora - 2 ore)")
    print("  4) Molto Lunghi (> 2 ore)")
    print("  5) Qualsiasi durata (Tutti)")

    scelta = input("Inserisci 1, 2, 3, 4 o 5 [default: 5]: ").strip()

    # Senza .wav la durata non si conosce: quegli audio passano solo con "Tutti"
    known = [c for c in clips if c["duration"] is not None]

    # Calcoliamo in secondi
    if scelta == "1":
        return [c for c in known if c["duration"] < 1800]
    elif scelta == "2":
        return [c for c in known if 1800 <= c["duration"] < 3600]
    elif scelta == "3":
        return [c for c in known if 3600 <= c["duration"] <= 7200]
    elif scelta == "4":
        return [c for c in known if c["duration"] > 7200]
    else:
        return clips

def select_clips_strategy(all_clips, mode, existing_ids, num_samples):
    """
    Gestisce la logica di filtro (Rifare/Aggiungere), poi filtro per durata,
    e infine chiede se si vuole una pesca Random o Sequenziale.
    """
    # 1. Filtro base in base all'azione scelta (Rifare o Aggiungere)
    if mode == "add":
        pool = [c for c in all_clips if c["id"] not in existing_ids]
    else: # mode == "redo"
        pool = [c for c in all_clips if c["id"] in existing_ids]

    if not pool:
        print("Non ci sono audio disponibili per questa scelta!")
        return []

    # 2. Filtro per durata
    pool = filter_by_duration(pool)
    print(f"\nAudio disponibili dopo il filtro della durata: {len(pool)}")

    if not pool:
        print("Nessun audio corrisponde a questa durata.")
        return []

    # 3. Random o Sequenziale
    print("\nCome vuoi estrarre i tuoi audio?")
    if mode == "add":
        print("  1) Casuale (Una a caso tranne quelle già fatte)")
        print("  2) Sequenziale (Le prime disponibili non ancora fatte)")
    else:
        print("  1) Casuale (Pesca a caso tra i sommari esistenti da rifare)")
        print("  2) Sequenziale (Prendi i primi sommari esistenti)")

    scelta = input("Inserisci 1 o 2 [default: 1]: ").strip()

    actual_samples = min(num_samples, len(pool))

    if scelta == "2":
        return pool[:actual_samples]
    else:
        # random shuffle the pool to ensure it's completely random
        return random.sample(pool, actual_samples)

def archive_old_summary(filepath):
    if filepath.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{filepath.stem}_{timestamp}.txt"
        history_dir = filepath.parent / "history"
        history_dir.mkdir(exist_ok=True)

        archive_path = history_dir / archive_name
        filepath.rename(archive_path)
        print(f"    -> [Storico] Vecchio riassunto salvato come: history/{archive_name}")

def load_template(template_name="interview-it.txt"):
    base_dir = Path(__file__).resolve().parent.parent
    template_path = base_dir / "src" / "audio_transcriber" / "data" / "summary-templates" / template_name

    if not template_path.exists():
        raise FileNotFoundError(f"Template non trovato: {template_path}")

    with open(template_path, "r", encoding="utf-8") as f:
        return f.read()

def generate_summary(transcription_text, template_text, model_name):
    prompt = f"""Sei un assistente esperto in analisi testuale e riassunti.
Di seguito ti fornisco la trascrizione di un audio e un template specifico da seguire per estrarne le informazioni.

Il tuo compito è analizzare la trascrizione e generare un riassunto compilando ESATTAMENTE le sezioni richieste dal template. Non aggiungere altre sezioni e mantieni il tono oggettivo.

<template>
{template_text}
</template>

<trascrizione>
{transcription_text}
</trascrizione>

Restituisci solo l'output formattato secondo il template, senza preamboli o conclusioni.
"""
    # Se il filtro di sicurezza di Opus 5 rifiuta, l'API ripete la richiesta su un altro modello
    fallback = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"} if model_name == "claude-opus-5" else {}
    response = client.beta.messages.create(
        model=model_name,
        # Opus 5 e Sonnet 5 ragionano prima di rispondere, e il ragionamento conta nel limite
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
        **fallback,
    )
    # Un riassunto tagliato o rifiutato non è un ground truth: meglio fermarsi
    if response.stop_reason != "end_turn":
        raise RuntimeError(f"risposta incompleta (stop_reason={response.stop_reason})")
    return "".join(block.text for block in response.content if block.type == "text")

def choose_model():
    print("\n" + "="*50)
    print("Scegli il modello Claude da utilizzare per i riassunti:")
    print("1) Claude Opus 5    (Consigliato)")
    print("2) Claude Sonnet 5  (Più economico)")
    print("3) Claude Haiku 4.5 (Veloce/Economico)")
    print("="*50)
    scelta = input("Inserisci 1, 2 o 3 [default: 1]: ").strip()
    if scelta == "2": return "claude-sonnet-5"
    elif scelta == "3": return "claude-haiku-4-5"
    else: return "claude-opus-5"

def main():
    parser = argparse.ArgumentParser(description="Genera riassunti da dataset CLIPS tramite Claude.")
    parser.add_argument("--model", type=str, choices=["claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"], help="Modello Anthropic da usare.")
    parser.add_argument("--template", type=str, default="interview-it.txt", help="Template da usare.")
    parser.add_argument("--samples", type=int, default=40, help="Numero di audio da processare.")
    parser.add_argument("--clips-dir", type=Path, default=os.environ.get("CLIPS_DIR") or None, help="Cartella del dataset CLIPS. Default: CLIPS_DIR nel .env.")
    args = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        parser.error("manca ANTHROPIC_API_KEY: mettila nel .env accanto allo script")
    if not args.clips_dir or not args.clips_dir.is_dir():
        parser.error("serve la cartella del dataset CLIPS: --clips-dir oppure CLIPS_DIR nel .env")

    all_clips = load_clips(args.clips_dir)
    if not all_clips:
        print(f"Nessuna trascrizione .txt in {args.clips_dir}. Uscita in corso.")
        return
    senza_durata = sum(1 for c in all_clips if c["duration"] is None)
    print(f"Trovate {len(all_clips)} trascrizioni ({senza_durata} senza .wav leggibile, quindi senza durata).")

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(exist_ok=True)

    # 1. Rifacciamo o Aggiungiamo?
    mode, existing_ids = ask_first_action(output_dir)

    # 2. Logica di selezione (include il filtro per DURATA e RANDOM/SEQ)
    selected_clips = select_clips_strategy(all_clips, mode, existing_ids, args.samples)

    if not selected_clips:
        print("Nessun audio selezionato. Uscita in corso.")
        return

    # 3. Scelta modello
    if args.model:
        selected_model = args.model
        print(f"\nModello specificato: {selected_model}")
    else:
        selected_model = choose_model()
        print(f"\nModello selezionato: {selected_model}")

    template = load_template(args.template)

    print(f"\nInizio elaborazione di {len(selected_clips)} audio ({selected_model})...")
    for item in selected_clips:
        try:
            print(f"Elaborazione di {item['id']} (Durata: {item['duration'] or '?'}s)...")
            result_path = output_dir / f"{item['id']}_summary.txt"

            summary = generate_summary(item["transcription"], template, selected_model)

            # Il vecchio va nello storico solo quando il nuovo è arrivato
            if mode == "redo" and result_path.exists():
                archive_old_summary(result_path)

            with open(result_path, "w", encoding="utf-8") as f:
                f.write(summary)

        except Exception as e:
            print(f"Errore durante l'elaborazione di {item['id']}: {e}")
            break

    print("\nProcesso completato.")

if __name__ == "__main__":
    main()
