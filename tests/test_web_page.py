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
