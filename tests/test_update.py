from __future__ import annotations


def test_latest_pypi_version_returns_none_on_error(monkeypatch):
    import urllib.request

    def bad_open(*a, **kw):
        raise OSError("network")

    monkeypatch.setattr(urllib.request, "urlopen", bad_open)
    from arc.update import latest_pypi_version

    assert latest_pypi_version() is None


def test_version_hint_returns_none_when_current(monkeypatch):
    from pathlib import Path

    from arc.update import version_hint

    monkeypatch.setattr("arc.update.current_version", lambda: "0.3.0")
    monkeypatch.setattr("arc.update.latest_pypi_version", lambda **kw: "0.3.0")
    # with no state file, should return None gracefully
    assert version_hint(Path("/nonexistent")) is None


def test_version_hint_does_not_retry_a_failed_check_the_same_day(tmp_path, monkeypatch):
    from arc import state as st
    from arc.update import version_hint

    (tmp_path / ".arc").mkdir()
    st.save(tmp_path, st.init_state(base="main"))
    calls = []
    monkeypatch.setattr("arc.update.latest_pypi_version", lambda **kw: calls.append(1))

    version_hint(tmp_path)
    version_hint(tmp_path)

    assert len(calls) == 1
