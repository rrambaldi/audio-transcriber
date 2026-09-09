# Choosing a backend

Two engines run Whisper. They produce the same kind of result and take the same
options; what differs is the hardware they are good at.

| | `faster-whisper` | `openvino` |
|---|---|---|
| Install | `pip install -e ".[cpu]"` | `pip install -e ".[openvino]"` |
| Underneath | CTranslate2 | OpenVINO + optimum-intel |
| Best on | CPU-only servers, CUDA GPUs | Intel iGPU and NPU |
| Precision | int8 by default on CPU | fp32 |
| Devices | `CPU`, `CUDA` | `CPU`, `GPU`, `NPU` |
| Install size | small; no PyTorch | large; PyTorch and OpenVINO |

## How `auto` decides

`--backend auto` and `--device auto` are the defaults, and they answer two
questions in order.

1. Did you ask for a specific device? `NPU` or `GPU.0` means OpenVINO; `CUDA`
   means faster-whisper.
2. Otherwise: OpenVINO if it can see an Intel iGPU or NPU, then whichever
   engine is installed, preferring faster-whisper.

The check never imports either engine — it only asks whether the packages exist
and what devices are visible — so `audio-transcriber hardware` answers instantly
even with a full OpenVINO stack installed.

A device you asked for but that is not there is not fatal. It warns and falls
back to the CPU, which is what makes one command line work on a laptop and on a
headless server.

## Long recordings, and the doubling to watch for

Whisper hears thirty seconds at a time, so anything longer has to be broken up,
and the two engines do it differently.

faster-whisper runs Whisper's own loop: decode a window, start the next one
where the last thing understood ended. It also has a **voice-activity filter**
(`vad = true`), which cuts the silences out before the model sees them — the
surest way not to have a phrase invented over one.

OpenVINO asks for that same loop through `transformers`, and needs a recent
enough `optimum-intel` to get it. Where it cannot, it falls back to fixed
thirty-second windows with five seconds of overlap, stitched together by
matching the words two windows share — and where that match fails, over a
silence or two people talking at once, **the overlap comes out twice**. Both
copies are then cut from the transcript by the cleaning pass, but a passage
that was doubled and cut is not as good as one that was never doubled: if a
transcript comes back with sentences said twice, that fallback is what
happened, and the run says so on stderr. There is no voice-activity filter on
this backend.

On a machine with no Intel accelerator, prefer faster-whisper for both reasons.

## Precision, with faster-whisper

`--compute-type` defaults to `int8` on CPU and `float16` on CUDA. `int8` roughly
halves the memory for a barely perceptible quality cost, which is usually the
difference between a large model fitting and not fitting. If a CPU or a build
does not support it, the backend says so and falls back to `float32`.

## What to expect on a small server

Measured on a 2 vCPU Xeon (Skylake, KVM) with 3.7 GB RAM, `faster-whisper`
int8, model load included:

| model | speed | 1 hour of audio takes about |
|---|---|---|
| `tiny` | 2.0x realtime | 30 min |
| `base` | 1.0x realtime | 1 h |
| `small` | 0.6x realtime | 1 h 40 |
| `large-v3` | — | does not fit comfortably in 3.7 GB |

More cores scale this close to linearly. On a machine like that, `--model small`
is the sweet spot.

You do not have to work this out yourself: before a run, the tool warns when the
model you asked for is likely to swap, be killed for memory, or take far longer
than the recording itself.

## The VAD filter

faster-whisper runs voice-activity detection before transcribing, which cuts
silence out of the input. This matters more than it sounds: silence is exactly
what Whisper hallucinates over, inventing "Thanks for watching" and its
relatives. It is on by default; `--no-vad` turns it off.

`condition_on_previous_text` is disabled, which prevents the model from getting
stuck repeating a phrase for minutes at a time.


## Choosing the model: what `auto` does

`--model auto` is the default, and it is arithmetic rather than magic.

1. **A CUDA GPU** makes the size almost irrelevant: take `large-v3`.
2. **An Intel iGPU or NPU** through OpenVINO is limited by memory, not by
   patience: take the best model whose full-precision figure fits in the free
   RAM.
3. **On a CPU** the estimate is `cores x speed-per-core`, anchored on a
   measured machine — a 2 vCPU Xeon Skylake does `small` at 0.6x realtime,
   `base` at 1.0x, `tiny` at 2.0x. The best model that still reaches **half
   realtime** (an hour of audio in two) *and* leaves 0.8 GiB of RAM free wins.

| machine | picked |
|---|---|
| 1 core, 1.5 GiB | `base` |
| 2 cores, 1 GiB | `tiny` — memory decides before speed does |
| 2 cores, 2.8 GiB | `small` |
| 8 cores, 16 GiB | `large-v3-turbo` |
| 16 cores, 32 GiB | `large-v3` |
| any, CUDA | `large-v3` |
| Intel iGPU, 21 GiB | `large-v3` |

`large-v3-turbo` outranks `medium` on purpose: it is distilled from `large-v3`
and is both better and faster.

The numbers are approximate and the point is not precision — it is that
somebody who never chose a model does not get handed one their machine cannot
run. `audio-transcriber hardware` prints what would be chosen here, and naming
a model always overrides it. The estimate never blocks anything: it only
decides what "no answer" means.
