# The local web interface

```bash
pip install -e ".[web]"       # fastapi, uvicorn, python-multipart
audio-transcriber web
# Web interface: http://127.0.0.1:8765  (Ctrl-C to stop)
```

Everything the page does, the command line already did. It exists because
dropping a file into a browser tab beats copying it onto a server first, and
because a transcription that takes an hour is easier to watch than to wait for.

## What it does

- **Two ways in.** Drop a recording on the page (or pick one), or record
  straight from the browser with the *Record* tab.
- **Say what the run is for, first**: *just the text*, *the text with who said
  what*, or *subtitles*. A note under the three says what the chosen one
  produces, and the controls belonging to the other two are put away — no
  subtitle preset next to plain text, and the subtitle numbers (with the
  optional "who said what") appear only when subtitles are the answer. *Who
  said what* is disabled outright, with the reason on it, when this machine
  cannot diarize. Same three answers as the window and as `--output`;
  `[general] output` decides which one is preselected.
- Choose the model, the spoken language, and the keyword sets — the installed
  ones, your own, or both. See [vocabularies.md](vocabularies.md).
- Watch the job: queued, transcribing with a progress bar **and the stage it is
  in**, done, failed with the error, or cancelled. *Stop* interrupts the one
  running, after asking; *take out of the queue* drops one that has not
  started.
- **Browse the library**: search the transcripts and notes, open an entry, play
  the recording while reading along, jump to any moment from its timestamp,
  write notes, rename, delete, download the text or the timestamps.

Every finished job is filed in the library, exactly as `--library` does, and
the page's library list is the same entries `audio-transcriber library list`
shows. Notes written on the page are the entry's `notes.md`, so the CLI, an
editor and the browser all see the same file.

## Recording in the browser

The *Record* tab uses `MediaRecorder`: audio is captured in the browser, kept
there while you record, and uploaded as one file when you start the
transcription — it is `audio/webm` (Opus) in most browsers, which ffmpeg reads
without help.

Browsers only hand the microphone to a **secure context**: `https://`, or
`http://localhost`. Running the server on your own machine qualifies. Reaching
one over the network does not, so tunnel it rather than binding it wide:

```bash
ssh -L 8765:127.0.0.1:8765 user@server     # then open http://127.0.0.1:8765
```

The tab says as much, instead of failing silently, when the browser refuses.

**A level meter runs while you record**, next to the timer. A clock counting up
says the browser is recording; it does not say that anything is arriving, and
the classic failure of this feature is an hour of digital silence because the
wrong input was chosen or the microphone is muted. It reads in decibels with a
floor at -60 dBFS, the same scale the desktop window uses, so ordinary speech
fills about two thirds. And a recording that never rose above silence says so
when it stops — the file is still there and can still be transcribed, but you
find out now rather than from an empty transcript.

What the browser cannot offer, and the window can: choosing the audio system
(MME, DirectSound, WASAPI), recording what the speakers are playing, and mixing
a microphone with that. A page gets one microphone through `getUserMedia` and
nothing else. See [gui.md](gui.md).

## Jobs

Uploading creates a job and returns immediately; the page polls it every three
seconds. Jobs run **one at a time**: on a two-core server two transcriptions at
once finish neither any sooner, and risk running out of memory.

**A job says what it is doing, not only how far it has got.** The status shows
the stage — loading the model, converting it, transcribing, who said what,
laying out the text — because the percentage stands still for the whole of a
long transcription on an engine that reports no progress of its own, and
"transcribing" next to a motionless bar is the difference between waiting and
wondering.

**A job can be taken back.** *Take out of the queue* drops one that has not
started: nothing happened to it, so it leaves no row behind. *Stop* asks first
and then interrupts the one running — a transcription here is measured in
hours, and being able to stop one matters as much as being able to start it.
What a stop can promise depends on the engine: the only moment a running
transcription can be interrupted is its progress callback, so faster-whisper
stops within seconds while the OpenVINO backend, which reports none until it
has finished the file, runs to the end and has its result discarded. Nothing
cancelled reaches the library, and the uploaded file stays on the server, so it
can be queued again.

The queue lives in memory. Restarting the server forgets the queue — every
finished transcription is already in the library, and an interrupted one has to
be uploaded again. Uploads wait in the cache directory and are *moved* into the
library entry when the job succeeds; the copy of a job that failed is deleted.

## Security

**There is no authentication.** The server binds to `127.0.0.1` by default:
only this machine can reach it. Anyone who can reach the port can upload
recordings, read every transcript in the library and see where the files are —
so if you bind it to anything else (`--host 0.0.0.0`), put it behind something
that asks who is knocking, or use an SSH tunnel:

```bash
ssh -L 8765:127.0.0.1:8765 user@server     # then open http://127.0.0.1:8765
```

The tool warns when it starts on a non-local address.

## Behind a reverse proxy

The interface speaks plain HTTP and asks nobody who they are. Both problems are
solved by the web server you probably already run: it terminates TLS, asks for
a password, and forwards to the app on localhost.

Every URL the page builds is relative to itself, so it works under any prefix
without being told what the prefix is. The proxy only has to redirect the
prefix without its trailing slash to the one with it, so that a browser
resolves `static/app.js` against `/transcriber/` and not against `/`.

```nginx
# inside the existing "listen 443 ssl" server block
location = /transcriber {
        return 301 https://$host/transcriber/;
}

location /transcriber/ {
        auth_basic "audio-transcriber";
        auth_basic_user_file /etc/nginx/audio-transcriber.htpasswd;

        proxy_pass http://127.0.0.1:8888/;      # the trailing / strips the prefix
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Recordings are large and jobs take hours.
        client_max_body_size 2g;
        proxy_request_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
}
```

Create the password file with `htpasswd -c /etc/nginx/audio-transcriber.htpasswd
NAME` (or `openssl passwd -apr1`), then run the app on localhost only:

```bash
audio-transcriber web --host 127.0.0.1 --port 8888 --root-path /transcriber
```

`--root-path` is not needed by the page; it only tells FastAPI where it really
lives, so that `/api/docs` keeps working.

The three settings that matter are the ones above: without
`client_max_body_size` nginx refuses any upload over 1 MB, without
`proxy_request_buffering off` it spools the whole recording to disk before the
app sees a byte, and without the long timeouts a job that takes an hour looks
like a gateway error.

> **A browser cannot reach a plain-HTTP port on an HSTS host.** If the site
> already sends `Strict-Transport-Security`, that applies to the whole host
> name, non-standard ports included: `http://example.org:8888/` is silently
> upgraded to `https://` and fails. Use the proxy, the bare IP address, or a
> tunnel.

## The API

The page is one static file talking to a small JSON API; nothing stops you
using it directly. `GET /api/docs` serves the generated schema.

| endpoint | what it does |
|---|---|
| `GET /api/status` | version, interface language, models, defaults, limits |
| `GET /api/vocabularies` | the installed keyword sets, with their text |
| `GET /api/vocabularies/{name}` | one of them |
| `POST /api/jobs` | multipart upload; returns the job |
| `GET /api/jobs` · `GET /api/jobs/{id}` | what is running and what happened |
| `POST /api/jobs/{id}/cancel` | take a waiting job out, or ask the running one to stop |
| `DELETE /api/jobs/{id}` | forget a finished job |
| `GET /api/library?q=` | the entries, newest first; `q` searches transcripts and notes |
| `GET /api/library/{id}` | one entry: metadata, transcript, segments, notes, summary |
| `PATCH /api/library/{id}` | rename it (`{"title": "..."}`); the folder keeps its id |
| `DELETE /api/library/{id}` | delete the entry and everything in it |
| `PUT /api/library/{id}/notes` | replace `notes.md` (`{"notes": "..."}`) |
| `GET /api/library/{id}/transcript.txt` | the transcript as a download |
| `GET /api/library/{id}/transcript.json` | the timestamped segments |
| `GET /api/library/{id}/subtitles.srt` · `.vtt` | the entry cut into subtitles on the spot; `?preset=`, `?chars=`, `?words=` |
| `GET /api/library/{id}/audio` | the recording, with range requests so seeking works |
| `POST /api/library/{id}/summary` | queue a summary (`{"engine": "", "length": ""}`); returns a job to poll |
| `GET /api/library/{id}/summary.md` | the summary as a download |
| `DELETE /api/library/{id}/summary` | throw the summary away; the transcript is untouched |
| `GET /api/summary/engines` | which summary engines this machine has, and which one `auto` picks |

Only a recording the entry actually holds is served: an entry created with
`--library-store reference` points at a file elsewhere on disk, and the page is
not a way to read arbitrary paths.

`POST /api/jobs` takes the file plus `title`, `model`, `language`, `backend`,
`output` (`text`, `speakers` or `subtitles`, which settles the flags it
implies), `diarize`, `speakers`, repeated `vocabulary` fields (names of
installed sets), `custom_vocabulary` (free text, the browser's own terms), and
the subtitle settings: `subtitles_save` (`srt`, `vtt`, `srt,vtt` or empty),
`subtitle_preset`, `subtitle_chars`, `subtitle_words`. An unknown output, a
misspelled preset or an unknown format is refused before the upload is stored —
an hour of transcription is a poor way to learn that a name was wrong.

The subtitle downloads cut the entry from its segments every time, so an entry
transcribed months ago can be cut with today's numbers; with no query the
preset is the one it was cut with when it was made. `X-Subtitle-Cues` and
`X-Subtitle-Preset` come back in the headers. See
[subtitles.md](subtitles.md).

## The page itself

`web/static/`: one HTML file, one stylesheet, one script, no build step and no
framework. It is served by the same process. The interface language follows the
server's — `audio-transcriber --lang it web` gives an Italian page.

It is laid out as a sheet of paper rather than as an application: each section
puts its explanation in a narrow column and its controls in a wide one, fields
are a single rule under the text, and the buttons are typographic. Two
typefaces, both self-hosted under `static/fonts/` with their OFL licences —
Fraunces for the headings, Karla for everything else — so the page loads with
no network and calls nobody.

Three properties are enforced by `tests/test_web_page.py`, because they are the
ones that rot quietly:

- every field has a `<label for=...>` bound to it, and the tabs report which
  one is selected;
- the two message catalogues in `app.js` define the same keys, and every
  `data-t` the markup asks for exists;
- every colour pair in both the light and the dark palette clears WCAG AA —
  4.5:1 for text, and 3:1 for the rule under a field, which is the only
  boundary an input has.

**Nothing is deleted without asking.** Removing a job from the list, deleting a
library entry and deleting one of your own keyword sets all go through the same
in-page dialog, which names what will happen and, for a job, says plainly that
the transcription stays in the library — a button labelled "forget" once read
as "delete the recording", and it should not have.
