import os
import subprocess
import tempfile
from pathlib import Path

try:
    import imageio_ffmpeg
except ImportError:
    imageio_ffmpeg = None


MAX_FILE_SIZE_MB = 200
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
_ffmpeg_diagnostics = []


def _resolve_ffmpeg_executable():
    """Resolve ffmpeg executable path from managed helper."""
    if imageio_ffmpeg is None:
        _ffmpeg_diagnostics.append("imageio-ffmpeg is not installed.")
        return None

    try:
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        _ffmpeg_diagnostics.append(f"Failed to resolve managed ffmpeg binary: {exc}")
        return None

    if not ffmpeg_path:
        _ffmpeg_diagnostics.append("Managed ffmpeg binary path is empty.")
        return None

    if not Path(ffmpeg_path).exists():
        _ffmpeg_diagnostics.append(f"Managed ffmpeg binary not found at resolved path: {ffmpeg_path}")
        return None

    return ffmpeg_path


def _run_preflight(ffmpeg_path):
    """Validate ffmpeg binary and required codecs."""
    try:
        version_result = subprocess.run(
            [ffmpeg_path, "-version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except Exception as exc:
        _ffmpeg_diagnostics.append(f"Failed running ffmpeg version check: {exc}")
        return False

    if version_result.returncode != 0:
        _ffmpeg_diagnostics.append(f"ffmpeg -version failed: {version_result.stderr.strip()}")
        return False

    try:
        codec_result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-codecs"],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except Exception as exc:
        _ffmpeg_diagnostics.append(f"Failed running ffmpeg codec check: {exc}")
        return False

    codec_output = (codec_result.stdout or "") + (codec_result.stderr or "")
    has_vp9 = ("libvpx-vp9" in codec_output) or (" vp9 " in codec_output)
    has_opus = ("libopus" in codec_output) or (" opus " in codec_output)
    if not has_vp9:
        _ffmpeg_diagnostics.append("ffmpeg build does not expose VP9 encoding support.")
        return False
    if not has_opus:
        _ffmpeg_diagnostics.append("ffmpeg build does not expose Opus audio support.")
        return False

    _ffmpeg_diagnostics.append("Managed ffmpeg is available with VP9/Opus support.")
    return True


def is_ffmpeg_available():
    """Check whether managed ffmpeg is available and supports VP9/Opus."""
    _ffmpeg_diagnostics.clear()
    ffmpeg_path = _resolve_ffmpeg_executable()
    if not ffmpeg_path:
        return False
    return _run_preflight(ffmpeg_path)


def get_ffmpeg_diagnostics():
    """Return diagnostics for ffmpeg availability checks."""
    return _ffmpeg_diagnostics.copy()


def _format_ffmpeg_error(stderr_text):
    error_excerpt = (stderr_text or "").strip()
    if len(error_excerpt) > 1200:
        error_excerpt = error_excerpt[-1200:]
    return (
        "Video conversion failed.\n"
        "Likely cause: unsupported input container/codec or ffmpeg codec mismatch.\n"
        "Remediation: verify the input file is valid and ffmpeg supports libvpx-vp9 + libopus.\n"
        f"ffmpeg details:\n{error_excerpt}"
    )


def _input_has_audio_stream(ffmpeg_path, input_path):
    """Best-effort check for presence of audio stream in input."""
    try:
        probe_result = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-i", str(input_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
    except Exception:
        return False
    probe_text = (probe_result.stdout or "") + (probe_result.stderr or "")
    return "Audio:" in probe_text


def convert_video_to_webm(
    video_bytes,
    input_filename="input.mp4",
    crf=32,
    speed=4,
    audio_bitrate_kbps=128,
    width=None,
    height=None,
    fps=None,
    reverse_output=False,
    timeout_seconds=1800,
):
    """Convert input video bytes to WebM bytes using managed ffmpeg."""
    if not video_bytes:
        raise ValueError("Empty video data provided.")
    if len(video_bytes) > MAX_FILE_SIZE_BYTES:
        size_mb = len(video_bytes) / (1024 * 1024)
        raise ValueError(
            f"Video size ({size_mb:.1f}MB) exceeds the maximum limit of {MAX_FILE_SIZE_MB}MB."
        )

    ffmpeg_path = _resolve_ffmpeg_executable()
    if not ffmpeg_path:
        raise RuntimeError(
            "Managed ffmpeg is unavailable. Install imageio-ffmpeg and retry."
        )

    if not _run_preflight(ffmpeg_path):
        raise RuntimeError(
            "Managed ffmpeg preflight failed. Check ffmpeg codec support in diagnostics."
        )

    if not 0 <= int(crf) <= 63:
        raise ValueError("CRF must be between 0 and 63 for VP9.")
    if not 0 <= int(speed) <= 6:
        raise ValueError("Speed must be between 0 and 6 for libvpx-vp9.")
    if int(audio_bitrate_kbps) <= 0:
        raise ValueError("Audio bitrate must be greater than 0 kbps.")
    if fps is not None and float(fps) <= 0:
        raise ValueError("FPS must be greater than 0.")
    if (width is None) ^ (height is None):
        raise ValueError("Specify both width and height for resizing, or neither.")
    if width is not None and (int(width) <= 0 or int(height) <= 0):
        raise ValueError("Width and height must be greater than 0.")

    input_suffix = Path(input_filename).suffix or ".mp4"
    with tempfile.TemporaryDirectory(prefix="imgconverter_video_") as temp_dir:
        input_path = Path(temp_dir) / f"input{input_suffix}"
        output_path = Path(temp_dir) / "output.webm"
        input_path.write_bytes(video_bytes)
        has_audio_stream = _input_has_audio_stream(ffmpeg_path, input_path)

        command = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-c:v",
            "libvpx-vp9",
            "-crf",
            str(int(crf)),
            "-b:v",
            "0",
            "-deadline",
            "good",
            "-cpu-used",
            str(int(speed)),
            "-c:a",
            "libopus",
            "-b:a",
            f"{int(audio_bitrate_kbps)}k",
        ]

        if fps is not None:
            command.extend(["-r", str(float(fps))])

        video_filters = []
        if reverse_output:
            video_filters.append("reverse")
            # areverse only when source has audio stream, to avoid filter failures on silent inputs.
            if has_audio_stream:
                command.extend(["-af", "areverse"])
        if width is not None and height is not None:
            # Keep dimensions even to avoid encoder failures.
            video_filters.append(f"scale={int(width)}:{int(height)}:force_divisible_by=2")
        if video_filters:
            command.extend(["-vf", ",".join(video_filters)])

        command.append(str(output_path))

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=False,
                timeout=int(timeout_seconds),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Video conversion timed out.\n"
                "Likely cause: large/complex input or strict encoding settings.\n"
                "Remediation: try a smaller file, higher speed value, or lower resolution."
            ) from exc
        except Exception as exc:
            raise RuntimeError(
                f"Video conversion process could not start.\nLikely cause: ffmpeg runtime issue.\nDetails: {exc}"
            ) from exc

        if result.returncode != 0:
            raise RuntimeError(_format_ffmpeg_error(result.stderr))
        if not output_path.exists():
            raise RuntimeError(
                "Video conversion failed: output file was not created.\n"
                "Likely cause: ffmpeg terminated early.\n"
                "Remediation: retry with a different input or less aggressive settings."
            )

        output_bytes = output_path.read_bytes()
        if not output_bytes:
            raise RuntimeError(
                "Video conversion failed: output file is empty.\n"
                "Likely cause: unsupported input stream or codec failure.\n"
                "Remediation: verify the input can be played and retry."
            )
        return output_bytes
