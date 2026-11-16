import shutil
import wave

import numpy as np
import pytest

import analyzer

RATE = 44100


def click_track(path, bpm, seconds=30):
    """Write a mono wav with a short 1 kHz click on every beat."""
    audio = np.zeros(RATE * seconds, dtype=np.float32)
    click = np.sin(2 * np.pi * 1000 * np.arange(int(RATE * 0.02)) / RATE)
    step = 60.0 / bpm
    for t in np.arange(0, seconds, step):
        i = int(t * RATE)
        audio[i:i + len(click)] += click[:len(audio) - i]
    with wave.open(str(path), 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((audio * 0.8 * 32767).astype(np.int16).tobytes())


# RhythmExtractor2013 snaps to whole onset frames (5168 / n BPM), so 128
# reads as 129.2. 1.5% covers that; cadence matching allows 4%.
@pytest.mark.parametrize('bpm', [95, 128, 150])
def test_analyze_click_track(tmp_path, bpm):
    path = tmp_path / 'click.wav'
    click_track(path, bpm)
    res = analyzer.analyze_wav(str(path))
    assert abs(res['bpm'] - bpm) <= bpm * 0.015
    assert abs(res['percival_bpm'] - bpm) <= bpm * 0.015


@pytest.mark.skipif(shutil.which('ffmpeg') is None, reason='needs ffmpeg')
def test_to_wav_round_trip(tmp_path):
    src = tmp_path / 'click.wav'
    click_track(src, 120, seconds=5)
    out = analyzer.to_wav(str(src))
    with wave.open(out) as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == RATE


def test_candidates():
    assert analyzer.candidates(75) == [37.5, 75.0, 150.0]


def test_fits_cadence_half_time():
    assert analyzer.fits_cadence(75, 150)
    assert not analyzer.fits_cadence(100, 150)
