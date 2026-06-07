from __future__ import annotations

import importlib.metadata
import json
import urllib.request
from pathlib import Path


def current_version() -> str:
    try:
        return importlib.metadata.version("arc-prs")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def latest_pypi_version(timeout: int = 2) -> str | None:
    try:
        url = "https://pypi.org/pypi/arc-prs/json"
        with urllib.request.urlopen(url, timeout=timeout) as r:  # noqa: S310
            return json.load(r)["info"]["version"]
    except Exception:
        return None


def version_hint(root: Path) -> str | None:
    """Return upgrade hint string if newer version available, else None.
    Checks PyPI at most once per day; caches result in .arc/state.json metadata.
    """
    import time

    from arc import state as st

    try:
        data = st.load(root)
    except Exception:
        return None
    meta = data.get("metadata", {})
    last_check = meta.get("version_check_ts", 0)
    cached_latest = meta.get("version_check_latest")
    if time.time() - last_check > 86400:
        latest = latest_pypi_version()
        if latest:
            meta["version_check_ts"] = int(time.time())
            meta["version_check_latest"] = latest
            data["metadata"] = meta
            try:
                st.save(root, data)
            except Exception:
                pass
            cached_latest = latest
    if cached_latest and cached_latest != current_version():
        return f"arc {cached_latest} available — run: arc upgrade"
    return None
