# -*- coding: utf-8 -*-
"""模型引擎：把原始序列翻译成『四象限 + 9组信号 + 环境评分 + 资产适配度』。

设计原则
  1. 每个结论都必须能回溯到具体指标和具体数字，不做无来源判断。
  2. 缺数据时降级而不是崩溃：降级路径写在 note 里，工作台会显式标注。
  3. 方向判定统一用"变化量 vs 阈值"，避免均线类方法的滞后与主观。
"""

import statistics

import config as C
import regime as RG
from indicators import (align, back, chg, chg_d, clip, direction, direction_d,
                        last, latest_common, pct_chg, pct_chg_d, percentile,
                        score_from_z, zscore)


# ============================================================ 一、指标层
def ma_series(series, n):
    """简单移动平均序列（月度/周度数据平滑用）。"""
    vals = [v for _d, v in series]
    out = []
    for i in range(len(series)):
        if i + 1 < n:
            continue
        out.append((series[i][0], sum(vals[i - n + 1:i + 1]) / n))
    return out


def _src(sources, key):
    """取数据源展示名（供指标卡片标注来源）。"""
    return (sources.get(key) or {}).get("name", key)


def _mk(key, name, value, unit, chg1w, chg1m, chg3m, d, z, pct, src, note="",
        chg_label="1月"):
    return {"key": key, "name": name, "value": value, "unit": unit,
            "chg1w": chg1w, "chg1m": chg1m, "chg3m": chg3m, "chg_label": chg_label,
            "dir": d, "z": z, "pct": pct, "src": src, "note": note}


def credit_series(series):
    """信用利差数据。

    返回 (序列, 类型, 说明, 是否反向)。
      real  —— ICE BofA HY OAS 原始百分点，上升=利差扩大
      proxy —— HYG/IEF 相对强弱比值，上升=高收益债跑赢国债=信用改善，
               所以方向需要反向解读（invert=True）
    """
    if series.get("hy_oas"):
        return series["hy_oas"], "real", "ICE BofA 美国高收益债 OAS（FRED 官方）", False

    hyg, ief = series.get("px_HYG"), series.get("px_IEF")
    if not hyg or not ief:
        return None, "none", "信用数据缺失", False
    dates, h, i = align(hyg, ief)
    if len(dates) < 30:
        return None, "none", "信用代理样本不足", False
    ratio = [(d, hh / ii) for d, hh, ii in zip(dates, h, i) if ii]
    # 把比值转成 0~100 的滚动分位压力分：越高＝高收益债相对国债越弱＝信用越紧
    vals = [v for _d, v in ratio]
    stress = []
    for idx in range(len(ratio)):
        win = vals[max(0, idx - 251): idx + 1]
        if len(win) < 20:
            continue
        pos = sum(1 for x in win if x <= vals[idx]) / len(win)
        stress.append((ratio[idx][0], round(100.0 - 100.0 * pos, 2)))
    return stress, "proxy", "代理：HYG/IEF 相对强弱（非 bp，仅用于方向与分位）", False


def build_indicators(series, sources):
    """返回 (indicators dict, extras dict)。"""
    ind, ex = {}, {}
    W = C.DIR_WINDOW
    E = C.FLAT_EPS

    # --- 实际利率（模型第 1 号核心指标）
    s = series.get("real10y")
    if s:
        v = last(s)[1]
        ind["real10y"] = _mk(
            "real10y", "10年期TIPS实际收益率", v, "%",
            chg_d(s, 7), chg_d(s, 30), chg_d(s, 91),
            direction_d(s, E["real10y"], 30), zscore(s), percentile(s),
            _src(sources,"treasury"),
            "估值端的总闸门：上行压估值，下行抬估值")
        ex["real10y_series"] = s

    # --- 盈亏平衡通胀 = 名义 - 实际
    n10, r10 = series.get("nom10y"), series.get("real10y")
    if n10 and r10:
        dates, a, b = align(n10, r10)
        if dates:
            be = [(d, aa - bb) for d, aa, bb in zip(dates, a, b)]
            ind["be10y"] = _mk(
                "be10y", "10年盈亏平衡通胀", last(be)[1], "%",
                chg_d(be, 7), chg_d(be, 30), chg_d(be, 91),
                direction_d(be, E["be10y"], 30), zscore(be), percentile(be),
                "财政部名义 − 实际收益率", "通胀预期：下行利好软着陆叙事")
            ex["be10y_series"] = be

    # --- 名义 10Y / 2Y 与曲线
    if n10:
        ind["nom10y"] = _mk("nom10y", "10年期美债名义收益率", last(n10)[1], "%",
                            chg_d(n10, 7), chg_d(n10, 30), chg_d(n10, 91),
                            direction_d(n10, E["nom10y"], 30), zscore(n10), percentile(n10),
                            _src(sources,"treasury"), "")
    n2 = series.get("nom2y")
    if n10 and n2:
        dates, a, b = align(n10, n2)
        if dates:
            curve = [(d, aa - bb) for d, aa, bb in zip(dates, a, b)]
            ind["curve"] = _mk(
                "curve", "2s10s 期限利差", round(last(curve)[1], 3), "pp",
                chg_d(curve, 7), chg_d(curve, 30), chg_d(curve, 91),
                direction_d(curve, E["curve_2s10s"], 30), zscore(curve), percentile(curve),
                "10Y − 2Y", "曲线陡化＝增长/银行环境改善，倒挂＝衰退预警")
            ex["curve_series"] = curve
            ex["curve_raw"] = last(curve)[1]

    # --- 盈利预期
    rev = series.get("eps_rev")
    fwd = series.get("fwd_eps_idx")
    if rev:
        v = last(rev)[1]
        earn_dir, earn_note = "flat", ""
        if len(rev) >= 2:
            d21 = chg(rev, 21)
            earn_dir = "up" if (d21 or 0) > E["eps_rev"] else (
                "down" if (d21 or 0) < -E["eps_rev"] else "flat")
            earn_note = f"近 1 个月净上修比率变化 {d21:+.3f}" if d21 is not None else ""
        else:
            earn_dir = "up" if v > 0.55 else ("down" if v < 0.45 else "flat")
            earn_note = "仅单日快照，用横截面净上修水平判定（历史随每日运行累积）"
        ind["eps_rev"] = _mk(
            "eps_rev", "盈利预期净上修比率", v, "",
            chg(rev, 5), chg(rev, 21), chg(rev, 63),
            earn_dir, zscore(rev), percentile(rev),
            _src(sources,"earnings"),
            "标普500前20大权重股，4周内分析师上修/（上修+下修）" + ("；" + earn_note if earn_note else ""))
        ex["eps_rev_series"] = rev
        ex["earn_dir"] = earn_dir
    if fwd:
        ind["fwd_eps"] = _mk(
            "fwd_eps", "前瞻EPS指数（首次快照=100）", last(fwd)[1], "",
            chg(fwd, 5), chg(fwd, 21), chg(fwd, 63),
            direction(fwd, 0.05), zscore(fwd), percentile(fwd),
            _src(sources,"earnings"), "一致预期 EPS 水平的累计变化")

    # --- 信用利差
    cs, cs_kind, cs_src, invert = credit_series(series)
    if cs:
        raw_dir = direction(cs, E["hy_oas"] if cs_kind == "real" else 0.8)
        d = {"up": "down", "down": "up"}.get(raw_dir, raw_dir) if invert else raw_dir
        note = ("扩大＝风险偏好恶化，收窄＝风险偏好改善。"
                + (f"绝对水平仍在历史中枢（约 450bp）下方，属偏紧区间；"
                   f"分位只反映近一年相对位置。" if cs_kind == "real"
                   and (last(cs)[1] or 9) < 4.5 else "")) if cs_kind == "real" else \
               "0＝一年最宽松，100＝一年最紧张；由 HYG 与 IEF 相对强弱反推"
        ind["credit"] = _mk(
            "credit",
            "高收益债信用利差 HY OAS" if cs_kind == "real" else "信用压力指数（代理）",
            last(cs)[1], "%" if cs_kind == "real" else "idx",
            chg_d(cs, 7), chg_d(cs, 30), chg_d(cs, 91), d,
            zscore(cs), percentile(cs), cs_src, note)
        ex["credit_series"] = cs
        ex["credit_kind"] = cs_kind

    # --- 美元
    dxy = series.get("dxy")
    if dxy:
        ind["dxy"] = _mk(
            "dxy", "美元指数 DXY", last(dxy)[1], "",
            chg_d(dxy, 7), chg_d(dxy, 30), chg_d(dxy, 91),
            direction_d(dxy, E["dxy"], 30), zscore(dxy), percentile(dxy),
            _src(sources,"dxy"), "走强＝全球金融条件收紧，压制黄金与新兴市场")
        ex["dxy_series"] = dxy

    # --- 波动率与期限结构
    vix, vix3m = series.get("vix"), series.get("vix3m")
    if vix:
        ind["vix"] = _mk("vix", "VIX 恐慌指数", last(vix)[1], "",
                         chg_d(vix, 7), chg_d(vix, 30), chg_d(vix, 91),
                         direction_d(vix, E["vix"], 30), zscore(vix), percentile(vix),
                         _src(sources,"cboe"), "市场对 30 天波动的定价")
        ex["vix_series"] = vix
    if vix and vix3m:
        d, v1, v3 = latest_common(vix, vix3m)
        if v1 and v3:
            ts = [(dd, aa / bb) for dd, aa, bb in zip(*align(vix, vix3m))]
            ratio = v1 / v3
            state = "倒挂" if ratio > 1.0 else "正常升水"
            ind["vix_ts"] = _mk(
                "vix_ts", "VIX 期限结构（VIX/VIX3M）", ratio, "x",
                chg_d(ts, 7), chg_d(ts, 30), chg_d(ts, 91),
                direction_d(ts, 0.03, 30), zscore(ts), percentile(ts),
                _src(sources,"cboe"),
                f"{state}：近月 {v1:.2f} / 远月 {v3:.2f}。" +
                ("短期恐慌高于中期，需警惕波动放大" if ratio > 1 else "风险情绪相对平稳"))
            ex["vix_ratio"] = ratio
            ex["vix_state"] = state

    # --- 通胀预期（FRED T10YIE，与财政部口径互校）
    tie = series.get("t10yie")
    if tie:
        ind["t10yie"] = _mk("t10yie", "10年通胀预期（T10YIE）", last(tie)[1], "%",
                            chg_d(tie, 7), chg_d(tie, 30), chg_d(tie, 91),
                            direction_d(tie, 0.05, 30), zscore(tie), percentile(tie),
                            _src(sources, "fred"), "市场定价的通胀补偿，与盈亏平衡通胀互校")

    # --- 核心 PCE 同比（月频）
    cp = series.get("core_pce_yoy")
    if cp:
        ind["core_pce_yoy"] = _mk(
            "core_pce_yoy", "核心PCE 同比", last(cp)[1], "%",
            None, chg(cp, 3), chg(cp, 12),
            direction(cp, 0.05, 3), None, percentile(cp),
            _src(sources, "fred"), "美联储最看重的通胀指标，月频；变化取最近 3 个月",
            chg_label="3月")

    # --- 失业率（月频）
    ur = series.get("unrate")
    if ur:
        ind["unrate"] = _mk(
            "unrate", "美国失业率", last(ur)[1], "%",
            None, chg(ur, 3), chg(ur, 12),
            direction(ur, 0.1, 3), None, percentile(ur),
            _src(sources, "fred"), "上升＝增长走弱（Sahm 规则关注 3 个月抬升幅度）",
            chg_label="3月")
        ex["unrate_chg3"] = chg(ur, 3)

    # --- 初请失业金（周频，用 4 周均值降噪）
    claims = series.get("claims")
    if claims:
        ma = ma_series(claims, 4)
        if ma:
            ind["claims"] = _mk(
                "claims", "初请失业金（4周均值）", last(ma)[1] / 1e4, "万",
                None, (chg(ma, 13) or 0) / 1e4, (chg(ma, 26) or 0) / 1e4,
                direction(ma, 2000, 13), None, percentile(ma),
                _src(sources, "fred"), "周频高频就业指标，上行＝裁员压力增加",
                chg_label="13周")
            ex["claims_chg13"] = chg(ma, 13)
            ex["claims_series"] = ma

    # --- WTI 原油
    wti = series.get("wti")
    if wti:
        ind["wti"] = _mk("wti", "WTI 原油现货", last(wti)[1], "$",
                         chg_d(wti, 7), chg_d(wti, 30), chg_d(wti, 91),
                         direction_d(wti, 1.0, 30), zscore(wti), percentile(wti),
                         _src(sources, "fred"),
                         f"商品链条的价格锚；EIA 现货，数据日 {last(wti)[0]}（通常滞后数个交易日）")
        ex["wti_series"] = wti

    # --- 金融条件（芝加哥联储 NFCI，花旗框架的核心 late-cycle 信号）
    nfci = series.get("nfci")
    if nfci:
        ind["fci"] = _mk(
            "fci", "金融条件指数 NFCI", last(nfci)[1], "",
            chg_d(nfci, 7), chg_d(nfci, 30), chg_d(nfci, 91),
            direction_d(nfci, 0.1, 30), zscore(nfci), percentile(nfci),
            _src(sources, "fred"),
            "正值＝金融条件收紧。研报核心：late-cycle 的警报来自 FCI 收紧，而非增长本身")
        ex["nfci_series"] = [round(v, 3) for _d, v in nfci[-90:]]

    # --- 融资成本
    sofr = series.get("sofr")
    if sofr:
        ind["sofr"] = _mk("sofr", "SOFR 隔夜融资利率", last(sofr)[1], "%",
                          chg_d(sofr, 7), chg_d(sofr, 30), chg_d(sofr, 91),
                          direction_d(sofr, E["sofr"], 30), zscore(sofr), percentile(sofr),
                          _src(sources,"nyfed"), "短端资金成本，银行与杠杆资金的压力表")
        ex["sofr_series"] = sofr

    return ind, ex


# ============================================================ 二、四象限
QUADRANTS = {
    ("up", "down"): {
        "id": "Q1", "label": "最不利环境", "color": "#d93025",
        "keyword": "杀估值 + 杀盈利",
        "desc": "实际利率上行压制估值，盈利预期下修侵蚀基本面，风险资产通常面临双重压力。",
        "playbook": "防守：降低高久期成长暴露，提高现金/短债，回避无盈利支撑的主题。",
    },
    ("up", "up"): {
        "id": "Q2", "label": "偏中性 / 震荡", "color": "#f2b705",
        "keyword": "盈利对抗紧缩",
        "desc": "盈利上修能对冲部分估值压力，市场更容易分化，强基本面资产相对占优。",
        "playbook": "结构：看盈利兑现度而非指数方向，质量因子与现金流确定性优先。",
    },
    ("down", "down"): {
        "id": "Q3", "label": "反弹但持续性存疑", "color": "#f57c00",
        "keyword": "宽松支撑 vs 基本面走弱",
        "desc": "利率回落有利估值，但盈利恶化压制中期表现，常见于『衰退式宽松』阶段。",
        "playbook": "交易反弹而非趋势：缩短持有周期，等待盈利预期止跌再加久期。",
    },
    ("down", "up"): {
        "id": "Q4", "label": "最有利环境", "color": "#0f9d58",
        "keyword": "估值扩张 + 盈利改善",
        "desc": "估值压力缓解，盈利基础改善，科技股 / QQQ 通常更受益。",
        "playbook": "进攻：久期与成长弹性占优，回撤是加仓机会。",
    },
}

_DIR_CN = {"up": "上行", "down": "下行", "flat": "走平", "na": "未知"}


def build_quadrant(ind, ex):
    real_dir = ind.get("real10y", {}).get("dir", "na")
    earn_dir = ex.get("earn_dir") or ind.get("eps_rev", {}).get("dir", "na")
    # 「未恶化」归入上修一侧，符合模型表述："实际利率↓ + 盈利预期未恶化"
    y = {"up": 1, "flat": 0, "down": -1, "na": 0}[real_dir]
    x = {"up": 1, "flat": 0, "down": -1, "na": 0}[earn_dir]

    key_y = "up" if y > 0 else ("down" if y < 0 else
                                ("up" if (ind.get("real10y", {}).get("chg1m") or 0) > 0 else "down"))
    key_x = "up" if x > 0 else ("down" if x < 0 else
                                ("up" if (ind.get("eps_rev", {}).get("value") or 0.5) >= 0.5 else "down"))
    q = QUADRANTS[(key_y, key_x)]
    out = dict(q)
    out.update({
        "x": x, "y": y, "x_axis": "盈利预期", "y_axis": "实际利率",
        "real_dir": _DIR_CN[real_dir], "earn_dir": _DIR_CN[earn_dir],
        "real_val": ind.get("real10y", {}).get("value"),
        "real_chg": ind.get("real10y", {}).get("chg1m"),
        "eps_val": ind.get("eps_rev", {}).get("value"),
    })
    return out


# ============================================================ 三、环境评分
def build_score(ind, ex):
    parts = {}

    # 1) 实际利率：水平(z) + 方向 各半
    z = ind.get("real10y", {}).get("z")
    lvl = score_from_z(z, invert=True)
    dr = ind.get("real10y", {}).get("dir")
    dscore = {"down": 90, "flat": 50, "up": 12, "na": 50}.get(dr, 50)
    parts["real_rate"] = {"score": 0.55 * lvl + 0.45 * dscore,
                          "label": "实际利率（估值）",
                          "detail": f"10Y TIPS {ind.get('real10y', {}).get('value')}%，"
                                    f"近1月 {ind.get('real10y', {}).get('chg1m'):+.2f}pp"
                                    if ind.get("real10y") and ind["real10y"].get("chg1m") is not None else ""}

    # 2) 盈利预期：净上修水平 + 方向
    rev = ind.get("eps_rev", {}).get("value")
    lvl = clip((rev - 0.3) / 0.4 * 100) if rev is not None else 50
    de = ind.get("eps_rev", {}).get("dir")
    dscore = {"up": 88, "flat": 50, "down": 15, "na": 50}.get(de, 50)
    parts["earnings"] = {"score": 0.55 * lvl + 0.45 * dscore,
                         "label": "盈利预期（基本面）",
                         "detail": f"净上修比率 {rev:.2f}（>0.5 上修占优）" if rev is not None else ""}

    # 3) 信用
    cs = ind.get("credit", {})
    if cs:
        if ex.get("credit_kind") == "real":
            # 真实 HY OAS 用绝对水平锚定（分位会把"低位小幅走阔"误判为极度紧张）：
            # 250bp→100 分，450bp（历史中枢）→52 分，700bp→0 分
            oas = cs.get("value") or 4.0
            lvl = clip(100 - (oas - 2.5) * 24)
            dc = {"up": 15, "flat": 50, "down": 85, "na": 50}.get(cs.get("dir"), 50)
            parts["credit"] = {"score": 0.62 * lvl + 0.38 * dc, "label": "信用利差",
                               "detail": f"HY OAS {oas:.2f}%（{oas*100:.0f}bp）"
                                         + (f"，近1月 {cs.get('chg1m'):+.2f}pp"
                                            if cs.get("chg1m") is not None else "")}
        else:
            p = cs.get("pct")
            sc = 100 - (p if p is not None else 50)
            dc = {"up": 12, "flat": 50, "down": 88, "na": 50}.get(cs.get("dir"), 50)
            parts["credit"] = {"score": 0.5 * sc + 0.5 * dc, "label": "信用（代理）",
                               "detail": "代理指数：值越高信用越紧"}

    # 4) 美元
    dz = ind.get("dxy", {})
    if dz:
        sc = score_from_z(dz.get("z"), invert=True)
        dd = {"up": 25, "flat": 50, "down": 80, "na": 50}.get(dz.get("dir"), 50)
        parts["dollar"] = {"score": 0.55 * sc + 0.45 * dd, "label": "美元",
                           "detail": f"DXY {dz.get('value')}，近1月 {dz.get('chg1m'):+.2f}"
                                     if dz.get("chg1m") is not None else ""}

    # 5) 波动率：水平 + 期限结构
    vix = ind.get("vix", {})
    if vix:
        v = vix.get("value") or 18
        lvl = clip(100 - (v - 10) * 5)          # 10→100, 30→0
        tsr = ex.get("vix_ratio")
        ts_score = clip(50 - (tsr - 1.0) * 270) if tsr else 50
        parts["vol"] = {"score": 0.55 * lvl + 0.45 * ts_score, "label": "波动率与期限结构",
                        "detail": f"VIX {v:.1f}｜期限结构 {ex.get('vix_state', '-')}"
                                  + (f"（{tsr:.2f}x）" if tsr else "")}

    # 6) 增长动能（有 FRED 就业数据时才启用）
    ur_chg = ex.get("unrate_chg3")
    cl_chg = ex.get("claims_chg13")
    g_parts = []
    if ur_chg is not None:
        g_parts.append(clip(80 - ur_chg * 120))        # 失业率 3 个月 +0.4pp → 32 分
    if cl_chg is not None:
        cl_pctchg = cl_chg / 220000.0 * 100            # 相对 22 万人的基准变化
        g_parts.append(clip(60 - cl_pctchg * 8))
    if g_parts:
        parts["growth"] = {
            "score": sum(g_parts) / len(g_parts),
            "label": "增长动能（就业）",
            "detail": "｜".join(filter(None, [
                f"失业率3月{ur_chg:+.1f}pp" if ur_chg is not None else "",
                f"初请13周{cl_chg / 1000:+.0f}千" if cl_chg is not None else "",
            ])) or "就业数据",
        }

    total = 0.0
    wsum = 0.0
    for k, w in C.SCORE_WEIGHTS.items():
        if k in parts:
            total += parts[k]["score"] * w
            wsum += w
    total = total / wsum if wsum else 50.0
    band = next(b for b in C.SCORE_BANDS if total >= b[0])
    return {"total": round(total, 1), "band": band[1], "color": band[2],
            "verdict": band[3], "parts": parts}


# ============================================================ 四、9 组信号
def _st(cond_all, cond_any):
    if cond_all:
        return "on"
    if cond_any:
        return "near"
    return "off"


def build_signals(ind, ex):
    g = lambda k, f=None: (ind.get(k, {}) or {}).get(f) if f else ind.get(k, {})  # noqa: E731
    real_dir = g("real10y", "dir")
    earn_dir = ex.get("earn_dir") or g("eps_rev", "dir")
    dxy_dir = g("dxy", "dir")
    vix_dir = g("vix", "dir")
    credit_dir = g("credit", "dir")
    be_dir = g("be10y", "dir")
    sofr_dir = g("sofr", "dir")
    vix_ratio = ex.get("vix_ratio") or 0.9
    curve = ex.get("curve_raw")

    # 增长稳定性：曲线未深度倒挂 + 美股相对短债不弱
    growth_ok = (curve is None or curve > -0.2) and (ex.get("spy_vs_shy") is None
                                                    or ex["spy_vs_shy"] > -2)

    # 估值是否扩张：QQQ 3M 涨幅 - 前瞻EPS指数涨幅
    qqq_3m = ex.get("qqq_3m")
    eps_3m = g("fwd_eps", "chg3m")
    val_stable = True
    if qqq_3m is not None and eps_3m is not None:
        val_stable = (qqq_3m - eps_3m) < 8

    # 避险需求
    risk_off = (vix_ratio > 1.0) or (g("vix", "z") or 0) > 1.0

    sig = []

    sig.append({
        "id": 1, "name": "实际利率↑ + 盈利预期↓",
        "meaning": "科技股双重承压", "target": "QQQ / 成长股",
        "state": _st(real_dir == "up" and earn_dir == "down",
                     real_dir == "up" or earn_dir == "down"),
        "read": f"实际利率{_DIR_CN.get(real_dir)}、盈利预期{_DIR_CN.get(earn_dir)}",
        "indicators": ["real10y", "eps_rev"],
    })
    sig.append({
        "id": 2, "name": "实际利率↓ + 盈利预期未恶化",
        "meaning": "科技股估值环境改善", "target": "QQQ / 成长股",
        "state": _st(real_dir == "down" and earn_dir != "down",
                     real_dir == "down"),
        "read": f"实际利率{_DIR_CN.get(real_dir)}、盈利预期{_DIR_CN.get(earn_dir)}",
        "indicators": ["real10y", "eps_rev"],
    })
    sig.append({
        "id": 3, "name": "美元↑ + 实际利率↑",
        "meaning": "黄金面临压力", "target": "GLD",
        "state": _st(dxy_dir == "up" and real_dir == "up",
                     dxy_dir == "up" or real_dir == "up"),
        "read": f"美元{_DIR_CN.get(dxy_dir)}、实际利率{_DIR_CN.get(real_dir)}",
        "indicators": ["dxy", "real10y"],
    })
    sig.append({
        "id": 4, "name": "实际利率↓ + 避险需求↑",
        "meaning": "黄金环境改善", "target": "GLD",
        "state": _st(real_dir == "down" and risk_off, real_dir == "down" or risk_off),
        "read": f"实际利率{_DIR_CN.get(real_dir)}、避险需求{'上升' if risk_off else '平稳'}"
                f"（VIX/VIX3M {vix_ratio:.2f}x）",
        "indicators": ["real10y", "vix_ts"],
    })
    # 信号 5：有 FRED 就用核心PCE + 失业率/初请，没有就退回盈亏平衡通胀 + 曲线代理
    pce_dir = (g("core_pce_yoy", "dir") if "core_pce_yoy" in ind else None)
    infl_dir = pce_dir if pce_dir in ("up", "down") else be_dir
    ur_chg = ex.get("unrate_chg3")
    cl_chg = ex.get("claims_chg13")
    if ur_chg is not None or cl_chg is not None:
        growth_stable = ((ur_chg is None or ur_chg <= 0.3)
                         and (cl_chg is None or cl_chg <= 20000))
        g_txt = "｜".join(filter(None, [
            f"失业率3月{ur_chg:+.1f}pp" if ur_chg is not None else "",
            f"初请13周{cl_chg / 1000:+.0f}千" if cl_chg is not None else ""]))
        infl_txt = "核心PCE同比" if pce_dir in ("up", "down") else "盈亏平衡通胀"
    else:
        growth_stable = growth_ok
        g_txt = (f"2s10s {curve:+.2f}pp" if curve is not None else "曲线代理")
        infl_txt = "盈亏平衡通胀"
    sig.append({
        "id": 5, "name": "通胀↓ + 增长稳定",
        "meaning": "软着陆环境利于股票", "target": "SPY",
        "state": _st(infl_dir == "down" and growth_stable,
                     infl_dir == "down" or growth_stable),
        "read": f"{infl_txt}{_DIR_CN.get(infl_dir)}、增长{'稳定' if growth_stable else '走弱'}"
                f"（{g_txt}）",
        "indicators": ["core_pce_yoy", "unrate", "claims"],
    })
    sig.append({
        "id": 6, "name": "信用利差↑ + 波动率↑",
        "meaning": "风险资产承压", "target": "SPY / HYG",
        "state": _st(credit_dir == "up" and vix_dir == "up",
                     credit_dir == "up" or vix_dir == "up"),
        "read": f"信用利差{'扩大' if credit_dir == 'up' else '收窄' if credit_dir == 'down' else '走平'}、"
                f"VIX{_DIR_CN.get(vix_dir)}",
        "indicators": ["credit", "vix"],
    })
    sig.append({
        "id": 7, "name": "盈利预期↑ + 估值稳定",
        "meaning": "美股基本面支撑改善", "target": "SPY",
        "state": _st(earn_dir == "up" and val_stable, earn_dir == "up" or val_stable),
        "read": f"盈利预期{_DIR_CN.get(earn_dir)}、估值{'未明显扩张' if val_stable else '已扩张'}"
                + (f"（QQQ 3M {qqq_3m:+.1f}% vs EPS {eps_3m:+.1f}%）"
                   if qqq_3m is not None and eps_3m is not None else ""),
        "indicators": ["eps_rev", "fwd_eps"],
    })
    sig.append({
        "id": 8, "name": "融资成本↓ + 信用风险稳定",
        "meaning": "银行盈利环境改善", "target": "KBE / XLF",
        "state": _st(sofr_dir == "down" and credit_dir != "up",
                     sofr_dir == "down" or credit_dir != "up"),
        "read": f"SOFR{_DIR_CN.get(sofr_dir)}、信用{'稳定' if credit_dir != 'up' else '恶化'}",
        "indicators": ["sofr", "credit"],
    })
    sig.append({
        "id": 9, "name": "供应中断 + 商品库存↓",
        "meaning": "相关商品上涨风险增加", "target": "XLE / DBC",
        "state": _st(ex.get("commodity_up") and ex.get("commodity_tight"),
                     ex.get("commodity_up")),
        "read": "价格动量" + ("向上" if ex.get("commodity_up") else "走弱")
                + (f"（WTI 近1月 {ex.get('wti_1m'):+.1f}%）" if ex.get("wti_1m") is not None else "")
                + "；库存/产量需人工核对（EIA/OPEC 月报）",
        "indicators": ["commodity"],
    })
    return sig


# ============================================================ 五、资产适配度
def build_assets(series, ind, ex, score, regime=None):
    p = score["parts"]
    S = lambda k: p.get(k, {}).get("score", 50)  # noqa: E731
    real, earn, cred, dollar, vol = (S("real_rate"), S("earnings"),
                                     S("credit"), S("dollar"), S("vol"))
    tight = 100 - vol           # 避险紧张度
    cheap_money = 100 - clip((ind.get("sofr", {}).get("value") or 3.5) * 12)
    curve_steep = 50 + (ex.get("curve_chg") or 0) * 100
    commod = clip(50 + (ex.get("commodity_chg") or 0) * 250)   # 1 个月动量，10% 幅度≈±25 分

    infl_score = (100 if ind.get("core_pce_yoy", {}).get("dir") == "up"
                  else (0 if ind.get("core_pce_yoy", {}).get("dir") == "down" else 50))
    fit_rules = {
        "SPY": 0.30 * earn + 0.25 * cred + 0.25 * real + 0.20 * vol,
        "QQQ": 0.42 * earn + 0.38 * real + 0.10 * cred + 0.10 * vol,
        "GLD": 0.35 * real + 0.30 * dollar + 0.35 * tight,
        "KBE": 0.38 * cred + 0.30 * cheap_money + 0.32 * clip(curve_steep),
        "XLF": 0.35 * cred + 0.28 * cheap_money + 0.22 * clip(curve_steep) + 0.15 * vol,
        "XLE": (0.55 * clip(commod)
                + 0.25 * (100 if ind.get("be10y", {}).get("dir") == "up" else 0)
                + 0.20 * earn),
        "HYG": 0.70 * cred + 0.30 * vol,
        "TLT": 0.55 * real + 0.45 * tight,
        "SHY": 0.55 * (100 - real) + 0.45 * (100 - vol),
        "IEF": 0.50 * real + 0.50 * (100 - vol),
        "DBC": 0.60 * clip(commod) + 0.40 * dollar,   # 美元走弱利好商品
        # 花旗框架：Quality 在信用收紧、波动抬升时相对抗跌
        "QUAL": 0.45 * (100 - cred) + 0.30 * (100 - vol) + 0.25 * earn,
        # TIPS：实际利率低 + 美元弱时占优，是"实物资产"里的抗通胀腿
        "TIP": 0.35 * (100 - real) + 0.30 * infl_score + 0.35 * (100 - dollar),
        "UUP": 0.60 * (100 - dollar) + 0.40 * (100 - vol),
    }

    # 花旗 10 状态给出的资产倾向（-1~+1），作为适配度的条件修正
    tilt = (regime or {}).get("tilt") or {}
    TILT_MAP = {"SPY": "equity", "QQQ": "equity", "XLF": "equity", "KBE": "equity",
                "TLT": "bond", "IEF": "bond", "SHY": "cash", "UUP": "cash",
                "HYG": "credit", "GLD": "gold", "XLE": "energy", "DBC": "energy",
                "QUAL": "quality", "TIP": "gold"}

    rows = []
    for key, ticker, name, role in C.ASSETS:
        s = series.get(f"px_{key}")
        if not s:
            continue
        d, v = last(s)
        rows.append({
            "ticker": ticker, "name": name, "role": role,
            "px": v, "date": d,
            "chg1d": pct_chg_d(s, 1), "chg1w": pct_chg_d(s, 7),
            "chg1m": pct_chg_d(s, 30), "chg3m": pct_chg_d(s, 91),
            "pct52": percentile(s, 252),
            "fit": round(clip(fit_rules[key] + tilt.get(TILT_MAP.get(key, ""), 0) * 18), 1)
                   if key in fit_rules else None,
            "spark": [round(x, 4) for _d, x in s[-63:]],
        })
    return rows


# ============================================================ 六、汇总
def build_snapshot(series, sources, meta):
    ind, ex = build_indicators(series, sources)

    # 资产层先算一部分，供信号使用
    for key in ("SPY", "QQQ", "SHY"):
        s = series.get(f"px_{key}")
        if s:
            ex[f"{key.lower()}_3m"] = pct_chg_d(s, 91)
    spy, shy = series.get("px_SPY"), series.get("px_SHY")
    if spy and shy:
        ex["spy_vs_shy"] = (pct_chg_d(spy, 91) or 0) - (pct_chg_d(shy, 91) or 0)

    dbc, xle, wti = series.get("px_DBC"), series.get("px_XLE"), series.get("wti")
    ex["wti_1m"] = pct_chg_d(wti, 30) if wti else None
    cm = [v for v in [(pct_chg_d(dbc, 30) if dbc else None),
                      (pct_chg_d(xle, 30) if xle else None),
                      ex["wti_1m"]] if v is not None]
    ex["commodity_chg"] = (statistics.mean(cm) / 100.0) if cm else None
    ex["commodity_up"] = bool(cm and statistics.mean(cm) > 2)
    dbc_pct = percentile(dbc, 252) if dbc else None
    ex["commodity_tight"] = bool(dbc_pct is not None and dbc_pct > 70)
    if ex.get("curve_series"):
        ex["curve_chg"] = chg_d(ex["curve_series"], 30)

    # 分位统一为 365 天口径；样本不足 12 个点时标记出来，不硬给数字
    src_len = {"real10y": "real10y", "be10y": "nom10y", "nom10y": "nom10y",
               "curve": "nom10y", "eps_rev": "eps_rev", "fwd_eps": "fwd_eps_idx",
               "credit": "hy_oas", "dxy": "dxy", "vix": "vix", "vix_ts": "vix",
               "sofr": "sofr", "t10yie": "t10yie", "core_pce_yoy": "core_pce_yoy",
               "unrate": "unrate", "claims": "claims", "wti": "wti"}
    for k, v in ind.items():
        s_ = series.get(src_len.get(k, k)) or []
        span = 0
        if len(s_) > 1:
            from datetime import date as _d
            try:
                span = (_d.fromisoformat(s_[-1][0]) - _d.fromisoformat(s_[0][0])).days
            except ValueError:
                span = 0
        # 记录该指标的数据日期，供前端标注"数据滞后"
        if s_:
            v["as_of"] = s_[-1][0]
            try:
                from datetime import date as _dd
                v["lag_days"] = (_dd.today() - _dd.fromisoformat(s_[-1][0])).days
            except ValueError:
                v["lag_days"] = None
        if v.get("pct") is None:
            v["pct_label"] = "分位"
        elif span < 300:
            v["pct_label"] = f"近 {max(span, 1)} 天分位"
        else:
            v["pct_label"] = "近一年分位"

    quadrant = build_quadrant(ind, ex)
    score = build_score(ind, ex)
    signals = build_signals(ind, ex)

    # ---------- 花旗 10-regime 框架 ----------
    vec = RG.build_state_vector(series)
    reg = RG.classify(vec) or {}
    hist, _ = RG.regime_history(series)
    transitions = RG.transition_matrix(hist)
    corr_series, corr_now = RG.stock_bond_corr(series.get("px_SPY"), series.get("px_IEF"))
    lei_series, lei_used = RG.build_lei(series)

    # 状态与四象限的一致性判断（两者分歧本身就是信息）
    agree = None
    if reg:
        defensive = reg["key"] in ("tightening_fci", "early_stagflation_tight",
                                   "growth_shock", "fin_shock", "stagflation_loose")
        if quadrant["id"] in ("Q2", "Q4") and defensive:
            agree = ("象限偏正面（盈利在支撑），但状态机已进入防御型区间 —— "
                     "典型的结构性行情：指数扛得住，但信用与高波动资产先出问题。")
        elif quadrant["id"] in ("Q1", "Q3") and not defensive:
            agree = ("象限偏负面，但状态机尚未进入防守区间 —— 下行更多是估值修复，"
                     "不是基本面崩塌。")
        else:
            agree = "两个框架方向一致，可以按象限的动作指引执行。"

    assets = build_assets(series, ind, ex, score, regime=reg)

    # 数据日期：取核心指标里最新的日期
    # 数据日期：以行情/利率类"日频"数据的最晚日期为准（盈利预期是快照，不参与）
    core_dates = [sources.get(k, {}).get("last") or ""
                  for k in ("treasury", "cboe", "dxy", "prices")]
    as_of = max([d for d in core_dates if d] or [""]) or None

    chain = {
        "macro": [
            {"name": "利率", "state": _DIR_CN.get(ind.get("nom10y", {}).get("dir"), "未知"),
             "detail": f"10Y {ind.get('nom10y', {}).get('value', '-')}%"},
            {"name": "通胀",
             "state": _DIR_CN.get(ind.get("core_pce_yoy", ind.get("be10y", {})).get("dir"), "未知"),
             "detail": (f"核心PCE {ind.get('core_pce_yoy', {}).get('value', '-')}%"
                        if "core_pce_yoy" in ind else
                        f"BE {ind.get('be10y', {}).get('value', '-')}%")},
            {"name": "增长",
             "state": ("稳定" if (ex.get("unrate_chg3") is not None
                                  and ex.get("unrate_chg3") <= 0.3) else "走弱")
                      if ex.get("unrate_chg3") is not None else
                      ("稳定" if (ex.get("curve_raw") or 0) > -0.2 else "走弱"),
             "detail": (f"失业率 {ind.get('unrate', {}).get('value', '-')}%"
                        if "unrate" in ind else
                        f"2s10s {ex.get('curve_raw', 0):+.2f}pp")},
            {"name": "美元", "state": _DIR_CN.get(ind.get("dxy", {}).get("dir"), "未知"),
             "detail": f"DXY {ind.get('dxy', {}).get('value', '-')}"},
            {"name": "地缘风险", "state": "需人工跟踪", "detail": "暂未接入自动化数据源"},
        ],
        "transmission": [
            {"name": "实际利率", "state": _DIR_CN.get(ind.get("real10y", {}).get("dir"), "未知"),
             "detail": f"{ind.get('real10y', {}).get('value', '-')}%"},
            {"name": "流动性环境",
             "state": {"up": "收紧", "down": "转松", "flat": "平稳"}.get(
                 ind.get("sofr", {}).get("dir"), "未知"),
             "detail": f"SOFR {ind.get('sofr', {}).get('value', '-')}%"},
            {"name": "盈利预期", "state": {"up": "上修", "down": "下修", "flat": "持平"}.get(ex.get("earn_dir"), "未知"),
             "detail": f"净上修 {ind.get('eps_rev', {}).get('value', '-')}"},
            {"name": "风险偏好", "state": "改善" if (ex.get("vix_ratio") or 1) < 0.95 else "恶化",
             "detail": f"VIX {ind.get('vix', {}).get('value', '-')}"},
            {"name": "金融条件",
             "state": ("收紧" if ind.get("fci", {}).get("dir") == "up" else
                       "宽松" if ind.get("fci", {}).get("dir") == "down" else "平稳"),
             "detail": f"NFCI {ind.get('fci', {}).get('value', '-')}"},
            {"name": "信用利差", "state": "扩大" if ind.get("credit", {}).get("dir") == "up" else "收窄",
             "detail": f"{ind.get('credit', {}).get('value', '-')}"},
        ],
    }

    return {
        "version": "1.0",
        "generated_at": meta["generated_at"],
        "as_of": as_of,
        "indicators": ind,
        "quadrant": quadrant,
        "score": score,
        "signals": signals,
        "assets": assets,
        "chain": chain,
        "regime": reg,
        "regime_agree": agree,
        "transitions": transitions.get(reg.get("key", ""), {}) if reg else {},
        "regime_history": [{"date": d, "key": k} for d, k in hist[-60:]],
        "stock_bond": {
            "now": corr_now,
            "series": [round(v, 3) for _d, v in corr_series[-90:]],
            "pct": percentile(corr_series) if corr_series else None,
            "note": ("正值＝股债同向、对冲失效；负值＝对冲有效。"
                     "研报结论：只有增长冲击(+0.30)与深度衰退(+0.27)时债券才真能护盘。"),
        },
        "lei": {
            "now": lei_series[-1][1] if lei_series else None,
            "date": lei_series[-1][0] if lei_series else None,
            "series": [round(v, 3) for _d, v in lei_series[-60:]],
            "components": lei_used,
        },
        "sources": sources,
        "extras": {k: v for k, v in ex.items() if not k.endswith("_series")},
        "nfci_series": ex.get("nfci_series") or [],
        "series_slim": {k: [round(v, 4) for _d, v in s[-90:]] for k, s in series.items()
                        if len(s) > 5},
    }
