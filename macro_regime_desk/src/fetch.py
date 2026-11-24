# -*- coding: utf-8 -*-
"""数据源适配器：每个函数负责一类数据，返回 (series, status)。

series 统一格式：{"指标名": [(YYYY-MM-DD, 数值), ...]}，按日期升序。
status 统一格式：{"name": 数据源, "status": ok|stale|failed, "detail": 说明, "last": 最新日期}
"""

import csv
import io
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import config as C
from netutil import get_json, get_text, num


# ----------------------------------------------------------------- 工具
def _mdY(s):
    """'11/23/2026' -> '2026-11-23'"""
    try:
        return datetime.strptime(s.strip(), "%m/%d/%Y").strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return None


def _iso(s):
    """'2026-11-23' 或 '2026-11-23T00:00:00' -> '2026-11-23'"""
    s = (s or "").strip()
    if not s:
        return None
    return s.split("T")[0][:10]


def _sort(d):
    return sorted(d.items())


def _rows_to_series(rows):
    """{date: value} -> [(date, value)]，按日期升序。"""
    items = rows.items() if isinstance(rows, dict) else rows
    return [(d, v) for d, v in sorted(items) if d and v is not None]


# ------------------------------------------------------- 1. 美国财政部收益率
def fetch_treasury():
    """实际收益率曲线（TIPS）与名义收益率曲线 —— 模型第 1 号核心指标。"""
    series, details, ok_years = {}, [], []
    years = [date.today().year, date.today().year - 1]

    for label, dtype in (("real", "daily_treasury_real_yield_curve"),
                         ("nom", "daily_treasury_yield_curve")):
        acc = {}
        for y in years:
            url = (f"https://home.treasury.gov/resource-center/data-chart-center/"
                   f"interest-rates/daily-treasury-rates.csv/{y}/all"
                   f"?type={dtype}&field_tdr_date_value={y}&page&_format=csv")
            text, err = get_text(url, cache_name=f"treasury_{label}_{y}.csv",
                                 host_key="treasury")
            if not text:
                details.append(f"{label}/{y}: {err}")
                continue
            ok_years.append(y)
            reader = csv.DictReader(io.StringIO(text))
            for row in reader:
                d = _mdY(row.get("Date", ""))
                if not d:
                    continue
                for col, val in row.items():
                    if not col or col == "Date":
                        continue
                    key = col.strip().upper().replace(" ", "")
                    v = num(val)
                    if v is None:
                        continue
                    acc.setdefault(key, {})[d] = v

        # real: 5YR/7YR/10YR/20YR/30YR ；nom: 1MO..30YR
        mapping = {
            "real": {"10YR": "real10y", "5YR": "real5y", "30YR": "real30y",
                     "7YR": "real7y", "20YR": "real20y"},
            "nom": {"10YR": "nom10y", "2YR": "nom2y", "30YR": "nom30y",
                    "3MO": "nom3m", "5YR": "nom5y", "1YR": "nom1y"},
        }[label]
        for col, name in mapping.items():
            if col in acc:
                series[name] = _rows_to_series(acc[col])

    if not series:
        return {}, {"name": "美国财政部(收益率曲线)", "status": "failed",
                    "detail": "; ".join(details)[:200], "last": None}

    last = max(v[-1][0] for v in series.values() if v)
    return series, {"name": "美国财政部(收益率曲线)", "status": "ok",
                    "detail": f"{sorted(set(ok_years))} 年官方日度数据",
                    "last": last}


# --------------------------------------------------------------- 2. CBOE 波动
def fetch_cboe():
    """VIX 与 3M VIX —— 模型的波动率与期限结构指标。"""
    out, details = {}, []
    for idx, name in (("VIX", "vix"), ("VIX3M", "vix3m"), ("VIX9D", "vix9d")):
        url = f"https://cdn.cboe.com/api/global/us_indices/daily_prices/{idx}_History.csv"
        text, err = get_text(url, cache_name=f"cboe_{idx}.csv", host_key="cboe")
        if not text:
            details.append(f"{idx}: {err}")
            continue
        rows = {}
        for line in text.strip().splitlines()[1:]:
            parts = line.split(",")
            if len(parts) < 5:
                continue
            d = _mdY(parts[0])
            v = num(parts[4])
            if d and v:
                rows[d] = v
        if rows:
            # 只保留最近 5 年，控制文件体积
            cutoff = (date.today() - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
            out[name] = _rows_to_series({k: v for k, v in rows.items() if k >= cutoff})

    if not out:
        return {}, {"name": "CBOE 波动率", "status": "failed",
                    "detail": "; ".join(details)[:200], "last": None}
    last = max(v[-1][0] for v in out.values() if v) if out else None
    return out, {"name": "CBOE 波动率(VIX/VIX3M)", "status": "ok",
                 "detail": "官方日度收盘", "last": last}


# ------------------------------------------------- 3. 美元指数（ECB 汇率合成）
_DXY_W = {"EUR": -0.576, "JPY": 0.136, "GBP": -0.119,
          "CAD": 0.091, "SEK": 0.042, "CHF": 0.036}


def fetch_dxy():
    """用 ECB 每日参考汇率精确合成 ICE 美元指数（DXY），无需付费行情。"""
    url = "https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist-90d.xml"
    text, err = get_text(url, cache_name="ecb_hist90.xml", host_key="ecb")
    if not text:
        return {}, {"name": "美元指数(DXY, ECB合成)", "status": "failed",
                    "detail": err, "last": None}

    ns = {"g": "http://www.gesmes.org/xml/2002-08-01",
          "e": "http://www.ecb.int/vocabulary/2002-08-01/eurofxref"}
    try:
        root = ET.fromstring(text)
    except Exception as e:  # noqa: BLE001
        return {}, {"name": "美元指数(DXY, ECB合成)", "status": "failed",
                    "detail": f"XML解析失败: {e}", "last": None}

    dxy, eurusd = {}, {}
    for cube in root.findall(".//e:Cube[@time]", ns):
        d = cube.get("time")
        rates = {}
        for c in cube.findall("e:Cube", ns):
            v = num(c.get("rate"))
            if v and c.get("currency"):
                rates[c.get("currency")] = v
        e = rates.get("USD")  # ECB 以 EUR 为基准，EUR/USD 就是 USD 项报价
        if not e:
            continue
        eurusd[d] = e
        try:
            jpy = rates["JPY"] / e          # USDJPY
            gbp = e / rates["GBP"]          # GBPUSD
            cad = rates["CAD"] / e          # USDCAD
            sek = rates["SEK"] / e          # USDSEK
            chf = rates["CHF"] / e          # USDCHF
            val = (50.14348112
                   * (rates["USD"] ** -0.576)
                   * (jpy ** 0.136)
                   * (gbp ** -0.119)
                   * (cad ** 0.091)
                   * (sek ** 0.042)
                   * (chf ** 0.036))
            dxy[d] = round(val, 3)
        except Exception:  # noqa: BLE001
            continue

    if not dxy:
        return {}, {"name": "美元指数(DXY, ECB合成)", "status": "failed",
                    "detail": "合成失败（ECB 缺篮子货币）", "last": None}

    # ECB 只提供 90 天窗口，本地按天累积，跑得越久历史越长
    hist = C.SERIES / "dxy_hist.csv"
    merged = {}
    if hist.exists():
        for line in hist.read_text(encoding="utf-8").strip().splitlines()[1:]:
            parts = line.split(",")
            if len(parts) == 2:
                v = num(parts[1])
                if v:
                    merged[parts[0]] = v
    before = len(merged)
    merged.update(dxy)
    if len(merged) > before or not hist.exists():
        hist.write_text("date,dxy\n" + "\n".join(
            f"{d},{merged[d]}" for d in sorted(merged)) + "\n", encoding="utf-8")
    dxy = merged  # 用累积后的更长序列

    out = {"dxy": _rows_to_series(dxy)}
    if eurusd:
        out["eurusd"] = _rows_to_series(eurusd)
    return out, {"name": "美元指数(DXY, ECB合成)", "status": "ok",
                 "detail": f"按 ICE 官方权重合成，本地已累积 {len(dxy)} 个交易日", 
                 "last": max(dxy)}


# ---------------------------------------------------------- 4. ETF 行情（资产层）
def fetch_prices():
    """Nasdaq 官方报价接口，取模型涉及的全部资产日线。"""
    out, failed = {}, []
    start = (date.today() - timedelta(days=420)).strftime("%Y-%m-%d")
    end = date.today().strftime("%Y-%m-%d")
    for key, ticker, _name, _role in C.ASSETS:
        url = (f"https://api.nasdaq.com/api/quote/{ticker}/historical"
               f"?assetclass=etf&fromdate={start}&todate={end}&limit=400")
        js, err = get_json(url, cache_name=f"px_{ticker}.json", host_key="nasdaq")
        rows = (((js or {}).get("data") or {}).get("tradesTable") or {}).get("rows") or []
        if not rows:
            failed.append(f"{ticker}({err or '空'})")
            continue
        acc = {}
        for r in rows:
            d = _mdY(r.get("date", ""))
            v = num(r.get("close"))
            if d and v:
                acc[d] = v
        if acc:
            out[f"px_{key}"] = _rows_to_series(acc)

    if not out:
        return {}, {"name": "Nasdaq 行情(ETF)", "status": "failed",
                    "detail": "全部失败: " + ",".join(failed)[:150], "last": None}
    last = max(v[-1][0] for v in out.values() if v)
    status = "ok" if not failed else "stale"
    return out, {"name": "Nasdaq 行情(ETF)", "status": status,
                 "detail": f"{len(out)}/{len(C.ASSETS)} 只成功"
                           + (f"；失败: {','.join(failed)[:120]}" if failed else ""),
                 "last": last}


# ------------------------------------------------------ 5. 盈利预期（分析师一致预期）
def fetch_earnings():
    """用标普500权重前 20 名的分析师一致预期，合成『盈利预期动量』。

    两个输出：
      eps_rev     —— 4 周净上修比率 (0~1)，>0.5 表示上修占优
      fwd_eps_idx —— 以首次快照为 100 的前瞻 EPS 指数，反映预期水平的累计变化
    """
    import csv as _csv

    rows_out, failed, per_symbol = [], [], {}
    for sym in C.EPS_POOL:
        s = sym.replace("-", ".")
        url = f"https://api.nasdaq.com/api/analyst/{s}/earnings-forecast"
        js, err = get_json(url, cache_name=f"eps_{s.replace('.', '_')}.json",
                           host_key="nasdaq")
        data = (js or {}).get("data") or {}
        yearly = (data.get("yearlyForecast") or {}).get("rows") or []
        if not yearly:
            failed.append(s)
            continue
        # 取最近两个财年（当年=FY1，下一年=FY2）
        fy1 = yearly[0]
        eps1 = num(fy1.get("consensusEPSForecast"))
        up = num(fy1.get("up")) or 0
        down = num(fy1.get("down")) or 0
        if eps1 is None:
            failed.append(s)
            continue
        per_symbol[s] = {"eps1": eps1, "up": up, "down": down,
                         "n": num(fy1.get("noOfEstimates")) or 0,
                         "fy": fy1.get("fiscalEnd")}
        rows_out.append([date.today().isoformat(), s, fy1.get("fiscalEnd"),
                         eps1, up, down])

    if not per_symbol:
        return {}, {"name": "分析师盈利预期(Nasdaq)", "status": "failed",
                    "detail": "全部失败: " + ",".join(failed)[:150], "last": None}

    # 累积原始快照（每天一行，工作台跑得越久，历史越完整）
    hist_path = C.SERIES / "analyst_eps_raw.csv"
    header = ["date", "symbol", "fiscal_end", "eps_fy1", "up_4w", "down_4w"]
    today = date.today().isoformat()
    kept = []
    if hist_path.exists():
        with hist_path.open(newline="", encoding="utf-8") as f:
            kept = [r for r in _csv.reader(f) if r and r[0] != "date" and r[0] != today]
    with hist_path.open("w", newline="", encoding="utf-8") as f:
        w = _csv.writer(f)
        w.writerow(header)
        w.writerows(kept)
        w.writerows(rows_out)

    tot_up = sum(v["up"] for v in per_symbol.values())
    tot_dn = sum(v["down"] for v in per_symbol.values())
    rev = tot_up / (tot_up + tot_dn) if (tot_up + tot_dn) > 0 else 0.5

    # 前瞻 EPS 指数：按当日样本内一致预期 EPS 之和归一
    eps_sum = sum(v["eps1"] for v in per_symbol.values())

    series = {}
    # 从累积文件重建历史序列
    try:
        by_date = {}
        with hist_path.open(newline="", encoding="utf-8") as f:
            for r in _csv.DictReader(f):
                d = r["date"]
                if d not in by_date:
                    by_date[d] = {"up": 0.0, "dn": 0.0, "eps": 0.0, "n": 0}
                by_date[d]["up"] += float(r["up_4w"] or 0)
                by_date[d]["dn"] += float(r["down_4w"] or 0)
                # 只对同一财年口径做累加，避免口径变化
                by_date[d]["eps"] += float(r["eps_fy1"] or 0)
                by_date[d]["n"] += 1
        rev_pts, eps_pts = [], []
        base = None
        for d in sorted(by_date):
            v = by_date[d]
            if v["up"] + v["dn"] > 0:
                rev_pts.append((d, round(v["up"] / (v["up"] + v["dn"]), 4)))
            if v["n"] > 0:
                if base is None:
                    base = v["eps"]
                if base:
                    eps_pts.append((d, round(100 * v["eps"] / base, 3)))
        series["eps_rev"] = rev_pts
        series["fwd_eps_idx"] = eps_pts
    except Exception:  # noqa: BLE001
        series["eps_rev"] = [(today, round(rev, 4))]
        series["fwd_eps_idx"] = [(today, 100.0)]

    last = max((p[-1][0] for p in series.values() if p), default=None)
    status = "ok" if len(per_symbol) >= len(C.EPS_POOL) * 0.6 else "stale"
    return series, {"name": "分析师盈利预期(Nasdaq 一致预期)",
                    "status": status,
                    "detail": f"{len(per_symbol)}/{len(C.EPS_POOL)} 只权重股，"
                              f"4周上修 {int(tot_up)} / 下修 {int(tot_dn)}"
                              + (f"；缺: {','.join(failed)[:80]}" if failed else ""),
                    "last": last}


# ---------------------------------------------------------------- 6. 短端利率
def fetch_rates_nyfed():
    """SOFR —— 模型『融资成本』维度。"""
    start = (date.today() - timedelta(days=730)).strftime("%Y-%m-%d")
    end = date.today().strftime("%Y-%m-%d")
    url = ("https://markets.newyorkfed.org/api/rates/secured/sofr/search.json"
           f"?startDate={start}&endDate={end}")
    js, err = get_json(url, cache_name="nyfed_sofr.json", host_key="nyfed")
    refs = ((js or {}).get("refRates") or []) if js else []
    pts = [(_iso(r.get("effectiveDate")), num(r.get("percentRate"))) for r in refs]
    pts = [(d, v) for d, v in pts if d and v is not None]
    if not pts:
        return {}, {"name": "SOFR(NY Fed)", "status": "failed",
                    "detail": err or "无数据", "last": None}
    return {"sofr": _rows_to_series(pts)}, {
        "name": "SOFR(NY Fed)", "status": "ok", "detail": f"近 2 年共 {len(pts)} 个交易日",
        "last": max(d for d, _ in pts)}


# ------------------------------------------------------------ 7. FRED（多序列）
def fetch_fred():
    """FRED 官方序列：信用利差真值 + 增长/通胀/商品维度。

    只走 api.stlouisfed.org（不依赖 fred 网站是否可达）。
    未配置 key 时返回 failed，模型会自动降级到代理指标。
    """
    if not C.FRED_API_KEY:
        return {}, {"name": "FRED 官方序列", "status": "failed",
                    "detail": "未配置 FRED_API_KEY → 信用利差使用代理，增长维度不启用",
                    "last": None}

    import json as _json  # noqa: F401

    out, detail, ok, bad = {}, [], 0, []
    for name, (sid, _desc) in C.FRED_SERIES.items():
        url = ("https://api.stlouisfed.org/fred/series/observations"
               f"?series_id={sid}&api_key={C.FRED_API_KEY}&file_type=json"
               f"&observation_start=2022-01-01&sort_order=asc")
        js, err = get_json(url, cache_name=f"fred_{sid}.json", host_key="fred_api",
                           timeout=25, retry=2)
        if js is None:
            bad.append(f"{sid}:{err}")
            continue
        obs = js.get("observations") or []
        pts = []
        for o in obs:
            v = num(o.get("value"))
            d = _iso(o.get("date"))
            if d and v is not None:
                pts.append((d, v))
        if pts:
            out[name] = _rows_to_series(pts)
            ok += 1
        else:
            bad.append(f"{sid}:空")

    if not out:
        return {}, {"name": "FRED 官方序列", "status": "failed",
                    "detail": "全部失败: " + "; ".join(bad)[:200], "last": None}

    # 核心PCE 是价格指数，转成同比（%），便于直接判断通胀方向
    if "core_pce" in out:
        idx = out["core_pce"]
        yoy = []
        for i in range(len(idx)):
            if i < 12:
                continue
            base = idx[i - 12][1]
            if base:
                yoy.append((idx[i][0], round((idx[i][1] / base - 1) * 100, 3)))
        if yoy:
            out["core_pce_yoy"] = yoy

    last = max(v[-1][0] for v in out.values() if v)
    status = "ok" if ok == len(C.FRED_SERIES) else "stale"
    return out, {"name": "FRED 官方序列", "status": status,
                 "detail": f"{ok}/{len(C.FRED_SERIES)} 条成功（HY OAS、通胀预期、初请、失业率、核心PCE、WTI）"
                           + (f"；失败: {'; '.join(bad)[:120]}" if bad else ""),
                 "last": last}


# 兼容旧调用名
fetch_hy_oas_fred = fetch_fred
# ---------------------------------------------------------- 8. 未来事件日历
CAL_KEYWORDS = [
    "CPI", "Consumer Price", "PCE", "Nonfarm", "Unemployment", "FOMC",
    "Fed", "Federal Reserve", "GDP", "Retail Sales", "ISM", "PMI", "Jobless",
    "Payrolls", "PPI", "Durable Goods", "Housing Starts", "Consumer Confidence",
    "JOLTS", "ADP Employment", "Treasury", "Crude Oil", "Trade Balance",
]


def fetch_calendar(days=7):
    """未来一周的美国关键数据与事件（Nasdaq 官方日历）。"""
    import datetime as _dt

    today = _dt.date.today()
    dates = [today + _dt.timedelta(days=i) for i in range(days + 1)]
    dates = [d for d in dates if d.weekday() < 5][:days]
    out, seen, errs = [], set(), []
    for d in dates:
        url = f"https://api.nasdaq.com/api/calendar/economicevents?date={d.isoformat()}"
        js, err = get_json(url, cache_name=f"cal_{d.isoformat()}.json", host_key="nasdaq")
        rows = ((js or {}).get("data") or {}).get("rows") or []
        if not rows:
            errs.append(f"{d}:{err or '空'}")
        for r in rows:
            country = (r.get("country") or "").strip()
            name = (r.get("eventName") or "").strip()
            if country != "United States":
                continue
            if not any(k.lower() in name.lower() for k in CAL_KEYWORDS):
                continue
            key = (d.isoformat(), name)
            if key in seen:
                continue
            seen.add(key)
            cons = (r.get("consensus") or "").replace("&nbsp;", "").strip()
            prev = (r.get("previous") or "").replace("&nbsp;", "").strip()
            out.append({"date": d.isoformat(), "time": (r.get("gmt") or "").strip(),
                        "event": name, "consensus": cons, "previous": prev})
    status = "ok" if out else ("stale" if errs else "failed")
    return out, {"name": "经济日历(Nasdaq)", "status": status,
                 "detail": f"未来一周美国关键数据，共 {len(out)} 条"
                           + (f"；{'; '.join(errs)[:80]}" if errs else ""),
                 "last": out[0]["date"] if out else None}
