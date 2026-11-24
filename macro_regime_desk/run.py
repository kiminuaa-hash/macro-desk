# -*- coding: utf-8 -*-
"""主流程：抓数 → 校验 → 建模 → 存档 → 渲染工作台。

用法：
    python3 run.py            # 正常每日运行
    python3 run.py --no-net   # 只用本地缓存（断网也能出图）
"""

import json
import sys
import traceback
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent / "src"))

import config as C  # noqa: E402
import fetch  # noqa: E402
import model  # noqa: E402
import render  # noqa: E402


def rebuild():
    """不联网，用上一次落盘的原始序列重建工作台（改模型/改样式时用，秒级）。"""
    p = C.DATA / "cache_series.json"
    if not p.exists():
        print("没有序列缓存，请先正常跑一次 run.py")
        return 1
    blob = json.loads(p.read_text(encoding="utf-8"))
    series = blob["series"]
    sources = blob["sources"]
    cal = blob.get("calendar") or []
    sources.setdefault("fred", {"name": "高收益债利差(FRED)", "status": "cached",
                                "detail": "离线重建，沿用上次结果", "last": None})
    meta = {"generated_at": (datetime.now(timezone.utc) + timedelta(hours=C.TZ_OFFSET))
            .strftime("%Y-%m-%d %H:%M:%S") + " (UTC+8)"}
    snap = model.build_snapshot(series, sources, meta)
    snap["calendar"] = cal
    snap["history"] = _load_history()
    (C.OUTPUT / "latest.json").write_text(json.dumps(snap, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    slim_snap = {k: v for k, v in snap.items() if k not in ("series_slim",)}
    (C.SNAPSHOTS / f"{date.today().isoformat()}.json").write_text(
        json.dumps(slim_snap, ensure_ascii=False, indent=1), encoding="utf-8")
    _append_history(date.today().isoformat(), snap)
    (C.OUTPUT / "dashboard.html").write_text(render.render(snap), encoding="utf-8")
    (C.OUTPUT / f"daily_{date.today().isoformat()}.md").write_text(
        render.daily_note(snap), encoding="utf-8")
    q = snap["quadrant"]
    print(f"[rebuild] {snap['as_of']} | {q['id']} {q['label']} | "
          f"评分 {snap['score']['total']} {snap['score']['band']}")
    return 0


def run(use_net=True):
    series, sources = {}, {}
    cal = []
    tasks = [
        ("treasury", fetch.fetch_treasury),
        ("cboe", fetch.fetch_cboe),
        ("dxy", fetch.fetch_dxy),
        ("prices", fetch.fetch_prices),
        ("earnings", fetch.fetch_earnings),
        ("nyfed", fetch.fetch_rates_nyfed),
        ("fred", fetch.fetch_hy_oas_fred),
        ("calendar", fetch.fetch_calendar),
    ]

    print("=" * 62)
    print(f"宏观环境工作台 · 抓取开始 {datetime.now(timezone.utc) + timedelta(hours=C.TZ_OFFSET):%Y-%m-%d %H:%M:%S}")
    print("=" * 62)

    for key, fn in tasks:
        if not use_net:
            sources[key] = {"name": key, "status": "cached", "detail": "跳过网络", "last": None}
            continue
        try:
            s, st = fn()
            if key == "calendar":
                cal = s
                sources[key] = st
                print(f"  ✓ {st['name']:<26} {st['status']:<8} last={st.get('last')} | {st['detail'][:70]}")
                continue
            series.update(s)
            sources[key] = st
            flag = {"ok": "✓", "stale": "△", "failed": "✗"}.get(st["status"], "?")
            print(f"  {flag} {st['name']:<26} {st['status']:<8} "
                  f"last={st.get('last')} | {st['detail'][:70]}")
        except Exception as e:  # noqa: BLE001
            sources[key] = {"name": key, "status": "failed",
                            "detail": f"{type(e).__name__}: {e}", "last": None}
            print(f"  ✗ {key} 异常: {e}")
            traceback.print_exc()

    if not series:
        print("\n[中止] 无任何可用数据（首次运行请确认网络）。")
        return 1

    # 序列落盘，便于不联网反复重建模型
    (C.DATA / "cache_series.json").write_text(
        json.dumps({"saved_at": date.today().isoformat(),
                    "sources": sources, "calendar": cal,
                    "series": {k: v for k, v in series.items()}},
                   ensure_ascii=False), encoding="utf-8")

    meta = {"generated_at": (datetime.now(timezone.utc) + timedelta(hours=C.TZ_OFFSET))
            .strftime("%Y-%m-%d %H:%M:%S") + " (UTC+8)"}
    snap = model.build_snapshot(series, sources, meta)
    snap["calendar"] = cal

    # ---------- 存档 ----------
    day = date.today().isoformat()
    slim_snap = {k: v for k, v in snap.items() if k not in ("series_slim",)}
    (C.SNAPSHOTS / f"{day}.json").write_text(
        json.dumps(slim_snap, ensure_ascii=False, indent=1), encoding="utf-8")
    _prune_snapshots(keep=180)
    _append_history(day, snap)
    (C.OUTPUT / "latest.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    snap["history"] = _load_history()

    # ---------- 渲染 ----------
    html = render.render(snap)
    out = C.OUTPUT / "dashboard.html"
    out.write_text(html, encoding="utf-8")

    note = render.daily_note(snap)
    (C.OUTPUT / f"daily_{day}.md").write_text(note, encoding="utf-8")

    print("-" * 62)
    q = snap["quadrant"]
    print(f"数据日期 {snap['as_of']} | 象限 {q['id']} {q['label']}")
    print(f"环境评分 {snap['score']['total']}/100 → {snap['score']['band']}")
    on = [s["name"] for s in snap["signals"] if s["state"] == "on"]
    print(f"触发信号 {len(on)} 组: {'；'.join(on) if on else '无'}")
    print(f"已生成: {out}")
    return 0


def _prune_snapshots(keep=180):
    """只保留最近 N 天的快照，避免仓库无限膨胀。"""
    files = sorted(C.SNAPSHOTS.glob("*.json"))
    for f in files[:-keep] if len(files) > keep else []:
        try:
            f.unlink()
        except OSError:
            pass


def _load_history():
    p = C.SERIES / "model_history.csv"
    if not p.exists():
        return []
    import csv as _csv
    out = []
    with p.open(newline="", encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            try:
                out.append({"date": r["date"], "score": float(r["score"]),
                            "quadrant": r.get("quadrant", "")})
            except (ValueError, KeyError):
                continue
    return sorted(out, key=lambda x: x["date"])[-180:]


def _append_history(day, snap):
    """维护一条跨日期的模型历史，用于画评分与象限的时间序列。"""
    p = C.SERIES / "model_history.csv"
    cols = ["date", "score", "quadrant", "real10y", "eps_rev", "dxy", "vix",
            "vix_ratio", "credit", "be10y", "sofr", "curve"]
    ind = snap["indicators"]
    row = {
        "date": day, "score": snap["score"]["total"],
        "quadrant": snap["quadrant"]["id"],
        "real10y": ind.get("real10y", {}).get("value"),
        "eps_rev": ind.get("eps_rev", {}).get("value"),
        "dxy": ind.get("dxy", {}).get("value"),
        "vix": ind.get("vix", {}).get("value"),
        "vix_ratio": snap["extras"].get("vix_ratio"),
        "credit": ind.get("credit", {}).get("value"),
        "be10y": ind.get("be10y", {}).get("value"),
        "sofr": ind.get("sofr", {}).get("value"),
        "curve": ind.get("curve", {}).get("value"),
    }
    lines = []
    if p.exists():
        lines = p.read_text(encoding="utf-8").strip().splitlines()
    else:
        lines = [",".join(cols)]
    body = [ln for ln in lines[1:] if not ln.startswith(day + ",")]
    body.append(",".join("" if row[c] is None else str(row[c]) for c in cols))
    p.write_text("\n".join([lines[0]] + body) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if "--rebuild" in sys.argv:
        sys.exit(rebuild())
    if "--render-only" in sys.argv:
        snap = json.loads((C.OUTPUT / "latest.json").read_text(encoding="utf-8"))
        snap["history"] = _load_history()
        (C.OUTPUT / "dashboard.html").write_text(render.render(snap), encoding="utf-8")
        (C.OUTPUT / f"daily_{date.today().isoformat()}.md").write_text(
            render.daily_note(snap), encoding="utf-8")
        print("已重新渲染:", C.OUTPUT / "dashboard.html")
        sys.exit(0)
    sys.exit(run(use_net="--no-net" not in sys.argv))
