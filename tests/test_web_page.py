"""The page itself, checked as text.

There is no browser in the test suite and there never will be, but the three
things that go quietly wrong in a hand-written page can all be checked by
reading it: a field with no label attached, a message that exists in one
language and not the other, and a colour pair that fails the contrast
guidelines. So they are checked here.
"""
import os
import re

import pytest

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "src", "audio_transcriber", "web", "static")


def read(name):
    with open(os.path.join(STATIC, name), encoding="utf-8") as handle:
        return handle.read()


@pytest.fixture(scope="module")
def page():
    return read("index.html")


@pytest.fixture(scope="module")
def script():
    return read("app.js")


@pytest.fixture(scope="module")
def stylesheet():
    return read("style.css")


# --- accessibility --------------------------------------------------------

def test_every_field_has_a_label_bound_to_it(page):
    """WCAG 1.3.1/4.1.2: a placeholder or a nearby word is not a label."""
    labelled = set(re.findall(r'<label[^>]*\bfor="([^"]+)"', page))
    fields = re.findall(r'<(?:input|select|textarea)\b[^>]*\bid="([^"]+)"', page)
    assert fields, "no fields found: has the markup changed shape?"
    assert [field for field in fields if field not in labelled] == []


def test_labels_point_at_fields_that_exist(page):
    ids = set(re.findall(r'\bid="([^"]+)"', page))
    for target in re.findall(r'<label[^>]*\bfor="([^"]+)"', page):
        assert target in ids, target


def test_the_keyword_checkboxes_are_generated_with_a_label(script):
    """They are built in JavaScript, so the markup test cannot see them."""
    assert 'el("input", { type: "checkbox", value: key, className: "pick", id })' in script
    assert 'el("label", { htmlFor: id' in script


def test_tabs_say_which_one_is_selected(page, script):
    assert 'role="tab"' in page and 'aria-selected' in page
    assert 'setAttribute("aria-selected"' in script


# --- destructive actions --------------------------------------------------

def test_nothing_is_deleted_without_asking(script):
    """Every call that removes something must be preceded by ask(), the page's
    own confirmation dialog: the browser's confirm() is not used any more."""
    assert "window.confirm" not in script
    assert not re.search(r"(?<![.\w])confirm\(", script)
    assert not re.search(r"(?<![.\w])prompt\(", script)

    for call in re.finditer(r'method: "DELETE"', script):
        before = script[max(0, call.start() - 700):call.start()]
        assert "await ask({" in before, "a DELETE with no confirmation before it"


def test_the_confirmation_says_what_is_not_touched(script):
    """The label that caused a scare said 'forget'; the dialog now spells out
    that the transcription stays in the library."""
    assert "confirm_remove_job_kept" in script
    assert "remove_from_list" in script
    assert '"forget"' not in script


def test_the_keyword_sets_can_be_filtered_and_never_hide_a_selection(page, script):
    """Nineteen sets are a list to search, not one to scroll — but a filter
    that hides a ticked set would let someone transcribe with a vocabulary
    they believe they removed."""
    assert 'id="set-search"' in page
    assert "function filterSets()" in script
    body = script.split("function filterSets()", 1)[1].split("\nfunction ", 1)[0]
    assert "matches || checked" in body, "the filter must keep checked sets visible"


def test_an_unavailable_option_explains_itself(page, script):
    """Whatever the page cannot offer must say why, next to the control."""
    assert 'id="diarize-note"' in page and 'aria-describedby="diarize-note"' in page
    assert 'diarize_not_installed' in script and 'diarize_no_model' in script


# --- the message catalogue ------------------------------------------------

def catalogues(script):
    def keys(text):
        return set(re.findall(r"^    (\w+):", text, re.M))

    block = re.search(r"const I18N = \{(.*?)\n\};", script, re.S).group(1)
    english, italian = block.split("  it: {")
    return keys(english), keys(italian)


def test_both_languages_define_the_same_messages(script):
    english, italian = catalogues(script)
    assert english == italian


def test_every_message_the_page_asks_for_exists(page, script):
    english, _ = catalogues(script)
    used = set(re.findall(r'data-t="([^"]+)"', page))
    used |= set(re.findall(r't\("([a-z_]+)"', script))
    # job statuses are looked up through a variable, t(job.status)
    known = english | {"queued", "running", "done", "failed"}
    assert used - known == set()


# --- what happens when something is missing -------------------------------

def test_the_page_reads_before_javascript_fills_it_in(page):
    """Every label is written by translatePage(), which runs after the status
    call: when that call failed the visitor got a page whose titles, buttons
    and labels were literally empty."""
    empty = re.findall(r'<[^>]*\bdata-t="([^"]+)"[^>]*>\s*</', page)
    assert empty == [], f"nodi senza testo di riserva: {empty}"


def test_the_page_says_when_the_server_is_not_answering(page, script):
    """The page polls, so a server that goes away is invisible: the last known
    state sits there looking alive."""
    assert 'id="offline"' in page and 'role="status"' in page
    assert "function offline(" in script
    assert "server_unreachable" in script
    # every periodic call reports through it, and the first one too
    assert script.count("offline(true") >= 3
    assert script.count("offline(false)") >= 3


def test_an_exit_never_validates(page):
    """The name is required, and Cancel is a submit button in the same form:
    with the name empty - which is exactly when you change your mind about a
    new set - Cancel ran the validation and the dialog stayed open."""
    cancel = re.search(r'<button value="cancel"[^>]*>', page).group(0)
    assert "formnovalidate" in cancel


# --- accessibility, checked as text ---------------------------------------

def test_the_clipped_file_input_shows_its_focus(page, stylesheet):
    """It is clipped away but still takes focus, so the ring has to be drawn
    on the label that stands in for it (WCAG 2.4.7)."""
    assert 'id="file"' in page and "visually-hidden" in page
    assert "#file:focus-visible + p .button" in stylesheet


def test_both_progress_bars_carry_a_name(page, script):
    """A progressbar whose value changes ten times a second and has no name
    announces a number and nothing else (WCAG 4.1.2)."""
    assert 'setAttribute("aria-label", t("level_label"))' in script
    assert '"aria-label": stateText(job)' in script
    assert '"aria-valuemin": 0, "aria-valuemax": 100' in script
    # ...and the meter is a continuous signal, not a status message
    assert 'id="record-level"' in page and 'aria-live="off"' in page


def test_only_a_short_line_is_announced_not_the_whole_list(page, script):
    """The list is rewritten on every poll; a live region around it makes a
    screen reader read every job again every three seconds (WCAG 4.1.3)."""
    jobs = re.search(r'<div id="jobs"[^>]*>', page).group(0)
    assert "aria-live" not in jobs
    assert 'id="jobs-status" aria-live="polite"' in page
    assert 'id="library-status" aria-live="polite"' in page
    assert "function announceJobs(" in script
    # rewriting a live region with the same text announces it again
    assert "if (box.textContent !== line) box.textContent = line;" in script
    # the library says how many it found - to the reader as well
    assert "library_results" in script


def test_the_recorder_line_folds_on_a_narrow_screen(stylesheet):
    """Button plus timer plus a fixed 8rem meter came to more than a 320px
    viewport is wide, which is a horizontal scrollbar (WCAG 1.4.10)."""
    line = re.search(r"\.record-line \{[^}]*\}", stylesheet).group(0)
    assert "flex-wrap: wrap" in line
    level = re.search(r"\.level \{[^}]*\}", stylesheet).group(0)
    assert "flex: 1 1" in level and "0 0 8rem" not in level


def test_the_empty_part_of_a_bar_can_be_seen(stylesheet):
    """--rule against the page is 1.33:1: at rest the level meter was
    indistinguishable from not being there, which is the one question it
    exists to answer."""
    for selector in (r"\.level \{[^}]*\}", r"\.bar \{[^}]*\}"):
        rule = re.search(selector, stylesheet).group(0)
        assert "background: var(--line)" in rule, rule


def test_the_quiet_buttons_are_big_enough_to_hit(stylesheet):
    """"delete", "stop" and "remove from the list" are all .link, and at 22px
    they were the smallest targets on the page (WCAG 2.2, 2.5.8)."""
    rule = re.search(r"^\.link \{[^}]*\}", stylesheet, re.M).group(0)
    assert "min-height: 24px" in rule


def test_the_field_labels_are_not_the_smallest_text(stylesheet):
    """Uppercase 0.72rem is right for a section eyebrow and wrong for the
    words that have to be understood before acting."""
    rule = re.search(r"\.field label[^{]*\{[^}]*\}", stylesheet).group(0)
    assert "font-size: 0.82rem" in rule
    assert "text-transform: none" in rule


def test_the_tab_strips_answer_the_arrows(page, script):
    """A strip that announces itself as role=tablist tells a screen reader to
    press the arrows; until now nothing happened."""
    assert "function wireTabs(" in script
    assert "ArrowRight" in script and "Home" in script
    assert 'tabIndex = name === which ? 0 : -1' in script
    # and its label comes from the catalogue, not typed into the markup
    assert "aria-label" not in re.search(r'<div class="tabs"[^>]*>', page).group(0)
    assert 'setAttribute("aria-label", t("source_tabs"))' in script


def test_the_subtitle_numbers_say_what_zero_means(script):
    """Zero is not a value there, it is "whatever the preset says" - which is
    what the window writes in the same place."""
    assert 'placeholder = t("sub_from_preset")' in script


# --- colour ---------------------------------------------------------------

def palettes(stylesheet):
    """The light palette from :root, the dark one from the media query."""
    def variables(text):
        return dict(re.findall(r"--([a-z-]+):\s*(#[0-9A-Fa-f]{6})", text))

    light_block = stylesheet.split(":root {", 1)[1].split("}", 1)[0]
    dark_block = stylesheet.split("prefers-color-scheme: dark", 1)[1].split("}", 1)[1]
    light = variables(light_block)
    dark = dict(light, **variables(dark_block))
    return light, dark


def relative_luminance(colour):
    channels = [int(colour[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
              for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first, second):
    lighter, darker = sorted((relative_luminance(first), relative_luminance(second)),
                             reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


#: (foreground, background, minimum). 4.5 is AA for text, 3.0 is AA for the
#: boundary of a control — and a field drawn as one underline is all boundary.
CONTRAST_RULES = [
    ("ink", "paper", 4.5), ("ink", "sheet", 4.5),
    ("muted", "paper", 4.5), ("muted", "sheet", 4.5),
    ("forest", "paper", 4.5), ("forest", "sheet", 4.5),
    ("clay", "paper", 4.5), ("clay", "sheet", 4.5),
    ("line", "paper", 3.0), ("line", "sheet", 3.0),
]


def test_a_running_job_shows_the_stage_not_only_the_bar(script):
    """On an engine that reports no progress of its own the bar stands still
    for the whole transcription, exactly as in the window: the stage is what
    says the difference between waiting and wondering."""
    assert "function stateText(" in script
    assert "function stageLabel(" in script
    for stage in ("stage_loading_model", "stage_transcribing", "stage_diarizing"):
        assert f"{stage}:" in script


def test_the_queue_can_be_stopped_from_the_page(script):
    """A transcription here is measured in hours; being able to stop one
    matters as much as being able to start it."""
    assert 'jobs/${job.id}/cancel' in script
    assert "confirm_stop_job" in script            # the running one is asked about


def test_the_form_offers_the_subtitle_numbers(page, script):
    """The same knobs the window has: how they are cut, and whether a file is
    kept with the entry."""
    for field in ("subtitle-preset", "subtitle-chars", "subtitle-words",
                  "save-srt", "save-vtt"):
        assert f'id="{field}"' in page
    assert "subtitles_save" in script
    assert "subtitle_preset" in script
    # Zero means "whatever the preset says", and is not sent as a limit of zero.
    assert 'Number($("subtitle-chars").value) > 0' in script


def test_the_form_asks_what_the_run_is_for(page, script):
    """The same three-way choice the window makes, in the same words: it is
    the first thing to decide and everything else is a detail of it."""
    for name in ("text", "speakers", "subtitles"):
        assert f'id="output-{name}"' in page
        assert f"output_{name}_note:" in script
    assert 'body.append("output", output)' in script
    # The other two answers' controls are put away, not left doing nothing.
    assert 'function applyOutput(' in script
    assert '$("subtitle-fields").hidden = output !== "subtitles"' in script


def test_an_output_the_machine_cannot_produce_is_not_offered(page, script):
    """Without diarization "who said what" is a job that fails after the
    wait, which is a worse way to find out than a disabled button."""
    assert '$("output-speakers").disabled = true' in script
    assert 'if ($("output-speakers").checked) $("output-text").checked = true' in script


def test_an_entry_can_be_downloaded_as_subtitles(page, script):
    """Cut on request from the segments, so an old entry can be cut again with
    today's numbers."""
    assert 'id="viewer-download-srt"' in page
    assert 'id="viewer-download-vtt"' in page
    assert "subtitles.${kind}" in script


def test_recording_shows_the_input_level(page, script):
    """A timer counting up says the browser is recording. It does not say that
    anything is arriving, which is the failure worth catching."""
    assert 'id="record-level"' in page
    assert 'role="progressbar"' in page
    assert "getFloatTimeDomainData" in script
    assert "function levelPercent(" in script
    assert "LEVEL_FLOOR_DB = -60" in script        # decibels, like the window
    assert "recording_silent" in script


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_the_palette_meets_wcag_aa(stylesheet, scheme):
    light, dark = palettes(stylesheet)
    palette = light if scheme == "light" else dark
    failures = []
    for foreground, background, minimum in CONTRAST_RULES:
        ratio = contrast(palette[foreground], palette[background])
        if ratio < minimum:
            failures.append(f"{scheme}: {foreground} on {background} "
                            f"is {ratio:.2f}:1, needs {minimum}")
    assert failures == []


def test_controls_the_browser_paints_have_an_explicit_background(stylesheet):
    """A <select> drop-down and an autofilled field are painted by the browser,
    not by this stylesheet. Left transparent they come out in the theme's
    colours against ours — ivory text on white, or on Chrome's autofill
    yellow — so both get an explicit pair."""
    assert re.search(r"select,\s*select option[^{]*\{[^}]*background-color: var\(--field-bg\)",
                     stylesheet, re.S)
    assert re.search(r"select[^{]*\{[^}]*color: var\(--ink\)", stylesheet, re.S)
    autofill = re.search(r":-webkit-autofill[^{]*\{([^}]*)\}", stylesheet, re.S).group(1)
    assert "--field-bg" in autofill and "-webkit-text-fill-color: var(--ink)" in autofill
    light, dark = palettes(stylesheet)
    assert "field-bg" in light and "field-bg" in dark
    # what the browser paints must be readable with our own ink on it
    for palette, scheme in ((light, "light"), (dark, "dark")):
        assert contrast(palette["ink"], palette["field-bg"]) >= 4.5, scheme


def test_both_schemes_define_every_colour(stylesheet):
    light, dark = palettes(stylesheet)
    assert set(light) <= set(dark)


# --- the fonts are ours, not a third party's ------------------------------

def test_the_page_calls_nobody(page, script, stylesheet):
    """'Nothing leaves this machine' includes the fonts: no CDN, no analytics.

    Only what the browser would actually load counts, so an address written in
    a comment as an example is not a finding."""
    loads = re.findall(r'(?:src|href)=["\']([^"\']+)|url\((["\']?)([^)"\']+)',
                       page + stylesheet)
    remote = [url or third for url, _, third in loads
              if (url or third).startswith(("http:", "//"))
              or (url or third).startswith("https:")]
    assert remote == []
    assert "@import" not in stylesheet
    assert not re.search(r'fetch\(\s*["\'`]https?:', script)
    for name in ("fraunces.woff2", "karla.woff2", "fraunces-OFL.txt", "karla-OFL.txt"):
        assert os.path.exists(os.path.join(STATIC, "fonts", name)), name


def test_the_page_is_prefix_agnostic(page, script):
    """It has to work under a reverse proxy at /transcriber/ as well as at /."""
    assert 'href="static/style.css"' in page and 'src="static/app.js"' in page
    assert not re.search(r'(?:fetch|href|src)\(?["\'`]/(?:api|static)/', script)
    assert 'new URL(`api/${path}`, document.baseURI)' in script


def test_the_stylesheet_is_balanced(stylesheet):
    assert stylesheet.count("{") == stylesheet.count("}")
