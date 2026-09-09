# Subtitles

A transcript and a subtitle track are not the same thing. Whisper returns
segments of twenty or thirty seconds and hundreds of characters; nobody reads
three lines that appear for half a minute. So the segments are cut again,
against the numbers the subtitling trade actually uses.

```bash
audio-transcriber meeting.mp4 --srt                    # meeting.srt beside it
audio-transcriber meeting.mp4 --library --srt --vtt    # both, inside the entry
audio-transcriber meeting.mp4 --srt --subtitle-preset ebu_broadcast
audio-transcriber meeting.mp4 --srt --subtitle-chars 32 --subtitle-words 10
```

The cues are always available — they are computed from the segments whenever
something asks — so saving a file is the option, not the mechanism. An entry in
the library can be exported later, with different numbers, from the same
segments.

## From the window and the browser

Both offer the same four things next to the model and the language: which
preset cuts the subtitles, characters per line, words per subtitle, and whether
to keep an `.srt` or a `.vtt` with the entry. A zero in either number means
"whatever the preset says" — the box says so.

In the library, *Export the subtitles* (the window) and the `.srt` / `.vtt`
links (the page) cut the entry again **from its segments**, so a recording
transcribed months ago can be cut with today's numbers without transcribing it
again. With no preset asked for, the download matches the one the entry was
cut with when it was made.

## The numbers

| key | what it limits |
|---|---|
| `max_chars_per_line` | characters on one line, spaces included (CPL) |
| `max_lines` | lines in one cue |
| `max_words_per_cue` | words in one cue — not one of the trade's numbers, but the one people reach for first |
| `max_chars_per_second` | reading speed (CPS) |
| `max_words_per_minute` | the same thing as some standards state it (WPM) |
| `min_duration_ms` · `max_duration_ms` | below the first a cue blinks; past the second it outstays the speech |
| `min_gap_ms` | the pause between two cues, so they do not read as one |
| `sync_lead_in_ms` · `tail_ms` | how early a cue may appear, and how long it lingers |
| `gap_chaining` | a gap too small to read as a gap is opened out to the minimum |

They come in named sets:

| preset | CPL | lines | CPS | duration | for |
|---|---|---|---|---|---|
| `netflix` | 42 | 2 | 17 | 0.8–7 s | the de facto reference for professional multi-language work |
| `bbc` | 37 | 2 | 14 (180 WPM) | 1–6 s | broadcast accessibility |
| `ebu_broadcast` | 37 | 2 | 15 | 1–6 s | European broadcast, the "six second rule" |
| `fcc_verbatim` | 32 | 2 | 20 | 0.8–7 s | US captioning: every word, nothing condensed |
| `social_vertical` | 34 | 2 | 15 | 0.7–5 s | Reels, Shorts, TikTok |
| `social_karaoke` | 20 | 1 | 15 | 0.3–2 s | two to four words at a time, word-timed |
| `kids_accessible` | 34 | 2 | 13 | 1.2–6 s | teaching, young audiences |

`[subtitles]` in `config.toml` chooses one and overrides any of its numbers;
`--subtitle-preset`, `--subtitle-chars`, `--subtitle-lines` and
`--subtitle-words` do the same for one run. Your own sets go in
`<config>/srt-presets.json` and win over the bundled ones by name — the same
two-places arrangement the [keyword sets](vocabularies.md) use, so a house
style can replace `netflix` without touching the package.

## How a cue is cut

1. **Sentences first**, then clauses, then commas: a cue rarely starts
   mid-thought.
2. **A group too wide or too long is split** at the best break nearest its
   middle — two balanced cues read better than a full one followed by a scrap.
3. **The line break inside a cue** goes after punctuation, then before a
   conjunction, then anywhere allowed. Never between an article and its noun,
   a preposition and its phrase, an auxiliary and its participle, a negation
   and its verb, a verb and its clitic, or between two capitalised words —
   which is usually a name and a surname.
4. **Two lines are balanced**, the shorter first where the break allows it, and
   a split more lopsided than half the longer line is demoted.
5. **Timing**: a cue may appear up to the lead-in early and never late, lingers
   for the tail, is never shorter than the minimum nor longer than the maximum,
   and leaves the minimum gap. A gap too small to be seen as a gap is opened
   out to exactly the minimum rather than left to flicker.

**Word timings.** When subtitles are asked for, the engine is asked to time
every word — faster-whisper can — and the cuts then fall exactly where the
speaker paused. Without them the times are interpolated across the segment by
character count, which is good to a few tenths of a second: enough to notice in
a subtitle, which is why the real thing is worth the small cost. The OpenVINO
backend reports timings per chunk, so there the interpolation is what you get.

## What it will not do

Reading speed is **not** a reason to split. Splitting cannot change it — half
the text in half the time is the same characters per second — and using it as a
trigger produced one word per cue, each padded to the minimum duration, which
is nonsense on screen. Speech faster than the preset allows is a fact about the
speech: the trade's own remedy is to condense the text, and this program does
not rewrite what was said. It cuts as far as cutting helps, writes the cues,
and reports the overrun.

Everything omitted is omitted for that reason or because the information is not
here:

| not done | why |
|---|---|
| condensing text too fast to read | it changes what was said; a warning is reported instead |
| simplifying for a young audience (`allow_simplification`) | the same, and more so |
| `[music]` and other sound labels (`sdh_labels`) | needs sound-event detection |
| spelling numbers under ten as words | a language-by-language editorial rule |
| the adjective/noun line break | needs a part-of-speech tagger |
| not crossing scene cuts | needs the video |
| the burn-in safe zone | not something an .srt file controls |
| `cps_overshoot_tolerance` | it is what the guidance allows *before* condensing, and condensing is the step declined above |

## Checking the result

Every run reports what a subtitler would object to: a line too wide, a cue too
short or too long, an overlap, a gap under the minimum, speech faster than the
preset allows. They are warnings, not errors — subtitles that break a rule are
still better than no subtitles, and the person who asked for them is the one
who decides what to do about it.

```
  Subtitles: 4 things a subtitler would object to, against 'netflix':
    cue : characters per second to read x4
```

## Files

`subtitles.srt` and `subtitles.vtt`, inside the library entry, beside
`transcript.txt`. SRT is written the way players expect it: an index from 1,
`HH:MM:SS,mmm` with a comma, ` --> `, a blank line between blocks, UTF-8, plain
text with no markup. WebVTT is the same cues with a `WEBVTT` header and dots.
