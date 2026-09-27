# Piano di restyle: audio-transcriber (pagina web e finestra Qt)

- **Origine:** `docs/ux/analisi-2026-09-27.md` · commit analizzato `412a7ce` · web: `audio-transcriber web` (in produzione dietro nginx su `/transcriber/`)
- **Stato del piano:** fasi 1-3 applicate e verificate il 27 settembre 2026 (commit `7421d2f`, `2ee4471`, `c83ba87`, `032bc73`, `a7be302`)
- **Direzione scelta:** trasformativa: la libreria è la casa anche nel browser

## Da non toccare

- **I 12 token per schema e la loro uguaglianza fra le due interfacce.** Contrasto del testo sopra 5,5:1 ovunque. Dove: `web/static/style.css`, `gui/theme.py:48`, `tests/test_gui_theme.py`.
- **Fraunces per i titoli, Karla per il resto**, self-hosted e senza rete: sono l'identità. Dove: `data/brand/fonts/`, `branding.py`.
- **I colori per funzione dei bottoni** (commit `dd646b0`): ognuno sopra 6:1, scelta recente e motivata.
- **L'accessibilità della pagina web:** axe 0 violazioni; Invio / Esc / ritorno del focus nel visualizzatore; anello di focus di 2 px `--signal`.
- **Il timestamp che porta il player al punto**, nel web e in Qt.
- **Le conferme distruttive che nominano l'oggetto**, e "No" come default in Qt.
- **La domanda "Note non salvate" della finestra** (`_offer_to_save_notes`): è il modello da portare nel web.
- **Gli errori in lingua umana** ("Nessun testo trascritto (audio vuoto o silenzioso?)", "Nessun microfono trovato…").
- **Lo spazio della forma d'onda riservato prima del disegno** (CLS 0,008).
- **La riga della libreria:** titolo in Fraunces, forma d'onda, fatti in `--muted`.

## Vincoli

- **Web:** HTML/JS/CSS senza build step, nessuna dipendenza nuova, nessuna chiamata di rete verso terzi (i font restano self-hosted).
- **Qt:** PySide6; la logica sta in `gui/options.py`, che non importa Qt, così i test girano senza display.
- **Testi:** ogni stringa visibile passa da `i18n.py` (en, it, fr, de) o dal catalogo di `app.js`, in **tutte** le lingue.
- **Token:** un token cambiato va cambiato in `style.css` **e** in `gui/theme.py`, o `tests/test_gui_theme.py` fallisce.
- **Suite:** la suite deve passare senza motori e senza Qt (vincolo della CI).
- **Browser:** gli ultimi Chrome, Firefox e Safari; contesto sicuro per il microfono.

## Token proposti

```css
/* Nuovo: il testo nascosto resta nascosto, qualunque display abbia la classe (A1). */
[hidden] { display: none !important; }

/* Selezione e focus nelle liste (A5): un filetto non cromatico oltre al lavaggio. */
--select-rule: 3px solid var(--signal);     /* nuovo; signal su sheet 6,42:1 chiaro, 9,04:1 scuro */

/* Indicatori di caselle e radio (A4), solo Qt: contorno in --line. */
/* QCheckBox::indicator, QRadioButton::indicator { border: 1px solid {line}; }   line su paper 3,17:1 / 5,04:1 */

/* Corpo di lettura del pannello Qt (M15): nuovo token di dimensione. */
--read-size: 15px;   /* nuovo; oggi il pannello usa il corpo dei controlli, 12 px */
--read-leading: 1.45;
```

Nessun colore nuovo: la palette resta quella del marchio.

## Interventi

| ID | Fase | Severità | Dove | Correzione minima | Criterio di accettazione | Stato |
|---|---|---|---|---|---|---|
| C1 | 1 rapidi | Critica | `web/static/app.js:1752`, `startRecording`/`stopRecording` | istanza di `MediaRecorder` in una costante locale, letta dall'handler `stop` | registrare 4 s e fermare → file scelto, anteprima visibile, 0 eccezioni | verificato |
| C2 | 1 rapidi | Critica | `app.js:2577` (chiusura del visualizzatore), `app.js:1882` (`applyBusy`) | domanda Salva / Scarta / Annulla se la nota è cambiata; `notes-save` fuori dal blocco | Esc con una nota cambiata apre la domanda; durante un lavoro "Salva" risponde "Salvate." | verificato |
| A1 | 1 rapidi | Alta | `style.css` (in cima) | `[hidden] { display: none !important; }` | fuori da Trascrizione `#viewer-transcript` ha `display: none` | verificato |
| A2 | 3 strutturali | Alta | `index.html:31`, `:209`, `:259`, `:182` | indice di tre link sotto il masthead; opzioni rare in `<details>` chiuso | ricerca della Libreria entro 2 Tab; a 390 Libreria a un tocco | verificato |
| A3 | 1 rapidi | Alta | `gui/symbols.py:170-194` | `self.setAccessibleName(tooltip)` | nessun bottone visibile con testo e nome accessibile vuoti | verificato |
| A4 | 1 rapidi | Alta | `gui/theme.py:524` | `::indicator` con bordo `{line}`, pieno `{signal}` se selezionato | contorno almeno 3:1 in entrambi gli schemi | verificato |
| A5 | 2 sistema visivo | Alta | `gui/theme.py:479`, `:483`; `gui/widgets.py:163` | filetto di 3 px `{signal}` sulla riga selezionata | indicatore di selezione almeno 3:1 | verificato |
| M1 | 3 strutturali | Media | piede del visualizzatore in `index.html` | comandi per scheda, download in "Scarica…", piede sticky | a 1440×900 il comando principale di ogni scheda è visibile | verificato |
| M2 | 1 rapidi | Media | `web/api.py` (`/api/library`), `app.js:2233` | `has_summary` e `copies` nella risposta; "riassunto" e "×N" nella riga | voce con riassunto → "riassunto"; copie → "×2" | verificato |
| M3 | 1 rapidi | Media | `app.js` (scheda Riassunto) | convertitore minimo per `#`, `##`, `- `, `_…_` su testo escapato | nessuna riga visibile comincia con `#` o `_` | verificato |
| M4 | 3 strutturali | Media | `app.js:1852`, `docs/web.md` | upload accettato come "in attesa" durante un lavoro; riassunti ancora bloccati | con un lavoro in corso si accoda un secondo file | verificato |
| M5 | 1 rapidi | Media | `i18n.py` (it), `app.js` (it), `data/vocabularies/*.txt` | accenti veri al posto dell'apostrofo | grep delle forme con apostrofo = 0 | verificato |
| M6 | 1 rapidi | Media | testi pip, `paths.describe`, carico, slug, "prompt" | testi per la persona; comandi nei tooltip | nessun `pip `, `docs/`, chiave inglese o slug visibile | verificato |
| M7 | 1 rapidi | Media | `gui/library_panel.py:666`; meta del visualizzatore in `app.js` | solo il titolo; id nel tooltip | titolo di 90 caratteri in al massimo 2 righe a 1366; nessuno slug visibile | verificato |
| M8 | 1 rapidi | Media | `gui/window.py` (`launch`), `speakers_dialog.py` | `QTranslator` con `qtbase_<lingua>` | nessun bottone standard in inglese | verificato |
| M9 | 1 rapidi | Media | `gui/window.py:327` | annunciare il titolo; aprire la voce se la coda è vuota | messaggio con il titolo; la trascrizione a un clic o meno | verificato |
| M10 | 1 rapidi | Media | `gui/options.py` (`transcription_choices`) | titolo nell'etichetta se diverso; titoli nel tooltip di ×N | ogni titolo si legge nella lista o nel menu | verificato |
| M11 | 1 rapidi | Media | `gui/library_panel.py` (`delete_entry`) | "le altre {n-1} restano"; percorso nei dettagli | la conferma dice quante trascrizioni restano | verificato (percorso tolto dal testo; la cartella resta in Dettagli) |
| M12 | 1 rapidi | Media | `gui/theme.py:504` | `max-height: 6px`, senza testo | barra alta al massimo 6 px | verificato |
| M13 | 3 strutturali | Media | `gui/library_panel.py:462`, `home.py` | stretch 2:3, lista con minimo 260 px | a 1024×640 almeno 25 caratteri di titolo | verificato |
| M14 | 1 rapidi | Media | `gui/options.py:723` | la voce predefinita nomina il motore che verrà usato | idem | verificato |
| M15 | 2 sistema visivo | Media | `gui/theme.py` (pannello di lettura) | `--read-size` 15 px, interlinea 1,45 | trascrizione ad almeno 14 px | verificato |
| B1 | 1 rapidi | Bassa | `#view-tabs`, `style.css` sotto 40rem | `flex-wrap: wrap` | a 390 nessuno scorrimento laterale delle schede | verificato |
| B2 | 1 rapidi | Bassa | `app.js:443` (`summary_queued`) | frase solo con un lavoro in corso | idem | verificato |
| B3 | 1 rapidi | Bassa | `gui/about_dialog.py:57` | icona e nome, motto tradotto | nessun testo non tradotto in Info | verificato |
| B4 | 1 rapidi | Bassa | `app.js` (`#file-name`) | stesso formattatore della coda | una sola unità, niente "0 MB" | verificato |
| B5 | 1 rapidi | Bassa | `i18n.py` (`gui.drop_hint`) | "della finestra"; una sola istruzione | idem | verificato |
| N1 | 1 rapidi | Media | `index.html:87-91` (ordine), gruppo "In corso" in `app.js` | ricerca in cima alla colonna; falliti e finiti riassunti in una riga apribile | con 5 lavori falliti la ricerca comincia sopra y=500 a 1440 e sopra y=844 a 390 | verificato (commit `767ba31`) |
| N2 | 1 rapidi | Bassa | link "‹ Libreria", `style.css` sotto 40rem | `min-height: 44px` | a 390 il ritorno è alto almeno 44 px | verificato (commit `767ba31`) |

Stati ammessi: da fare · fatto · verificato · ancora presente · nuovo problema · rinviato

## Fasi

1. **Interventi rapidi:** C1, C2, A1, A3, A4, M2, M3, M5, M6, M7, M8, M9, M10, M11, M12, M14, B1, B2, B3, B4, B5.
   - Verifica: la pagina a 390 e a 1440, chiaro e scuro, con `misure.js` e axe; la finestra a 1024 e a 1440 in entrambi gli schemi.
   - Si rifanno i due flussi rotti: registrare e fermare; scrivere una nota e chiudere.
2. **Sistema visivo** (token e componenti): A5, M15.
   - Verifica: `tests/test_gui_theme.py` verde; contrasto dell'indicatore di selezione almeno 3:1.
3. **Strutturali:** A2, M1, M4, M13.
   - Con la direzione trasformativa, A2, M1 e M4 diventano un intervento solo: libreria in due colonne, lettura in linea, "Nuova trascrizione" in un dialog.
   - Verifica: Libreria entro 2 Tab; comando principale del visualizzatore visibile a 1440×900.

## Regole anti-regressione

Da copiare in `CLAUDE.md` dopo il restyle.

1. **Un elemento che si nasconde con `hidden` resta nascosto.** C'è `[hidden] { display: none !important; }` e non si toglie.
   - Giusto: `.with-copy { display: flex }` e il pannello si nasconde con `hidden`.
   - Sbagliato: togliere la regola globale "perché non serve".
2. **Un callback asincrono non legge una variabile di modulo che un altro gesto può azzerare.** Usa la costante catturata alla creazione.
   - Giusto: `const current = new MediaRecorder(s); current.addEventListener("stop", () => current.mimeType)`.
   - Sbagliato: `recorder.addEventListener("stop", () => recorder.mimeType)` con `recorder = null` altrove.
3. **Il testo scritto dalla persona non si scarta mai senza chiedere.**
   - Giusto: chiudendo con una nota cambiata compare Salva / Scarta / Annulla.
   - Sbagliato: il dialog si chiude e la nota sparisce.
4. **Ogni bottone a sola icona ha un nome** (`aria-label` nel web, `setAccessibleName` in Qt).
   - Giusto: `Button("edit", "Rinomina")` imposta tooltip e nome.
   - Sbagliato: solo il tooltip.
5. **L'italiano ha gli accenti veri.**
   - Giusto: "non è reversibile".
   - Sbagliato: "non e' reversibile".
6. **Un token si cambia in `style.css` e in `gui/theme.py` insieme.**
   - Giusto: un commit che tocca tutti e due e il test resta verde.
   - Sbagliato: cambiare solo il QSS "per la finestra".
7. **Alla persona si mostra il titolo, non l'id.**
   - Giusto: "Archiviata: Riesame della direzione…".
   - Sbagliato: "Archiviata: 2026-09-27_1838_riunione-…".
