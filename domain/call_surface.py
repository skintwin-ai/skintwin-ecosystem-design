"""Call one product function and print its ledger result."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def normalize(result: object) -> tuple[bool, dict]:
    if result is None:
        return False, {"ok": False, "error": "surface recorded nothing"}
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], dict):
        body, status = result
        ok = isinstance(status, int) and status < 400 and body.get("ok", True) is not False
        return ok, body
    if isinstance(result, dict):
        return result.get("ok") is True, result
    return False, {"ok": False, "error": "surface returned an unknown result"}


def main() -> None:
    module_path = Path(sys.argv[1])
    function = sys.argv[2]
    sys.path.insert(0, str(module_path.resolve().parent))
    spec = importlib.util.spec_from_file_location("skintwin_surface", module_path)
    if spec is None or spec.loader is None:
        json.dump({"ok": False, "error": "surface module is missing"}, sys.stdout)
        raise SystemExit(1)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, function, None)
    if not callable(fn):
        json.dump({"ok": False, "error": f"{function} is not exported"}, sys.stdout)
        raise SystemExit(1)
    try:
        result = fn(*json.load(sys.stdin))
    except Exception as exc:  # noqa: BLE001 — surface failures become a ledger error
        json.dump({"ok": False, "error": str(exc)}, sys.stdout)
        raise SystemExit(1)
    ok, payload = normalize(result)
    json.dump(payload, sys.stdout)
    if not ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
