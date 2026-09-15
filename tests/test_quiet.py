"""The upstream lines this program does not pass on, and the ones it does."""
import logging
import warnings

from audio_transcriber import quiet


def reset():
    """Undo what an earlier test, or an earlier run, installed."""
    logging.getLogger(quiet.GENERATION_LOGGER).filters.clear()
    warnings.resetwarnings()
    quiet._installed.clear()


def test_the_duplicate_processor_line_is_dropped(caplog):
    reset()
    quiet.hush_duplicate_logits_processors()
    logger = logging.getLogger(quiet.GENERATION_LOGGER)

    with caplog.at_level(logging.WARNING, logger=quiet.GENERATION_LOGGER):
        logger.warning(
            "A custom logits processor of type <class 'SuppressTokensLogitsProcessor'>"
            " has been passed to `.generate()`, but it was also created in"
            " `.generate()`, given its parameterization.")

    assert caplog.records == []
    reset()


def test_anything_else_that_logger_says_still_comes_through(caplog):
    """The filter is the wording of one line, not the library's voice."""
    reset()
    quiet.hush_duplicate_logits_processors()
    logger = logging.getLogger(quiet.GENERATION_LOGGER)

    with caplog.at_level(logging.WARNING, logger=quiet.GENERATION_LOGGER):
        logger.warning("Setting `pad_token_id` to `eos_token_id` for open-end "
                       "generation.")

    assert len(caplog.records) == 1
    reset()


def test_installing_it_twice_leaves_one_filter():
    """It is called before every recording; a queue must not pile them up."""
    reset()
    quiet.hush_duplicate_logits_processors()
    quiet.hush_duplicate_logits_processors()

    assert len(logging.getLogger(quiet.GENERATION_LOGGER).filters) == 1
    reset()


def test_the_pooling_deviation_warning_is_dropped():
    reset()
    quiet.hush_pooling_deviation()

    with warnings.catch_warnings(record=True) as raised:
        warnings.warn("std(): degrees of freedom is <= 0. Correction should be"
                      " strictly less than the reduction factor",
                      UserWarning, stacklevel=1)

    assert raised == []
    reset()


def test_another_warning_from_the_same_run_is_not_dropped():
    reset()
    quiet.hush_pooling_deviation()

    with warnings.catch_warnings(record=True) as raised:
        warnings.simplefilter("always")
        warnings.warn("data discontinuity in recording", UserWarning,
                      stacklevel=1)

    assert len(raised) == 1
    reset()


def test_a_record_that_cannot_be_formatted_is_left_alone():
    """Judging a message means formatting it, and a broken format string is
    the library's problem to report, not this module's to swallow."""
    broken = logging.LogRecord("x", logging.WARNING, __file__, 1,
                               "%d words", ("not a number",), None)

    assert quiet._Without(["anything"]).filter(broken) is True
