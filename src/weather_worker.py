"""决策天气后台刷新器。

每轮并行刷新杭州、宁波的 ensemble；``src.live_data`` 自身的 24 小时
缓存负责 station/archive 的每日调用节流。所有运行时文件仍位于
``runtime/decision_weather/<location>/``。
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone
import json
from pathlib import Path
import time
from typing import Any

from src import live_data
from src.decision_weather import LOCATIONS, _atomic_write, _cache_dir, _iso, _utc_datetime, get_weather


UTC = timezone.utc
DEFAULT_INTERVAL_SECONDS = 3600


def _refresh_ensemble(root: Path, location_key: str, now: datetime, force: bool) -> dict[str, Any]:
    return get_weather(root, location_key, now=now, refresh=True, force=force)


def _safe_live_snapshot(root: Path, location_key: str, product: str, now: datetime, force: bool) -> dict[str, Any]:
    try:
        return live_data.fetch_snapshot(root, location_key, product, now=now, force=force)
    except Exception as exc:  # 让一个来源失败不影响其他来源和城市
        return {"status": "error", "snapshot": None, "error": str(exc) or exc.__class__.__name__}


def _write_status(root: Path, location_key: str, status: dict[str, Any]) -> None:
    directory = _cache_dir(root, location_key)
    _atomic_write(directory / "worker.json", json.dumps(status, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n")


def update_all(root: str | Path, now: datetime | date | None = None, force: bool = False) -> dict[str, Any]:
    """刷新两地 ensemble，并按现有 live_data 缓存调用 station/archive。

    ensemble 两个城市在线请求彼此独立，因此并行执行；station/archive
    仍使用现有模块的每日 TTL。``force`` 只用于显式手动刷新。
    """

    root_path = Path(root)
    current = _utc_datetime(now)
    location_results: dict[str, dict[str, Any]] = {key: {} for key in sorted(LOCATIONS)}
    errors: list[dict[str, str]] = []

    with ThreadPoolExecutor(max_workers=len(location_results), thread_name_prefix="decision-weather") as executor:
        future_map = {
            executor.submit(_refresh_ensemble, root_path, key, current, force): key
            for key in location_results
        }
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                result = future.result()
            except Exception as exc:  # 防止线程异常中断另一城市
                result = {"status": "error", "snapshot": None, "error": str(exc) or exc.__class__.__name__}
            location_results[key]["ensemble"] = result
            if result.get("error") or result.get("status") == "error":
                errors.append({"location_key": key, "product": "ensemble", "error": str(result.get("error") or "刷新失败")})

    for key in location_results:
        for product in ("station", "archive"):
            result = _safe_live_snapshot(root_path, key, product, current, force)
            location_results[key][product] = result
            if result.get("error") or result.get("status") == "error":
                errors.append({"location_key": key, "product": product, "error": str(result.get("error") or "刷新失败")})
        status = {
            "schema_version": 1,
            "location_key": key,
            "updated_at_utc": _iso(current),
            "results": location_results[key],
            "errors": [item for item in errors if item["location_key"] == key],
        }
        try:
            _write_status(root_path, key, status)
        except Exception as exc:
            errors.append({"location_key": key, "product": "worker_status", "error": str(exc) or exc.__class__.__name__})

    return {
        "updated_at_utc": _iso(current),
        "locations": location_results,
        "errors": errors,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="每小时刷新杭州、宁波的决策天气数据。")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--once", action="store_true", help="只执行一轮")
    parser.add_argument("--force", action="store_true", help="手动刷新，忽略缓存刷新间隔")
    parser.add_argument("--interval-seconds", type=int, default=DEFAULT_INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    if args.interval_seconds <= 0:
        parser.error("--interval-seconds 必须为正数")

    while True:
        started = time.monotonic()
        result = update_all(args.root, force=args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), flush=True)
        if args.once:
            return 0 if not result["errors"] else 1
        elapsed = time.monotonic() - started
        time.sleep(max(0.0, args.interval_seconds - elapsed))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

