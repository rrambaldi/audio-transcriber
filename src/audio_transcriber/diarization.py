"""Speaker diarization with pyannote, and mapping speakers onto segments.

pyannote runs on the CPU here. It can work fully offline from local files, or
online from the Hugging Face repository with a token.

Offline comes in two shapes, and both are accepted, because pyannote changed
its mind between versions. A 3.x setup is a hand-written ``config.yaml``
pointing at weights elsewhere on the disk; a 4.x one is a whole cloned
repository — ``config.yaml`` plus the weights beside it — and the directory
itself is what you hand over. The paths inside a config are resolved by
pyannote against the *working directory*, which is why a folder that is
plainly there stops being found the moment the program is started from
somewhere else; :func:`localised_config` settles them against the config's own
folder first, so where you started from stops mattering.
"""
import os
import re
import sys

from .audio import SAMPLE_RATE
from .cleaning import clean_text
from .hardware import module_available
from .i18n import t

DEFAULT_PIPELINE = "pyannote/speaker-diarization-3.1"

#: Extensions that mark a config entry as a path rather than a repo id.
_WEIGHT_SUFFIXES = (".bin", ".pt", ".ckpt", ".onnx", ".safetensors")
_CONFIG_SUFFIXES = (".yaml", ".yml")


def looks_like_path(value):
    """Whether a value names something on this disk rather than a hub repo.

    A slash alone cannot decide it: a repo id is ``owner/name`` and has one
    too, which is how ``--diar-model pyannote/speaker-diarization-community-1``
    used to be mistaken for a missing file and quietly replaced by the default
    pipeline. What tells them apart is everything else — a file extension, a
    backslash, a leading dot or root, or a second slash."""
    if not value:
        return False
    if value.lower().endswith(_WEIGHT_SUFFIXES + _CONFIG_SUFFIXES):
        return True
    if "\\" in value or os.path.isabs(value) or value.startswith((".", "~")):
        return True
    return value.count("/") != 1


#: Why diarization cannot run here, if it cannot.
NOT_INSTALLED = "not_installed"
NO_MODEL = "no_model"
READY = "ready"


def availability(model=None, token=None):
    """``(state, detail)``: can this machine work out who said what?

    Asked before anything is offered rather than after an upload, so a front
    end can grey the option out and say why instead of accepting a job that is
    going to fail. Imports nothing heavy: pyannote pulls in PyTorch."""
    if not module_available("pyannote.audio"):
        return NOT_INSTALLED, "pyannote.audio"
    from . import paths

    # Local files first, because that is the order the run itself uses: with
    # both a token and a folder of models, the folder is what gets loaded.
    # Reported the other way round, "available (token)" said the network would
    # be used on a machine that had not needed it for weeks.
    config = model or paths.diarization_config()
    if os.path.exists(config_in(config)):
        return READY, config
    token = token or os.environ.get("HUGGINGFACE_TOKEN") or os.environ.get("HF_TOKEN")
    if token:
        return READY, "token"
    return NO_MODEL, config


#: The file a cloned pipeline repository is recognised by.
CONFIG_NAME = "config.yaml"

#: Keys in a pyannote config whose value is a model: a repo id, or a file.
_MODEL_KEYS = r"(embedding|segmentation)"


def config_in(model):
    """The config file for ``model``, which may name a directory.

    pyannote 4 keeps a pipeline and its weights in one repository and is handed
    the directory; everything before it was handed a ``config.yaml``. Both are
    allowed here, so a folder cloned from the hub works without anybody having
    to know which of the two shapes it is."""
    if os.path.isdir(model):
        return os.path.join(model, CONFIG_NAME)
    return model


def resolve_reference(value, base):
    """Where a path written inside a config really is, or None.

    Tried in the order that keeps an existing setup working: as pyannote
    itself would read it (against the working directory), then beside the
    config, then one level up — which is where a config that names its own
    folder, ``pyannote-diar/segmentation/...``, expects to be read from.

    Then, and only then, the same path with its leading folders dropped one
    at a time, looked for under the config's own folder. That is for the
    folder that has been moved or renamed since its config was written —
    dropped into the managed ``diarization/`` directory, say, while the
    config still calls it ``pyannote-diar``. The tail has to match exactly,
    so this finds the file that was meant or nothing at all."""
    if os.path.isabs(value):
        return value if os.path.exists(value) else None
    parts = value.replace("\\", "/").split("/")
    candidates = [value,
                  os.path.join(base, value),
                  os.path.join(os.path.dirname(base), value)]
    candidates += [os.path.join(base, *parts[cut:])
                   for cut in range(1, len(parts))]
    for candidate in candidates:
        if os.path.exists(candidate):
            return os.path.abspath(candidate)
    return None


def weights_near(base, limit=12):
    """Model files found under ``base``, as written for a person to read.

    What turns "the config references files that do not exist" from a dead
    end into something to do: the names that *are* there, next to the ones
    that are not. Two levels deep, because that is how these folders are
    shaped — one directory per model, the weights inside."""
    found = []
    base = os.path.abspath(base)
    for root, _dirs, files in os.walk(base):
        depth = root[len(base):].count(os.sep)
        for name in sorted(files):
            if name.lower().endswith(_WEIGHT_SUFFIXES):
                found.append(os.path.relpath(os.path.join(root, name), base))
                if len(found) >= limit:
                    return found
        if depth >= 2:
            _dirs[:] = []
    return found


def config_references(content):
    """The ``(key, value)`` model references written in a config's text.

    Only a key with a value on its own line counts. A config also has a
    ``params:`` block where ``segmentation:`` opens a mapping and says nothing
    itself — and a pattern spelled with ``\\s``, which matches a newline,
    read the line below as its value and reported the tuning parameter as a
    model file that had gone missing."""
    references = []
    for key, value in re.findall(rf"^[ \t]*{_MODEL_KEYS}[ \t]*:[ \t]*(\S.*?)[ \t]*$",
                                 content, re.M):
        references.append((key, value.strip().strip('"').strip("'")))
    return references


def localise(content, base):
    """Rewrite a config's relative model paths as absolute ones.

    Returns ``(text, missing)``. pyannote resolves what it reads against the
    working directory, so a perfectly good folder is invisible to a program
    started from anywhere else — a window launched from the desktop, a service
    with a WorkingDirectory of its own. Settling the paths here means the
    folder is found because of where *it* is."""
    missing = []
    for key, value in config_references(content):
        if not looks_like_path(value):
            continue  # a repo id: pyannote will fetch it, token already checked
        found = resolve_reference(value, base)
        if found is None:
            missing.append((key, value))
            continue
        if found != value:
            content = replace_reference(content, key, value, found)
    return content, missing


def replace_reference(content, key, value, replacement):
    """Point one key at something else, leaving the rest of the file alone.

    A function as the replacement, not a string: a Windows path is full of
    backslashes and :func:`re.sub` would read them as escapes."""
    return re.sub(rf"^([ \t]*{key}[ \t]*:[ \t]*){re.escape(value)}[ \t]*$",
                  lambda match, settled=replacement: match.group(1) + settled,
                  content, count=1, flags=re.M)


#: A pyannote 3.1 pipeline written against files on this disk. The numbers
#: are the published ones for ``pyannote/speaker-diarization-3.1``; the two
#: paths are filled in with what was actually found, relative to this file,
#: which is what makes the folder movable.
CONFIG_TEMPLATE = """\
version: 3.1.0

pipeline:
  name: pyannote.audio.pipelines.SpeakerDiarization
  params:
    clustering: AgglomerativeClustering
    embedding: {embedding}
    embedding_batch_size: 32
    embedding_exclude_overlap: true
    segmentation: {segmentation}
    segmentation_batch_size: 32

params:
  clustering:
    method: centroid
    min_cluster_size: 12
    threshold: 0.7045654963945799
  segmentation:
    min_duration_off: 0.0
"""

#: What the two models are called, best first. A folder often holds both sets
#: — somebody downloading twice, from two sets of instructions — and the
#: template written here is the 3.1 pipeline, so its own weights win.
_EMBEDDING_NAMES = ("wespeaker", "embedding")
_SEGMENTATION_NAMES = ("segmentation-3.0", "segmentation")


def guess_models(directory):
    """``(embedding, segmentation)`` found in a folder, relative to it.

    Either may be None. Nothing is downloaded and nothing is opened: the
    files are recognised by the names pyannote publishes them under, which is
    how somebody reading the folder recognises them too."""
    found = weights_near(directory, limit=64)

    def pick(names):
        for wanted in names:
            for name in found:
                if wanted in name.lower().replace(os.sep, "/"):
                    return name
        return None

    return pick(_EMBEDDING_NAMES), pick(_SEGMENTATION_NAMES)


def looks_like_community(directory):
    """Whether this folder is a pyannote 4 clone rather than a 3.1 set.

    Its clustering is PLDA-based and reads two ``.npz`` files that the 3.1
    pipeline knows nothing about: a config written here would ignore them,
    and saying so beats writing one that quietly uses half the folder."""
    return os.path.isdir(os.path.join(directory, "plda"))


def write_config(directory, embedding, segmentation, overwrite=False):
    """Write ``config.yaml`` into ``directory`` and return its path."""
    path = os.path.join(directory, CONFIG_NAME)
    if os.path.exists(path) and not overwrite:
        raise FileExistsError(path)
    os.makedirs(directory, exist_ok=True)
    text = CONFIG_TEMPLATE.format(
        embedding=embedding.replace(os.sep, "/"),
        segmentation=segmentation.replace(os.sep, "/"))
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)
    return path


#: Variables that tell huggingface_hub not to use the network at all. Worth
#: naming, because the way past one refused file is to set one of these, and
#: the next thing anybody does is wonder why nothing downloads any more.
OFFLINE_VARIABLES = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE")


def offline_mode():
    """The variable that has switched the network off, if one has."""
    for name in OFFLINE_VARIABLES:
        value = (os.environ.get(name) or "").strip().lower()
        if value and value not in ("0", "false", "no", "off"):
            return name
    return None


def looks_unreachable(error):
    """Whether the hub was out of reach, rather than shut in our face.

    A refusal is a token or a licence; being unable to reach the hub at all
    is a network, a proxy, or offline mode — and the advice for one is no use
    for the other. huggingface_hub says so in the type where it can, and in
    the text where the type is a plain ``OSError``."""
    if type(error).__name__ in ("LocalEntryNotFoundError", "OfflineModeIsEnabled",
                                "ConnectionError", "HfHubOfflineError",
                                "ReadTimeout", "ConnectTimeout"):
        return True
    text = str(error).lower()
    return any(mark in text for mark in
               ("internet connection", "cannot find the requested files",
                "offline mode", "connection error", "max retries",
                "failed to establish a new connection"))


class DiarizationError(Exception):
    """Something that stops the models from being fetched or used."""


def _snapshot(repo, destination, token):
    """Every file of a repository, as plain files in a folder of your own.

    ``local_dir`` rather than the hub cache on purpose: the cache is a tree of
    commit hashes and symlinks that nobody can be asked to look after, and the
    whole point here is a folder that can be copied to another machine, backed
    up, or put on a stick."""
    from huggingface_hub import snapshot_download

    return snapshot_download(repo, local_dir=destination, token=token or None)


def fetch(model, destination, token=None, download=None):
    """Download a pipeline and everything it names into one folder.

    A pipeline config points at other repositories — the segmentation model,
    the embedding model — which are gated separately and, downloaded by
    pyannote itself, end up in the hub cache. Here they are fetched into
    subfolders of the same directory and the config is rewritten to point at
    them, so what is left behind is one self-contained folder of ordinary
    files that ``--diar-model`` can be handed.

    Returns ``(config path, [repositories fetched])``."""
    download = download or _snapshot
    destination = os.path.abspath(os.path.expanduser(destination))
    os.makedirs(destination, exist_ok=True)
    fetched = [model]
    try:
        download(model, destination, token)
    except Exception as exc:       # noqa: BLE001 - reported with the repo name
        raise DiarizationError(t("diarize.fetch_failed", repo=model,
                                 error=exc)) from exc

    config = os.path.join(destination, CONFIG_NAME)
    if not os.path.exists(config):
        raise DiarizationError(t("diarize.fetch_no_config", repo=model,
                                 path=destination))
    with open(config, encoding="utf-8") as handle:
        content = handle.read()

    settled = content
    for key, value in config_references(content):
        if looks_like_path(value):
            continue               # already a file inside what we just fetched
        name = value.split("/")[-1]
        folder = os.path.join(destination, name)
        try:
            download(value, folder, token)
        except Exception as exc:   # noqa: BLE001
            raise DiarizationError(t("diarize.fetch_failed", repo=value,
                                     error=exc)) from exc
        fetched.append(value)
        found = weights_near(folder, limit=1)
        if found:
            settled = replace_reference(
                settled, key, value,
                f"{name}/{found[0]}".replace(os.sep, "/"))
    if settled != content:
        with open(config, "w", encoding="utf-8") as handle:
            handle.write(settled)
    return config, fetched


def hub_repo(model):
    """The repository a run downloads when ``model`` is not on this disk.

    The same decision :func:`resolve_model` makes, without the announcement:
    a path that leads nowhere falls back to the default pipeline, and it is
    that pipeline — not the path somebody typed — whose conditions have to be
    accepted."""
    return DEFAULT_PIPELINE if looks_like_path(model) else model


def hub_check(model, token):
    """Ask the hub whether this token may actually read this pipeline.

    ``[(repo, error or None)]``, the pipeline first and then every model its
    config names — because they are separate gated repositories and the
    conditions are accepted one at a time, which is how somebody ends up with
    the pipeline downloaded and its segmentation model refused.

    Two seconds, and no model weights: the alternative is finding out an hour
    into a transcription. Nothing here raises; a hub that cannot be reached at
    all is reported like any other refusal."""
    try:
        from huggingface_hub import HfApi, hf_hub_download
    except ImportError as exc:
        return [(model, exc)]

    api = HfApi()
    try:
        api.model_info(model, token=token)
    except Exception as exc:       # noqa: BLE001 - every failure is the answer
        return [(model, exc)]

    checked = [(model, None)]
    try:
        path = hf_hub_download(model, CONFIG_NAME, token=token)
        with open(path, encoding="utf-8") as handle:
            content = handle.read()
    except Exception:              # noqa: BLE001 - the pipeline alone, then
        return checked
    for _key, value in config_references(content):
        if looks_like_path(value):
            continue               # a file in the repo, not a repo of its own
        try:
            api.model_info(value, token=token)
            checked.append((value, None))
        except Exception as exc:   # noqa: BLE001
            checked.append((value, exc))
    return checked


def check_diar_assets(model, token):
    """Pre-flight check, run before the long transcription starts.

    Exits with a clear message if something is missing, so nobody waits an hour
    for a transcript only to find the diarization cannot run. Downloads
    nothing and loads nothing heavy."""
    try:
        import pyannote.audio  # noqa: F401
    except ImportError:
        sys.exit(t("diarize.missing"))

    config = config_in(model)
    if not os.path.exists(config):
        if looks_like_path(model):
            print(t("diarize.local_config_missing", path=config))
        if not token:
            sys.exit(t("diarize.no_config_no_token"))
        print(t("diarize.online_ok", model=hub_repo(model)))
        return

    try:
        with open(config, encoding="utf-8") as handle:
            content = handle.read()
    except OSError as exc:
        sys.exit(t("diarize.config_unreadable", path=config, error=exc))

    base = os.path.dirname(os.path.abspath(config))
    _text, missing = localise(content, base)
    if missing:
        listed = "\n".join(f"    - {key}: {value}" for key, value in missing)
        nearby = weights_near(base)
        found = ("\n".join(f"    - {name}" for name in nearby) if nearby
                 else t("diarize.nothing_nearby"))
        sys.exit(t("diarize.missing_files", files=listed, path=config,
                   folder=base, found=found))
    print(t("diarize.preflight_ok", path=config))


def reads_itself(content, base):
    """Whether every model path in a config resolves inside its own folder.

    That is what a repository cloned from the hub looks like — the pipeline
    and its weights in one directory — and pyannote 4 resolves those on its
    own. Such a folder is handed over untouched, because it may refer to more
    than the two keys read here."""
    references = [value for _key, value in config_references(content)
                  if looks_like_path(value)]
    return bool(references) and all(os.path.exists(os.path.join(base, value))
                                    for value in references)


def localised_config(model):
    """What to hand pyannote for a local model: the path, or a settled copy.

    A cloned repository is handed over as it is. A ``config.yaml`` whose paths
    are relative is copied into the cache with those paths made absolute,
    because pyannote would otherwise read them against the working directory
    and find nothing. The copy is written rather than the original edited: the
    folder is the user's, and a program that rewrites what it was pointed at
    is a program nobody points anywhere twice."""
    config = config_in(model)
    try:
        with open(config, encoding="utf-8") as handle:
            content = handle.read()
    except OSError:
        return model                    # pyannote will say what it makes of it
    base = os.path.dirname(os.path.abspath(config))
    if os.path.isdir(model) and reads_itself(content, base):
        return model
    settled, missing = localise(content, base)
    if missing or settled == content:
        return model
    from . import paths

    copy = os.path.join(paths.ensure(os.path.join(paths.cache_dir(), "diarization")),
                        CONFIG_NAME)
    with open(copy, "w", encoding="utf-8") as handle:
        handle.write(settled)
    print(t("diarize.config_settled", path=config))
    return copy


def resolve_model(model):
    """The model that will really be used, decided without loading anything.

    A local file or folder stands. A path that is not there falls back to the
    default pipeline, and says so, because a silent substitution is how one
    ends up wondering which model produced a result. A repo id stands too: it
    is not a file that has gone missing."""
    if os.path.exists(model):
        return model
    if looks_like_path(model):
        print(t("diarize.config_fallback", path=model, fallback=DEFAULT_PIPELINE))
        return DEFAULT_PIPELINE
    return model


def load_pipeline(model, token):
    """The pyannote pipeline, from local files or from the hub.

    A hub failure is turned into one sentence rather than a page of traceback,
    because there are only two things it is ever about: conditions not
    accepted for that repository, or a fine-grained token without access to
    public gated repositories. Neither is visible in an HTTP 403."""
    from pyannote.audio import Pipeline

    if os.path.exists(model):
        return Pipeline.from_pretrained(localised_config(model))  # no token
    try:
        try:
            return Pipeline.from_pretrained(model, use_auth_token=token)
        except TypeError:               # newer pyannote renamed the argument
            return Pipeline.from_pretrained(model, token=token)
    except SystemExit:
        raise
    except Exception as exc:
        sys.exit(t("diarize.online_failed", model=model, error=exc))


def diarize(audio, token, num_speakers, model=DEFAULT_PIPELINE,
            sample_rate=SAMPLE_RATE):
    """Return speech turns as a list of ``(start, end, speaker_label)``.

    ``model`` is a Hugging Face id (downloaded, needs a token), the path of a
    local ``config.yaml``, or the directory of a cloned pipeline repository —
    the last two offline, with no token."""
    try:
        import torch
        from pyannote.audio import Pipeline  # noqa: F401
    except ImportError:
        sys.exit(t("diarize.missing"))

    model = resolve_model(model)
    if not os.path.exists(model) and not token:
        sys.exit(t("diarize.token_required"))

    print(t("diarize.loading", model=model))
    pipeline = load_pipeline(model, token)
    if pipeline is None:
        sys.exit(t("diarize.not_initialised"))

    pipeline.to(torch.device("cpu"))
    waveform = torch.from_numpy(audio).unsqueeze(0)  # (1, samples)
    options = {"num_speakers": num_speakers} if num_speakers else {}

    print(t("diarize.running"))
    annotation = pipeline({"waveform": waveform, "sample_rate": sample_rate}, **options)
    turns = [(segment.start, segment.end, label)
             for segment, _, label in annotation.itertracks(yield_label=True)]
    print(t("diarize.result", turns=len(turns),
            speakers=len({label for _, _, label in turns})))
    return turns


def assign_speakers(segments, turns):
    """Give each segment the speaker it overlaps with most.

    A segment without timestamps inherits the previous speaker, which is the
    least surprising guess in a conversation."""
    assigned = []
    last = turns[0][2] if turns else "SPEAKER_00"
    for segment in segments:
        start, end = segment.get("start"), segment.get("end")
        speaker = None
        if start is not None and end is not None and turns:
            best = 0.0
            for turn_start, turn_end, label in turns:
                overlap = min(end, turn_end) - max(start, turn_start)
                if overlap > best:
                    best, speaker = overlap, label
        if speaker is None:
            speaker = last
        last = speaker
        assigned.append({**segment, "speaker": speaker})
    return assigned


def format_dialogue(segments):
    """Merge consecutive segments from the same speaker into readable turns."""
    blocks, current_speaker, buffer = [], None, []
    for segment in segments:
        if segment["speaker"] != current_speaker:
            if buffer:
                blocks.append((current_speaker, clean_text(" ".join(buffer))))
            current_speaker, buffer = segment["speaker"], [segment["text"]]
        else:
            buffer.append(segment["text"])
    if buffer:
        blocks.append((current_speaker, clean_text(" ".join(buffer))))
    return "\n\n".join(f"[{speaker}] {text}" for speaker, text in blocks if text)
