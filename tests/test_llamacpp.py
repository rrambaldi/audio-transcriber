"""The GGUF engine: everything around the model, with no model.

The runtime is one call — a string in, a string out — and both ways into it,
the Python binding and the ``llama-server`` binary, are stubbed here. What is
actually tested is the part that is easy to get wrong and impossible to notice
afterwards: where the file goes, what happens when a download stops halfway,
that the server is never bound anywhere but the loopback, and that the process
is stopped even when the summary fails.
"""
import os
from pathlib import Path

import pytest

from audio_transcriber import paths
from audio_transcriber.summarizers import llamacpp as engine
from audio_transcriber.summarizers import plan
from audio_transcriber.summary import Material, Sentence, SummaryError


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch, tmp_path):
    monkeypatch.setenv(paths.ENV_HOME, str(tmp_path / "home"))
    monkeypatch.delenv("AUDIO_TRANSCRIBER_LANG", raising=False)
    monkeypatch.delenv(engine.ENV_SERVER, raising=False)
    plan.forget()
    yield
    plan.forget()


SENTENCES = [
    Sentence("Parliamo del budget.", 0.0, 8.0, "SPEAKER_00"),
    Sentence("Sono quarantaduemila euro.", 8.0, 20.0, "SPEAKER_00"),
    Sentence("Decidiamo entro venerdi.", 75.0, 90.0, "SPEAKER_01"),
]


def material(sentences=SENTENCES, language="it"):
    return Material(title="Riunione", sentences=sentences, language=language)


# --- is it here at all ----------------------------------------------------

def test_a_machine_with_neither_way_in_does_not_offer_the_engine(monkeypatch):
    monkeypatch.setattr(engine, "module_available", lambda name: False)
    monkeypatch.setattr(engine.shutil, "which", lambda name: None)
    assert engine.is_available() is False


def test_the_binary_counts_as_installed_even_off_the_path(monkeypatch, tmp_path):
    """On a server it is one file somebody dropped on a volume."""
    monkeypatch.setattr(engine, "module_available", lambda name: False)
    monkeypatch.setattr(engine.shutil, "which", lambda name: None)
    binary = tmp_path / "llama-server"
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(0o755)

    assert engine.is_available({"summary_llama_server": str(binary)})
    assert engine.server_path({"summary_llama_server": str(binary)}) == str(binary)
    monkeypatch.setenv(engine.ENV_SERVER, str(binary))
    assert engine.is_available()


def test_a_configured_path_that_is_not_there_is_not_believed(monkeypatch, tmp_path):
    monkeypatch.setattr(engine, "module_available", lambda name: False)
    monkeypatch.setattr(engine.shutil, "which", lambda name: None)
    assert engine.server_path({"summary_llama_server": str(tmp_path / "nope")}) is None


def test_the_binding_is_enough_on_its_own(monkeypatch):
    monkeypatch.setattr(engine, "module_available",
                        lambda name: name == "llama_cpp")
    monkeypatch.setattr(engine.shutil, "which", lambda name: None)
    assert engine.is_available() is True


# --- where the file goes --------------------------------------------------

def test_the_gguf_is_named_as_its_publisher_named_it():
    model = plan.named("openbmb/MiniCPM5-1B")
    assert engine.gguf_name(model, "Q4_K_M") == "MiniCPM5-1B-Q4_K_M.gguf"


def test_the_gguf_lives_under_the_managed_model_directory(tmp_path):
    model = plan.named("openbmb/MiniCPM5-1B")
    where = engine.model_path(model, "Q4_K_M", str(tmp_path))
    assert where.startswith(os.path.join(str(tmp_path), "summary"))
    assert where.endswith("MiniCPM5-1B-Q4_K_M.gguf")


def test_a_model_with_no_gguf_published_is_refused_by_name(tmp_path):
    model = plan.named("Qwen/Qwen3.5-4B")
    assert engine.model_path(model, "Q4_K_M", str(tmp_path)) is None
    with pytest.raises(SummaryError) as raised:
        engine.fetch(model, "Q4_K_M", str(tmp_path))
    assert "Qwen3.5-4B" in str(raised.value)


def test_a_model_already_here_is_not_downloaded_again(monkeypatch, tmp_path):
    model = plan.named("openbmb/MiniCPM5-1B")
    where = engine.model_path(model, "Q4_K_M", str(tmp_path))
    paths.ensure(os.path.dirname(where))
    Path(where).write_bytes(b"GGUF")
    monkeypatch.setattr(engine.urllib.request, "urlopen",
                        lambda *a, **k: pytest.fail("it went to the network"))
    assert engine.fetch(model, "Q4_K_M", str(tmp_path)) == where


class FakeDownload:
    """A response that hands over a body, optionally less of it than promised."""

    def __init__(self, body, claimed=None):
        self.body, self.claimed = body, claimed if claimed is not None else len(body)
        self.headers = {"Content-Length": str(self.claimed)}
        self._at = 0

    def read(self, size):
        block = self.body[self._at:self._at + size]
        self._at += len(block)
        return block

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_a_download_that_stops_early_leaves_nothing_behind(monkeypatch, tmp_path):
    """A truncated file looks like a model and fails at the first prompt.

    Days later, on somebody else's machine."""
    model = plan.named("openbmb/MiniCPM5-1B")
    monkeypatch.setattr(engine.urllib.request, "urlopen",
                        lambda *a, **k: FakeDownload(b"GGUF" * 10, claimed=10_000))
    with pytest.raises(SummaryError) as raised:
        engine.fetch(model, "Q4_K_M", str(tmp_path))
    assert "10000" in str(raised.value).replace(",", "")
    where = engine.model_path(model, "Q4_K_M", str(tmp_path))
    assert not os.path.exists(where)
    assert not os.path.exists(where + ".part")


def test_a_download_that_completes_is_kept_under_its_own_name(monkeypatch, tmp_path):
    model = plan.named("openbmb/MiniCPM5-1B")
    monkeypatch.setattr(engine.urllib.request, "urlopen",
                        lambda *a, **k: FakeDownload(b"GGUF" * 1000))
    where = engine.fetch(model, "Q4_K_M", str(tmp_path))
    assert os.path.getsize(where) == 4000
    assert not os.path.exists(where + ".part")


def test_the_download_goes_to_the_publisher_and_nowhere_else(monkeypatch, tmp_path):
    asked = []
    model = plan.named("openbmb/MiniCPM5-1B")

    def record(url, *args, **kwargs):
        asked.append(url)
        return FakeDownload(b"GGUF")

    monkeypatch.setattr(engine.urllib.request, "urlopen", record)
    engine.fetch(model, "Q4_K_M", str(tmp_path))
    assert asked == ["https://huggingface.co/openbmb/MiniCPM5-1B-GGUF/"
                     "resolve/main/MiniCPM5-1B-Q4_K_M.gguf"]


# --- the server, which must never leave this machine ----------------------

def test_the_server_is_bound_to_the_loopback_and_a_free_port(monkeypatch, tmp_path):
    started = {}

    class FakeProcess:
        returncode = None

        def poll(self):
            return None

        def terminate(self):
            started["stopped"] = True

        def wait(self, timeout=None):
            return 0

    def record(command, **kwargs):
        started["command"] = command
        return FakeProcess()

    monkeypatch.setattr(engine.subprocess, "Popen", record)
    monkeypatch.setattr(engine.Server, "_wait", lambda self: None)
    chosen = plan.resolve_plan(plan.LLAMACPP, ram=32.0, total=64.0, cores=4)
    server = engine.Server("/usr/bin/llama-server", str(tmp_path / "m.gguf"),
                           chosen)

    command = started["command"]
    assert "--host" in command and command[command.index("--host") + 1] == "127.0.0.1"
    assert "0.0.0.0" not in command
    port = int(command[command.index("--port") + 1])
    assert 1024 < port < 65536
    assert command[command.index("--ctx-size") + 1] == str(chosen.context_tokens)
    assert command[command.index("--cache-type-k") + 1] == chosen.kv_k
    assert command[command.index("--cache-type-v") + 1] == chosen.kv_v
    server.close()
    assert started.get("stopped")


def test_a_quantised_cache_asks_for_flash_attention(monkeypatch, tmp_path):
    """llama.cpp will not quantise the cache without it."""
    seen = {}
    monkeypatch.setattr(engine.subprocess, "Popen",
                        lambda command, **kw: seen.setdefault("cmd", command)
                        or _StoppedProcess())
    monkeypatch.setattr(engine.Server, "_wait", lambda self: None)
    chosen = plan.resolve_plan(plan.LLAMACPP, ram=2.4, total=4.0, cores=2)
    assert chosen.kv_v == "q4_0"
    engine.Server("/usr/bin/llama-server", str(tmp_path / "m.gguf"), chosen)
    assert "--flash-attn" in seen["cmd"]


class _StoppedProcess:
    returncode = 0

    def poll(self):
        return 0

    def terminate(self):
        pass

    def wait(self, timeout=None):
        return 0


def test_a_server_that_dies_before_answering_says_so(monkeypatch, tmp_path):
    monkeypatch.setattr(engine.subprocess, "Popen",
                        lambda command, **kw: _StoppedProcess())
    chosen = plan.resolve_plan(plan.LLAMACPP, ram=32.0, total=64.0, cores=4)
    with pytest.raises(SummaryError) as raised:
        engine.Server("/usr/bin/llama-server", str(tmp_path / "m.gguf"), chosen)
    assert "llama-server" in str(raised.value)


# --- the whole run, with the runtime stubbed ------------------------------

class FakePipeline:
    """Answers with a well-formed summary, and remembers being closed."""

    made = []

    def __init__(self):
        self.asked = []
        self.closed = False
        FakePipeline.made.append(self)

    def ask(self, system, user, max_new_tokens=None, think=False):
        self.asked.append({"prompt": user, "tokens": max_new_tokens,
                           "think": think})
        return "## In breve\nUn riassunto vero.\n\n## Punti chiave\n- [0:08] Budget."

    def close(self):
        self.closed = True


@pytest.fixture
def stubbed(monkeypatch, tmp_path):
    FakePipeline.made = []
    monkeypatch.setattr(plan, "available_ram_gb", lambda: 32.0)
    monkeypatch.setattr(plan, "total_ram_gb", lambda: 64.0)
    monkeypatch.setattr(plan, "physical_cores", lambda: 4)
    monkeypatch.setattr(engine, "available_ram_gb", lambda: 32.0)
    monkeypatch.setattr(engine, "total_ram_gb", lambda: 64.0)
    monkeypatch.setattr(engine, "fetch",
                        lambda model, quant, models_dir=None: str(tmp_path / "m.gguf"))
    monkeypatch.setattr(engine, "open_pipeline",
                        lambda path, chosen, settings=None: FakePipeline())
    return FakePipeline


def test_a_transcript_is_summarised_and_the_model_is_let_go(stubbed):
    sections, note = engine.summarize(material(), {})
    assert sections.abstract == "Un riassunto vero."
    assert len(stubbed.made) == 1
    assert stubbed.made[0].closed


def test_one_model_is_loaded_for_the_whole_run(stubbed):
    """Reloading per prompt would cost more than the prompts do."""
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    engine.summarize(material(many), {"summary_chunk_tokens": 120})
    assert len(stubbed.made) == 1
    assert len(stubbed.made[0].asked) > 2


def test_the_model_is_let_go_even_when_the_summary_fails(stubbed, monkeypatch):
    monkeypatch.setattr(FakePipeline, "ask",
                        lambda self, system, user, max_new_tokens=None,
                        think=False: "   ")
    with pytest.raises(SummaryError):
        engine.summarize(material(), {})
    assert stubbed.made[0].closed


def test_the_page_is_told_which_model_wrote_it(stubbed):
    assert engine.LABEL in engine.label({})
    assert "MiniCPM" in engine.label({"summary_model": "MiniCPM5-1B"})


def test_a_gguf_file_given_by_hand_is_used_as_it_is(stubbed, tmp_path, monkeypatch):
    mine = tmp_path / "mio-modello.gguf"
    mine.write_bytes(b"GGUF")
    monkeypatch.setattr(engine, "fetch",
                        lambda *a, **k: pytest.fail("it fetched anyway"))
    sections, _ = engine.summarize(material(), {"summary_model": str(mine)})
    assert sections.abstract


# --- not reading the same chunk twice -------------------------------------

def test_a_second_run_over_the_same_recording_re_reads_nothing(stubbed, tmp_path):
    """The point of the cache, on a machine where a pass is minutes.

    Asking again at a different length must re-use every pass and only write
    the page again."""
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    cache = {"cache_dir": str(tmp_path / "cache"), "summary_chunk_tokens": 120}

    engine.summarize(material(many), cache)
    first = len([call for call in stubbed.made[0].asked
                 if call["prompt"].startswith("Questa e' la parte")])
    assert first > 1

    engine.summarize(material(many), dict(cache, summary_length="short"))
    second = len([call for call in stubbed.made[1].asked
                  if call["prompt"].startswith("Questa e' la parte")])
    assert second == 0
    assert stubbed.made[1].asked, "the page was still written"


def test_a_changed_prompt_invalidates_what_was_cached(stubbed, tmp_path, monkeypatch):
    """A cache that survives a prompt change is a bug that accumulates."""
    from audio_transcriber.summarizers import prompting

    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    cache = {"cache_dir": str(tmp_path / "cache"), "summary_chunk_tokens": 120}
    engine.summarize(material(many), cache)

    monkeypatch.setattr(prompting, "PROMPT_VERSION", prompting.PROMPT_VERSION + 1)
    engine.summarize(material(many), cache)
    again = [call for call in stubbed.made[1].asked
             if call["prompt"].startswith("Questa e' la parte")]
    assert again


def test_a_cache_that_cannot_be_written_costs_nothing_but_time(stubbed,
                                                               monkeypatch):
    from audio_transcriber.summarizers import partials

    monkeypatch.setattr(partials, "put", lambda *a, **k: False)
    monkeypatch.setattr(partials, "get", lambda *a, **k: None)
    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    sections, _ = engine.summarize(material(many), {"summary_chunk_tokens": 120})
    assert sections.abstract


def test_answers_nobody_comes_back_for_are_swept_away(stubbed, tmp_path,
                                                      monkeypatch):
    """The program has no daemon, so writing is the only time to tidy up."""
    import os
    import time

    from audio_transcriber.summarizers import partials

    cache = {"cache_dir": str(tmp_path / "cache"), "summary_chunk_tokens": 120}
    stale = partials._path("ff" + "0" * 62, cache["cache_dir"])
    os.makedirs(os.path.dirname(stale), exist_ok=True)
    Path(stale).write_text("an answer from last month", encoding="utf-8")
    old = time.time() - (partials.KEEP_DAYS + 1) * 86400
    os.utime(stale, (old, old))

    many = [Sentence(f"Frase numero {n} del verbale.", n * 10.0) for n in range(60)]
    engine.summarize(material(many), cache)
    assert not os.path.exists(stale)


def test_a_binding_too_old_for_the_template_still_answers(monkeypatch):
    """It costs the tokens the narration takes, and nothing else.

    Claiming to have switched reasoning off would be worse than paying for
    it: the symptom of a switch that silently failed is a truncated answer
    several passes later."""
    seen = []

    class OldBinding:
        def create_chat_completion(self, messages, **kwargs):
            seen.append(kwargs)
            if "chat_template_kwargs" in kwargs:
                raise TypeError("unexpected keyword argument")
            return {"choices": [{"message": {"content": "Un riassunto."}}]}

    binding = engine.Binding.__new__(engine.Binding)
    binding.model = OldBinding()
    binding.template_kwargs = True
    binding.formatter = None            # this model publishes no template

    assert binding.ask("sys", "user", 100) == "Un riassunto."
    assert binding.template_kwargs is False
    assert binding.ask("sys", "user", 100) == "Un riassunto."
    # Asked once, refused, and never asked again.
    assert sum("chat_template_kwargs" in call for call in seen) == 1


def test_the_models_own_template_is_how_reasoning_is_turned_off():
    """A binding that cannot pass the variable is not the end of the road.

    The variable lives in the model's own chat template, and the template is
    in the model's metadata, so it can be rendered here instead. Without this
    a reasoning model narrates until its allowance runs out and comes back
    with nothing — which looks from the outside like a model too small for the
    job, and is not."""
    rendered, asked = [], []

    class Formatter:
        def __call__(self, messages, **kwargs):
            rendered.append(kwargs)

            class Response:
                prompt = "<|im_start|>assistant\n<think>\n\n</think>\n\n"
                stop = ["<|im_end|>"]
            return Response()

    class Model:
        def create_completion(self, prompt, **kwargs):
            asked.append(prompt)
            return {"choices": [{"text": " Un riassunto vero."}]}

        def create_chat_completion(self, messages, **kwargs):
            pytest.fail("it went through the chat path anyway")

    binding = engine.Binding.__new__(engine.Binding)
    binding.model, binding.formatter = Model(), Formatter()
    binding.template_kwargs = True

    assert binding.ask("sys", "user", 200) == "Un riassunto vero."
    assert rendered == [{"enable_thinking": False}]
    assert "</think>" in asked[0]
