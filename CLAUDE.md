# Rules for working on the two front ends

Written after the UX pass of 27 September 2026 (`docs/ux/`): each rule is a
defect that pass found and fixed. Keep them true.

1. **An element hidden with `hidden` stays hidden.** `style.css` carries
   `[hidden] { display: none !important; }`; do not remove it.
   Right: `.with-copy { display: flex }` on a panel that is hidden with `hidden`.
   Wrong: dropping the global rule "because nothing needs it" — a class's
   `display` then beats the attribute, and every tab shows at once.

2. **An asynchronous callback does not read a module variable another gesture
   can clear.** It uses the constant captured when it was created.
   Right: `const current = new MediaRecorder(s); current.addEventListener("stop", () => current.mimeType)`.
   Wrong: `recorder.addEventListener("stop", () => recorder.mimeType)` with
   `recorder = null` elsewhere — every recording was lost that way.

3. **Text the person typed is never thrown away without asking.**
   Right: leaving an entry with changed notes asks Save / Discard / Cancel, in
   the page as in the window.
   Wrong: the reader closes and the notes are gone.

4. **Every icon-only button has a name** — `aria-label` in the page,
   `setAccessibleName` in the window.
   Right: `symbols.Button("edit", "Rename")` sets the tooltip and the name.
   Wrong: a tooltip only.

5. **Italian is written with real accents.**
   Right: "non è reversibile". Wrong: "non e' reversibile".

6. **A colour token changes in `web/static/style.css` and `gui/theme.py`
   together**; `tests/test_gui_theme.py` fails otherwise.
   Right: one commit touching both, with the test green.
   Wrong: changing the QSS "just for the window".

7. **The person is shown the title, not the entry id.**
   Right: "Filed in the library: Management review…".
   Wrong: "Filed in the library: 2026-09-27_1838_riunione-…".
