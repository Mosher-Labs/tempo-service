"""Tempo analysis: audio file -> BPM (+ half/double-time candidates)."""
import os
import subprocess
import tempfile

import essentia.standard as es


def to_wav(src_path: str) -> str:
    """Decode any preview format (m4a/mp3) to 44.1 kHz mono wav with ffmpeg."""
    fd, out = tempfile.mkstemp(suffix='.wav')
    os.close(fd)
    subprocess.run(
        ['ffmpeg', '-y', '-loglevel', 'error', '-i', src_path,
         '-ac', '1', '-ar', '44100', out],
        check=True,
    )
    return out


def analyze_wav(wav_path: str) -> dict:
    audio = es.MonoLoader(filename=wav_path, sampleRate=44100)()
    bpm, _beats, beats_conf, _est, _intervals = es.RhythmExtractor2013(
        method='multifeature')(audio)
    percival = es.PercivalBpmEstimator()(audio)
    return {
        'bpm': round(float(bpm), 1),
        'confidence': round(float(beats_conf), 2),   # ~0-5.3, >3 is solid
        'percival_bpm': round(float(percival), 1),   # independent second opinion
    }


def candidates(bpm: float) -> list:
    """Half-time and double-time readings of the same song."""
    return sorted({round(bpm / 2, 1), round(bpm, 1), round(bpm * 2, 1)})


def fits_cadence(bpm: float, spm: float, tol: float = 0.04) -> bool:
    """True if any half/normal/double reading is within tol of the cadence."""
    return any(abs(c - spm) <= spm * tol for c in candidates(bpm))
