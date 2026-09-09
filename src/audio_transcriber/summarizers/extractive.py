"""The engine that uses no model: the transcript, with most of it removed.

TextRank scores every sentence by how much of the rest of the transcript it
speaks for; the best ones are printed in the order they were said, with the
minute they were said at. The shortest of them open the page as an abstract.

What comes out is honestly limited, and the page says so: these are somebody's
own words, selected, not a text written about the meeting. It cannot tell a
decision from a digression, and it will never write "the team agreed to ship
on Friday" unless somebody said roughly that. In exchange it is instant, needs
nothing installed, works in any language whose stopwords are listed, and is
the same arithmetic the model engines use to cut a transcript down before
reading it.
"""
from ..summary import (
    HEADINGS,
    STAGE_SELECTING,
    Point,
    Sections,
    how_many,
    keywords,
    language_of,
    rank,
    select,
)

NAME = "extractive"

#: How the page names this engine.
LABEL = "extractive (TextRank)"

#: The most sentences that open the page as an abstract. Three is what fits in
#: a glance, which is the only job that paragraph has — but it is a ceiling,
#: not a quota: a short summary of a short recording may only have three
#: sentences in total, and an abstract that swallowed all of them would leave
#: the page with no key points at all.
ABSTRACT_SENTENCES = 3

#: At most this share of the chosen sentences goes into the abstract.
ABSTRACT_SHARE = 3

#: Terms listed at the foot of the page.
KEYWORDS = 10


def label(settings=None):
    """How the page should name this engine. It has no model to name."""
    return LABEL


def summarize(material, settings=None, progress=None):
    """Choose the sentences that carry the transcript.

    Returns the sections and the caveat to print under the title: an
    extractive summary that does not admit to being one invites the reader to
    trust it as prose somebody wrote."""
    settings = settings or {}
    language = language_of(material.language)
    sentences = list(material.sentences)

    scores = rank(sentences, language)
    count = how_many(len(sentences), settings.get("summary_length"))
    chosen = select(sentences, scores, count, language)

    # The abstract is the highest-scoring few of what was already chosen, back
    # in spoken order — not a second selection, so it can never disagree with
    # the points below it.
    best = sorted(chosen, key=lambda index: float(scores[index]), reverse=True)
    room = max(1, min(ABSTRACT_SENTENCES, len(chosen) // ABSTRACT_SHARE))
    opening = sorted(best[:room])
    abstract = " ".join(sentences[index].text for index in opening)

    points = [Point(sentences[index].start, sentences[index].speaker,
                    sentences[index].text)
              for index in chosen if index not in opening]

    if progress:
        # There is no honest intermediate figure to report: the ranking is one
        # matrix multiplication and it is already over.
        progress(90, STAGE_SELECTING)
    words = HEADINGS.get(language, HEADINGS["en"])
    return (Sections(abstract=abstract, points=points,
                     keywords=keywords(sentences, language, KEYWORDS)),
            words["extractive_note"])
