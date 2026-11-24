# -*- coding: utf-8 -*-
"""基础统计工具：取点、变化、方向、z-score、分位、对齐。"""

import math
from datetime import date, timedelta


def last(series):
    """返回 (日期, 值)；无效返回 (None, None)。"""
    if not series:
        return None, None
    return series[-1]


def back(series, n):
    """回溯 n 个观测（交易日）。不足则取最早一条。"""
    if not series:
        return None, None
    i = max(0, len(series) - 1 - n)
    return series[i]


def chg(series, n):
    """n 个观测的变化量（绝对）。"""
    if not series or len(series) < 2:
        return None
    d0, v0 = back(series, n)
    d1, v1 = last(series)
    if v0 is None or v1 is None:
        return None
    return v1 - v0


def pct_chg(series, n):
    """n 个观测的百分比变化。"""
    if not series or len(series) < 2:
        return None
    _d0, v0 = back(series, n)
    _d1, v1 = last(series)
    if not v0 or v1 is None:
        return None
    return (v1 / v0 - 1.0) * 100.0


def chg_d(series, days):
    """按自然日回溯的变化量：取「最新日期 - days」当天或之前最近的观测。

    相比按数据点回溯，这样即使序列中间有假日/缺数（如 EIA 油价滞后），
    "1 个月变化"也真的是 1 个月，不会被缺口拉长。
    """
    if not series or len(series) < 2:
        return None
    d1, v1 = series[-1]
    try:
        target = (date.fromisoformat(d1) - timedelta(days=days)).isoformat()
    except ValueError:
        return None
    for d, v in reversed(series):
        if d <= target:
            return None if v is None else v1 - v
    return None


def pct_chg_d(series, days):
    """按自然日回溯的百分比变化。"""
    if not series or len(series) < 2:
        return None
    d1, v1 = series[-1]
    try:
        target = (date.fromisoformat(d1) - timedelta(days=days)).isoformat()
    except ValueError:
        return None
    for d, v in reversed(series):
        if d <= target:
            return None if not v else (v1 / v - 1.0) * 100.0
    return None


def direction_d(series, eps, days=30):
    """按自然日的方向判定。"""
    c = chg_d(series, days)
    if c is None:
        return "na"
    if c > eps:
        return "up"
    if c < -eps:
        return "down"
    return "flat"


def window(series, n):
    if not series:
        return []
    return [v for _d, v in series[-n:] if v is not None]


def mean(xs):
    return sum(xs) / len(xs) if xs else None


def stdev(xs):
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _by_days(series, days):
    """取最近 days 个自然日内的观测（不同频率统一口径）。"""
    if not series:
        return []
    try:
        end = date.fromisoformat(series[-1][0])
    except ValueError:
        return [v for _d, v in series[-252:]]
    cut = (end - timedelta(days=days)).isoformat()
    xs = [v for d, v in series if d >= cut and v is not None]
    return xs or [v for _d, v in series[-252:] if v is not None]


def zscore(series, days=365):
    """基于最近 days 个自然日的 z-score（跨频率统一，月频也真的是"近一年"）。"""
    xs = _by_days(series, days)
    if len(xs) < 12:
        return None
    m, s = mean(xs), stdev(xs)
    if not s:
        return None
    return (xs[-1] - m) / s


def percentile(series, days=365):
    """当前值在最近 days 个自然日中的分位（0~100）；样本 <12 个时不给。"""
    xs = _by_days(series, days)
    if len(xs) < 12:
        return None
    cur = xs[-1]
    below = sum(1 for x in xs if x <= cur)
    return 100.0 * below / len(xs)


def direction(series, eps, n=21):
    """方向判定：'up' / 'down' / 'flat'。"""
    c = chg(series, n)
    if c is None:
        return "na"
    if c > eps:
        return "up"
    if c < -eps:
        return "down"
    return "flat"


def align(a, b):
    """把两条序列按共同日期对齐，返回 (dates, [a_vals], [b_vals])。"""
    da = {d: v for d, v in a if v is not None}
    db = {d: v for d, v in b if v is not None}
    common = sorted(set(da) & set(db))
    return common, [da[d] for d in common], [db[d] for d in common]


def latest_common(a, b):
    """两条序列的最新共同日期及对应值。"""
    dates, va, vb = align(a, b)
    if not dates:
        return None, None, None
    return dates[-1], va[-1], vb[-1]


def clip(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def score_from_z(z, invert=False, k=18.0):
    """把 z-score 映射成 0~100 的环境分（50 为中性）。"""
    if z is None:
        return 50.0
    z = -z if invert else z
    return clip(50 + k * z)
