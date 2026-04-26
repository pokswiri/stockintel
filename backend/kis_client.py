# -*- coding: utf-8 -*-
"""
kis_client.py
pykis (python-kis) 래퍼 - 일봉 차트 + 현재 시세 조회
pykis는 동기식이므로 ThreadPoolExecutor로 비동기 래핑
"""

import os
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

KIS_APP_KEY    = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_HTS_ID     = os.getenv("KIS_HTS_ID", "")
KIS_ACCOUNT    = os.getenv("KIS_ACCOUNT", "")

_kis = None
_executor = ThreadPoolExecutor(max_workers=5)
_init_lock = asyncio.Lock()


def _init_pykis():
    """pykis 초기화 (동기, 최초 1회만)"""
    global _kis
    if _kis is not None:
        return _kis
    if not KIS_APP_KEY or not KIS_APP_SECRET:
        return None
    try:
        from pykis import PyKis
        _kis = PyKis(
            id=KIS_HTS_ID or "unknown",
            account=KIS_ACCOUNT or "00000000-01",
            appkey=KIS_APP_KEY,
            secretkey=KIS_APP_SECRET,
            keep_token=True,
        )
        return _kis
    except Exception:
        return None


async def get_kis():
    """pykis 인스턴스 반환 (비동기 안전)"""
    global _kis
    if _kis is not None:
        return _kis
    async with _init_lock:
        if _kis is not None:
            return _kis
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _init_pykis)
        return _kis


def _fetch_chart_sync(code: str) -> dict:
    """동기: 일봉 60일 + 현재 시세 조회"""
    kis = _init_pykis()
    if kis is None:
        return {"error": "KIS not initialized", "code": code}
    try:
        stock = kis.stock(code)
        chart = stock.daily_chart(
            start=timedelta(days=70),  # 주말 포함 여유있게 70일
            market="KRX",
            period="day",
            adjust=True,
        )
        quote = stock.quote()
        bars = chart.bars  # list[KisChartBar], 오름차순

        # bars → 직렬화 가능한 dict list
        bars_data = [
            {
                "date": b.time.strftime("%Y%m%d"),
                "open": float(b.open),
                "high": float(b.high),
                "low": float(b.low),
                "close": float(b.close),
                "volume": b.volume,
                "amount": float(b.amount),
            }
            for b in bars
        ]

        # 52주 고저가 (indicator에서)
        w52_high = w52_low = 0.0
        try:
            w52_high = float(quote.indicator.week52_high)
            w52_low  = float(quote.indicator.week52_low)
        except Exception:
            pass

        return {
            "code": code,
            "name": getattr(quote, "name", "") or "",
            "sector": getattr(quote, "sector_name", "") or "",
            "price": float(quote.price),
            "prev_price": float(quote.prev_price),
            "volume": quote.volume,
            "prev_volume": int(getattr(quote, "prev_volume", 0) or 0),
            "market_cap": float(quote.market_cap),
            "per": float(getattr(quote.indicator, "per", 0) or 0),
            "pbr": float(getattr(quote.indicator, "pbr", 0) or 0),
            "week52_high": w52_high,
            "week52_low": w52_low,
            "halt": bool(quote.halt),
            "overbought": bool(quote.overbought),
            "bars": bars_data,
            "bars_count": len(bars_data),
        }
    except Exception as e:
        return {"error": str(e), "code": code}


async def fetch_chart(code: str) -> dict:
    """비동기: 일봉 차트 + 현재 시세 조회"""
    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(_executor, _fetch_chart_sync, code)
        return result
    except Exception as e:
        return {"error": str(e), "code": code}


async def fetch_charts_parallel(codes: list) -> dict:
    """여러 종목 차트 병렬 조회 (최대 5개 동시)"""
    tasks = [fetch_chart(code) for code in codes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = {}
    for i, r in enumerate(results):
        code = codes[i]
        if isinstance(r, dict) and "bars" in r:
            out[code] = r
        elif isinstance(r, Exception):
            out[code] = {"error": str(r), "code": code}
    return out


def is_pykis_available() -> bool:
    return bool(KIS_APP_KEY and KIS_APP_SECRET)
