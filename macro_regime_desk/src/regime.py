# -*- coding: utf-8 -*-
"""花旗 10-regime 宏观状态框架（整合自 Citi Quantitative Global Macro Strategy, 2023-11-23）

原研报的核心批评：只看增长/通胀的「水平」不足以区分宏观状态，
必须叠加「3 个月变化」才能把衰退早期与晚期分开；并且 late-cycle 的信号
主要藏在金融条件（FCI）的收紧里，而不在增长本身。

本模块把该框架落到可每日自动运行的数据上：
  7 维状态向量 → 10 个宏观状态 → 状态条件资产倾向 → 资产适配度修正

与研报的差异（诚实标注）：
  · G7 通胀/领先指标 → 用美国 CPI 同比 + 自建 LEI 代理（成分见 build_lei）
  · 聚类算法（k-means）→ 高斯核打分 + 硬规则兜底（可复现、可解释、零依赖）
  · 簇中心沿用研报公布的标准化数值，仅作参考坐标，不假装是重新估计的结果
"""

import math

from indicators import align, last, mean, stdev

# ---------------------------------------------------------------- 10 个状态
# gy: 通胀水平, gl: 增长水平, dc: 通胀3月变化, dl: 增长3月变化,
# xv: 跨资产波动率, fci: 金融条件, dfci: 金融条件3月变化
# 中心值来自研报图4（标准化后），仅作坐标参考
REGIMES = {
    "normal": {
        "name": "Normal 常态", "cn": "常态", "color": "#4e9bff",
        "center": {"gy": 0.27, "gl": 0.26, "dc": 0.11, "dl": 0.03,
                   "xv": -0.68, "fci": -0.60, "dfci": 0.0},
        "desc": "增长与通胀都在中枢附近，金融条件宽松。风险资产温和占优，但缺乏强驱动。",
        "tilt": {"equity": 0.3, "bond": 0.0, "credit": 0.3, "gold": 0.0,
                 "energy": 0.0, "quality": 0.1, "cash": -0.2},
    },
    "recovery": {
        "name": "Recovery 复苏", "cn": "复苏", "color": "#12b886",
        "center": {"gy": -1.09, "gl": -0.33, "dc": -0.16, "dl": 0.00,
                   "xv": -0.39, "fci": -0.85, "dfci": 0.0},
        "desc": "增长仍低但不再恶化，通胀已回落，金融条件极度宽松。金融与地产领先。",
        "tilt": {"equity": 0.5, "bond": 0.1, "credit": 0.4, "gold": 0.0,
                 "energy": 0.2, "quality": -0.1, "cash": -0.4},
    },
    "goldilocks": {
        "name": "Goldilocks 金发女孩", "cn": "金发女孩", "color": "#0f9d58",
        "center": {"gy": -1.19, "gl": 1.35, "dc": 0.16, "dl": 0.27,
                   "xv": 0.21, "fci": -0.39, "dfci": 0.0},
        "desc": "低通胀 + 强增长 + 增长在加速。最舒服的环境，科技与工业领先，股债双牛。",
        "tilt": {"equity": 0.7, "bond": 0.1, "credit": 0.5, "gold": -0.2,
                 "energy": 0.0, "quality": 0.0, "cash": -0.5},
    },
    "growth_shock": {
        "name": "Growth shock 增长冲击", "cn": "增长冲击", "color": "#f57c00",
        "center": {"gy": -0.23, "gl": -1.44, "dc": -0.11, "dl": -0.48,
                   "xv": 0.22, "fci": 0.09, "dfci": 0.0},
        "desc": "增长快速下滑且仍在恶化。这是债券对冲唯一可靠的场景之一（股债相关 +0.30）。",
        "tilt": {"equity": -0.4, "bond": 0.6, "credit": -0.3, "gold": 0.3,
                 "energy": -0.3, "quality": 0.2, "cash": 0.3},
    },
    "tightening_fci": {
        "name": "Tightening FCI 金融条件收紧", "cn": "条件收紧", "color": "#e8590c",
        "center": {"gy": 0.49, "gl": -0.37, "dc": -0.02, "dl": -0.18,
                   "xv": 0.28, "fci": 1.22, "dfci": 0.3},
        "desc": "金融条件在收紧，典型 late-cycle。主要资产收益转负，防御、Quality、实物资产占优，信用最差。",
        "tilt": {"equity": -0.3, "bond": -0.1, "credit": -0.7, "gold": 0.4,
                 "energy": 0.1, "quality": 0.6, "cash": 0.4},
    },
    "stagflation_loose": {
        "name": "Stagflation-loose FCI 滞胀·宽松", "cn": "滞胀·松", "color": "#d9480f",
        "center": {"gy": 2.43, "gl": -0.86, "dc": -0.31, "dl": -0.07,
                   "xv": 1.73, "fci": 0.32, "dfci": 0.0},
        "desc": "高通胀 + 弱增长，但金融条件尚未紧到极端。能源与贵金属是少数正收益来源。",
        "tilt": {"equity": -0.4, "bond": -0.4, "credit": -0.5, "gold": 0.7,
                 "energy": 0.6, "quality": 0.3, "cash": 0.2},
    },
    "early_stagflation_tight": {
        "name": "Early Stagflation-tight 早期滞胀·紧", "cn": "早期滞胀·紧", "color": "#c92a2a",
        "center": {"gy": 2.35, "gl": -1.30, "dc": -0.20, "dl": -0.70,
                   "xv": 1.63, "fci": 3.39, "dfci": 0.5},
        "desc": "研报认定最恶性的组合：高通胀、增长崩塌、金融条件极端收紧。几乎无处可躲，现金优先。",
        "tilt": {"equity": -0.8, "bond": -0.7, "credit": -0.9, "gold": 0.3,
                 "energy": 0.3, "quality": 0.4, "cash": 0.8},
    },
    "inflationary_boom": {
        "name": "Inflationary boom 通胀繁荣", "cn": "通胀繁荣", "color": "#f0b90b",
        "center": {"gy": 3.14, "gl": 0.90, "dc": 1.14, "dl": -0.21,
                   "xv": 0.05, "fci": 0.13, "dfci": 0.0},
        "desc": "通胀高企且在加速，但增长强劲。商品能源最受益，价值优于成长，债券受损。",
        "tilt": {"equity": 0.3, "bond": -0.6, "credit": 0.1, "gold": 0.5,
                 "energy": 0.8, "quality": -0.2, "cash": -0.1},
    },
    "recession": {
        "name": "Recession 衰退", "cn": "衰退", "color": "#862e9c",
        "center": {"gy": -2.25, "gl": -0.67, "dc": -1.05, "dl": 1.50,
                   "xv": 1.40, "fci": 1.16, "dfci": 0.0},
        "desc": "通胀快速回落、增长深度收缩但已在边际改善。衰退深处高beta资产反而最佳（政策转向预期）。",
        "tilt": {"equity": -0.2, "bond": 0.7, "credit": -0.4, "gold": 0.5,
                 "energy": -0.5, "quality": 0.1, "cash": 0.3},
    },
    "fin_shock": {
        "name": "Fin market shock 金融冲击", "cn": "金融冲击", "color": "#d93025",
        "center": {"gy": -1.08, "gl": 0.98, "dc": 0.01, "dl": -0.22,
                   "xv": 3.72, "fci": -0.12, "dfci": 0.0},
        "desc": "流动性冲击主导（1987、1998 型）。跨资产波动率极端抬升，此时宏观基本面几乎不起作用。",
        "tilt": {"equity": -0.9, "bond": 0.4, "credit": -0.8, "gold": 0.5,
                 "energy": -0.6, "quality": 0.3, "cash": 0.7},
    },
}

# 各维度在簇中心的离散度，作为高斯核的带宽（自适应，避免手调）
def _dims():
    return ["gy", "gl", "dc", "dl", "xv", "fci", "dfci"]


BANDWIDTH = {}
for _d in _dims():
    vals = [r["center"][_d] for r in REGIMES.values()]
    BANDWIDTH[_d] = max(stdev(vals) or 1.0, 0.45)


# ------------------------------------------------------------------ 工具
def to_monthly(series):
    """把任意频率序列压成月度值，日期统一归到月初。

    必须归一到月初：周频数据（如 ICSA）的月末落在周六，月频数据（如 PERMIT）
    落在 1 号，不统一的话多条序列取交集永远是空集。
    """
    out = {}
    for d, v in series:
        if v is None:
            continue
        out[d[:7]] = v          # 同一月份重复出现时保留最后一个观测
    return [(k + "-01", out[k]) for k in sorted(out)]


def expanding_z(series, min_periods=36):
    """扩张窗口 z-score：更接近研报用全样本标准化的做法，且不偷看未来。"""
    out, vals = [], []
    for d, v in series:
        vals.append(v)
        if len(vals) < min_periods:
            continue
        m, s = mean(vals), stdev(vals)
        if not s:
            continue
        out.append((d, (v - m) / s))
    return out


def _chg_n(series, n):
    """第 i 个点相对第 i-n 个点的变化（月度序列用）。"""
    out = []
    for i in range(len(series)):
        if i < n:
            continue
        out.append((series[i][0], series[i][1] - series[i - n][1]))
    return out


def _align_many(*series_list):
    """按日期取交集对齐多条月度序列。"""
    maps = [{d: v for d, v in s} for s in series_list]
    common = sorted(set.intersection(*[set(m) for m in maps]))
    return common, [[m[d] for d in common] for m in maps]


# ------------------------------------------------------------- LEI 代理
LEI_COMPONENTS = [
    ("claims", -1),      # 初请失业金：反向
    ("permit", +1),      # 建筑许可
    ("umcsent", +1),     # 消费者预期
    ("awhameman", +1),   # 制造业周工时
    ("curve", +1),       # 收益率曲线
    ("hy_oas", -1),      # 信用利差：反向
    ("px_SPY", +1),      # 股价：反向指标里的领先项
]


def build_lei(series):
    """自建领先指标（LEI 代理）。

    研报用的是 G7 OECD 领先指标，但该序列在 FRED 已停更（2024-01）。
    这里按 Conference Board LEI 的核心成分思路自建，成分全部可日更：
    初请、建筑许可、消费者预期、制造业工时、期限利差、信用利差、股价。
    输出为标准化后的合成值（正=扩张）。
    """
    # 期限利差在原始序列里没有，就地构造
    work = dict(series)
    if "nom10y" in work and "nom2y" in work:
        dd, aa, bb = align(work["nom10y"], work["nom2y"])
        work["curve"] = [(d, x - y) for d, x, y in zip(dd, aa, bb)]

    parts = []
    for key, sign in LEI_COMPONENTS:
        s = work.get(key)
        if not s or len(s) < 24:
            continue
        z = expanding_z(to_monthly(s), min_periods=36)
        if len(z) < 18:
            continue
        parts.append([(d, sign * v) for d, v in z])
    if len(parts) < 3:
        return [], list(series.keys())[:0]

    dates, cols = _align_many(*parts)
    lei = [(d, mean([c[i] for c in cols])) for i, d in enumerate(dates)]
    used = [k for k, _s in LEI_COMPONENTS if work.get(k)]
    return lei, used


# ------------------------------------------------------- 7 维状态向量
def build_state_vector(series):
    """构造研报的 7 维状态向量，全部标准化。"""
    vec = {}

    cpi = series.get("cpi_yoy")
    if cpi:
        m = to_monthly(cpi)
        lvl = expanding_z(m, 36)
        if lvl:
            vec["gy"] = lvl[-1][1]
            vec["gy_date"] = lvl[-1][0]
        chg = expanding_z(_chg_n(m, 3), 36)
        if chg:
            vec["dc"] = chg[-1][1]

    lei, _ = build_lei(series)
    if lei:
        # lei 已是 z 量级，再做一次扩张标准化使其与簇中心同尺度
        lvl = expanding_z(lei, 36)
        if lvl:
            vec["gl"] = lvl[-1][1]
            vec["gl_date"] = lvl[-1][0]
        chg = expanding_z(_chg_n(lei, 3), 36)
        if chg:
            vec["dl"] = chg[-1][1]

    vix, hy = series.get("vix"), series.get("hy_oas")
    xs = []
    for s in (vix, hy):
        if s:
            z = expanding_z(s, 120)
            if z:
                xs.append(z[-1][1])
    if xs:
        vec["xv"] = mean(xs)

    nfci = series.get("nfci")
    if nfci:
        lvl = expanding_z(nfci, 60)
        if lvl:
            vec["fci"] = lvl[-1][1]
            vec["fci_date"] = lvl[-1][0]
            vec["fci_raw"] = nfci[-1][1]
        chg = expanding_z(_chg_n(nfci, 13), 60)
        if chg:
            vec["dfci"] = chg[-1][1]
            vec["dfci_raw"] = nfci[-1][1] - nfci[max(0, len(nfci) - 14)][1]
    return vec


# ------------------------------------------------------- 状态分类
def classify(vec):
    """高斯核打分（连续）+ 硬规则兜底（离散），双通道给结论。"""
    dims = [d for d in _dims() if d in vec]
    if len(dims) < 4:
        return None

    scores = {}
    for key, r in REGIMES.items():
        s = 0.0
        for d in dims:
            z = (vec[d] - r["center"][d]) / BANDWIDTH[d]
            s += z * z
        scores[key] = math.exp(-0.5 * s)

    total = sum(scores.values()) or 1.0
    probs = {k: v / total for k, v in scores.items()}
    ranked = sorted(probs.items(), key=lambda t: -t[1])

    # 硬规则：研报明确指出这几类由单一维度主导，不该被距离算法稀释
    rule = None
    gy, gl = vec.get("gy", 0), vec.get("gl", 0)
    xv, fci, dl = vec.get("xv", 0), vec.get("fci", 0), vec.get("dl", 0)
    if xv > 2.5:
        rule = "fin_shock"
    elif fci > 2.2 and gy > 0.5:
        rule = "early_stagflation_tight"
    elif fci > 1.2 and gy > 0.3:
        rule = "stagflation_loose"
    elif fci > 1.0:
        rule = "tightening_fci"

    final = rule or ranked[0][0]
    out = dict(REGIMES[final])
    out.update({
        "key": final,
        "prob": round(probs.get(final, 0), 3),
        "by_rule": rule is not None,
        "top": [{"key": k, "name": REGIMES[k]["name"], "cn": REGIMES[k]["cn"],
                 "prob": round(v, 3)} for k, v in ranked[:3]],
        "vector": {d: round(vec[d], 2) for d in dims},
        "confidence": ("高" if probs.get(final, 0) > 0.45 or rule
                       else ("中" if probs.get(final, 0) > 0.28 else "低")),
    })
    return out


def regime_history(series, months=120):
    """逐月回算历史状态，用于状态迁移统计。"""
    cpi = series.get("cpi_yoy")
    lei, _ = build_lei(series)
    nfci = series.get("nfci")
    vix, hy = series.get("vix"), series.get("hy_oas")
    if not (cpi and lei and nfci):
        return [], {}

    cm = {d: v for d, v in to_monthly(cpi)}
    lm = {d: v for d, v in lei}
    fm = {d: v for d, v in to_monthly(nfci)}
    xm = {}
    for s in (vix, hy):
        if s:
            for d, v in to_monthly(s):
                xm.setdefault(d, []).append(v)
    vix_m = {d: v for d, v in to_monthly(vix)} if vix else {}

    dates = sorted(set(cm) & set(lm) & set(fm))[-months:]
    if len(dates) < 24:
        return [], {}

    def z_at(series_map, d):
        keys = [k for k in sorted(series_map) if k <= d]
        if len(keys) < 24:
            return None
        vals = [series_map[k] for k in keys]
        m, s = mean(vals), stdev(vals)
        return (series_map[d] - m) / s if s else None

    hist = []
    for i, d in enumerate(dates):
        if i < 12:
            continue
        gy = z_at(cm, d)
        gl = z_at(lm, d)
        fci = z_at(fm, d)
        prev = dates[i - 3]
        gy_prev = z_at(cm, prev)
        gl_prev = z_at(lm, prev)
        fci_prev = z_at(fm, prev)
        if None in (gy, gl, fci, gy_prev, gl_prev, fci_prev):
            continue
        xv = z_at(vix_m, d) if vix_m else 0.0
        v = {"gy": gy, "gl": gl, "fci": fci,
             "dc": (gy - gy_prev), "dl": (gl - gl_prev),
             "dfci": (fci - fci_prev), "xv": xv or 0.0}
        r = classify(v)
        if r:
            hist.append((d, r["key"]))
    return hist, {}


def transition_matrix(hist):
    """状态迁移矩阵：研报图7 的做法，看当前状态最可能往哪走。"""
    if len(hist) < 12:
        return {}
    keys = list(REGIMES)
    mat = {a: {b: 0 for b in keys} for a in keys}
    for i in range(1, len(hist)):
        a, b = hist[i - 1][1], hist[i][1]
        if a in mat and b in mat[a]:
            mat[a][b] += 1
    out = {}
    for a in keys:
        tot = sum(mat[a].values())
        if tot:
            out[a] = {b: round(c / tot, 2) for b, c in sorted(
                mat[a].items(), key=lambda t: -t[1]) if c}
    return out


# --------------------------------------------------- 股债相关性（研报图13/14）
def stock_bond_corr(spy, ief, window=63):
    """63 日滚动相关：S&P500 日收益 vs 中期国债日收益。

    正值＝股债同向（对冲失效），负值＝对冲有效。
    研报结论：只在 growth shock（+0.30）与深度衰退（+0.27）可靠，其余状态多为负甚至失效。
    """
    if not spy or not ief:
        return [], None
    dates, a, b = align(spy, ief)
    if len(dates) < window + 5:
        return [], None
    ra = [a[i] / a[i - 1] - 1 for i in range(1, len(a))]
    rb = [b[i] / b[i - 1] - 1 for i in range(1, len(b))]
    out = []
    for i in range(window, len(ra) + 1):
        x, y = ra[i - window:i], rb[i - window:i]
        mx, my = mean(x), mean(y)
        cov = sum((xx - mx) * (yy - my) for xx, yy in zip(x, y))
        sx = math.sqrt(sum((xx - mx) ** 2 for xx in x))
        sy = math.sqrt(sum((yy - my) ** 2 for yy in y))
        if sx and sy:
            out.append((dates[i], round(cov / (sx * sy), 3)))
    return out, (out[-1][1] if out else None)
