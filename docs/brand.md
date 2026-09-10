# The mark, and the two faces

A padlock whose body is cut through by an audio waveform: the two things this
program is — it writes down what was said, and nothing leaves the machine it
runs on — in one shape. The waveform is knocked out of the lock rather than
drawn next to it, so the icon stays a solid silhouette at the sizes where a
detail would turn to mud.

Palette: `#6FF0D8` → `#22D3EE` → `#4F7BF7`, on `#0C1526`.

Typefaces: **Fraunces** for headings and titles, **Karla** for everything read
while typing. Both OFL, both self-hosted, both used by *both* front ends — the
page loads them over HTTP and the window hands the same files to Qt.

## Where the files are

The icon set and the fonts are **package data**, in
`src/audio_transcriber/data/brand/`, because the program serves them: the web
page links its favicon and its `@font-face` there and the desktop window builds
its window icon and its palette's typefaces from the same files. `branding.py`
is the only module that knows the path — ask it, don't join paths of your own.

| File | Use |
|---|---|
| `icon.svg` | The master: the lock on its rounded plate. Everything else is derived from it. |
| `icon-small.svg` | Three fat bars instead of five, for renders of 32 px and below, where five stop reading as separate. |
| `icon-mark.svg` | The lock alone, no plate, for putting on a dark background of someone else's. |
| `icon-16/32/48.png` | Rendered from `icon-small.svg`. |
| `icon-64/128/256/512.png` | Rendered from `icon.svg`. |
| `favicon.ico` | 16/32/48/64/128/256 in one file, for browsers that ask for one. |
| `fonts/fraunces.ttf`, `fonts/karla.ttf` | The variable faces, as TrueType. **The page loads these**: a browser applies `font-variation-settings`, so one file covers a display heading and a row's title. Not WOFF2, although that is the better format for a page — Qt hands an application font to the platform's font engine, and DirectWrite rejects WOFF2, which left the window in a fallback face on Windows. |
| `fonts/fraunces-display.ttf` | Fraunces at `opsz 144, wght 500`, as a static face called **Fraunces Display**. |
| `fonts/fraunces-text.ttf`, `fonts/fraunces-text-semibold.ttf` | Fraunces at `opsz 14` in weights 400 and 600, as one static family called **Fraunces Text**. |
| `fonts/*-OFL.txt` | Their licences, which travel with the files. |
| `fonts/*-OFL.txt` | Their licences, which travel with the files. |

One file is neither package data nor art: `packaging/audio-transcriber.desktop`
is the Linux desktop entry. It names `Icon=audio-transcriber`, an icon-theme
name and not a path, and `./install.sh` installs it into
`~/.local/share/applications/` while copying the renders into
`~/.local/share/icons/hicolor/*/apps/audio-transcriber.png` — which is what
makes the dock and the app menu show the mark on Wayland.

The rest is repository art, which the program never opens, and it lives in
`docs/assets/`:

| File | Use |
|---|---|
| `banner.png`, `banner@2x.png`, `banner.svg` | The README header, 1280×320. |
| `social-preview.png`, `.svg` | GitHub's social preview, 1280×640 — the size it asks for exactly. |
| `icon-1024.png` | The large render: an avatar, or the source for a platform icon format. |

## Where it is already applied

- **The web page** links three icons in its `<head>` — the SVG first, the
  `.ico` for browsers that ignore it, and the 256 px PNG as the
  `apple-touch-icon` — and shows the mark next to the title. The files come
  from the app's `/brand` mount, so they work under a `--root-path` prefix
  like `/transcriber` without anything being rewritten. `GET /favicon.ico`
  answers as well, for the tab that is restored before the page loads.
- **The desktop window** sets the icon on the `QApplication` *and* on the
  window, from every PNG size present: the title bar takes the 16 px drawing
  and the alt-tab list the 256 px one, instead of one render scaled twice. It
  also opens with the page's masthead above the tabs — the mark, an eyebrow,
  the name in Fraunces and the promise in Fraunces italic — and the mark is
  drawn from `icon-mark.svg` when the scheme is dark.
- **The window is painted in this palette**, in both schemes, in the same two
  faces: `gui/theme.py` is the stylesheet's tokens as a `QPalette`, a font
  set and a Qt style sheet, and `tests/test_gui_theme.py` compares them with
  `style.css` itself so the two front ends cannot drift. That reverses the
  window's earlier "let the desktop paint it" rule; [gui.md](gui.md) says what
  the reversal cost. Setting the window icon is
  not enough on two platforms, so `branding.py` also holds the two names a
  desktop attaches the mark by: `DESKTOP_ENTRY`, the basename of the Linux
  desktop entry a Wayland compositor looks the icon up from, and
  `WINDOWS_APP_ID`, the Application User Model ID Explorer takes a task-bar
  button's icon from. [gui.md](gui.md) says what each of them fixes.
- **The README** opens with the banner.
- **The web page's palette** is the mark's, not a second palette next to it:
  the dark scheme is the brand's own ground and cyan, the light one the same
  identity inverted, with the accent stepped back to the blue end of the
  gradient and darkened until it reads as text on paper. The values and the
  reasoning are at the top of `web/static/style.css`; `tests/test_web_page.py`
  keeps every pair above WCAG AA in both schemes, so a palette change that
  looks nice and cannot be read fails the suite.

Two things are uploads, not commits, and have to be done by hand in the
repository settings: the **social preview** (Settings → General → Social
preview → `docs/assets/social-preview.png`) and the org or repo **avatar**
(`docs/assets/icon-1024.png`, or the 512 px render).

## Changing it

## Why the window loads static cuts

**The window does not load the variable file, and this is the reason.** Qt
does not apply a variable axis itself: it asks the platform's font engine, and
where that engine does not, it draws the file's *default instance*. Fraunces'
default is `opsz 9, wght 900` — the Black text cut. So the window came out
heavy, with the wrong letterforms, on Windows while looking exactly right on
Linux, twice, and asking harder for the axis could not fix it. A static cut
has nothing left to ignore.

They are instanced from the variable file, and remaking them is three calls:

```python
from fontTools.varLib import instancer
from fontTools.ttLib import TTFont

for name, family, style, axes, weight in (
        ("fraunces-display.ttf", "Fraunces Display", "Regular", {"opsz": 144, "wght": 500}, 500),
        ("fraunces-text.ttf", "Fraunces Text", "Regular", {"opsz": 14, "wght": 400}, 400),
        ("fraunces-text-semibold.ttf", "Fraunces Text", "SemiBold", {"opsz": 14, "wght": 600}, 600)):
    font = TTFont("fraunces.ttf")
    instancer.instantiateVariableFont(font, axes, inplace=True)
    for name_id, value in ((1, family), (2, style), (4, f"{family} {style}"),
                           (6, f"{family.replace(' ', '')}-{style}"),
                           (16, family), (17, style)):
        font["name"].setName(value, name_id, 3, 1, 0x409)
        font["name"].setName(value, name_id, 1, 0, 0)
    font["OS/2"].usWeightClass = weight
    font.save(name)
```

The family names are derived ones, which the OFL allows here: neither licence
declares a reserved font name. The text cut ships in two weights so that a
weight is a *face* and never a synthesis — Qt matches Regular or SemiBold and
has nothing to embolden.

The SVGs are the source of truth; the PNGs and the `.ico` are renders of them.
Any renderer will do — `cairosvg`, `rsvg-convert`, Inkscape — but keep the
split: sizes up to 48 px come from `icon-small.svg`, the rest from `icon.svg`.
A palette change belongs in the `<defs>` of all three drawings at once,
otherwise the plate and the plateless mark drift apart.
