"""The engine that writes without an accelerator: a GGUF, through llama.cpp.

This is the engine for the machine the rest of this feature is about — a
server with two cores, no GPU and a few gigabytes of memory. OpenVINO is not
installed there and would not help if it were; without this, such a machine is
the only one that never gets prose, which is the wrong way round.

What makes it fit where the other engine does not:

*nothing to convert*
    a GGUF is downloaded already quantised and is loaded as it arrives. No
    ``transformers``, no ``optimum``, no conversion step that needs more
    memory than the model itself.
*the weights are mapped, not read*
    the file stays on disk and the kernel pages in what is used, so a model
    larger than the free memory is slow rather than fatal.
*the cache is quantisable, separately for keys and values*
    which is where the plan's ``kv_k`` and ``kv_v`` go, and the reason they
    are two fields rather than one.

It is also, and this was not the plan, the engine for a machine that *has*
an accelerator. The other engine converts a model to OpenVINO IR first, and
that conversion is where the larger models fail; llama.cpp takes the GGUF as
it is and asks its own backend — Vulkan, SYCL, OpenVINO — to run it. So the
same file that writes on two cores writes on an Arc, and which of the two
happens is a question put to the binary rather than assumed here.

Two ways in, and both are supported because they suit different machines. The
Python binding is one ``pip install`` on a desktop. The ``llama-server``
binary is a single file with no Python at all, which is what somebody
administering a server would rather deploy. Whichever is present is used; the
binding first, because it needs no process and no port.

**Nothing leaves this machine.** Downloading a model is a separate, announced
step; the server is bound to the loopback address on a port nobody else is
told about, and the summary itself never touches the network. That is the
same promise the rest of the program makes, and the reason it exists.
"""
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from .. import paths
from ..hardware import available_ram_gb, module_available, total_ram_gb
from ..i18n import t
from ..summary import NotEnoughMemory, SummaryError
from . import plan, reading

NAME = "llamacpp"

#: How the page names this engine. The model is appended when it is known.
LABEL = "llama.cpp"

#: Where GGUF files are kept, under the managed model directory — the same
#: namespace the other engine's converted models use, because from the user's
#: side they are the same thing: the models that write summaries.
NAMESPACE = "summary"

#: The binary, when the binding is not installed.
SERVER = "llama-server"

#: Where to look for it besides the ``PATH``. Named like the other path
#: overrides so that a server administrator can set it the same way.
ENV_SERVER = "AUDIO_TRANSCRIBER_LLAMA_SERVER"

#: Where the GGUF files come from. A model download is the one moment this
#: engine uses the network, and it says so before it starts.
HUB = "https://huggingface.co/{repo}/resolve/main/{file}"

#: How long to wait for the server to answer, and how long for one prompt.
#: A map pass on two cores is minutes, not seconds, and a timeout that
#: expires mid-summary would waste every pass before it.
STARTUP_TIMEOUT = 120.0
ANSWER_TIMEOUT = 1800.0

#: ggml type numbers for the cache, for the binding — the server takes the
#: names. Only the three the plan can produce are listed; anything else is a
#: bug in the plan rather than a case to handle here.
GGML_TYPES = {"f16": 1, "q4_0": 2, "q8_0": 8}

#: How ``llama-server --list-devices`` announces one: an indent, a name, a
#: colon, and a description.
#:
#:     Available devices:
#:       Vulkan0: Intel(R) Arc(TM) 140V GPU (16GB) (18413 MiB, 17645 MiB free)
#:
#: The log lines it writes around them start at the left margin, so the indent
#: is what tells a device from the rest of the output.
_DEVICE_LINE = re.compile(r"^ {2,}([A-Za-z][A-Za-z0-9_.]*):\s+(\S.*?)\s*$")

#: Names that are the processor under another name, and so are not a reason
#: to prefer the binary over the binding.
_PROCESSOR = ("cpu", "blas", "accelerate")

#: What "all of them" is to llama.cpp: more layers than any model has.
EVERY_LAYER = 999

#: How long to wait for a binary to say what it can see. Asking is one short
#: process, but it loads the backend to do it, and a cold Vulkan driver on a
#: laptop takes its time.
LIST_TIMEOUT = 30.0

#: What each binary answered, so that a summary costs one such process and
#: not one per chunk. Keyed by path and modification time: a binary replaced
#: by another build is a different binary.
_DEVICES = {}


def read_devices(written):
    """The devices named in what ``--list-devices`` wrote, as (name, what)."""
    found = []
    for line in str(written or "").splitlines():
        match = _DEVICE_LINE.match(line)
        if match:
            found.append((match.group(1), match.group(2)))
    return found


def devices(binary):
    """What this binary says it can run on.

    Asked of the binary rather than worked out here, because two builds of
    llama.cpp on one machine answer differently — a Vulkan build sees the
    Arc, an OpenVINO build sees the OpenVINO runtime, a plain one sees
    neither — and only the binary knows which it is. A build too old for the
    flag answers nothing, which reads as a processor and is the truth as far
    as this program can act on it."""
    try:
        stamp = os.path.getmtime(binary)
    except OSError:
        stamp = None
    key = (binary, stamp)
    if key in _DEVICES:
        return _DEVICES[key]
    try:
        done = subprocess.run([binary, "--list-devices"], timeout=LIST_TIMEOUT,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        written = (done.stdout or b"") + b"\n" + (done.stderr or b"")
        found = read_devices(written.decode("utf-8", "replace"))
    except (OSError, ValueError, subprocess.SubprocessError):
        found = []
    _DEVICES[key] = found
    return found


def is_processor(name):
    """Whether a device name is the processor rather than an accelerator."""
    return str(name).lower().startswith(_PROCESSOR)


def resolve_device(binary, requested=None):
    """Which device to run on: (name, what), or None for the processor.

    ``auto`` takes the first accelerator the binary can see, because nobody
    installs a Vulkan build of llama.cpp in order to run on two cores.
    Anything else is matched against what it listed, by name or by the family
    in front of the number, so that ``vulkan`` finds ``Vulkan0``."""
    asked = str(requested or "auto").strip()
    found = devices(binary) if binary else []
    usable = [pair for pair in found if not is_processor(pair[0])]
    if asked.lower() in ("", "auto"):
        return usable[0] if usable else None
    if asked.lower() in ("cpu", "none"):
        return None
    for name, what in found:
        if name.lower() == asked.lower() or name.lower().startswith(asked.lower()):
            return None if is_processor(name) else (name, what)
    print(t("openvino.device_unavailable", requested=asked,
            found=", ".join(name for name, _what in found) or "-",
            fallback="CPU"), file=sys.stderr)
    return None


def device_for(binary, settings=None):
    """The device and what to put on it: ``(device, gpu_layers)``.

    All of the layers or none of them. A model with half its layers on an
    integrated GPU is slower than a model wholly on the processor, because
    every token then crosses the bus twice; and what fits is the plan's
    business, which sizes against system memory — the same memory an
    integrated GPU uses, whatever its driver reports as free.

    ``gpu_layers`` of None means say nothing and let llama.cpp keep its own
    default, which is what happens when nobody asked for anything and nothing
    was found."""
    asked = str((settings or {}).get("summary_device") or "auto").strip()
    device = resolve_device(binary, asked)
    if device:
        return device, EVERY_LAYER
    return None, 0 if asked.lower() in ("cpu", "none") else None


def _binding_layers(settings=None):
    """What to offload in process, which can only be what was asked for.

    The binding cannot be asked what it can see the way the binary can, so
    ``auto`` stays on the processor: the wheel ``pip`` installs is built for
    one, and a number this module invented would be a promise it cannot
    keep."""
    asked = str((settings or {}).get("summary_device") or "auto").strip().lower()
    return 0 if asked in ("", "auto", "cpu", "none") else EVERY_LAYER


def device_label(device, chosen=None, gpu_layers=None):
    """How the line on the screen names where the model went."""
    if device:
        return f"{device[0]} ({device[1]})"
    if gpu_layers:
        return "GPU"
    threads = getattr(chosen, "threads", None)
    return f"CPU x{threads}" if threads else "CPU"


def server_path(settings=None):
    """The ``llama-server`` binary, or None.

    Three places, in the order somebody would expect: what the configuration
    says, the environment override, and the ``PATH``."""
    for candidate in ((settings or {}).get("summary_llama_server"),
                      os.environ.get(ENV_SERVER)):
        if candidate and os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return shutil.which(SERVER)


def is_available(settings=None):
    """Whether either way in is present on this machine."""
    return module_available("llama_cpp") or bool(server_path(settings))


def models_root(models_dir=None):
    """Where the GGUF files live."""
    return (os.path.join(models_dir, NAMESPACE) if models_dir
            else paths.models_dir(NAMESPACE))


def gguf_name(model, quant):
    """The file this model is published as, at this quantisation."""
    if not model.gguf_file:
        return None
    return model.gguf_file.format(quant=quant)


def model_path(model, quant, models_dir=None):
    """Where that file is kept once it has been fetched."""
    name = gguf_name(model, quant)
    return os.path.join(models_root(models_dir), name) if name else None


def fetch(model, quant, models_dir=None):
    """Return the GGUF, downloading it once if it is not here yet.

    No conversion: what is downloaded is what is loaded, which is half the
    reason this engine exists. The size is checked against what the server
    said it was sending, because a download cut short leaves a file that looks
    like a model and fails at the first prompt — days later, on somebody
    else's machine."""
    target = model_path(model, quant, models_dir)
    if target is None:
        raise SummaryError(t("summary.no_gguf", model=model.name))
    if os.path.exists(target):
        return target

    url = HUB.format(repo=model.gguf_repo, file=os.path.basename(target))
    paths.ensure(os.path.dirname(target))
    print(t("summary.downloading", model=model.name, quant=quant),
          file=sys.stderr)
    partial = target + ".part"
    try:
        with urllib.request.urlopen(url, timeout=60) as response:
            expected = int(response.headers.get("Content-Length") or 0)
            written = 0
            with open(partial, "wb") as handle:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    handle.write(block)
                    written += len(block)
        if expected and written != expected:
            raise SummaryError(t("summary.download_truncated", model=model.name,
                                 got=written, expected=expected))
    except SummaryError:
        _discard(partial)
        raise
    except Exception as exc:
        _discard(partial)
        raise SummaryError(t("summary.download_failed", model=model.name,
                             error=exc)) from exc
    os.replace(partial, target)
    print(t("summary.model_ready", path=target), file=sys.stderr)
    return target


def _discard(path):
    """Remove a half-written download; a missing one is already gone."""
    try:
        os.remove(path)
    except OSError:
        pass


def resolve_model(model=None, settings=None):
    """What to load: a file as given, or whatever the plan chose."""
    name = str(model or "auto").strip()
    if name and name.lower() != "auto":
        return name
    chosen = plan.resolve_plan(plan.LLAMACPP, settings or {})
    return None if chosen is None else chosen.model.name


class Binding:
    """The model in this process, through ``llama-cpp-python``."""

    def __init__(self, path, chosen, gpu_layers=0):
        try:
            import llama_cpp
        except ImportError:                     # pragma: no cover - see Server
            raise SummaryError(t("summary.llamacpp_missing")) from None
        where = device_label(None, chosen, gpu_layers)
        print(t("summary.loading_model", path=os.path.basename(path),
                device=where), file=sys.stderr)
        try:
            self.model = llama_cpp.Llama(
                model_path=path, n_ctx=chosen.context_tokens,
                n_threads=chosen.threads, logits_all=False, verbose=False,
                n_gpu_layers=int(gpu_layers or 0),
                type_k=GGML_TYPES.get(chosen.kv_k, 1),
                type_v=GGML_TYPES.get(chosen.kv_v, 1),
                flash_attn=chosen.kv_k != "f16" or chosen.kv_v != "f16")
        except Exception as exc:
            raise SummaryError(t("summary.load_failed", device=where,
                                 error=exc)) from exc
        #: Whether this binding will pass arguments through to the chat
        #: template. Newer ones will and older ones raise; there is no way to
        #: ask beforehand, so it is discovered once and remembered.
        self.template_kwargs = True
        self.formatter = self._own_template()

    def _own_template(self):
        """A renderer for the model's own chat template, or None.

        The way to turn reasoning off is a variable in that template, and a
        binding too old to pass one leaves no other route — so the template is
        taken out of the model's metadata and rendered here instead. It is
        worth the reach: a reasoning model whose reasoning cannot be turned
        off spends its whole allowance narrating, is cut off before the answer
        begins, and looks from the outside exactly like a model too small for
        the job.

        None when the model has no template, or when its template has no such
        variable, and then nothing here pretends otherwise."""
        try:
            from llama_cpp import llama_chat_format

            template = (self.model.metadata or {}).get("tokenizer.chat_template")
            if not template or "enable_thinking" not in template:
                return None
            return llama_chat_format.Jinja2ChatFormatter(
                template=template,
                eos_token=self.model.metadata.get("tokenizer.ggml.eos_token", "</s>"),
                bos_token=self.model.metadata.get("tokenizer.ggml.bos_token", "<s>"),
                stop_token_ids=None, add_generation_prompt=True)
        except Exception:               # pragma: no cover - runtime dependent
            return None

    def ask(self, system, user, max_new_tokens=None, think=False):
        """One prompt, one answer, greedily.

        Turning reasoning off is the model's chat template's business, and
        reaching it means passing arguments through the binding. Where the
        binding is too old for that, the request goes without: the narration
        is stripped from the answer either way, it is only the token budget
        that pays for it. Pretending to have switched it off would be worse
        than paying."""
        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": user}]
        options = {"max_tokens": int(max_new_tokens or 512), "temperature": 0.0}
        if not think and self.formatter is not None:
            rendered = self.formatter(messages=messages, enable_thinking=False)
            answer = self.model.create_completion(
                rendered.prompt, stop=rendered.stop or [], **options)
            choices = answer.get("choices") or [{}]
            return str(choices[0].get("text") or "").strip()
        if not think and self.template_kwargs:
            try:
                return self._content(self.model.create_chat_completion(
                    messages=messages,
                    chat_template_kwargs={"enable_thinking": False}, **options))
            except TypeError:
                self.template_kwargs = False
        return self._content(self.model.create_chat_completion(
            messages=messages, **options))

    @staticmethod
    def _content(answer):
        choices = answer.get("choices") or [{}]
        return str(choices[0].get("message", {}).get("content") or "").strip()

    def close(self):
        self.model = None


class Server:
    """The model in a ``llama-server`` process, spoken to over the loopback.

    The zero-dependency way in: one binary, no Python bindings to build. The
    process is ours for the length of one summary and is stopped in a
    ``finally``, the port is whatever the kernel had free, and the bind
    address is ``127.0.0.1`` — this must not become a way to serve a model to
    a network."""

    def __init__(self, binary, path, chosen, device=None, gpu_layers=None):
        self.port = _free_port()
        self.process = None
        self.log = None
        command = [binary, "--model", path, "--host", "127.0.0.1",
                   "--port", str(self.port), "--ctx-size",
                   str(chosen.context_tokens), "--threads", str(chosen.threads),
                   "--cache-type-k", chosen.kv_k, "--cache-type-v", chosen.kv_v,
                   "--no-warmup"]
        if chosen.kv_k != "f16" or chosen.kv_v != "f16":
            # A quantised cache needs flash attention in llama.cpp; recent
            # builds pick it automatically, older ones have to be told.
            command += ["--flash-attn", "on"]
        if device:
            command += ["--device", device[0]]
        if gpu_layers is not None:
            command += ["--n-gpu-layers", str(int(gpu_layers))]
        where = device_label(device, chosen, gpu_layers)
        print(t("summary.loading_model", path=os.path.basename(path),
                device=where), file=sys.stderr)
        try:
            # Kept rather than discarded: when a server will not start, what
            # it wrote on its way out is the only thing that says why, and a
            # temporary file cannot fill up and block the process the way a
            # pipe nobody is reading does.
            self.log = tempfile.TemporaryFile()
            self.process = subprocess.Popen(
                command, stdout=subprocess.DEVNULL, stderr=self.log)
        except OSError as exc:
            self._forget_log()
            raise SummaryError(t("summary.load_failed", device=where,
                                 error=exc)) from exc
        self._wait()

    def _wait(self):
        """Poll until it answers, backing off, and give up rather than hang."""
        deadline, delay = time.time() + STARTUP_TIMEOUT, 0.2
        while time.time() < deadline:
            code = self.process.poll()
            if code is not None:
                said = self._said()
                self.close()
                raise SummaryError(t("summary.server_stopped", code=code)
                                   + said)
            try:
                with urllib.request.urlopen(
                        f"http://127.0.0.1:{self.port}/health", timeout=2) as answer:
                    if answer.status == 200:
                        return
            except Exception:
                pass
            time.sleep(delay)
            delay = min(2.0, delay * 1.6)
        said = self._said()
        self.close()
        raise SummaryError(t("summary.server_silent",
                             seconds=int(STARTUP_TIMEOUT)) + said)

    def ask(self, system, user, max_new_tokens=None, think=False):
        """One prompt, one answer, over the loopback and nowhere else."""
        body = {"messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "max_tokens": int(max_new_tokens or 512),
                "temperature": 0.0, "stream": False}
        if not think:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=ANSWER_TIMEOUT) as answer:
                payload = json.loads(answer.read().decode("utf-8"))
        except Exception as exc:
            raise SummaryError(t("summary.server_failed", error=exc)) from exc
        choices = payload.get("choices") or [{}]
        return str(choices[0].get("message", {}).get("content") or "").strip()

    def _said(self, lines=15):
        """The last thing the server wrote, for when it will not start.

        Its own words, in its own language, with ours in front of them: a
        wrong flag, a file that is not a GGUF and a driver that would not
        load all look the same from out here, and all three say so plainly in
        that log."""
        if self.log is None:
            return ""
        try:
            self.log.seek(0)
            written = self.log.read().decode("utf-8", "replace")
        except (OSError, ValueError):           # pragma: no cover - closed
            return ""
        tail = [line for line in written.splitlines() if line.strip()][-lines:]
        return "\n" + t("summary.server_said") + "\n" + "\n".join(
            f"  {line}" for line in tail) if tail else ""

    def _forget_log(self):
        """Let go of the log file, which deletes it."""
        log, self.log = self.log, None
        if log is not None:
            try:
                log.close()
            except OSError:                     # pragma: no cover - closed
                pass

    def close(self):
        """Stop the process, and do not leave it behind if it will not stop."""
        process, self.process = self.process, None
        self._forget_log()
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:       # pragma: no cover - stubborn
            process.kill()
            process.wait(timeout=10)


def _free_port():
    """A port the kernel says is free, on the loopback interface."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def open_pipeline(path, chosen, settings=None):
    """Load the model whichever way this machine offers.

    An accelerator first, wherever it is: a binary that can see one beats a
    binding that cannot, and the binding ``pip`` installs is built for the
    processor. Then the binding, which needs no process, no port and no
    health check. Then the binary on the processor, which is the machine this
    engine was written for."""
    binary = server_path(settings)
    device, layers = device_for(binary, settings) if binary else (None, None)
    if binary and device:
        return Server(binary, path, chosen, device, layers)
    if module_available("llama_cpp"):
        return Binding(path, chosen, _binding_layers(settings))
    if binary:
        return Server(binary, path, chosen, device, layers)
    raise SummaryError(t("summary.llamacpp_missing"))


def summarize(material, settings=None, progress=None):
    """Write the summary, in one pass or as a tree of them.

    Everything between having a model and having a page is shared with the
    other engine that writes, in
    :mod:`~audio_transcriber.summarizers.reading`. What is here is the model's
    life cycle, which is the only part that is about llama.cpp."""
    settings = settings or {}
    given = str(settings.get("summary_model") or "auto").strip()
    by_name = bool(given) and given.lower() != "auto"
    refused, last = [], None
    while True:
        try:
            chosen = reading.choose(plan.LLAMACPP, settings, available_ram_gb(),
                                    total_ram_gb(), skip=refused)
        except NotEnoughMemory as no_room:
            if last is not None:
                raise last from no_room
            raise

        if by_name and os.path.isfile(given):
            path, name = given, os.path.basename(given)
        else:
            path, name = None, chosen.model.name

        def start(path=path, chosen=chosen):
            target = path or fetch(chosen.model, chosen.quant,
                                   settings.get("models_dir"))
            try:
                return open_pipeline(target, chosen, settings)
            except SummaryError as exc:
                if by_name:
                    raise
                raise _Refused(exc) from exc

        try:
            return reading.summarize_with(start, chosen, material, settings,
                                          progress, model_name=name)
        except _Refused as refusal:
            # A build of llama.cpp older than the model's architecture refuses
            # the file when it loads it, before anything is read: the next
            # model down is a summary, the refusal is not. A model named by
            # hand is not replaced, as on the other engine.
            last = refusal.error
            print(t("summary.model_unusable_next", model=name, error=last),
                  file=sys.stderr)
            refused.append(chosen.model.name)


class _Refused(Exception):
    """A model this installation would not load, carrying why."""

    def __init__(self, error):
        super().__init__(str(error))
        self.error = error


def label(settings=None):
    """How the page should name this engine, model included."""
    settings = settings or {}
    name = resolve_model(settings.get("summary_model"), settings)
    return f"{LABEL} — {name}" if name else LABEL
