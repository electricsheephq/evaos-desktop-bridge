from __future__ import annotations

import sys
from collections.abc import Iterable
from pathlib import Path


def bundled_bridge_bin_candidates(binary_names: Iterable[str], *, executable: str | None = None, argv0: str | None = None) -> tuple[str, ...]:
    """Return installed Workbench Bridge/bin candidates before PATH/Homebrew fallbacks."""
    raw_paths = [executable if executable is not None else sys.executable]
    if argv0 is not None:
        raw_paths.append(argv0)
    elif sys.argv:
        raw_paths.append(sys.argv[0])

    roots: list[Path] = []
    seen_roots: set[str] = set()
    for raw in raw_paths:
        if not raw:
            continue
        path = Path(raw).expanduser()
        if not path.is_absolute():
            try:
                path = path.resolve()
            except OSError:
                path = Path.cwd() / path
        start = path if path.is_dir() else path.parent
        for candidate in (start, *start.parents):
            if candidate.name != "Bridge":
                continue
            key = str(candidate)
            if key not in seen_roots:
                roots.append(candidate)
                seen_roots.add(key)
            break

    results: list[str] = []
    seen_results: set[str] = set()
    for root in roots:
        for name in binary_names:
            candidate = str(root / "bin" / name)
            if candidate in seen_results:
                continue
            results.append(candidate)
            seen_results.add(candidate)
    return tuple(results)
