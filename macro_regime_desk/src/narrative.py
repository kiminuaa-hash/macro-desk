# -*- coding: utf-8 -*-
"""叙事引擎：把数据翻译成人话日报。

设计原则
  1. 每一句都必须挂在一个具体数字上，不用"较高/较低"这类模糊词。
  2. 先说人话，再说术语 —— 术语是给人查证用的，不是给人理解用的。
  3. 必须给动作，也必须给"什么情况下这个判断会错"，否则就是算命。
  4. 全部规则化生成，不调用任何模型，保证每天自动跑、内容可复现。
"""

# ------------------------------------------------------------ 状态类比
REGIME_ANALOGY = {
    "tightening_fci":
        "像银行的放贷部门突然收紧了审批——不是经济本身出了问题，而是钱不好借了。"
        "这种时候最先出事的是靠借钱活着的行业，最后才轮到指数。",
    "growth_shock":
        "像工厂突然接不到订单，开始给工人放假。需求端的塌陷比价格端的反应快得多。",
    "goldilocks":
        "经济增长不冷不热，通胀也不闹事。这是拿着资产什么都不用做、它自己会涨的阶段。",
    "stagflation_loose":
        "物价还在涨，但生意已经不好做了，偏偏央行还没下狠手。夹在中间最难受。",
    "early_stagflation_tight":
        "物价涨、生意差、钱还借不到，三个坏消息一起来。历史上这种组合几乎无处可躲。",
    "inflationary_boom":
        "生意很火，但物价也在飞。所有人都在赚钱，同时所有人都知道央行迟早要踩刹车。",
    "recession":
        "经济已经在坑底了，坏消息基本出完。这时候市场开始提前交易'下一轮放水'。",
    "fin_shock":
        "不是经济出了问题，是金融管道堵了，钱转不动。这种时候基本面分析基本失效。",
    "recovery":
        "最坏的时候已经过去，但还没有人敢确认。市场会反复怀疑，然后一路上涨。",
    "normal":
        "不冷不热，也没什么故事可讲。这种环境下赚的是结构性的钱，不是方向的钱。",
}

DEFENSIVE = {"tightening_fci", "early_stagflation_tight", "growth_shock",
             "fin_shock", "stagflation_loose"}


def _n(v, d=2, suffix=""):
    if v is None:
        return "—"
    return f"{v:,.{d}f}{suffix}"


def _s(v, d=2, suffix=""):
    if v is None:
        return "—"
    return f"{v:+.{d}f}{suffix}"


def _pct_word(p):
    """把分位翻译成人话。"""
    if p is None:
        return ""
    if p >= 90:
        return "过去一年里几乎最高"
    if p >= 75:
        return "过去一年里偏高"
    if p >= 55:
        return "过去一年里略高"
    if p >= 45:
        return "过去一年里居中"
    if p >= 25:
        return "过去一年里略低"
    if p >= 10:
        return "过去一年里偏低"
    return "过去一年里几乎最低"


# ---------------------------------------------------------------- 标题
def _headline(s):
    rg, q, sc = s.get("regime") or {}, s.get("quadrant") or {}, s.get("score") or {}
    rk = rg.get("key")
    defensive = rk in DEFENSIVE
    q_pos = q.get("id") in ("Q2", "Q4")   # 盈利上修侧（x 可能归零，不能用来判断）
    if defensive and q_pos:
        return "指数扛得住，但钱先扛不住了"
    if defensive and not q_pos:
        return "两头都在逆风，先别想着赚多少"
    if (not defensive) and q_pos:
        return "顺风的窗口还开着，但别当成常态"
    return "坏消息出得差不多了，可以开始找机会"


def _standfirst(s):
    """导语：三句话说清今天处在什么位置。"""
    q, rg, sc = s.get("quadrant") or {}, s.get("regime") or {}, s.get("score") or {}
    i = s.get("indicators") or {}
    real = i.get("real10y") or {}
    parts = []

    parts.append(f"现在市场处在「{rg.get('cn','未知')}」状态，"
                 f"同时落在「{q.get('label','未知')}」这个象限里。")

    if real.get("value") is not None:
        parts.append(f"把通胀扣掉以后，钱的真实成本是 {_n(real['value'])}%，"
                     f"{_pct_word(real.get('pct'))}——这一条决定了所有资产的天花板。")

    total = sc.get("total")
    if total is not None:
        if total >= 60:
            parts.append("综合打分偏正面，可以承担风险，但要清楚顺风来自哪里。")
        elif total >= 45:
            parts.append("综合打分在中性区间，这个阶段赚的是结构性的钱，不是大盘的钱。")
        else:
            parts.append("综合打分偏负面，这个阶段的正确动作是守，不是攻。")
    return "".join(parts)


# ------------------------------------------------------------ 三件事
def _three_things(s):
    """今天最该知道的三件事：发生了什么 → 意味着什么 → 有什么用。"""
    i = s.get("indicators") or {}
    rg = s.get("regime") or {}
    out = []

    # 1) 状态机判定
    if rg:
        vec = rg.get("vector") or {}
        drivers = sorted(vec.items(), key=lambda t: -abs(t[1]))[:2]
        d_txt = "、".join(f"{_dim_cn(k)}（{v:+.2f}）" for k, v in drivers)
        out.append({
            "title": "市场已经进入「%s」" % rg.get("cn", ""),
            "body": [f"状态判断最依赖的两个信号是 {d_txt}。"
                     f"{REGIME_ANALOGY.get(rg.get('key'), '')}",
                     f"这个状态的拟合度是 {rg.get('prob', 0)*100:.0f}%，"
                     f"置信度「{rg.get('confidence','—')}」。"
                     + ("这是由硬规则直接判定的，不是打分算出来的。"
                        if rg.get("by_rule") else "")
                     + "它接下来最可能转向的三个方向是："
                     + "、".join(f"{x.get('cn', x['name'])}（{x['prob']*100:.0f}%）"
                                for x in (rg.get("top") or [])[1:]) + "。"],
        })

    # 2) 最极端的那个指标
    extremes = []
    for k, v in i.items():
        if v.get("pct") is None:
            continue
        extremes.append((abs(v["pct"] - 50), k, v))
    if extremes:
        extremes.sort(reverse=True)
        _d, k, v = extremes[0]
        hi = v["pct"] >= 50
        out.append({
            "title": "%s正处在极值位置" % _short(k, v["name"]),
            "body": [f"现在是 {_n(v['value'], 3 if v['unit'] == 'idx' else 2)}"
                     f"{v['unit'] if v['unit'] not in ('idx',) else ''}，"
                     f"{_pct_word(v['pct'])}（{v['pct']:.0f}% 分位）。",
                     _translate(k, v)],
        })

    # 3) 最该警惕的矛盾
    sb = s.get("stock_bond") or {}
    agree = s.get("regime_agree")
    contra = []
    credit = i.get("credit") or {}
    vix = i.get("vix") or {}
    if credit.get("dir") == "up" and (vix.get("dir") == "up"):
        contra.append("信用利差在走阔，同时波动率在抬升——这两个一起动，通常不是好信号。")
    if sb.get("now") is not None and sb["now"] > -0.15:
        contra.append(f"股票和债券的 63 日相关性是 {sb['now']:+.2f}，"
                      f"负值才代表对冲有效，现在这个力度基本护不住。")
    if agree and "分歧" not in agree:
        contra.append(agree)
    if not contra:
        contra.append("几个维度暂时没有明显互相打脸的地方，这本身就是个还不错的信号。")
    out.append({"title": "最该警惕的不是坏数据，是这两个信号在打架",
                "body": contra[:2]})
    return out


SHORT_NAME = {
    "credit": "高收益债利差", "real10y": "实际利率", "fci": "金融条件",
    "eps_rev": "盈利预期", "vix_ts": "VIX 期限结构", "vix": "VIX",
    "core_pce_yoy": "核心通胀", "unrate": "失业率", "claims": "初请失业金",
    "dxy": "美元指数", "curve": "期限利差", "nom10y": "10年美债",
    "t10yie": "通胀预期", "be10y": "盈亏平衡通胀", "sofr": "短期融资成本",
    "wti": "WTI 油价", "fwd_eps": "前瞻盈利",
}


def _short(k, fallback=""):
    return SHORT_NAME.get(k) or fallback


def _dim_cn(k):
    return {"gy": "通胀水平", "gl": "增长水平", "dc": "通胀3月变化",
            "dl": "增长3月变化", "xv": "跨资产波动", "fci": "金融条件",
            "dfci": "金融条件3月变化"}.get(k, k)


# -------------------------------------------------------- 指标翻译
def _translate(k, v):
    """把单个指标翻译成一句人话。"""
    val, d, p = v.get("value"), v.get("dir"), v.get("pct")
    if val is None:
        return ""
    if k == "real10y":
        return (f"换个说法：美国政府借十年期的钱，扣掉通胀后的真实成本是 {val:.2f}%。"
                + ("这个数字越高，愿意为'未来的利润'付高价的人就越少，"
                   "所以成长股和黄金最怕它。" if d == "up" else
                   "它往下走的时候，估值压力就松一档。"))
    if k == "credit":
        bp = val * 100
        return (f"翻译一下：企业借钱的溢价是 {bp:.0f} 个基点。"
                + ("历史上要到 500 以上，才算'市场开始担心企业还不上钱'。"
                   if bp < 500 else "这个水平已经进入市场真正开始担心的区间。")
                + (f"但一个月里它已经走阔了 {_s(v.get('chg1m'),2)} 个百分点，"
                   f"方向比水平更值得注意。" if (v.get("chg1m") or 0) > 0.1 else ""))
    if k == "dxy":
        return (f"DXY 是美元对一篮子货币的强弱，现在 {val:.1f}。"
                + ("美元越强，全球的钱越往美国跑，新兴市场和黄金就越难受。"
                   if d == "up" else "美元走弱，是对非美资产最直接的松绑。"))
    if k == "vix":
        return (f"VIX 是市场为未来 30 天波动付的保险费，现在 {val:.1f}。"
                + ("20 以下叫平静，30 以上叫恐慌，现在处在偏紧张的一侧。"
                   if val >= 22 else "这个水平说明市场情绪还算稳。"))
    if k == "vix_ts":
        return (f"VIX 期限结构 {val:.2f}：大于 1 代表近月比远月更贵，也就是"
                f"大家更怕眼前而不是以后——这叫倒挂，通常出现在急跌之后。"
                if val > 1 else
                f"VIX 期限结构 {val:.2f}，远月比近月贵，属于正常升水，说明市场认为眼前的风险可控。")
    if k == "core_pce_yoy":
        return (f"美联储最看重的通胀指标同比 {val:.2f}%。"
                + ("这个水平离 2% 的目标还有明显距离，所以降息不会是免费的午餐。"
                   if val > 2.5 else "已经接近目标区间。"))
    if k in ("t10yie", "be10y"):
        return (f"市场自己定价的未来十年通胀是 {val:.2f}%，"
                f"和真实的核心通胀（{_n((v.get('core_pce_ref') or 0), 2)}%）之间是有分歧的——"
                f"市场相信通胀会下去，数据还没答应。"
                if val < 2.5 else
                f"市场定价的未来十年通胀是 {val:.2f}%，通胀预期没有明显回落。")
    if k == "unrate":
        return (f"失业率 {val:.1f}%。就业是增长的最后一道防线，它不坏，消费就还有底。"
                if val < 4.5 else f"失业率 {val:.1f}%，已经在抬升，这是增长走弱的确认信号。")
    if k == "claims":
        return f"每周新申请失业金的人数（4周均值）{val:.1f} 万人，这是最灵敏的就业温度计。"
    if k == "fci":
        return (f"芝加哥联储的金融条件指数 {val:+.2f}，负数代表宽松。"
                + ("但它在往上走，意味着宽松正在被抽走——这正是研报说的 late-cycle 特征。"
                   if d == "up" else "目前还在宽松区间。"))
    if k == "curve":
        return (f"2年和10年国债的利差是 {val:+.2f} 个百分点。"
                + ("正值代表曲线正常，银行放贷的生意能做。" if val > 0
                   else "负值（倒挂）历史上是衰退的领先信号。"))
    if k == "wti":
        return f"WTI 原油 {val:.1f} 美元，商品是通胀链条最上游的那一环。"
    if k == "sofr":
        return f"隔夜融资利率 {val:.2f}%，这是杠杆资金每天要付的成本。"
    if k == "eps_rev":
        return (f"跟踪的 20 只权重股里，过去四周分析师上修盈利预测的比例是 {val*100:.0f}%。"
                f"超过 50% 说明基本面还在被上调，这是目前唯一撑住市场的东西。"
                if val > 0.5 else
                f"上修比例只有 {val*100:.0f}%，不足一半，说明基本面支撑正在松动。")
    return ""


# -------------------------------------------------------- 状态故事
def _regime_story(s):
    rg = s.get("regime") or {}
    if not rg:
        return []
    tilt = rg.get("tilt") or {}
    order = sorted(tilt.items(), key=lambda t: -t[1])
    best = "、".join(_tilt_cn(k) for k, v in order[:2] if v > 0) or "没有明显占优的资产"
    worst = "、".join(_tilt_cn(k) for k, v in order[-2:] if v < 0) or "没有明显要回避的资产"
    return [
        f"在这个状态下，历史上占优的是{best}，吃亏的是{worst}。"
        f"{rg.get('desc','')}",
        "需要提醒的是：状态判断给的是'赔率'，不是'结果'。"
        "它说的是在这种环境里哪类资产更容易跑赢，不是说明天就会涨。",
    ]


def _tilt_cn(k):
    return {"equity": "股票", "bond": "债券", "credit": "信用债", "gold": "黄金",
            "energy": "能源商品", "quality": "优质公司", "cash": "现金"}.get(k, k)


# -------------------------------------------------------- 资产人话
def _assets_story(s):
    rows = []
    for a in sorted(s.get("assets") or [], key=lambda x: -(x["fit"] or 0)):
        fit = a.get("fit")
        if fit is None:
            continue
        if fit >= 70:
            word, tone = "顺风", "#12b886"
        elif fit >= 55:
            word, tone = "微风", "#4e9bff"
        elif fit >= 40:
            word, tone = "没风", "#f0b90b"
        else:
            word, tone = "逆风", "#ef4b5a"
        rows.append({"ticker": a["ticker"], "name": a["name"], "fit": fit,
                     "word": word, "tone": tone, "chg1m": a.get("chg1m"),
                     "why": _asset_why(a["ticker"], s)})
    return rows


def _asset_why(ticker, s):
    i = s.get("indicators") or {}
    real = i.get("real10y") or {}
    credit = i.get("credit") or {}
    rg = s.get("regime") or {}
    reason = {
        "TIP": "实际利率站在高位，锁住的是扣掉通胀后的真收益；通胀还在 4%，这层保护值钱。",
        "SHY": "短债几乎不吃利率波动的亏，钱贵的时候它就是最好的停车场。",
        "UUP": "美元强、金融条件收紧的时候，现金和美元本身就是一种仓位。",
        "QUAL": "钱变贵时，市场只愿意为'现在就能赚钱'的公司付溢价，不给故事付溢价。",
        "GLD": "黄金最怕实际利率上行，这一条现在还没缓解。",
        "SPY": "盈利还在支撑，但估值被实际利率压着，指数能扛、个股会分化。",
        "QQQ": "高久期资产，对实际利率最敏感，四象限里最脆弱的那一头。",
        "HYG": "信用利差在走阔，高收益债是这条链上最先感觉到疼的。",
        "TLT": "长债同时在和实际利率、通胀预期两件事较劲，方向不明时别重仓押注。",
        "IEF": "中久期国债，跌得比长债少，但也没多少进攻性。",
        "KBE": "银行吃的是曲线和信用，曲线还正常，但信用在走阔，两股力量对冲。",
        "XLF": "金融板块跟着信用周期走，现在处于'不坏但也没催化'的状态。",
        "XLE": "油价一个月跌了两位数，能源的顺风期已经过去。",
        "DBC": "商品整体在跌，供应端的冲击没有出现。",
    }.get(ticker, "")
    if ticker in ("SPY", "QQQ") and credit.get("dir") == "up":
        reason += "另外信用利差同时在走阔，这是分子和分母一起挨打。"
    return reason


# -------------------------------------------------------- 操作层
def _actions(s):
    rg = s.get("regime") or {}
    q = s.get("quadrant") or {}
    rk = rg.get("key")
    defensive = rk in DEFENSIVE
    out = []

    if defensive:
        out.append({
            "who": "如果你偏稳健（不能承受 10% 以上回撤）",
            "do": "把股票里'靠估值扩张赚钱'的部分，换成'靠现金流赚钱'的部分；"
                  "现金和短债留够，别为了多一个点的收益去承担久期风险。",
            "why": "这个状态下最常见的亏钱方式不是买错方向，是'以为自己还有时间'。",
        })
        out.append({
            "who": "如果你偏平衡（能承受 10-15% 回撤）",
            "do": "股票仓位不必急着砍，但要把结构换掉：减高估值成长、加质量和实物资产。"
                  "质量因子现在比大盘高出不少分，这不是巧合。",
            "why": "指数可能扛很久，但内部已经在换血。仓位不动、结构不动，等于什么都没做。",
        })
        eps = (s.get("indicators") or {}).get("eps_rev") or {}
        supporting = (eps.get("value") or 0) > 0.5 and eps.get("dir") != "down"
        out.append({
            "who": "如果你偏进取（能承受 20% 以上回撤）",
            "do": ("可以做多波动率、做空信用，但别轻易做空指数——"
                   "盈利预期还在 50% 以上，指数的抗跌能力比看起来强，"
                   "做空容易被打反抽。" if supporting else
                   "可以做多波动率、做空信用；盈利预期已经失去支撑，"
                   "做空指数的胜率在上升，但要等波动率确认放大再动手。"),
            "why": "这个状态最赚的是'结构'的钱，不是'方向'的钱。方向做反的成本极高。",
        })
    else:
        out.append({
            "who": "如果你偏稳健",
            "do": "可以适度提高权益暴露，但优先选质量好、现金流稳的，不要追高弹性品种。",
            "why": "顺风期最大的风险是买贵了，而不是买错了。",
        })
        out.append({
            "who": "如果你偏平衡",
            "do": "这是可以承担beta的阶段，但要把止盈规则先写好——顺风期结束时不会有通知。",
            "why": "环境转差通常先出现在信用和波动率上，等指数跌了再反应就晚了。",
        })
        out.append({
            "who": "如果你偏进取",
            "do": "顺风期适合加杠杆做多风险资产，但要盯住金融条件指数，它是这个状态的天花板。",
            "why": "FCI 一旦转正并持续，这个状态就会翻面。",
        })
    return out


# -------------------------------------------------------- 观察清单
def _watch(s):
    out = []
    i = s.get("indicators") or {}
    for e in (s.get("calendar") or [])[:5]:
        name = e.get("event", "")
        cons, prev = e.get("consensus", ""), e.get("previous", "")
        hint = ""
        low = name.lower()
        if "pce" in low or "cpi" in low:
            hint = "高于预期＝实际利率继续上行，成长股压力加大；低于预期＝象限可能松动。"
        elif "jobless" in low or "claims" in low:
            hint = ("申请人数上升＝就业市场在恶化，防守要更彻底；"
                    "申请人数下降＝就业还稳，盈利预期有底。")
        elif "payroll" in low or "employment" in low:
            hint = ("新增就业走强＝增长维度不坏，盈利预期有支撑；"
                    "转负＝四象限会往不利方向切。")
        elif "fomc" in low or "fed" in low:
            hint = "看的是措辞里对通胀的定性，不是这次动不动利率。"
        elif "pmi" in low or "ism" in low:
            hint = "跌破 50 是分水岭，直接改变增长维度。"
        elif "confidence" in low or "sentiment" in low:
            hint = "消费者信心是消费的前瞻，掉下来会顺着盈利预期往下传。"
        elif "crude" in low or "oil" in low:
            hint = "库存变化直接影响油价和通胀预期，是商品链条最短的那根神经。"
        elif "gdp" in low:
            hint = "增长维度的锚，修正方向比绝对值更重要。"
        out.append({"date": e.get("date", ""), "event": name,
                    "cons": cons, "prev": prev, "hint": hint})
    return out


# -------------------------------------------------------- 证伪条件
def _falsify(s):
    """把'什么情况下我错了'写清楚，这是报告可信度的来源。"""
    i = s.get("indicators") or {}
    out = []
    credit = i.get("credit") or {}
    fci = i.get("fci") or {}
    eps = i.get("eps_rev") or {}
    vix_ts = i.get("vix_ts") or {}

    if credit.get("value") is not None:
        out.append(f"信用利差回落到 {max(credit['value'] - 0.4, 2.5):.2f}% 以下并稳住两周"
                   f"——说明信用担忧是假的，防御可以撤。")
    if fci.get("value") is not None:
        out.append(f"金融条件指数掉到 -0.6 以下（重新转松）——状态机会切回常态，"
                   f"防守的价值大幅下降。")
    if eps.get("value") is not None:
        out.append(f"盈利预期净上修比率跌破 0.45——四象限会切到最不利的 Q1，"
                   f"那才是真正的分子分母双杀，现在还不是。")
    if vix_ts.get("value") is not None:
        out.append(f"VIX 期限结构连续一周维持在 1.15 以上——恐慌从'急跌'变成'持续'，"
                   f"性质就变了。")
    out.append("如果上面几条都没发生，而指数又跌了一波，那大概率是估值和仓位的事，"
               "不是基本面的事——这种情况下砍仓往往砍在最低点。")
    return out


# ---------------------------------------------------------------- 主入口
def build(snap):
    """生成完整叙事，供 render 转成 HTML 与 Markdown。"""
    rg = snap.get("regime") or {}
    return {
        "date": snap.get("as_of"),
        "headline": _headline(snap),
        "standfirst": _standfirst(snap),
        "regime_name": rg.get("name", ""),
        "regime_cn": rg.get("cn", ""),
        "things": _three_things(snap),
        "regime_story": _regime_story(snap),
        "assets": _assets_story(snap),
        "actions": _actions(snap),
        "watch": _watch(snap),
        "falsify": _falsify(snap),
        "agree": snap.get("regime_agree"),
    }


def to_markdown(nv, snap):
    L = [f"# {nv['headline']}", ""]
    L.append(f"*{nv['date']} · {nv['regime_name']}*")
    L.append("")
    L.append(nv["standfirst"])
    L.append("")
    L.append("---")
    L.append("")
    L.append("## 今天最该知道的三件事")
    L.append("")
    for n, t in enumerate(nv["things"], 1):
        L.append(f"### {n}. {t['title']}")
        L.append("")
        for p in t["body"]:
            if p:
                L.append(p)
                L.append("")
    L.append("## 这个环境到底是什么意思")
    L.append("")
    for p in nv["regime_story"]:
        if p:
            L.append(p)
            L.append("")
    L.append("## 各类资产现在舒服吗")
    L.append("")
    L.append("| 资产 | 状态 | 适配度 | 为什么 |")
    L.append("|---|---|---|---|")
    for a in nv["assets"]:
        L.append(f"| {a['name']}（{a['ticker']}） | {a['word']} | {a['fit']:.0f} | {a['why']} |")
    L.append("")
    L.append("## 如果要动手，怎么动")
    L.append("")
    for a in nv["actions"]:
        L.append(f"**{a['who']}**")
        L.append("")
        L.append(f"- 做法：{a['do']}")
        L.append(f"- 原因：{a['why']}")
        L.append("")
    if nv["watch"]:
        L.append("## 接下来一周盯什么")
        L.append("")
        for w in nv["watch"]:
            L.append(f"- **{w['date'][5:]}｜{w['event']}**"
                     f"（预期 {w['cons'] or '—'}，前值 {w['prev'] or '—'}）")
            if w["hint"]:
                L.append(f"  - {w['hint']}")
        L.append("")
    L.append("## 什么情况下这个判断是错的")
    L.append("")
    for f in nv["falsify"]:
        L.append(f"- {f}")
    L.append("")
    L.append("---")
    L.append("")
    L.append("*本报告由公开数据按固定规则自动生成，用于理解环境，不构成投资建议。"
             "所有阈值和逻辑都在 README 里可查、可改、可复现。*")
    return "\n".join(L)
