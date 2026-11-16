import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(app, 'DB_PATH', str(tmp_path / 'tempo.db'))
    return TestClient(app.app)


def test_norm_drops_features_and_brackets():
    assert app.norm('Camo Shorts (feat. Someone) [Explicit]') == 'camo shorts'
    assert app.norm('Song ft. Other Artist') == 'song'


def test_healthz(client):
    assert client.get('/healthz').json() == {'ok': True}


def test_bpm_caches(client, monkeypatch):
    calls = []

    def fake_compute(artist, title):
        calls.append((artist, title))
        return {'bpm': 150.0, 'percival_bpm': 75.0, 'confidence': 3.5,
                'matched': f'{artist} - {title}'}

    monkeypatch.setattr(app, 'compute', fake_compute)
    first = client.get('/bpm', params={'artist': 'A', 'title': 'B'}).json()
    second = client.get('/bpm', params={'artist': 'A', 'title': 'B'}).json()
    assert len(calls) == 1
    assert first['cached'] is False and second['cached'] is True
    # 75 is the half-time reading of 150, so the estimators agree
    assert second['trust'] == 'high'
    assert second['readings'] == [75.0, 150.0, 300.0]


def test_batch_reports_errors_per_track(client, monkeypatch):
    def fake_compute(artist, title):
        if title == 'missing':
            raise HTTPException(404, 'no iTunes preview found for that track')
        return {'bpm': 120.0, 'percival_bpm': 120.0, 'confidence': 2.0,
                'matched': f'{artist} - {title}'}

    monkeypatch.setattr(app, 'compute', fake_compute)
    out = client.post('/batch', json=[
        {'id': '1', 'artist': 'A', 'title': 'found'},
        {'id': '2', 'artist': 'A', 'title': 'missing'},
    ]).json()
    assert out[0]['bpm'] == 120.0 and out[0]['trust'] == 'check'
    assert out[1]['error'] == 'no iTunes preview found for that track'


def test_fits(client):
    assert client.get('/fits', params={'bpm': 75, 'cadence': 150}).json()['fits']
