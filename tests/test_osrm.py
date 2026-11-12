"""The OSRM client, against canned responses. No server is needed."""

import io
import json
import urllib.error

import pytest

from pipeline import osrm
from pipeline.osrm import OsrmRouter


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def server(monkeypatch):
    """Record the requested URLs and answer with the queued bodies."""
    calls, queue = [], []

    def fake_urlopen(url, timeout):
        calls.append(url)
        answer = queue.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return FakeResponse(json.dumps(answer).encode())

    monkeypatch.setattr(osrm.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(osrm.time, "sleep", lambda seconds: None)
    return calls, queue


def test_nearest_sends_longitude_first_and_returns_latitude_first(server):
    calls, queue = server
    queue.append({"code": "Ok", "waypoints": [{"location": [-72.6741, 41.7652], "distance": 12.5}]})

    snap = OsrmRouter("http://localhost:5000").nearest(41.7658, -72.6734)

    assert calls == ["http://localhost:5000/nearest/v1/driving/-72.673400,41.765800?number=1"]
    assert (snap.lat, snap.lon, snap.moved_m) == (41.7652, -72.6741, 12.5)


def test_nearest_without_a_road_returns_nothing(server):
    _, queue = server
    queue.append({"code": "NoSegment", "message": "Could not find a matching segment"})

    assert OsrmRouter("http://localhost:5000").nearest(41.0, -72.0) is None


def test_table_asks_for_distances_from_the_origin_to_every_destination(server):
    calls, queue = server
    queue.append({"code": "Ok", "distances": [[1500.0, None, 42000.0]]})

    distances = OsrmRouter("http://localhost:5000/").road_distances_km(
        (41.76, -72.67), [(41.77, -72.66), (41.00, -72.00), (41.31, -72.93)]
    )

    assert distances == [1.5, None, 42.0]
    assert calls == [
        "http://localhost:5000/table/v1/driving/"
        "-72.670000,41.760000;-72.660000,41.770000;-72.000000,41.000000;-72.930000,41.310000"
        "?annotations=distance&sources=0&destinations=1;2;3"
    ]


def test_table_without_destinations_makes_no_request(server):
    calls, _ = server

    assert OsrmRouter("http://localhost:5000").road_distances_km((41.76, -72.67), []) == []
    assert calls == []


def test_a_failed_table_request_marks_every_destination_unroutable(server):
    _, queue = server
    queue.append({"code": "NoTable"})

    assert OsrmRouter("http://localhost:5000").road_distances_km((41.7, -72.6), [(41.8, -72.5)]) == [None]


def test_a_dropped_connection_is_retried(server):
    calls, queue = server
    queue.extend(
        [
            urllib.error.URLError("connection refused"),
            {"code": "Ok", "waypoints": [{"location": [-72.0, 41.0], "distance": 0}]},
        ]
    )

    assert OsrmRouter("http://localhost:5000").nearest(41.0, -72.0) is not None
    assert len(calls) == 2


def test_a_server_that_stays_down_is_an_error(server):
    _, queue = server
    queue.extend([urllib.error.URLError("connection refused")] * 3)

    with pytest.raises(RuntimeError, match="after 3 attempts"):
        OsrmRouter("http://localhost:5000").nearest(41.0, -72.0)


def test_only_http_urls_are_accepted():
    with pytest.raises(ValueError, match="http"):
        OsrmRouter("file:///etc/passwd")
