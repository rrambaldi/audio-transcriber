"""The licence, the claim the packaging metadata makes about it, and the list
of everybody else's.

The file is "the MIT license, with a wish": 164 words of preamble that say of
themselves that nothing in them is a condition, followed by the MIT grant. On
the strength of that, ``pyproject.toml`` declares the license expression
``MIT`` - which is what makes a dependency scanner tell a downstream user the
truth about what they owe, namely nothing beyond keeping the notice.

That claim is only true while the grant is untouched, and a licence file is
exactly the kind of file somebody edits for tone. So the operative paragraphs
are compared here with the canonical MIT text, word for word: the wish can be
rewritten freely, and the terms cannot be rewritten by accident.

Four files also carry the identifier in their own heads, and only four. They
are the ones that travel without the repository around them: the two install
scripts, which are copied out and run on their own, and the stylesheet and the
script the browser downloads. Everything else is covered by ``LICENSE`` and by
the package metadata, and a header in every module would be three lines of
boilerplate to keep in step with reality in each of them.
"""
import os
import re
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: The MIT license's three operative paragraphs, as published by the OSI.
MIT = """
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

GRANT = "Permission is hereby granted"


def words(text):
    """The text with its line breaks forgotten: this file is re-wrapped."""
    return re.sub(r"\s+", " ", text).strip()


def licence():
    with open(os.path.join(ROOT, "LICENSE"), encoding="utf-8") as handle:
        return handle.read()


def config():
    with open(os.path.join(ROOT, "pyproject.toml"), "rb") as handle:
        return tomllib.load(handle)


def test_the_grant_is_the_mit_license_word_for_word():
    """Not "based on", not "adapted from": the same words, so that declaring
    MIT downstream is a fact rather than a summary."""
    text = licence()
    assert GRANT in text, "the MIT grant is missing from LICENSE"
    assert words(text[text.index(GRANT):]) == words(MIT)


def test_the_wish_comes_first_and_asks_for_nothing():
    """It is a wish, and it says so. A preamble that quietly imposed a
    condition would make the metadata below a lie, and this program's licence
    something nobody could safely depend on."""
    text = licence()
    preamble = text[:text.index(GRANT)]

    assert "Copyright (c)" in preamble
    assert "Nothing here is a condition" in preamble
    assert "not enforceable" in preamble
    # Whatever else it says, it must not start adding requirements.
    for weasel in ("you must", "You must", "shall be required", "provided that"):
        assert weasel not in preamble, weasel


def test_the_metadata_declares_mit_and_ships_the_file():
    """The expression is what tooling reads; the file is what a person reads.
    Both, or somebody is told the wrong thing about their obligations."""
    project = config()["project"]

    assert project["license"] == "MIT"
    assert "LICENSE" in project["license-files"]
    # The classifier form of the same statement is deprecated, and saying it
    # twice is how the two come to disagree.
    assert not [c for c in project["classifiers"] if c.startswith("License ::")]


def test_the_readme_sends_the_reader_to_the_file():
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as handle:
        readme = handle.read()

    assert "[LICENSE](LICENSE)" in readme
    assert "Gratitude & Random Kindness" in readme


#: The files whose licence has to survive being taken out of the repository,
#: and the comment each of them is written in.
HEADERS = {
    "install.sh": "#",
    "install.cmd": "rem",
    os.path.join("src", "audio_transcriber", "web", "static", "app.js"): "//",
    os.path.join("src", "audio_transcriber", "web", "static", "style.css"): None,
}


def test_the_files_that_travel_alone_carry_the_identifier():
    """A machine-readable licence in the head of the file, so that a copy of
    one of these somewhere else is not a file of unknown provenance."""
    for name, comment in HEADERS.items():
        with open(os.path.join(ROOT, name), encoding="utf-8") as handle:
            head = "".join(handle.readlines()[:6])
        assert "SPDX-License-Identifier: MIT" in head, name
        assert "SPDX-FileCopyrightText: 2026 Roberto Rambaldi" in head, name
        # The identifier alone would drop the half of the licence that is the
        # point of it, so the head says where the words are.
        assert "See LICENSE" in head, name
        if comment:
            assert all(line.startswith(comment) for line in head.splitlines()
                       if "SPDX" in line), name


def test_the_header_does_not_get_in_the_way_of_what_runs_first():
    """Two files cannot simply start with a comment: a shell script has to
    start with its shebang, and a batch file that has not turned echo off yet
    prints its own header to the console."""
    with open(os.path.join(ROOT, "install.sh"), encoding="utf-8") as handle:
        assert handle.readline().startswith("#!/usr/bin/env bash")
    with open(os.path.join(ROOT, "install.cmd"), encoding="utf-8") as handle:
        assert handle.readline().strip().lower() == "@echo off"


def test_the_identifier_is_the_one_the_metadata_declares():
    """Two places state the licence to a machine; they have to agree."""
    with open(os.path.join(ROOT, "install.sh"), encoding="utf-8") as handle:
        head = "".join(handle.readlines()[:6])
    declared = config()["project"]["license"]

    assert f"SPDX-License-Identifier: {declared}" in head


# --- other people's work --------------------------------------------------

THIRD_PARTY = os.path.join(ROOT, "docs", "third-party.md")

#: Names that are not distributions to look up: the extras' own aliases.
_NOT_A_PACKAGE = {"all", "dev"}


def requirements():
    """Every distribution this project asks pip for, by bare name."""
    project = config()["project"]
    wanted = list(project.get("dependencies", []))
    for extra, names in project.get("optional-dependencies", {}).items():
        if extra in _NOT_A_PACKAGE:
            continue
        wanted.extend(names)
    bare = set()
    for requirement in wanted:
        # "optimum-intel[openvino]>=1.2" -> "optimum-intel"
        bare.add(re.split(r"[\[<>=!;\s]", requirement, maxsplit=1)[0].strip())
    return bare


def test_every_dependency_is_accounted_for():
    """A new dependency is one of the two things that rots a licence list, and
    it is the one a test can catch: docs/third-party.md has to name it.

    The other - a licence changing upstream - is a reading job, which is why
    that file records what was checked and when."""
    with open(THIRD_PARTY, encoding="utf-8") as handle:
        listed = handle.read()

    missing = sorted(name for name in requirements() if f"`{name}`" not in listed)
    assert missing == [], f"not in docs/third-party.md: {missing}"


def test_the_copyleft_ones_are_named_in_the_program_itself():
    """Qt and ffmpeg are LGPL, and an About box is where a user can
    reasonably be expected to find that. The rest are permissive and the file
    is enough for them."""
    from audio_transcriber import i18n

    for language in i18n.MESSAGES:
        i18n.set_language(language)
        said = i18n.t("about.dependencies")
        assert "PySide6" in said and "LGPL" in said, language
        assert "ffmpeg" in said, language
        assert "third-party.md" in said, language
    i18n.set_language("en")


def test_the_bundled_typefaces_are_the_only_vendored_thing():
    """Everything else is installed by pip into the user's own environment.
    If that stops being true, this file is where it has to be written down."""
    from audio_transcriber import branding

    with open(THIRD_PARTY, encoding="utf-8") as handle:
        listed = handle.read()

    for family, licence in branding.TYPEFACES:
        assert family in listed
        assert licence in listed
    assert "SIL Open Font License 1.1" in listed
