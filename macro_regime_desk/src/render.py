# -*- coding: utf-8 -*-
"""渲染层：把 snapshot 渲染成单文件、离线可用的可视化工作台。"""

import html
import json

from indicators import mean
from model import QUADRANTS

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0a0d13; --card:#12171f; --card2:#161d27; --line:#222b38;
  --tx:#e7edf5; --tx2:#9aa8ba; --tx3:#67758a;
  --up:#ef4b5a; --dn:#12b886; --warn:#f0b90b; --acc:#4e9bff; --pink:#ff7ab2;
}
body{background:var(--bg);color:var(--tx);
  font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  font-size:14px;line-height:1.55;-webkit-font-smoothing:antialiased;padding:0 0 60px}
.wrap{max-width:1280px;margin:0 auto;padding:0 16px}
.mono{font-family:"SF Mono",ui-monospace,Menlo,Consolas,monospace;font-variant-numeric:tabular-nums}
a{color:var(--acc);text-decoration:none}

/* ---------- 顶栏 ---------- */
header{border-bottom:1px solid var(--line);background:linear-gradient(180deg,#0e131b,#0a0d13);
  padding:18px 0 14px;margin-bottom:20px;position:relative;overflow:hidden}
header:after{content:"";position:absolute;right:-80px;top:-80px;width:280px;height:280px;
  background:radial-gradient(circle,rgba(78,155,255,.18),transparent 70%);pointer-events:none}
.brand{display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.logo{width:26px;height:26px;border-radius:7px;background:linear-gradient(135deg,#4e9bff,#7b5cff);
  display:grid;place-items:center;font-size:13px;font-weight:700;color:#fff}
h1{font-size:17px;font-weight:600;letter-spacing:.3px}
.sub{color:var(--tx2);font-size:12px;margin-top:6px;display:flex;gap:14px;flex-wrap:wrap;align-items:center}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:5px;vertical-align:1px}
.tag{font-size:11px;padding:2px 8px;border-radius:20px;border:1px solid var(--line);
  color:var(--tx2);background:#0f141c;white-space:nowrap}

/* ---------- 卡片 ---------- */
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:16px}
.card h2{font-size:13px;font-weight:600;color:var(--tx2);letter-spacing:.6px;
  text-transform:uppercase;margin-bottom:12px;display:flex;justify-content:space-between;align-items:center}
.card h2 span{text-transform:none;letter-spacing:0;font-weight:400;color:var(--tx3);font-size:11px}
.grid{display:grid;gap:14px}

/* ---------- HERO ---------- */
.hero{display:grid;grid-template-columns:1.05fr 1.25fr 1fr;gap:14px;margin-bottom:14px}
@media(max-width:980px){.hero{grid-template-columns:1fr}}
.score-wrap{display:flex;align-items:center;gap:16px}
.ring{position:relative;flex:0 0 108px;height:108px}
.ring svg{transform:rotate(-90deg)}
.ring-val{position:absolute;inset:0;display:grid;place-items:center;text-align:center}
.ring-val b{font-size:26px;font-weight:650;line-height:1}
.ring-val i{font-style:normal;font-size:10px;color:var(--tx3);display:block;margin-top:3px}
.score-meta b{font-size:15px;display:block;margin-bottom:2px}
.score-meta p{color:var(--tx2);font-size:12px}
.parts{margin-top:12px;display:grid;gap:7px}
.part{display:grid;grid-template-columns:64px 1fr 34px;align-items:center;gap:8px;font-size:11px;color:var(--tx2)}
.bar{height:5px;border-radius:3px;background:#1c2532;overflow:hidden}
.bar i{display:block;height:100%;border-radius:3px}

/* ---------- 四象限 ---------- */
.quad{display:flex;flex-direction:column;align-items:center}
.quad svg{width:100%;max-width:340px;height:auto}
.q-legend{display:flex;gap:8px;margin-top:10px;flex-wrap:wrap;justify-content:center}
.q-legend div{font-size:11px;color:var(--tx2);padding:3px 9px;border-radius:6px;
  border:1px solid var(--line);background:#0f141c}
.q-legend div.on{border-color:#4e9bff;color:#dbe8ff;background:rgba(78,155,255,.12)}

/* ---------- 结论 ---------- */
.verdict-big{font-size:19px;font-weight:650;line-height:1.4;margin-bottom:4px}
.kw{display:inline-block;font-size:12px;padding:3px 10px;border-radius:20px;
  background:rgba(255,122,178,.12);color:var(--pink);border:1px solid rgba(255,122,178,.25);margin:6px 0 10px}
.bullets{list-style:none;display:grid;gap:8px;margin-top:6px}
.bullets li{font-size:12.5px;color:var(--tx2);padding-left:16px;position:relative}
.bullets li:before{content:"";position:absolute;left:2px;top:7px;width:5px;height:5px;
  border-radius:50%;background:var(--acc)}
.bullets li b{color:var(--tx)}

/* ---------- 指标卡 ---------- */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(214px,1fr));gap:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:13px;padding:13px 14px;
  position:relative;overflow:hidden}
.kpi.core{border-color:#2b3a52;background:linear-gradient(160deg,#141c28,#12171f)}
.kpi .kname{font-size:12px;color:var(--tx2);display:flex;justify-content:space-between;gap:6px;align-items:flex-start}
.kpi .kval{font-size:23px;font-weight:640;margin:7px 0 2px;letter-spacing:-.4px}
.kpi .kval small{font-size:12px;font-weight:400;color:var(--tx2);margin-left:2px}
.kchg{font-size:11.5px;color:var(--tx3);display:flex;gap:9px;flex-wrap:wrap}
.kchg b{font-weight:500}
.kpi .spark{margin-top:8px;height:30px}
.pctbar{margin-top:8px;height:4px;border-radius:2px;background:#1c2532;position:relative}
.pctbar i{position:absolute;top:-2px;width:2px;height:8px;background:var(--acc);border-radius:1px}
.knote{font-size:10.5px;color:var(--tx3);margin-top:8px;line-height:1.45;border-top:1px dashed #1e2733;padding-top:7px}
.arrow{font-size:11px;padding:1px 6px;border-radius:5px;white-space:nowrap}
.a-up{color:#ff8b95;background:rgba(239,75,90,.13)}
.a-down{color:#4fd1a5;background:rgba(18,184,134,.13)}
.a-flat{color:var(--tx2);background:#1a2230}

/* ---------- 信号 ---------- */
.sig-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:11px}
.sig{border:1px solid var(--line);border-radius:12px;padding:12px 13px;background:var(--card);position:relative}
.sig.on{border-color:rgba(239,75,90,.45);background:linear-gradient(160deg,rgba(239,75,90,.09),var(--card))}
.sig.near{border-color:rgba(240,185,11,.35);background:linear-gradient(160deg,rgba(240,185,11,.06),var(--card))}
.sig .st{position:absolute;right:12px;top:12px;font-size:10px;padding:2px 7px;border-radius:20px;
  border:1px solid var(--line);color:var(--tx3)}
.sig.on .st{color:#ff8b95;border-color:rgba(239,75,90,.4);background:rgba(239,75,90,.1)}
.sig.near .st{color:var(--warn);border-color:rgba(240,185,11,.35);background:rgba(240,185,11,.1)}
.sig .sid{font-size:10px;color:var(--tx3);letter-spacing:.5px}
.sig .sname{font-size:13px;font-weight:600;margin:2px 0 4px;padding-right:56px}
.sig .smean{font-size:12px;color:var(--tx2)}
.sig .sread{font-size:11px;color:var(--tx3);margin-top:7px;border-top:1px dashed #1e2733;padding-top:6px}
.sig .starget{font-size:10.5px;color:var(--acc);margin-top:5px}

/* ---------- 资产表 ---------- */
.tbl{width:100%;border-collapse:collapse;font-size:12.5px}
.tbl th{text-align:right;font-weight:500;color:var(--tx3);font-size:11px;padding:8px 8px;
  border-bottom:1px solid var(--line);white-space:nowrap}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.tbl td{padding:9px 8px;border-bottom:1px solid #171e28;text-align:right;white-space:nowrap}
.tbl tr:last-child td{border-bottom:none}
.tbl .tk{font-weight:600}
.tbl .nm{font-size:10.5px;color:var(--tx3);font-weight:400}
.fitcell{display:flex;align-items:center;gap:7px;justify-content:flex-end}
.fitbar{width:54px;height:5px;background:#1c2532;border-radius:3px;overflow:hidden}
.fitbar i{display:block;height:100%;border-radius:3px}
.up{color:var(--up)}.dn{color:var(--dn)}.flat{color:var(--tx2)}
.tablewrap{overflow-x:auto;-webkit-overflow-scrolling:touch}

/* ---------- 传导链 ---------- */
.chain{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px;align-items:stretch}
@media(max-width:820px){.chain{grid-template-columns:1fr}}
.chain-col{background:var(--card2);border:1px solid var(--line);border-radius:12px;padding:12px}
.chain-col .ttl{font-size:11px;color:var(--tx3);letter-spacing:1px;margin-bottom:9px;text-transform:uppercase}
.node{display:flex;justify-content:space-between;align-items:baseline;gap:8px;padding:6px 0;
  border-bottom:1px dashed #1c242f;font-size:12px}
.node:last-child{border:none;padding-bottom:0}
.node .nv{color:var(--tx2);font-size:11px}
.node .ns{font-size:11px;padding:1px 6px;border-radius:4px;background:#1a2230;color:var(--tx2)}

/* ---------- 审计 ---------- */
.audit{font-size:11.5px;color:var(--tx2)}
.audit .row{display:grid;grid-template-columns:1.1fr .6fr .5fr 2fr;gap:10px;padding:7px 0;
  border-bottom:1px dashed #1a222d;align-items:center}
.audit .row.head{color:var(--tx3);font-size:10.5px;letter-spacing:.5px;text-transform:uppercase}
.ok{color:var(--dn)}.stale{color:var(--warn)}.failed{color:var(--up)}
footer{margin-top:26px;padding-top:16px;border-top:1px solid var(--line);
  color:var(--tx3);font-size:11px;line-height:1.7}
.sec{margin-bottom:16px}
/* ---------- 今日解读 ---------- */
.read h3{font-size:13px;color:var(--acc);letter-spacing:.5px;margin:18px 0 10px;
  padding-bottom:6px;border-bottom:1px solid #1e2733;font-weight:600}
.read .hl{font-size:21px;font-weight:650;line-height:1.35;margin:3px 0 0;letter-spacing:-.2px}
.read .lead{font-size:13px;color:var(--tx2);line-height:1.75;margin-top:10px}
.thing{background:var(--card2);border:1px solid var(--line);border-radius:11px;
  padding:13px 15px;margin-bottom:10px;position:relative}
.thing .no{position:absolute;left:-1px;top:13px;width:3px;height:22px;border-radius:2px;background:var(--acc)}
.thing h4{font-size:13.5px;font-weight:600;margin-bottom:7px;padding-left:11px;color:var(--tx)}
.thing p{font-size:12.5px;color:var(--tx2);line-height:1.72;margin-bottom:6px}
.thing p:last-child{margin-bottom:0}
.achip{display:flex;align-items:center;gap:9px;padding:9px 11px;border-radius:9px;
  background:var(--card2);border:1px solid var(--line);font-size:12px}
.achip .dot2{width:7px;height:7px;border-radius:50%;flex:0 0 7px}
.act{background:var(--card2);border:1px solid var(--line);border-radius:11px;padding:12px 14px}
.act .who{font-size:12px;font-weight:600;color:var(--acc);margin-bottom:7px}
.act .do{font-size:12px;color:var(--tx);line-height:1.65;margin-bottom:6px}
.act .why{font-size:11px;color:var(--tx3);line-height:1.6;border-top:1px dashed #1e2733;padding-top:6px}
.falsify{background:rgba(240,185,11,.06);border:1px solid rgba(240,185,11,.25);
  border-radius:11px;padding:13px 15px}
.falsify li{font-size:12px;color:var(--tx2);line-height:1.7;margin-left:16px;margin-bottom:5px}
@media(max-width:560px){
  .wrap{padding:0 11px}
  .card{padding:13px;border-radius:12px}
  .tbl th:nth-child(4),.tbl td:nth-child(4){display:none}   /* 窄屏隐藏「1周」列 */
  .kpi .kval{font-size:21px}
  .hero{grid-template-columns:1fr}
  .audit .row{grid-template-columns:1fr .55fr .6fr;font-size:11px}
  .audit .row span:last-child{grid-column:1/-1;color:var(--tx3)}
  .part{grid-template-columns:57px 1fr 30px}
}
.note-inline{font-size:11px;color:var(--tx3);margin-top:9px}
"""


# ------------------------------------------------------------------ 小工具
def esc(s):
    return html.escape(str(s if s is not None else ""))


def fnum(v, digits=2, suffix=""):
    if v is None:
        return "—"
    if isinstance(v, str):
        return esc(v)
    return f"{v:,.{digits}f}{suffix}"


def fsigned(v, digits=2, suffix=""):
    if v is None:
        return "—"
    return f"{v:+.{digits}f}{suffix}"


def color_for(v):
    if v is None or abs(v) < 1e-9:
        return "flat"
    return "up" if v > 0 else "dn"


def spark(vals, w=200, h=30, color="#4e9bff", fill=True):
    """极简 SVG 折线（无依赖，离线可用）。"""
    vals = [v for v in vals if v is not None]
    if len(vals) < 3:
        return '<svg width="100%%" height="%d"></svg>' % h
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    n = len(vals)
    pts = []
    for i, v in enumerate(vals):
        x = i / (n - 1) * (w - 2) + 1
        y = h - 3 - (v - lo) / rng * (h - 6)
        pts.append(f"{x:.1f},{y:.1f}")
    line = " ".join(pts)
    area = (f'<polygon points="1,{h} {line} {w - 1},{h}" fill="{color}" opacity=".10"/>'
            if fill else "")
    return (f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" width="100%" height="{h}">'
            f'{area}<polyline points="{line}" fill="none" stroke="{color}" '
            f'stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round"/></svg>')


def ring(score, color, size=108):
    r = size / 2 - 8
    c = 2 * 3.14159265 * r
    off = c * (1 - score / 100.0)
    return (f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
            f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="#1e2836" stroke-width="9"/>'
            f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{color}" stroke-width="9" '
            f'stroke-linecap="round" stroke-dasharray="{c:.1f}" stroke-dashoffset="{off:.1f}"/></svg>')


def quad_svg(q):
    """实际利率 × 盈利预期 四象限，带当前点位。"""
    W, H = 340, 300
    cx, cy = W / 2, H / 2
    x, y = q.get("x", 0), q.get("y", 0)
    px = cx + x * 112
    py = cy - y * 96
    cells = [
        (0, 0, "rgba(239,75,90,.10)", "Q1 杀估值+杀盈利", cx / 2, cy - 44),
        (cx, 0, "rgba(240,185,11,.09)", "Q2 盈利对抗紧缩", cx + cx / 2, cy - 44),
        (0, cy, "rgba(240,185,11,.08)", "Q3 宽松 vs 基本面", cx / 2, cy + 44),
        (cx, cy, "rgba(18,184,134,.11)", "Q4 估值+盈利双击", cx + cx / 2, cy + 44),
    ]
    buf = []
    for (x0, y0, col, label, tx, ty) in cells:
        buf.append(f'<rect x="{x0}" y="{y0}" width="{cx}" height="{cy}" fill="{col}"/>')
        buf.append(f'<text x="{tx}" y="{ty}" font-size="10.5" fill="#8593a5" '
                   f'text-anchor="middle">{label}</text>')
    buf.append(f'<line x1="0" y1="{cy}" x2="{W}" y2="{cy}" stroke="#2b3646" stroke-width="1"/>')
    buf.append(f'<line x1="{cx}" y1="0" x2="{cx}" y2="{H}" stroke="#2b3646" stroke-width="1"/>')
    buf.append(f'<text x="{W-10}" y="{cy-8}" font-size="9.5" fill="#5d6b7f" text-anchor="end">盈利上修 →</text>')
    buf.append(f'<text x="10" y="{cy-8}" font-size="9.5" fill="#5d6b7f">← 盈利下修</text>')
    buf.append(f'<text x="{cx+8}" y="16" font-size="9.5" fill="#5d6b7f">↑ 实际利率上行</text>')
    buf.append(f'<text x="{cx+8}" y="{H-6}" font-size="9.5" fill="#5d6b7f">↓ 实际利率下行</text>')
    # 当前点
    label_y = py + 22 if py + 22 < H - 26 else py - 17
    buf.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="16" fill="{q.get("color", "#4e9bff")}" opacity=".15"/>')
    buf.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6.5" fill="{q.get("color", "#4e9bff")}" '
               f'stroke="#0a0d13" stroke-width="2"/>')
    buf.append(f'<text x="{px:.1f}" y="{label_y:.1f}" font-size="10.5" fill="#e7edf5" '
               f'text-anchor="middle">{q.get("id", "")} 当前</text>')
    return (f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
            f'style="border-radius:10px;border:1px solid #222b38;background:#0d121a">'
            + "".join(buf) + "</svg>")


# ------------------------------------------------------------------ 各区块
def sec_hero(s):
    sc, q = s["score"], s["quadrant"]
    parts = "".join(
        f'<div class="part"><span>{esc(v["label"])}</span>'
        f'<span class="bar"><i style="width:{v["score"]:.0f}%;background:'
        f'{"#12b886" if v["score"]>=60 else ("#f0b90b" if v["score"]>=45 else "#ef4b5a")}"></i></span>'
        f'<span class="mono" style="text-align:right">{v["score"]:.0f}</span></div>'
        for v in sc["parts"].values())

    quad_badge = "".join(
        f'<div class="{"on" if q["id"] == k["id"] else ""}">{k["id"]} {k["keyword"]}</div>'
        for k in QUADRANTS.values())

    bullets = []
    i = s["indicators"]
    if i.get("real10y"):
        r = i["real10y"]
        bullets.append(f'实际利率 <b>{fnum(r["value"])}%</b>（近1月 {fsigned(r["chg1m"])}pp，'
                       f'近一年 {fnum(r["pct"],0)}% 分位）—— 估值端'
                       f'{"压力在加大" if r["dir"]=="up" else ("压力在缓解" if r["dir"]=="down" else "压力持平")}')
    if i.get("eps_rev"):
        e = i["eps_rev"]
        bullets.append(f'盈利预期净上修比率 <b>{fnum(e["value"],3)}</b>'
                       f'（>0.5 表示上修占优）—— 基本面{"有支撑" if (e["value"] or 0)>0.5 else "在走弱"}')
    if i.get("vix"):
        v = i["vix"]
        bullets.append(f'VIX <b>{fnum(v["value"],1)}</b>，期限结构 '
                       f'{fnum(i.get("vix_ts",{}).get("value"),2)}x '
                       f'（{esc(i.get("vix_ts",{}).get("note","")).split("：")[0] or "—"}）'
                       f'—— 风险偏好{"收缩" if v["dir"]=="up" else "修复"}')
    if i.get("credit"):
        c = i["credit"]
        bullets.append(f'{esc(c["name"])} <b>{fnum(c["value"], 1 if c["unit"] == "idx" else 2)}</b>'
                       f'—— 信用{"在恶化" if c["dir"]=="up" else ("在改善" if c["dir"]=="down" else "持平")}')

    qx = q.get("x", 0)
    gap = ""
    if qx > 0 and sc["total"] < 45:
        gap = ("象限维度偏正面，但总分偏低 —— 逆风不在盈利侧，而在"
               "信用/波动率/美元侧，这类组合通常表现为指数扛跌但内部剧烈分化。")
    elif qx < 0 and sc["total"] > 60:
        gap = ("盈利维度在恶化，但总分尚可 —— 支撑来自估值或信用，属于"
               "『宽松支撑 vs 基本面走弱』，反弹持续性要靠盈利预期止跌来验证。")
    gap_html = f'<div class="note-inline" style="color:#f0b90b">⚠ {esc(gap)}</div>' if gap else ""

    return f"""
<div class="hero">
  <div class="card">
    <h2>宏观环境评分 <span>0–100 · 越高越友好</span></h2>
    <div class="score-wrap">
      <div class="ring">{ring(sc["total"], sc["color"])}
        <div class="ring-val"><div><b style="color:{sc['color']}">{sc['total']:.0f}</b>
        <i>{esc(sc["band"])}</i></div></div>
      </div>
      <div class="score-meta">
        <b>{esc(sc["verdict"])}</b>
        <p>由实际利率、盈利预期、信用、美元、波动率五维加权，权重见页脚。</p>
      </div>
    </div>
    <div class="parts">{parts}</div>
  </div>

  <div class="card quad">
    <h2>实际利率 × 盈利预期 四象限 <span>模型核心坐标系</span></h2>
    {quad_svg(q)}
    <div class="q-legend">{quad_badge}</div>
  </div>

  <div class="card">
    <h2>今日结论 <span>{esc(s["as_of"] or "")}</span></h2>
    <div class="verdict-big">{esc(q["id"])} · {esc(q["label"])}</div>
    <div class="kw">{esc(q["keyword"])}</div>
    <p style="color:var(--tx2);font-size:12.5px">{esc(q["desc"])}</p>
    <ul class="bullets">{"".join(f"<li>{b}</li>" for b in bullets)}</ul>
    <div class="note-inline">对应动作：{esc(q["playbook"])}</div>
    {gap_html}
  </div>
</div>"""


KPI_ORDER = ["real10y", "eps_rev", "credit", "dxy", "vix_ts",
             "core_pce_yoy", "unrate", "claims", "be10y",
             "fci", "nom10y", "curve", "wti", "sofr", "vix"]
CORE = {"real10y", "eps_rev", "credit", "dxy", "vix_ts"}
# 只有日频指标迟到才算异常；月频/周频本身就有发布节奏
DAILY = {"real10y", "credit", "dxy", "vix", "vix_ts", "nom10y", "curve",
         "sofr", "t10yie", "wti"}


def sec_kpi(s):
    i = s["indicators"]
    slim = s.get("series_slim", {})
    keymap = {"real10y": "real10y", "eps_rev": "eps_rev", "credit": "credit_series",
              "dxy": "dxy", "vix_ts": "vix", "be10y": "be10y", "nom10y": "nom10y",
              "curve": "curve_series", "sofr": "sofr", "vix": "vix",
              "core_pce_yoy": "core_pce_yoy", "unrate": "unrate",
              "claims": "claims", "t10yie": "t10yie", "wti": "wti", "fci": "nfci"}
    cards = []
    for k in KPI_ORDER:
        d = i.get(k)
        if not d:
            continue
        digit = {"real10y": 2, "eps_rev": 3, "dxy": 2, "vix_ts": 2,
                 "be10y": 2, "t10yie": 2, "nom10y": 2, "curve": 2, "sofr": 2,
                 "vix": 1, "core_pce_yoy": 1, "unrate": 1, "claims": 1,
                 "wti": 1, "fci": 3}.get(k, 2)
        if k == "credit":
            digit = 1 if d["unit"] == "idx" else 2
        suffix = {"%": "%", "pp": "pp", "x": "x", "$": "$", "万": "万",
                  "idx": ""}.get(d["unit"], "")
        arrow = {"up": ("↑ 上行", "a-up"), "down": ("↓ 下行", "a-down"),
                 "flat": ("→ 走平", "a-flat"), "na": ("— 待累积", "a-flat")}[d["dir"]]
        vals = slim.get(keymap.get(k, k), [])
        cols = "#ef4b5a" if d["dir"] == "up" else ("#12b886" if d["dir"] == "down" else "#4e9bff")
        pct = d.get("pct")
        pctbar = (f'<div class="pctbar" title="{esc(d.get("pct_label", "近一年分位"))} {pct:.0f}%">'
                  f'<i style="left:calc({pct:.0f}% - 1px)"></i></div>') if pct is not None else ""
        sparkline = spark(vals[-90:], color=cols) if vals else ""
        lag = d.get("lag_days")
        lag_badge = (f'<span title="数据日期 {esc(d.get("as_of",""))}，滞后 {lag} 天" '
                     f'style="color:#f0b90b;font-size:10px;margin-left:4px">⚠ 滞后</span>'
                     if (lag is not None and lag > 5 and k in DAILY) else "")
        cls = "kpi core" if k in CORE else "kpi"
        cards.append(f"""
    <div class="{cls}">
      <div class="kname"><span>{esc(d["name"])}{lag_badge}</span><span class="arrow {arrow[1]}">{arrow[0]}</span></div>
      <div class="kval mono">{fnum(d["value"], digit)}<small>{suffix}</small></div>
      <div class="kchg mono">
        <span>1周 <b class="{color_for(d["chg1w"])}">{fsigned(d["chg1w"], digit)}</b></span>
        <span>{esc(d.get("chg_label", "1月"))} <b class="{color_for(d["chg1m"])}">{fsigned(d["chg1m"], digit)}</b></span>
        {f'<span>{esc(d.get("pct_label", "分位"))} <b>{pct:.0f}%</b></span>' if pct is not None else ''}
      </div>
      <div class="spark">{sparkline}</div>
      {pctbar}
      <div class="knote">{esc(d["note"])}<br><span style="color:#4a566a">源：{esc(d["src"])}</span></div>
    </div>""")
    return f"""
<div class="sec">
  <div class="card">
    <h2>核心指标 <span>深色＝模型每周必看的 5 个指标 · 迷你图为近 90 个交易日</span></h2>
    <div class="kpi-grid">{"".join(cards)}</div>
  </div>
</div>"""


DIM_CN = {"gy": "通胀水平", "gl": "增长水平", "dc": "通胀3月变化", "dl": "增长3月变化",
          "xv": "跨资产波动", "fci": "金融条件FCI", "dfci": "FCI 3月变化"}


def vbar(v, lo=-3.0, hi=3.0):
    """以 0 为中心的横向条，用于状态向量可视化。"""
    span = hi - lo
    zero = (0 - lo) / span * 100
    pct = abs(v) / span * 100
    left = zero if v >= 0 else zero - pct
    col = "#ef4b5a" if v > 0.15 else ("#12b886" if v < -0.15 else "#4e9bff")
    return (f'<div style="position:relative;height:6px;background:#1c2532;border-radius:3px">'
            f'<div style="position:absolute;left:{zero:.1f}%;top:-3px;width:1px;height:12px;'
            f'background:#3a4658"></div>'
            f'<div style="position:absolute;left:{left:.1f}%;width:{pct:.1f}%;height:6px;'
            f'border-radius:3px;background:{col}"></div></div>')


def sec_narrative(s):
    nv = s.get("narrative")
    if not nv:
        return ""
    things = "".join(
        f'<div class="thing"><div class="no"></div><h4>{n}. {esc(t["title"])}</h4>'
        + "".join(f'<p>{esc(p)}</p>' for p in t["body"] if p)
        + "</div>"
        for n, t in enumerate(nv["things"], 1))

    chips = "".join(
        f'<div class="achip"><span class="dot2" style="background:{a["tone"]}"></span>'
        f'<span style="flex:1"><b>{esc(a["name"])}</b>'
        f'<span style="color:var(--tx3);font-size:10.5px"> {esc(a["ticker"])}</span></span>'
        f'<span style="color:{a["tone"]};font-size:11px">{esc(a["word"])}</span>'
        f'<span class="mono" style="color:var(--tx2);font-size:11px;width:26px;text-align:right">'
        f'{a["fit"]:.0f}</span></div>'
        for a in nv["assets"])

    acts = "".join(
        f'<div class="act"><div class="who">{esc(a["who"])}</div>'
        f'<div class="do">{esc(a["do"])}</div>'
        f'<div class="why">为什么：{esc(a["why"])}</div></div>'
        for a in nv["actions"])

    fals = "".join(f"<li>{esc(f)}</li>" for f in nv["falsify"])

    watch = "".join(
        f'<div style="font-size:12px;color:var(--tx2);padding:6px 0;'
        f'border-bottom:1px dashed #1c242f">'
        f'<span class="mono" style="color:var(--tx3)">{esc(w["date"][5:])}</span>　'
        f'<b style="color:var(--tx)">{esc(w["event"])}</b>'
        f'<span style="color:var(--tx3)">　预期 {esc(w["cons"] or "—")}｜前值 {esc(w["prev"] or "—")}</span>'
        + (f'<div style="color:var(--tx3);font-size:11px;margin-top:3px">{esc(w["hint"])}</div>'
           if w["hint"] else "")
        + "</div>"
        for w in nv["watch"])

    return f"""
<div class="sec">
  <div class="card read" style="border-color:#2b3a52;background:linear-gradient(165deg,#141c28,#12171f)">
    <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap">
      <div style="flex:1;min-width:240px">
        <div style="font-size:10.5px;color:var(--tx3);letter-spacing:1.2px">今日解读 · 大白话版</div>
        <div class="hl">{esc(nv["headline"])}</div>
      </div>
      <span class="tag" style="border-color:#3a4a63;color:#bfd4f5">{esc(nv["regime_name"])}</span>
    </div>
    <p class="lead">{esc(nv["standfirst"])}</p>

    <h3>今天最该知道的三件事</h3>
    {things}

    <h3>各类资产现在舒服吗</h3>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(215px,1fr));gap:8px">
      {chips}
    </div>
    <div class="note-inline">「顺风/微风/没风/逆风」是当前环境对这类资产的有利程度，不是涨跌预测。</div>

    <h3>如果要动手，怎么动</h3>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(255px,1fr));gap:10px">
      {acts}
    </div>

    {f'<h3>接下来一周盯什么</h3>{watch}' if watch else ''}

    <h3>什么情况下这个判断是错的</h3>
    <div class="falsify"><ul>{fals}</ul></div>
  </div>
</div>"""


def sec_regime(s):
    r = s.get("regime")
    if not r:
        return ""
    vec = r.get("vector") or {}
    dims = "".join(
        f'<div style="display:grid;grid-template-columns:78px 1fr 42px;gap:9px;'
        f'align-items:center;font-size:11.5px;color:var(--tx2);margin-bottom:8px">'
        f'<span>{DIM_CN.get(k, k)}</span>{vbar(v)}'
        f'<span class="mono" style="text-align:right;color:var(--tx)">{v:+.2f}</span></div>'
        for k, v in vec.items())

    top3 = "".join(
        f'<div style="display:flex;justify-content:space-between;font-size:11.5px;'
        f'padding:5px 0;border-bottom:1px dashed #1c242f">'
        f'<span style="color:var(--tx2)">{esc(x["name"])}</span>'
        f'<span class="mono">{x["prob"]*100:.0f}%</span></div>'
        for x in r.get("top", []))

    tr = s.get("transitions") or {}
    trs = "".join(
        f'<div style="display:flex;justify-content:space-between;font-size:11.5px;padding:4px 0">'
        f'<span style="color:var(--tx2)">{esc(REGIME_CN.get(k, k))}</span>'
        f'<span class="mono">{v*100:.0f}%</span></div>'
        for k, v in list(tr.items())[:4])

    agree = s.get("regime_agree") or ""

    return f"""
<div class="sec">
  <div class="card">
    <h2>宏观状态机 · 花旗 10-Regime <span>7 维状态向量 → 高斯核打分 + 硬规则 · 与四象限互为交叉验证</span></h2>
    <div class="grid" style="grid-template-columns:1.15fr 1fr .85fr">
      <div>
        <div style="font-size:11px;color:var(--tx3);letter-spacing:.5px">CURRENT REGIME</div>
        <div style="font-size:19px;font-weight:650;margin:5px 0 3px;color:{r.get('color','#4e9bff')}">
          {esc(r.get("name",""))}</div>
        <div style="font-size:11.5px;color:var(--tx3);margin-bottom:9px">
          拟合度 {r.get("prob",0)*100:.0f}% · 置信 {esc(r.get("confidence","—"))}
          {"· 由硬规则判定" if r.get("by_rule") else ""}</div>
        <p style="font-size:12px;color:var(--tx2);line-height:1.6">{esc(r.get("desc",""))}</p>
        <div style="margin-top:11px;padding-top:10px;border-top:1px dashed #1e2733">
          <div style="font-size:10.5px;color:var(--tx3);margin-bottom:6px">状态转移倾向（历史频率）</div>
          {trs or '<span style="font-size:11px;color:var(--tx3)">历史样本不足</span>'}
        </div>
      </div>
      <div>
        <div style="font-size:10.5px;color:var(--tx3);margin-bottom:9px">7 维状态向量（标准化）</div>
        {dims}
        <div class="note-inline" style="margin-top:6px">
          正值＝高于历史均值。研报要点：只看水平不够，变化率才能分开「衰退早期」和「晚期」。
        </div>
      </div>
      <div>
        <div style="font-size:10.5px;color:var(--tx3);margin-bottom:9px">候选状态（拟合度）</div>
        {top3}
        <div style="margin-top:12px;padding-top:10px;border-top:1px dashed #1e2733">
          <div style="font-size:10.5px;color:var(--tx3);margin-bottom:6px">该状态的资产倾向</div>
          <div style="font-size:11.5px;color:var(--tx2);line-height:1.8">
            {"　".join(f'{n}{"+" if v>0 else ""}{v:.1f}' for n, v in [
              ("股票", r.get("tilt",{}).get("equity",0)),
              ("债券", r.get("tilt",{}).get("bond",0)),
              ("信用", r.get("tilt",{}).get("credit",0)),
              ("黄金", r.get("tilt",{}).get("gold",0)),
              ("能源", r.get("tilt",{}).get("energy",0)),
              ("优质股", r.get("tilt",{}).get("quality",0)),
              ("现金", r.get("tilt",{}).get("cash",0))])}
          </div>
        </div>
      </div>
    </div>
    {f'<div class="note-inline" style="color:#f0b90b;margin-top:12px">⚠ 交叉验证：{esc(agree)}</div>' if agree else ''}
  </div>
</div>"""


REGIME_CN = {
    "normal": "常态", "recovery": "复苏", "goldilocks": "金发女孩",
    "growth_shock": "增长冲击", "tightening_fci": "条件收紧",
    "stagflation_loose": "滞胀·松", "early_stagflation_tight": "早期滞胀·紧",
    "inflationary_boom": "通胀繁荣", "recession": "衰退", "fin_shock": "金融冲击",
}


def sec_diversification(s):
    sb = s.get("stock_bond") or {}
    lei = s.get("lei") or {}
    now = sb.get("now")
    pct = sb.get("pct")
    nfci = s["indicators"].get("fci")
    corr_col = "#12b886" if (now is not None and now < -0.1) else "#ef4b5a"
    verdict = ("对冲有效" if (now or 0) < -0.25 else
               ("对冲失效" if (now or 0) > 0.05 else "对冲力度偏弱"))
    return f"""
<div class="sec">
  <div class="card">
    <h2>分散化体检 <span>研报核心结论：股债对冲是「状态依赖」的，不能默认它一直有效</span></h2>
    <div class="grid" style="grid-template-columns:repeat(auto-fit,minmax(230px,1fr))">
      <div>
        <div class="kname" style="font-size:12px;color:var(--tx2)">股债 63 日滚动相关性</div>
        <div class="kval mono" style="font-size:23px;margin:6px 0 2px;color:{corr_col}">
          {"—" if now is None else f"{now:+.3f}"}</div>
        <div style="font-size:11px;color:var(--tx3)">
          {verdict}{"" if pct is None else f" · 近一年 {pct:.0f}% 分位（越低＝对冲越强）"}</div>
        <div class="spark">{spark(sb.get("series") or [], color=corr_col)}</div>
        <div class="knote">{esc(sb.get("note", ""))}</div>
      </div>
      <div>
        <div class="kname" style="font-size:12px;color:var(--tx2)">金融条件指数 NFCI</div>
        <div class="kval mono" style="font-size:23px;margin:6px 0 2px">
          {"—" if not nfci else f"{nfci['value']:+.3f}"}</div>
        <div style="font-size:11px;color:var(--tx3)">
          {"负值＝宽松，正值＝收紧"}{"" if not nfci else f" · 3 月 {nfci.get('chg1m',0):+.2f}"}</div>
        <div class="spark">{spark(s.get("nfci_series") or [], color="#4e9bff")}</div>
        <div class="knote">芝加哥联储官方金融条件指数（周频）。研报认定：<b>late-cycle 的信号主要在 FCI 收紧</b>，
        而不在增长或通胀本身。</div>
      </div>
      <div>
        <div class="kname" style="font-size:12px;color:var(--tx2)">自建领先指标 LEI（z 值）</div>
        <div class="kval mono" style="font-size:23px;margin:6px 0 2px">
          {"—" if lei.get("now") is None else f"{lei['now']:+.2f}"}</div>
        <div style="font-size:11px;color:var(--tx3)">数据 {esc(lei.get("date") or "—")} · {len(lei.get("components") or [])} 个成分</div>
        <div class="spark">{spark(lei.get("series") or [], color="#12b886" if (lei.get("now") or 0) > 0 else "#ef4b5a")}</div>
        <div class="knote">OECD G7 领先指标已停更，按 Conference Board 成分思路自建：
        初请、建筑许可、消费者预期、制造业工时、期限利差、信用利差、股价。</div>
      </div>
    </div>
  </div>
</div>"""


def sec_calendar(s):
    cal = s.get("calendar") or []
    if not cal:
        return ""
    rows = []
    for e in cal[:12]:
        rows.append(f"""<tr>
      <td style="text-align:left"><span class="mono" style="color:var(--tx2)">{esc(e['date'][5:])}</span>
        <span style="color:var(--tx3);font-size:11px;margin-left:6px">{esc(e['time'])}</span></td>
      <td style="text-align:left;color:var(--tx)">{esc(e['event'])}</td>
      <td class="mono">{esc(e['consensus']) or '—'}</td>
      <td class="mono" style="color:var(--tx3)">{esc(e['previous']) or '—'}</td>
    </tr>""")
    return f"""
<div class="sec">
  <div class="card">
    <h2>未来一周关键事件 <span>美国数据与政策 · 时间为美东时间</span></h2>
    <div class="tablewrap">
    <table class="tbl">
      <thead><tr><th>日期 / 时间</th><th>事件</th><th>市场预期</th><th>前值</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    </div>
    <div class="note-inline">事件本身不构成信号，但它决定了本周哪条传导链最可能被验证（利率/通胀/就业三类冲击的传导路径不同）。</div>
  </div>
</div>"""


STATE_CN = {"on": "已触发", "near": "部分满足", "off": "未触发"}


def sec_signals(s):
    cards = []
    for x in s["signals"]:
        cards.append(f"""
    <div class="sig {x['state']}">
      <div class="st">{STATE_CN[x['state']]}</div>
      <div class="sid">SIGNAL {x['id']:02d}</div>
      <div class="sname">{esc(x['name'])}</div>
      <div class="smean">→ {esc(x['meaning'])}</div>
      <div class="starget">标的：{esc(x['target'])}</div>
      <div class="sread">{esc(x['read'])}</div>
    </div>""")
    n_on = sum(1 for x in s["signals"] if x["state"] == "on")
    n_near = sum(1 for x in s["signals"] if x["state"] == "near")
    return f"""
<div class="sec">
  <div class="card">
    <h2>9 组组合信号 <span>已触发 {n_on} · 部分满足 {n_near} · 未触发 {9-n_on-n_near}</span></h2>
    <div class="sig-grid">{"".join(cards)}</div>
    <div class="note-inline">信号为「其他条件相近时」的倾向性判断，需与四象限和评分交叉验证，不构成交易指令。</div>
  </div>
</div>"""


def sec_assets(s):
    rows = []
    for a in sorted(s["assets"], key=lambda x: -(x["fit"] or 0)):
        fit = a["fit"]
        if fit is None:
            fit_cell = "—"
        else:
            c = "#12b886" if fit >= 60 else ("#f0b90b" if fit >= 45 else "#ef4b5a")
            fit_cell = (f'<div class="fitcell"><span class="fitbar"><i style="width:{fit:.0f}%;'
                        f'background:{c}"></i></span><span class="mono">{fit:.0f}</span></div>')
        rows.append(f"""<tr>
      <td><span class="tk">{esc(a['ticker'])}</span> <span class="nm">{esc(a['name'])}</span></td>
      <td class="mono">{fnum(a['px'])}</td>
      <td class="mono {color_for(a['chg1d'])}">{fsigned(a['chg1d'],2,'%')}</td>
      <td class="mono {color_for(a['chg1w'])}">{fsigned(a['chg1w'],2,'%')}</td>
      <td class="mono {color_for(a['chg1m'])}">{fsigned(a['chg1m'],2,'%')}</td>
      <td class="mono {color_for(a['chg3m'])}">{fsigned(a['chg3m'],2,'%')}</td>
      <td>{fit_cell}</td>
    </tr>""")
    return f"""
<div class="sec">
  <div class="card">
    <h2>资产温度表 <span>适配度＝当前宏观环境对该资产的有利程度（0–100，模型口径，非预测收益）</span></h2>
    <div class="tablewrap">
    <table class="tbl">
      <thead><tr><th>资产</th><th>最新价</th><th>1日</th><th>1周</th><th>1月</th><th>3月</th><th>环境适配度</th></tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
    </div>
  </div>
</div>"""


def sec_chain(s):
    def col(title, items):
        nodes = "".join(
            f'<div class="node"><span>{esc(n["name"])}</span>'
            f'<span><span class="nv">{esc(n["detail"])}</span> '
            f'<span class="ns">{esc(n["state"])}</span></span></div>'
            for n in items)
        return f'<div class="chain-col"><div class="ttl">{esc(title)}</div>{nodes}</div>'
    c = s["chain"]
    return f"""
<div class="sec">
  <div class="card">
    <h2>传导链：宏观变量 → 中间变量 → 资产 <span>市场交易的不是事件本身，而是事件对估值、盈利、风险偏好的影响</span></h2>
    <div class="chain">
      {col("① 宏观变量", c["macro"])}
      {col("② 中间传导", c["transmission"])}
      {col("③ 资产表现", [
        {"name":"美股 / SPY","detail":"综合适配度","state":f'{next((a["fit"] for a in s["assets"] if a["ticker"]=="SPY"), 0):.0f}'},
        {"name":"科技股 / QQQ","detail":"估值×盈利","state":f'{next((a["fit"] for a in s["assets"] if a["ticker"]=="QQQ"), 0):.0f}'},
        {"name":"黄金 / GLD","detail":"实际利率×美元","state":f'{next((a["fit"] for a in s["assets"] if a["ticker"]=="GLD"), 0):.0f}'},
        {"name":"银行股 / KBE","detail":"信用×融资成本","state":f'{next((a["fit"] for a in s["assets"] if a["ticker"]=="KBE"), 0):.0f}'},
        {"name":"能源 / XLE","detail":"商品动量×通胀","state":f'{next((a["fit"] for a in s["assets"] if a["ticker"]=="XLE"), 0):.0f}'},
        {"name":"短债 / SHY","detail":"现金类避风港","state":f'{next((a["fit"] for a in s["assets"] if a["ticker"]=="SHY"), 0):.0f}'},
      ])}
    </div>
    <div class="note-inline">③ 中数值 = 该资产当前环境适配度（0–100），可与① ②的方向交叉验证是否自洽。</div>
  </div>
</div>"""


def sec_history(s):
    h = s.get("history") or []
    if len(h) < 2:
        return f"""
<div class="sec"><div class="card">
  <h2>历史轨迹 <span>随每日运行累积</span></h2>
  <p class="note-inline">已累积 {len(h)} 个交易日。坚持每天运行，这里会长出环境评分与象限迁移的时间序列，
  用来验证「象限切换」是否领先资产价格 —— 这是模型最有价值的部分，但需要时间喂数据。</p>
</div></div>"""
    vals = [r["score"] for r in h]
    dates = [r["date"] for r in h]
    qs = "".join(
        f'<span class="tag" style="margin-right:6px">{esc(r["date"][5:])} · {esc(r.get("quadrant",""))}</span>'
        for r in h[-8:])
    return f"""
<div class="sec"><div class="card">
  <h2>环境评分轨迹 <span>{esc(dates[0])} → {esc(dates[-1])} · {len(h)} 个交易日</span></h2>
  {spark(vals, w=600, h=80, color="#4e9bff")}
  <div style="display:flex;gap:14px;margin-top:10px;flex-wrap:wrap;font-size:11px;color:var(--tx3)">
    <span>最新 {vals[-1]:.0f}</span>
    <span>区间 {min(vals):.0f} ~ {max(vals):.0f}</span>
    <span>均值 {mean(vals):.0f}</span>
  </div>
  <div style="margin-top:12px">{qs}</div>
</div></div>"""


def sec_audit(s):
    rows = []
    for k, v in s["sources"].items():
        cls = {"ok": "ok", "stale": "stale", "failed": "failed"}.get(v["status"], "")
        icon = {"ok": "●", "stale": "◐", "failed": "○"}.get(v["status"], "?")
        rows.append(f'<div class="row"><span>{esc(v["name"])}</span>'
                    f'<span class="{cls}">{icon} {esc(v["status"])}</span>'
                    f'<span class="mono">{esc(v.get("last") or "—")}</span>'
                    f'<span>{esc(v["detail"])}</span></div>')
    return f"""
<div class="sec">
  <div class="card">
    <h2>数据审计 <span>每个结论都能回溯到源；降级与代理会在这里显式暴露</span></h2>
    <div class="audit">
      <div class="row head"><span>数据源</span><span>状态</span><span>最新日期</span><span>说明</span></div>
      {"".join(rows)}
    </div>
    <div class="note-inline">
      抓取时间 {esc(s["generated_at"])} ｜ 信用利差优先用 FRED 官方 ICE BofA HY OAS；
      FRED 不可达时自动切换为「HYG/IEF 相对强弱」代理，并在指标卡上标注，恢复后自动切回官方值。
    </div>
  </div>
</div>"""


def render(s):
    q = s["quadrant"]
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#0a0d13">
<title>宏观环境工作台 · {esc(s['as_of'] or '')}</title>
<style>{CSS}</style>
</head>
<body>
<header><div class="wrap">
  <div class="brand">
    <div class="logo">M</div>
    <h1>宏观环境工作台</h1>
    <span class="tag">实际利率 × 盈利预期 × 信用 × 美元 × 波动率</span>
  </div>
  <div class="sub">
    <span><span class="dot" style="background:{s['score']['color']}"></span>
      环境评分 {s['score']['total']:.0f} · {esc(s['score']['band'])}</span>
    <span>象限 <b>{esc(q['id'])}</b> {esc(q['label'])}</span>
    {f'<span>状态 <b style="color:{s["regime"].get("color","#4e9bff")}">{esc(s["regime"].get("cn",""))}</b></span>' if s.get("regime") else ''}
    <span>数据日期 <b class="mono">{esc(s['as_of'] or '—')}</b></span>
    <span>生成于 <span class="mono">{esc(s['generated_at'])}</span></span>
  </div>
</div></header>

<div class="wrap">
{sec_hero(s)}
{sec_narrative(s)}
{sec_kpi(s)}
{sec_regime(s)}
{sec_diversification(s)}
{sec_calendar(s)}
{sec_signals(s)}
{sec_assets(s)}
{sec_chain(s)}
{sec_history(s)}
{sec_audit(s)}

<footer>
  <b>模型口径</b>：四象限（实际利率方向 × 盈利预期方向）决定大环境；9 组组合信号做交叉验证；
  环境评分 = 实际利率 22% + 盈利预期 23% + 信用 20% + 波动率 15% + 美元 10% + 增长动能 10%（缺项自动归一化）。<br>
  <b>方向判定</b>：以近 21 个交易日的指标变化量与阈值比较，超出阈值才算上行/下行，避免噪声误判。<br>
  <b>免责声明</b>：本工作台为宏观环境监测与模型可视化工具，所有结论来自公开数据的机械计算，
  不构成投资建议、荐股或交易信号。数据以官方源为准，如有偏差以源站为准。<br>
  <b>下一步</b>：把本页面加入书签，每个交易日运行一次 <span class="mono">./run_daily.sh</span> 即自动刷新。
</footer>
</div>
</body>
</html>"""


# ------------------------------------------------------------------ 每日简报
def daily_note(s):
    i, q, sc = s["indicators"], s["quadrant"], s["score"]
    L = []
    L.append(f"# 宏观环境日报 · {s['as_of']}\n")
    L.append(f"**象限 {q['id']}｜{q['label']}**（{q['keyword']}）　"
             f"**环境评分 {sc['total']:.0f}/100 · {sc['band']}**\n")
    L.append(f"> {q['desc']}\n")
    r = s.get("regime")
    if r:
        L.append("## 宏观状态机（花旗 10-Regime）\n")
        L.append(f"**{r['name']}**　拟合度 {r['prob']*100:.0f}% · 置信 {r['confidence']}"
                 f"{'· 硬规则判定' if r.get('by_rule') else ''}\n")
        L.append(f"> {r['desc']}\n")
        vec = r.get("vector") or {}
        L.append("| 维度 | 标准化值 |")
        L.append("|---|---|")
        for k in ["gy", "gl", "dc", "dl", "xv", "fci", "dfci"]:
            if k in vec:
                L.append(f"| {DIM_CN.get(k,k)} | {vec[k]:+.2f} |")
        L.append("")
        til = r.get("tilt") or {}
        L.append("资产倾向：" + "　".join(
            f"{n}{v:+.1f}" for n, v in [("股票", til.get("equity",0)), ("债券", til.get("bond",0)),
                                        ("信用", til.get("credit",0)), ("黄金", til.get("gold",0)),
                                        ("能源", til.get("energy",0)), ("优质股", til.get("quality",0)),
                                        ("现金", til.get("cash",0))]) + "\n")
        if s.get("regime_agree"):
            L.append(f"**交叉验证**：{s['regime_agree']}\n")

    sb = s.get("stock_bond") or {}
    if sb.get("now") is not None:
        L.append(f"**股债 63 日相关性 {sb['now']:+.3f}**"
                 f"（负＝对冲有效，正＝股债同跌；研报称只有增长冲击与深度衰退时可靠）\n")
    L.append("## 五个核心指标\n")
    L.append("| 指标 | 最新 | 变化 | 方向 | 近一年分位 |")
    L.append("|---|---|---|---|---|")
    for k in ["real10y", "eps_rev", "credit", "dxy", "vix_ts"]:
        d = i.get(k)
        if not d:
            continue
        pct = "—" if d["pct"] is None else f"{d['pct']:.0f}%"
        dg = 1 if d["unit"] == "idx" else 2
        lab = d.get("chg_label", "1月")
        L.append(f"| {d['name']} | {fnum(d['value'],dg)} | {lab} {fsigned(d['chg1m'],dg)} | "
                 f"{d['dir']} | {pct} |")
    L.append("")
    L.append("## 信号灯\n")
    for x in s["signals"]:
        mark = {"on": "🔴 触发", "near": "🟡 部分", "off": "⚪ 未触发"}[x["state"]]
        L.append(f"- {mark} **{x['id']}. {x['name']}** → {x['meaning']}（{x['read']}）")
    L.append("")
    L.append("## 资产适配度\n")
    L.append("| 资产 | 最新价 | 1月 | 3月 | 环境适配度 |")
    L.append("|---|---|---|---|---|")
    for a in sorted(s["assets"], key=lambda y: -(y["fit"] or 0)):
        fit = "—" if a["fit"] is None else f"{a['fit']:.0f}"
        L.append(f"| {a['ticker']} {a['name']} | {fnum(a['px'])} | {fsigned(a['chg1m'],2,'%')} | "
                 f"{fsigned(a['chg3m'],2,'%')} | {fit} |")
    L.append("")
    L.append(f"## 对应动作\n{q['playbook']}\n")
    L.append("---")
    L.append(f"生成于 {s['generated_at']}｜数据源：美国财政部、CBOE、ECB、Nasdaq、NY Fed"
             f"｜不构成投资建议")
    return "\n".join(L)
