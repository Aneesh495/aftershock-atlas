"""Account for project files and the actual writable filesystem before growth."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from .io import ROOT, append_json, now

PROJECT_LIMIT = 5_000_000_000
MAC_LIMIT = 400_000_000_000


def tree_bytes(path: Path) -> int:
    seen: set[tuple[int, int]] = set()
    total = 0
    for base, dirs, files in os.walk(path, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        for name in files:
            p = Path(base) / name
            if p.is_symlink():
                continue
            try:
                s = p.stat()
            except FileNotFoundError:
                continue
            identity = (s.st_dev, s.st_ino)
            if identity not in seen:
                total += max(s.st_size, s.st_blocks * 512)
                seen.add(identity)
    return total


def usage(reserve: int = 0, root: Path = ROOT) -> dict:
    volume = Path("/System/Volumes/Data") if platform.system() == "Darwin" else root
    disk = shutil.disk_usage(volume)
    local = tree_bytes(root)
    # Initial installer cache attribution is conservative, separately recorded.
    external_cache = 250_000_000 if platform.system() == "Darwin" else 0
    result = {"at": now(), "project_bytes": local, "external_cache_attribution": external_cache,
              "volume_used": disk.used, "reserve": reserve, "project_limit": PROJECT_LIMIT,
              "volume_limit": MAC_LIMIT, "volume_free": disk.free}
    append_json(root / ".agent-local/resources.jsonl", result)
    if local + external_cache + reserve > PROJECT_LIMIT:
        raise RuntimeError("Project storage budget would be exceeded")
    if disk.used + reserve > MAC_LIMIT:
        raise RuntimeError("Writable volume budget would be exceeded")
    if disk.free < reserve + 1_000_000_000:
        raise RuntimeError("Insufficient free space with recovery margin")
    return result


def doctor() -> dict:
    import numpy as np
    info = {"platform": platform.platform(), "machine": platform.machine(),
            "cpu_count": os.cpu_count(), "python": platform.python_version(),
            "storage": usage(), "float64_eps": float(np.finfo(float).eps),
            "backend": "NumPy CPU float64", "gpu": "not used", "paid_compute": False,
            "raw_available": (ROOT / "data/raw/index.json").exists(),
            "panel_available": (ROOT / "data/panel/observations.parquet").exists()}
    if platform.system() == "Darwin":
        info["memory_bytes"] = int(subprocess.check_output(["sysctl", "-n", "hw.memsize"]))
    return info
