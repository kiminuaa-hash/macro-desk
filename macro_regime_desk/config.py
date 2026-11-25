# -*- coding: utf-8 -*-
"""宏观环境工作台 · 全局配置

模型来源：用户上传的《宏观投资：9组组合信号》《实际利率×盈利预期四象限》
         《从宏观变量到资产表现》《每周跟踪5个指标》
本文件把所有可调参数集中在一处，改模型只需改这里。
"""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
RAW = DATA / "raw"
SERIES = DATA / "series"
SNAPSHOTS = DATA / "snapshots"
OUTPUT = ROOT / "output"
for _d in (RAW, SERIES, SNAPSHOTS, OUTPUT):
    _d.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------- 抓取参数
TZ_OFFSET = 8             # 时间戳按北京时间（UTC+8）显示
HTTP_TIMEOUT = 30
HTTP_RETRY = 3
HTTP_SLEEP = 1.2          # 同一数据源连续请求的间隔，避免被限流
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# FRED API Key：配上之后，信用利差换成官方 HY OAS，并解锁增长/通胀/商品三个维度。
# 走 api.stlouisfed.org，不依赖 fred 网站是否可达。
FRED_API_KEY = os.environ.get("FRED_API_KEY", "").strip()

# FRED 序列清单：name -> (series_id, 频率说明)
FRED_SERIES = {
    "hy_oas":      ("BAMLH0A0HYM2", "高收益债 OAS，日频"),
    "ig_oas":      ("BAMLC0A0CM",   "投资级 OAS，日频"),
    "t10yie":      ("T10YIE",       "10年通胀预期，日频"),
    "real10y_f":   ("DFII10",       "10年TIPS实际利率，日频（与财政部互校）"),
    "wti":         ("DCOILWTICO",   "WTI 原油现货，日频"),
    "claims":      ("ICSA",         "初请失业金人数，周频"),
    "unrate":      ("UNRATE",       "失业率，月频"),
    "core_pce":    ("PCEPILFE",     "核心PCE价格指数，月频"),
    "walcl":       ("WALCL",        "美联储总资产，周频"),
    # —— 以下为接入花旗 10-regime 框架后新增（金融条件 + 领先指标成分）——
    "nfci":        ("NFCI",         "芝加哥联储全国金融条件指数，周频（正值=收紧）"),
    "cpi":         ("CPIAUCSL",     "CPI 价格指数，月频"),
    "permit":      ("PERMIT",       "建筑许可，月频（LEI 成分）"),
    "umcsent":     ("UMCSENT",      "密歇根消费者预期，月频（LEI 成分）"),
    "awhameman":   ("AWHAEMAN",     "制造业平均周工时，月频（LEI 成分）"),
}

# ---------------------------------------------------------------- 资产池
# 模型里的资产表达，用 ETF 做可交易的代理
ASSETS = [
    # key        代码      名称                 模型中的角色
    ("SPY", "SPY", "标普500", "美股整体"),
    ("QQQ", "QQQ", "纳指100", "科技股 / 成长"),
    ("GLD", "GLD", "黄金", "贵金属"),
    ("KBE", "KBE", "银行股", "银行 / 信贷周期"),
    ("XLF", "XLF", "金融板块", "金融整体"),
    ("XLE", "XLE", "能源", "能源资产"),
    ("HYG", "HYG", "高收益债", "信用风险"),
    ("TLT", "TLT", "20年+美债", "长久期"),
    ("SHY", "SHY", "1-3年美债", "短债 / 现金类"),
    ("IEF", "IEF", "7-10年美债", "中期国债（信用代理基准）"),
    ("DBC", "DBC", "商品", "商品综合"),
    ("QUAL", "QUAL", "优质股因子", "Quality（花旗：FCI 收紧时的抗跌因子）"),
    ("TIP", "TIP", "TIPS债券", "实物资产（抗通胀）"),
    ("UUP", "UUP", "美元ETF", "美元（备用）"),
]

# 盈利预期采样池：标普500权重最大的 20 只，用分析师一致预期的 4 周修订方向
# 合成"大盘盈利预期动量"。Nasdaq 分析师接口逐只可查。
EPS_POOL = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "AVGO", "TSLA",
    "ORCL", "JPM", "LLY", "V", "XOM", "MA", "COST", "WMT",
    "NFLX", "JNJ", "PG", "HD",
]

# ---------------------------------------------------------------- 指标定义
# window: 判定"上行/下行"所用的回溯交易日数
WINDOWS = {"short": 5, "mid": 21, "long": 63}
DIR_WINDOW = 21           # 默认方向判定窗口（约1个月）
Z_WINDOW = 252            # z-score / 分位数窗口（约1年）

# 方向判定阈值：变化量超过该值才算"上行/下行"，否则视为"走平"
FLAT_EPS = {
    "real10y": 0.05,      # 实际利率，百分点
    "be10y": 0.05,        # 盈亏平衡通胀
    "dxy": 0.5,           # 美元指数点
    "hy_oas": 0.15,       # 信用利差，百分点
    "vix": 1.5,           # VIX 点
    "eps_rev": 0.03,      # 净上修比率
    "sofr": 0.05,
    "nom10y": 0.08,
    "curve_2s10s": 0.08,
}

# ---------------------------------------------------------------- 环境评分权重
# 总分 100，分值越高＝对风险资产越友好。负向指标已在计算时取反。
SCORE_WEIGHTS = {
    "real_rate": 22.0,    # 实际利率（估值）
    "earnings": 23.0,     # 盈利预期（基本面）
    "credit": 20.0,       # 信用利差（风险偏好）
    "vol": 15.0,          # 波动率与期限结构
    "dollar": 10.0,       # 美元（全球金融条件）
    "growth": 10.0,       # 增长动能（就业+通胀，有 FRED 时才启用）
}

SCORE_BANDS = [
    (75, "有利", "#0f9d58", "环境友好，风险资产顺风"),
    (60, "偏有利", "#4caf50", "温和顺风，可持有但需跟踪验证"),
    (45, "中性", "#f2b705", "多空交织，靠结构不靠方向"),
    (30, "偏不利", "#f57c00", "逆风渐强，控制仓位与久期"),
    (0, "不利", "#d93025", "多重逆风，防守优先"),
]
