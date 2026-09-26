import os
import glob
import argparse
import random
from datetime import datetime
from anthropic import Anthropic
from pathlib import Path
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

def get_all_available_clips(total=500):
    """
    Simula l'intero dataset CLIPS con l'aggiunta di una durata realistica per audio lunghi (1-2 ore).
    """
    clips = []
    # Usiamo un seed fisso in questo mock per non far fluttuare la durata a ogni esecuzione
    rnd = random.Random(42)
    for i in range(1, total + 1):
        # Durata simulata tra 15 minuti (900s) e 2.5 ore (9000s)
        duration = rnd.randint(900, 9000) 
        clips.append({
            "id": f"clips_audio_{i}",
            "duration": duration,
            "audio_path": f"/path/to/clips/audio_{i}.wav",
            "transcription": f"Trascrizione simulata per audio {i}. Durata: {duration}s (circa {round(duration/60, 1)} minuti)."
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
    
    # Calcoliamo in secondi
    if scelta == "1":
        return [c for c in clips if c["duration"] < 1800]
    elif scelta == "2":
        return [c for c in clips if 1800 <= c["duration"] < 3600]
    elif scelta == "3":
        return [c for c in clips if 3600 <= c["duration"] <= 7200]
    elif scelta == "4":
        return [c for c in clips if c["duration"] > 7200]
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
    response = client.messages.create(
        model=model_name,
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def choose_model():
    print("\n" + "="*50)
    print("Scegli il modello Claude da utilizzare per i riassunti:")
    print("1) Claude 3.5 Sonnet (Consigliato)")
    print("2) Claude 3.5 Haiku  (Veloce/Economico)")
    print("3) Claude 3 Opus     (Intelligente/Costoso)")
    print("="*50)
    scelta = input("Inserisci 1, 2 o 3 [default: 1]: ").strip()
    if scelta == "2": return "claude-3-5-haiku-20241022"
    elif scelta == "3": return "claude-3-opus-20240229"
    else: return "claude-3-5-sonnet-20241022"

def main():
    parser = argparse.ArgumentParser(description="Genera riassunti da dataset CLIPS tramite Claude.")
    parser.add_argument("--model", type=str, choices=["claude-3-5-sonnet-20241022", "claude-3-5-haiku-20241022", "claude-3-opus-20240229"], help="Modello Anthropic da usare.")
    parser.add_argument("--template", type=str, default="interview-it.txt", help="Template da usare.")
    parser.add_argument("--samples", type=int, default=40, help="Numero di audio da processare.")
    args = parser.parse_args()

    output_dir = Path(__file__).resolve().parent / "results"
    output_dir.mkdir(exist_ok=True)

    # 1. Rifacciamo o Aggiungiamo?
    mode, existing_ids = ask_first_action(output_dir)

    all_clips = get_all_available_clips(total=500)

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
            print(f"Elaborazione di {item['id']} (Durata: {item['duration']}s)...")
            result_path = output_dir / f"{item['id']}_summary.txt"
            
            if mode == "redo" and result_path.exists():
                archive_old_summary(result_path)
                
            summary = generate_summary(item["transcription"], template, selected_model)
            
            with open(result_path, "w", encoding="utf-8") as f:
                f.write(summary)
            
        except Exception as e:
            print(f"Errore durante l'elaborazione di {item['id']}: {e}")
            break
            
    print("\nProcesso completato.")

if __name__ == "__main__":
    main()
