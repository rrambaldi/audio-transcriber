# Verifica UX rapida: audio-transcriber dopo il restyle

27 settembre 2026, sera · commit analizzato `66a07b6` · livello rapido

- **Ambiente:** istanza di prova su `127.0.0.1:8899`, la stessa libreria finta dell'analisi del mattino. Chrome headless con un profilo nuovo, per vedere la pagina come chi la apre per la prima volta.
- **Persona:** la stessa dell'analisi `analisi-2026-09-27.md`: consulente ISO 27001, portatile e telefono.
- **Flusso percorso:** tornare, trovare la riunione, leggere cosa si è deciso, saltare a un minuto, prendere una nota. A 1440×900 e 390×844, in chiaro e in scuro.
- **Finestra Qt:** non ripercorsa qui. Vale la verifica offscreen fatta dopo ogni fase (`qt-after`, misure in `verify-*.json`), più due schermate riguardate a occhio (1024×640 chiaro, dialog delle domande in scuro) [V].
- **Non verificato:**
  - scenari di stress (livello rapido);
  - registrazione e caricamento, verificati durante il restyle ma non ripercorsi qui;
  - il servizio vero: gira ancora con l'API di prima del restyle, finché non viene riavviato.

Legenda: [M] misurato · [V] visto · [C] codice · [S] stimato · [P] preferenza · [?] non verificato

## Verdetto

**Pronta con riserve**, per il flusso principale.

Nessun rilievo Critico o Alto; restano un Medio e un Basso. Tutti i 27 interventi del piano risultano presenti, con queste prove:
- riassunto con titoli ed elenchi veri (1 h3, 3 h4, 5 voci) [M];
- timestamp 00:30 → player a 30,6 s [M];
- la nota si salva e risponde "Salvate." [M];
- "Salva le note" visibile senza scorrere (y=730 su 900) [M];
- riga selezionata con il filetto [V];
- "×2 · riassunto · note" nella riga [V].

**Controlli:**
- overflow 0 a 1440 e 390;
- 0 coppie sotto soglia in chiaro (90 elementi) e in scuro (89);
- 0 bersagli sotto 24 px (prima erano 26);
- axe 0 violazioni;
- console pulita;
- 9 dimensioni di testo (prima 11).

**Dimensione più debole:** chiarezza del compito su una libreria con lavori falliti (N1).

**Autocritica:** scritti 3 rilievi, tenuti 2. Scartato il contrasto di 2,46:1 dei link di "Scarica…" in scuro: compariva solo cambiando schema a pagina aperta; caricata in scuro la stessa voce è `#22D3EE` su `#122036` [M].

## Rilievi

### N1 · Media · Web · I lavori falliti stanno sopra la ricerca
- **Piano:** composizione
- **Dove:** colonna della Libreria, 1440×900 e 390×844
- **Riprodurre:** 1. avere tre lavori falliti (restano in "In corso" finché non si svuotano) 2. aprire la pagina
- **Osservato:** "Cerca nelle trascrizioni" comincia a y=1137 a 1440×900 e a y=1067 a 390×844, sotto la prima schermata. Prima ci sono "In corso" e le tre righe rosse dei lavori falliti [M]. A 390 la prima schermata è fatta solo di fallimenti [V] (`390-primo.png`)
- **Atteso:** la ricerca, che è il gesto di chi torna, in cima alla colonna; quello che è già finito, sotto o riassunto
- **Nel codice:** ordine in `index.html`: `#jobs` (riga 87) prima di `.search-field` (riga 91) [C]
- **Correzione minima:**
  - spostare `.search-field` sopra il gruppo "In corso";
  - i lavori falliti o finiti riassunti in una riga ("3 non riusciti · mostra"), aperta a richiesta; i lavori in esecuzione e in attesa restano visibili.
- **Criterio di accettazione:** con 5 lavori falliti, la ricerca comincia sopra y=500 a 1440×900 e sopra y=844 a 390×844
- **Fase:** interventi rapidi

### N2 · Bassa · Web · "‹ Libreria" è un bersaglio da 24 px sul telefono
- **Dove:** lettore a 390×844
- **Osservato:** 55×24 px [M]. È il solo modo di tornare all'elenco, sul dispositivo dove il dito è meno preciso
- **Correzione minima:** sotto `40rem`, `min-height: 44px; padding-inline: .5rem` per il link di ritorno
- **Criterio di accettazione:** a 390×844 il ritorno misura almeno 44 px di altezza
- **Fase:** interventi rapidi

## Registro delle prove

```
REGISTRO — verifica rapida, 127.0.0.1:8899, profilo Chrome nuovo — persona: consulente ISO 27001
1440×900  prima apertura                                     → libreria a sinistra, lettore sull'ultima voce a destra
1440×900  overflow 0; contrasto 0 su 90; bersagli <24 px 0; 9 dimensioni di testo
1440×900  cercato "fornitori" (#search)                       → "12 registrazioni contengono "fornitori"."
1440×900  aperto "×2 Riesame… small · riassunto · note"        → riga selezionata con filetto
1440×900  scheda Riassunto                                   → h3 + 3 h4 + 5 voci; "Elimina il riassunto" e "Riassumi di nuovo" nella scheda
1440×900  Timestamp, 00:30                                   → audio a 30,6 s
1440×900  Note, scritto, "Salva le note" (y=730)             → "Salvate."
1440×900  axe-core 4 sulla pagina con il lettore aperto      → 0 violazioni
1440×900  posizione della ricerca con 5 righe in In corso    → y=1137
390×844   prima apertura                                     → prima schermata: masthead e lavori falliti; ricerca a y=1067
390×844   overflow 0; bersagli <24 px 0 (24 sotto 44)
390×844   aperto "Kick-off progetto ACME"                    → lettore a tutta larghezza, "‹ Libreria" 55×24
390×844   schema scuro dopo il caricamento                   → link di Scarica… a 2,46:1 (scartato: vedi sotto)
1440×900  caricata direttamente in scuro, Scarica… aperto    → #22D3EE su #122036, contrasto 0 sotto soglia
```
