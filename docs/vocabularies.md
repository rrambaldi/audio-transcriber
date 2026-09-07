# Keyword sets

Whisper transcribes what it expects to hear. Tell it nothing and every
recurring acronym in your recordings comes out as the nearest ordinary word:
*CMDB* becomes *si emme di bi*, a colleague's surname becomes something else
entirely. The fix is Whisper's *initial prompt* — a short list of the terms you
know will come up.

A **keyword set** is that list, saved under a name:

```bash
audio-transcriber meeting.wav --vocab iso27001-it
```

`--prompt` (inline) and `--prompt-file` (any path) still work and still mean
what they meant. A named set is the same thing, kept somewhere the tool can
find it, so it can be listed, shared between projects, and offered in a menu by
the web interface.

## The file

A set is a plain text file, `<name>.txt`:

```
# title: ISO 27001 and risk assessment (Italian)
# language: it
# Lines starting with # are comments.

analisi dei rischi, asset, controllo, maturita', minaccia, scenario,
piano di trattamento dei rischi (PTR), ACM, CMDB, NIS, ISO 27001
```

Comments are dropped and whitespace is collapsed, so you can lay the file out
for a human: what Whisper receives is one compact line. `# title:` and
`# language:` are read as metadata and shown in the listings; everything else
in the header is a plain comment.

Terms may be separated by commas or written one per line. Commas win when the
file has any, because a comma-separated file wraps mid-term.

**Keep it short.** Whisper's initial prompt holds about 224 tokens — roughly
900 characters, which is what the tool warns above. Past that the end is simply
ignored, and a very long prompt makes the model start repeating it back at you.
A few dozen well-chosen terms beat two hundred.

The name is a slug: lowercase letters, digits, `-` and `_`, starting with a
letter or a digit. It is a file name and, in the web interface, part of a
request, so nothing else is accepted.

## What comes in the box

Nineteen Italian sets ship with the package, one per kind of meeting. They are
deliberately short — a couple of dozen terms each — because the point is to
**combine two**: the general one, plus the subject you are actually meeting
about.

```bash
audio-transcriber riunione.wav --vocab riunione-generale-it,finance-controllo-it
```

| set | for |
|---|---|
| `riunione-generale-it` | any meeting: action item, follow-up, KPI, OKR, deadline |
| `project-management-it` | gantt, WBS, SAL, change request, sprint, backlog |
| `sviluppo-software-it` | pull request, refactoring, CI/CD, deploy, staging |
| `infrastruttura-cloud-it` | Kubernetes, Terraform, RTO, RPO, autoscaling, FinOps |
| `dati-analytics-it` | data warehouse, ETL, self service BI, data quality |
| `intelligenza-artificiale-it` | LLM, prompt, embedding, RAG, fine tuning, AI Act |
| `cybersecurity-it` | SOC, SIEM, EDR, CVE, CVSS, zero trust, NIS2 |
| `iso27001-it` | risk assessment, PTR, controlli, maturita' |
| `privacy-gdpr-it` | DPIA, DPO, base giuridica, data breach, Garante |
| `it-service-desk-it` | ITIL, ticket, incident, SLA, CMDB, escalation |
| `marketing-it` | brand awareness, buyer persona, funnel, call to action |
| `digital-marketing-it` | SEO, SERP, GA4, CTR, CPC, ROAS, retargeting |
| `vendite-crm-it` | pipeline, closing, churn, ARR, MRR, LTV, CAC |
| `finance-controllo-it` | EBITDA, capex, opex, DSO, ratei e risconti |
| `contabilita-fisco-it` | fattura elettronica, SdI, F24, ritenuta d'acconto |
| `hr-personale-it` | CCNL, RAL, onboarding, performance review, RSPP |
| `acquisti-fornitori-it` | RdA, RFP, capitolato, DDT, TCO, vendor lock in |
| `legale-contratti-it` | clausola, manleva, NDA, foro competente, DPA |
| `board-strategia-it` | delibera, patti parasociali, due diligence, M&A |

They are Italian, and the `-it` suffix says so: an initial prompt only helps
when it is written in the language being spoken. For another language, write
the equivalent set with `vocab new` — the naming convention is
`<subject>-<language>`.

A test keeps them honest: every bundled set must carry a title and a language,
hold at least ten terms, and stay short enough that the general set plus any
other still fits in the prompt Whisper reads.

## Where they live

| where | who writes it | how it is labelled |
|---|---|---|
| `<config>/vocabularies/*.txt` | whoever installs and configures this machine | `user` |
| shipped with the package | the project, as examples | `bundled` |

`audio-transcriber vocab path` prints the first one; `audio-transcriber paths`
lists it alongside everything else. A set in the config directory **shadows** a
bundled one of the same name, which is how you replace an example with your own
version without losing the name.

A third directory can be added with `[paths] vocabularies` in `config.toml`, or
with `AUDIO_TRANSCRIBER_VOCABULARIES_DIR`; it is searched first. That is the
one to point at a shared folder when several people work from the same terms.

## From the command line

```bash
audio-transcriber vocab list                  # what can be selected, and from where
audio-transcriber vocab show iso27001-it      # the set, and the prompt it produces
audio-transcriber vocab new my-terms          # create one, then edit the file
audio-transcriber vocab new client-x --from terms.txt --title "Client X"
audio-transcriber vocab path my-terms         # where that file is

audio-transcriber meeting.wav --vocab iso27001-it
audio-transcriber meeting.wav --vocab iso27001-it --vocab client-x
audio-transcriber meeting.wav --vocab iso27001-it,client-x     # same thing
```

Several sets are concatenated in the order you name them, then the `--prompt`
or `--prompt-file` text is appended. To use one set every time, put it in
`config.toml`:

```toml
[transcription]
vocabulary = "iso27001-it"
```

## From the web interface

The upload form lists the installed sets in columns, with their term counts and
a preview, above a search box that filters them by name, title or term — typing
`EBITDA` finds the finance and the board set. A set you have ticked stays
visible whatever you filter by, so a search can never hide a vocabulary you are
about to use. Under them sits a second group: **your own sets**, which live in
your browser's `localStorage`.

The distinction is deliberate.

- **Installed sets** are chosen by whoever set the machine up. The browser
  selects them *by name*; the text comes from the server. There is no endpoint
  that writes them, so nobody can change another person's setup from a browser.
- **Your sets** never reach the server as a stored object. They are sent as
  text, with the job that uses them, and are recorded in that recording's
  metadata like any other prompt. Clearing the browser's site data deletes
  them, and they follow neither the machine nor another browser.

If a set of yours turns out to be worth sharing, paste it into a file and let
whoever administers the machine run `audio-transcriber vocab new`: it then
shows up in the installed group for everyone.

Both groups feed one counter under the picker, showing how much of the prompt
budget the current selection uses.

## What ends up in the library

A library entry records the names of the installed sets used for it, under
`transcription.vocabulary` in `metadata.json`, so a transcript can be traced
back to the vocabulary that shaped it.
