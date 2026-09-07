"""Audio Transcriber: audio and video to readable text, entirely on your machine.

Whisper transcription on two interchangeable backends — OpenVINO for Intel
iGPU/NPU/CPU, and faster-whisper (CTranslate2, int8) for CPU-only servers or
CUDA — chosen automatically from the hardware. Optional speaker diarization
with pyannote on the CPU.
"""
__version__ = "0.3.0"
__all__ = ["__version__"]
