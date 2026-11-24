# -*- coding: utf-8 -*-
"""统一的抓取层：重试、超时、本地缓存、单源失败不影响整体。"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from config import HTTP_RETRY, HTTP_SLEEP, HTTP_TIMEOUT, RAW, UA

_last_hit = {}


def get_text(url, cache_name=None, host_key=None, headers=None,
             timeout=None, retry=None):
    """抓取文本。失败时若存在本地缓存则回退到缓存，并在返回值里标记 stale。"""
    host_key = host_key or url.split("/")[2]
    # 同一 host 的请求之间稍作停顿
    gap = time.time() - _last_hit.get(host_key, 0)
    if gap < HTTP_SLEEP:
        time.sleep(HTTP_SLEEP - gap)

    timeout = timeout or HTTP_TIMEOUT
    retry = retry or HTTP_RETRY
    hdrs = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "en-US,en;q=0.9"}
    if headers:
        hdrs.update(headers)

    err = None
    for i in range(retry):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8", "ignore")
            _last_hit[host_key] = time.time()
            if cache_name:
                (RAW / cache_name).write_text(text, encoding="utf-8")
            return text, None
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:120]}"
            time.sleep(1.5 * (i + 1))

    _last_hit[host_key] = time.time()
    if cache_name:
        p = RAW / cache_name
        if p.exists():
            age_h = (time.time() - p.stat().st_mtime) / 3600
            return p.read_text(encoding="utf-8"), f"{err}（回退本地缓存，{age_h:.1f}h 前）"
    return None, err


def get_json(url, cache_name=None, host_key=None, timeout=None, retry=None):
    text, err = get_text(url, cache_name=cache_name, host_key=host_key,
                         headers={"Accept": "application/json"},
                         timeout=timeout, retry=retry)
    if text is None:
        return None, err
    try:
        return json.loads(text), err
    except Exception as e:  # noqa: BLE001
        return None, f"JSON解析失败: {e}"


def num(s):
    """把 '1,234.5' / '$608.45' / 'N/A' 之类清洗成 float。"""
    if s is None:
        return None
    if isinstance(s, (int, float)):
        return float(s)
    t = str(s).replace(",", "").replace("$", "").replace("%", "").strip()
    if t in ("", "N/A", "n/a", "--", "&nbsp;"):
        return None
    try:
        return float(t)
    except ValueError:
        return None
