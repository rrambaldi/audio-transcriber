"""Named sets of sections ("templates") that decide what a summary is made of.

The page a summary becomes used to be one of two things the program had an
opinion about: five fixed headings, or whatever subjects the recording turned
out to have. Both are right for some recordings and wrong for others, and
neither is a thing a reader could ask for. A template is that ask, written
down: *these* are the sections I want, and this is what goes under each.

It is deliberately the same object the keyword sets are. A template is a
plain text file, ``<name>.txt``, looked up in the config directory first and
in the package's own examples second, so that a file written by hand shadows
a bundled one of the same name. Lines starting with ``#`` are comments; four
of them are read as metadata::

    # title: Verbale operativo
    # language: it
    # layout: fixed
    # lists: Decisioni, Azioni

Everything else is the sections, one per line, ``Heading: what belongs
there``::

    Decisioni: una scelta presa davvero, non una che si sta valutando
    Azioni: qualcosa che qualcuno si e' impegnato a fare
    Questioni aperte: una domanda rimasta senza risposta

The explanation may be left off, and then the built-in one is used — which is
what makes a bundled template three words a line. A heading that *is* one of
the built-in kinds keeps that kind's canonical name, so "Decisioni" is still
``decision`` however it was asked for, and everything downstream that knows
what a decision is goes on knowing.

``layout`` is where the notes end up:

``fixed``
    one section per heading above, in that order. The operative minutes:
    decisions here, actions there, and nothing else on the page.
``discovered``
    the headings are only what the reading looks *for*; the page's sections
    are the subjects the recording turned out to have.
``hybrid``
    discovered, with the kinds named in ``lists`` repeated as lists at the
    foot. The default, and what a reader of minutes actually asks for twice:
    what was being discussed, and what has to be done about it.

What a template does *not* do is choose the length. They are separate
questions — a short operative minute and a long one are both sensible — and
they are settings that compose.

One warning that belongs on the tin, and is in the documentation too:
restricting the kinds restricts the *reading*, not only the page. A pass that
is not asked for opinions does not write them down, and those words do not
come back. That is the right trade for a verbale operativo and the wrong one
if the same recording is to be read again under another template, because
the second reading has to start from the transcript.
"""
import os
import re
from dataclasses import dataclass

from ..paths import summary_templates_dir
from ..summary import language_of
from . import grouping
from . import notes as note_kinds

SUFFIX = ".txt"
SOURCE_USER = "user"
SOURCE_BUNDLED = "bundled"

#: A name is a file name and it arrives from an HTTP request: no dots leading
#: anywhere, no separators, nothing to walk out of the directory with. The
#: same pattern the keyword sets use, for the same reason.
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: A template typed into an interface rather than saved under a name. Like the
#: terms box beside it this is a refusal and not a warning: the text arrives
#: from outside and something has to bound it.
MAX_CUSTOM_TEMPLATE = 4000

#: Fewer than this and there is no template. Two, because the reading prompt
#: carries a worked example with two headings in it, and an example headed
#: with a word the rules forbid is the one thing a small model copies more
#: reliably than the rules.
MIN_SECTIONS = 2

#: More sections than a reading pass can hold in front of it. The block is
#: read once per chunk and every heading costs two lines of a prompt that the
#: transcript also has to fit in.
MAX_SECTIONS = 12

BUNDLED_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "summary-templates")

#: The layouts, and the grouping mode each one is.
LAYOUTS = {
    "fixed": grouping.FIXED,
    "discovered": grouping.DISCOVER,
    "hybrid": grouping.HYBRID,
}

DEFAULT_LAYOUT = "hybrid"

#: The name of the template that is what the program does when nobody asks
#: for anything. It is a real file like the others, and it is the one place
#: the built-in catalogue is written down as a template.
DEFAULT_NAME = "meeting"

_METADATA_KEYS = ("title", "language", "layout", "lists")


class TemplateError(Exception):
    """Unknown, unreadable or badly written template."""


@dataclass(frozen=True)
class Template:
    """A page somebody decided they wanted."""

    name: str
    title: str
    language: str
    layout: str
    catalogue: object
    tail: tuple = ()
    source: str = SOURCE_USER
    path: str = ""

    @property
    def mode(self):
        """The grouping mode this layout is."""
        return LAYOUTS.get(self.layout, grouping.HYBRID)

    @property
    def headings(self):
        return tuple(kind.heading for kind in self.catalogue.kinds)

    @property
    def types(self):
        return self.catalogue.names

    def as_dict(self):
        """What a menu needs to show one, and a form to send it back."""
        return {
            "name": self.name,
            "title": self.title,
            "language": self.language,
            "layout": self.layout,
            "source": self.source,
            "sections": [{"heading": kind.heading,
                          "instruction": kind.instruction}
                         for kind in self.catalogue.kinds],
            "lists": [self.catalogue.heading(name) for name in self.tail],
        }


def valid_name(name):
    """True if ``name`` is a usable template name."""
    return bool(NAME_PATTERN.match(str(name or "")))


def normalise_name(text):
    """Turn a heading into a slug, or return '' if nothing is left."""
    flat = note_kinds._plain(text)
    slug = re.sub(r"[^a-z0-9]+", "-", flat).strip("-_")
    return slug[:64].strip("-_")


def metadata(raw):
    """The ``# key: value`` lines at the top, as a dictionary."""
    found = {}
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        body = stripped.lstrip("#").strip()
        if ":" not in body:
            continue
        key, _, value = body.partition(":")
        key = key.strip().lower()
        if key in _METADATA_KEYS:
            found[key] = value.strip()
    return found


def _built_in(language):
    """The built-in catalogue, and its headings the other way round."""
    catalogue = note_kinds.catalogue_for(language)
    by_heading = {}
    for kind in catalogue.kinds:
        by_heading[note_kinds._plain(kind.heading)] = kind
    for name, heading in note_kinds.HEADINGS["en"].items():
        by_heading.setdefault(note_kinds._plain(heading),
                              note_kinds.Kind(
                                  name=name, heading=heading,
                                  instruction=note_kinds.INSTRUCTIONS["en"][name]))
    return by_heading


def sections_of(raw, language="it"):
    """The section lines, as kinds.

    A heading the program already knows keeps that kind's canonical name and
    borrows its explanation when the line does not give one — which is what
    lets a bundled template be three words a line, and what keeps a decision
    called ``decision`` however somebody asked for it."""
    known = _built_in(language)
    kinds, seen = [], set()
    for line in str(raw or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        heading, _, says = stripped.partition(":")
        heading = heading.strip(" \t-*#")
        says = says.strip()
        if not heading:
            continue
        match = known.get(note_kinds._plain(heading))
        name = match.name if match else normalise_name(heading)
        if not name or name in seen:
            continue
        seen.add(name)
        kinds.append(note_kinds.Kind(
            name=name, heading=heading,
            instruction=says or (match.instruction if match else "")))
    return tuple(kinds)


def parse(raw, name="custom", language=None, source=SOURCE_USER, path=""):
    """A template out of the text of one, or raise :class:`TemplateError`."""
    said = metadata(raw)
    language = language_of(language or said.get("language") or "it")
    kinds = sections_of(raw, language)
    if len(kinds) < MIN_SECTIONS:
        raise TemplateError(
            f"{name}: a template needs at least {MIN_SECTIONS} sections, "
            f"one per line, and this one has {len(kinds)}")
    if len(kinds) > MAX_SECTIONS:
        raise TemplateError(
            f"{name}: {len(kinds)} sections is more than a reading pass can "
            f"be asked for at once (at most {MAX_SECTIONS})")

    layout = (said.get("layout") or DEFAULT_LAYOUT).strip().lower()
    if layout not in LAYOUTS:
        raise TemplateError(
            f"{name}: unknown layout {layout!r} "
            f"(one of: {', '.join(sorted(LAYOUTS))})")

    # A catalogue somebody wrote has no English twin to also match against;
    # the built-in one does, and keeps it. See notes.Catalogue.
    every = set(note_kinds.TYPES)
    also = ((tuple(note_kinds.HEADINGS["en"].items()),)
            if all(kind.name in every for kind in kinds) else ())
    catalogue = note_kinds.Catalogue(kinds=kinds, also=also)

    return Template(
        name=name, title=said.get("title") or name, language=language,
        layout=layout, catalogue=catalogue,
        tail=_tail(said.get("lists"), kinds, layout),
        source=source, path=path)


def _tail(written, kinds, layout):
    """Which kinds are repeated as lists at the foot of the page.

    Only ``hybrid`` has a foot. Said nothing, a hybrid template repeats
    whichever of decisions and actions it actually collects, which is the
    page this program shipped before templates existed."""
    if LAYOUTS.get(layout) != grouping.HYBRID:
        return ()
    have = {kind.name: kind for kind in kinds}
    by_heading = {note_kinds._plain(kind.heading): kind.name for kind in kinds}
    if written is None:
        return tuple(name for name in grouping.TAIL_TYPES if name in have)
    named = []
    for part in str(written).split(","):
        part = part.strip()
        if not part:
            continue
        name = (part if part in have
                else by_heading.get(note_kinds._plain(part)))
        if name and name not in named:
            named.append(name)
    return tuple(named)


# --- where they are kept ----------------------------------------------------

def user_dir():
    """Where hand-written templates go."""
    return summary_templates_dir()


def search_paths(extra=None):
    """``(directory, source)`` pairs, most significant first."""
    pairs = []
    if extra:
        pairs.append((os.path.abspath(os.path.expanduser(extra)), SOURCE_USER))
    pairs.append((user_dir(), SOURCE_USER))
    pairs.append((BUNDLED_DIR, SOURCE_BUNDLED))
    return pairs


def _read(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError as exc:
        raise TemplateError(f"{path}: {exc}") from exc


def available(extra=None, language=None):
    """Every template that can be selected, by name, shadowing included.

    ``language`` keeps the menu honest: a template's headings are words in a
    language, and offering an Italian one for an English recording would put
    Italian headings on an English page."""
    found = {}
    for directory, source in search_paths(extra):
        try:
            names = sorted(os.listdir(directory))
        except OSError:
            continue
        for filename in names:
            if not filename.endswith(SUFFIX):
                continue
            name = filename[:-len(SUFFIX)]
            if not valid_name(name) or name in found:
                continue
            path = os.path.join(directory, filename)
            try:
                template = parse(_read(path), name, source=source, path=path)
            except TemplateError:
                continue
            if language and template.language != language_of(language):
                continue
            found[name] = template
    return [found[name] for name in sorted(found)]


def get(name, extra=None, language=None):
    """The template called ``name``, or raise :class:`TemplateError`.

    A bundled template's headings are words in one language, so it is filed
    under the language it is for the way the keyword sets are:
    ``minutes-it``, ``minutes-en``. Asked for ``minutes`` while Italian is
    being spoken, the suffixed one is found first - the name to type is the
    same whoever is talking, which is the point of having one."""
    name = str(name or "").strip()
    if not valid_name(name):
        raise TemplateError(f"invalid template name: {name!r}")
    wanted = [name]
    if language:
        wanted.insert(0, f"{name}-{language_of(language)}")
    for directory, source in search_paths(extra):
        for filename in wanted:
            candidate = os.path.join(directory, filename + SUFFIX)
            if os.path.isfile(candidate):
                return parse(_read(candidate), filename, language=language,
                             source=source, path=candidate)
    known = ", ".join(item.name for item in available(extra)) or "none"
    raise TemplateError(f"unknown summary template '{name}' "
                        f"(available: {known})")


def resolve(settings=None, language="it"):
    """The template one run uses, or ``None`` for "however the program does it".

    Three ways to ask, in the order they win: the text of a template typed
    into an interface, a name, and nothing — which is nothing rather than the
    bundled default on purpose. A run that asks for no template is the run
    this program spent its measuring campaign on, and it goes on being
    exactly that run rather than becoming a file somebody could edit."""
    settings = settings or {}
    written = settings.get("summary_template_text")
    if written and str(written).strip():
        if len(str(written)) > MAX_CUSTOM_TEMPLATE:
            raise TemplateError(
                f"a template typed in by hand may be at most "
                f"{MAX_CUSTOM_TEMPLATE} characters")
        return parse(str(written), "custom", language=language)
    name = settings.get("summary_template")
    if not name or str(name).strip().lower() in ("", "auto", "none"):
        return None
    return get(str(name).strip(), settings.get("summary_templates_dir"),
               language)


def create(name, text, directory=None, overwrite=False):
    """Write a new template in the user directory and return its path."""
    if not valid_name(name):
        raise TemplateError(
            f"invalid template name: {name!r} (lowercase letters, digits, "
            "'-' and '_', starting with a letter or digit)")
    parse(text, name)
    directory = directory or user_dir()
    path = os.path.join(directory, name + SUFFIX)
    if os.path.exists(path) and not overwrite:
        raise TemplateError(f"{path} already exists")
    try:
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text if text.endswith("\n") else text + "\n")
    except OSError as exc:
        raise TemplateError(f"{name}: {exc}") from exc
    return path


TEMPLATE = """\
# title: {title}
# language: {language}
# layout: hybrid
# lists: Decisioni, Azioni

# One section a line: the heading, a colon, and what belongs under it.
# Leave the explanation off and a heading the program already knows keeps
# its own. Two sections at least, twelve at most.
Decisioni:
Azioni:
Questioni aperte:
"""


def template(name, title=None, language="it"):
    """The body of a new template, for somebody to edit."""
    return TEMPLATE.format(title=title or name, language=language_of(language))
