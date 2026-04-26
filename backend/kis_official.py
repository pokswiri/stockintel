# -*- coding: utf-8 -*-
"""
kis_official.py
공식 KIS REST API (koreainvestment/open-trading-api 패턴) 직접 호출
- 토큰 발급 및 인메모리 캐싱
- 현재가 조회 (prdy_vrss_vol_rate, frgn_ntby_qty 포함)
- 투자자별 매매동향 (외국인/기관 순매수 30일)
- 외국인/기관 가집계 (장중 실시간)
"""

import os
import asyncio
import httpx
from datetime import datetime, timedelta

KIS_APP_KEY    = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET = os.getenv("KIS_APP_SECRET", "")
KIS_ACCOUNT    = os.getenv("KIS_ACCOUNT", "")

BASE_URL = "https://openapi.koreainvestment.com:9443"

# ── 토큰 인메모리 캐시 ────────────────────────────────────────
_token_cache = {"token": "", "expires_at": datetime.min}


async def get_token() -> str:
    """KIS 접근토큰 발급 (24시간 인메모리 캐싱)"""
    now = datetime.now()
    if _token_cache["token"] and now < _token_cache["expires_at"]:
        return _token_cache["token"]

    if not KIS_APP_KEY or not KIS_APP_SECRET:
        return ""

    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                BASE_URL + "/oauth2/tokenP",
                json=body,
                headers={"content-type": "application/json"},
            )
            r.raise_for_status()
            data = r.json()
            token = data.get("access_token", "")
            if token:
                _token_cache["token"] = token
                _token_cache["expires_at"] = now + timedelta(hours=23)
            return token
    except Exception:
        return ""


def _headers(token: str, tr_id: str) -> dict:
    return {
        "content-type": "application/json",
        "authorization": "Bearer " + token,
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }


async def fetch_current_price(code: str) -> dict:
    """
    국내주식 현재가 시세 조회
    TR_ID: FHKST01010100
    반환: 현재가, 등락률, 거래량, 전일거래량비율, 외국인순매수, 시가총액, 신고가여부
    """
    token = await get_token()
    if not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                BASE_URL + "/uapi/domestic-stock/v1/quotations/inquire-price",
                headers=_headers(token, "FHKST01010100"),
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_input_iscd": code,
                },
            )
            r.raise_for_status()
            o = r.json().get("output", {})

            def to_int(v):
                try:
                    return int(str(v).replace(",", ""))
                except Exception:
                    return 0

            def to_float(v):
                try:
                    return float(str(v).replace(",", ""))
                except Exception:
                    return 0.0

            return {
                "code": code,
                "price": to_int(o.get("stck_prpr", 0)),
                "change": to_int(o.get("prdy_vrss", 0)),
                "change_rate": to_float(o.get("prdy_ctrt", 0)),
                "volume": to_int(o.get("acml_vol", 0)),
                "volume_rate": to_float(o.get("prdy_vrss_vol_rate", 0)),  # 전일 대비 거래량 비율
                "frgn_net": to_int(o.get("frgn_ntby_qty", 0)),           # 외국인 당일 순매수
                "pgtr_net": to_int(o.get("pgtr_ntby_qty", 0)),           # 프로그램 당일 순매수
                "mktcap": to_int(o.get("hts_avls", 0)),
                "high_52w": to_int(o.get("stck_dryy_hgpr", 0)),          # 52주 최고가
                "low_52w": to_int(o.get("stck_dryy_lwpr", 0)),           # 52주 최저가
                "new_high_low": o.get("new_hgpr_lwpr_cls_code", ""),     # 신고가/신저가 코드
                "halt": o.get("temp_stop_yn", "N") == "Y",
                "overbought": o.get("ovtm_vi_cls_code", "") != "",
                "name": o.get("hts_kor_isnm", ""),
            }
    except Exception:
        return {}


async def fetch_investor_trend(code: str) -> dict:
    """
    투자자별 매매동향 조회 (최근 30일)
    TR_ID: FHKST01010900
    반환: 외국인/기관/개인 순매수 최근 5일·20일 합계
    당일 데이터: 장 종료 후 제공 (장중에는 전일까지만)
    """
    token = await get_token()
    if not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                BASE_URL + "/uapi/domestic-stock/v1/quotations/inquire-investor",
                headers=_headers(token, "FHKST01010900"),
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_input_iscd": code,
                },
            )
            r.raise_for_status()
            items = r.json().get("output", [])
            if not items:
                return {}

            def to_int(v):
                try:
                    return int(str(v).replace(",", "").replace("-", "0"))
                except Exception:
                    return 0

            # 최근 5일, 20일 외국인/기관 순매수 합산
            frgn_5d = sum(to_int(d.get("frgn_ntby_qty", 0)) for d in items[:5])
            frgn_20d = sum(to_int(d.get("frgn_ntby_qty", 0)) for d in items[:20])
            inst_5d = sum(to_int(d.get("orgn_ntby_qty", 0)) for d in items[:5])  # 기관 순매수
            inst_20d = sum(to_int(d.get("orgn_ntby_qty", 0)) for d in items[:20])

            # 연속 외국인 순매수 일수 계산
            consec_days = 0
            for d in items:
                val = to_int(d.get("frgn_ntby_qty", 0))
                if val > 0:
                    consec_days += 1
                else:
                    break

            # 최근 5일 외국인 양수 일수
            frgn_positive_days = sum(
                1 for d in items[:5]
                if to_int(d.get("frgn_ntby_qty", 0)) > 0
            )

            return {
                "frgn_5d": frgn_5d,
                "frgn_20d": frgn_20d,
                "inst_5d": inst_5d,
                "inst_20d": inst_20d,
                "frgn_consec_days": consec_days,
                "frgn_positive_days_5": frgn_positive_days,
                "latest_date": items[0].get("stck_bsop_date", "") if items else "",
            }
    except Exception:
        return {}


async def fetch_foreign_realtime(code: str) -> dict:
    """
    외국인/기관 매매종목 가집계 (장중 실시간)
    TR_ID: FHKST01010000
    갱신: 09:30, 11:20, 13:20, 14:30
    """
    token = await get_token()
    if not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                BASE_URL + "/uapi/domestic-stock/v1/quotations/inquire-investor",
                headers=_headers(token, "FHKST01010900"),
                params={
                    "fid_cond_mrkt_div_code": "J",
                    "fid_input_iscd": code,
                },
            )
            r.raise_for_status()
            items = r.json().get("output", [])
            if not items:
                return {}
            d = items[0]

            def to_int(v):
                try:
                    return int(str(v).replace(",", "").replace("-", "0"))
                except Exception:
                    return 0

            return {
                "frgn_today": to_int(d.get("frgn_ntby_qty", 0)),
                "inst_today": to_int(d.get("orgn_ntby_qty", 0)),
                "date": d.get("stck_bsop_date", ""),
            }
    except Exception:
        return {}


async def batch_fetch_prices(codes: list) -> dict:
    """여러 종목 현재가 병렬 조회"""
    tasks = [fetch_current_price(code) for code in codes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return {
        codes[i]: results[i]
        for i in range(len(codes))
        if isinstance(results[i], dict) and results[i]
    }


async def batch_fetch_investors(codes: list) -> dict:
    """여러 종목 투자자 동향 병렬 조회 (딜레이 포함 - API 한도 준수)"""
    result = {}
    for i, code in enumerate(codes):
        if i > 0:
            await asyncio.sleep(0.12)  # 초당 8회 이하
        data = await fetch_investor_trend(code)
        if data:
            result[code] = data
    return result


def is_kis_available() -> bool:
    return bool(KIS_APP_KEY and KIS_APP_SECRET)


async def fetch_daily_chart(code: str, days: int = 70) -> dict:
    """
    공식 KIS REST API로 일봉 차트 조회 (pykis 불필요)
    TR_ID: FHKST03010100
    """
    token = await get_token()
    if not token:
        return {}
    from datetime import date, timedelta
    end_dt   = date.today().strftime("%Y%m%d")
    start_dt = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                BASE_URL + "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
                headers=_headers(token, "FHKST03010100"),
                params={
                    "FID_COND_MRKT_DIV_CODE": "J",
                    "FID_INPUT_ISCD": code,
                    "FID_INPUT_DATE_1": start_dt,
                    "FID_INPUT_DATE_2": end_dt,
                    "FID_PERIOD_DIV_CODE": "D",
                    "FID_ORG_ADJ_PRC": "1",
                },
            )
            r.raise_for_status()
            data = r.json()
            output2 = data.get("output2", [])  # 일별 데이터
            output1 = data.get("output1", {})  # 종목 기본 정보

            def to_int(v):
                try: return int(str(v).replace(",", ""))
                except: return 0
            def to_float(v):
                try: return float(str(v).replace(",", ""))
                except: return 0.0

            bars = []
            for d in reversed(output2):  # 오름차순 정렬
                dt = d.get("stck_bsop_date", "")
                if not dt:
                    continue
                bars.append({
                    "date": dt,
                    "open":   to_float(d.get("stck_oprc", 0)),
                    "high":   to_float(d.get("stck_hgpr", 0)),
                    "low":    to_float(d.get("stck_lwpr", 0)),
                    "close":  to_float(d.get("stck_clpr", 0)),
                    "volume": to_int(d.get("acml_vol", 0)),
                    "amount": to_float(d.get("acml_tr_pbmn", 0)),
                })

            if not bars:
                return {}

            return {
                "code": code,
                "name": output1.get("hts_kor_isnm", ""),
                "price": to_float(output1.get("stck_prpr", 0)),
                "week52_high": to_float(output1.get("stck_dryy_hgpr", 0)),
                "week52_low":  to_float(output1.get("stck_dryy_lwpr", 0)),
                "bars": bars,
                "bars_count": len(bars),
            }
    except Exception as e:
        return {"error": str(e), "code": code}


async def batch_fetch_charts(codes: list) -> dict:
    """여러 종목 일봉 차트 병렬 조회 (공식 KIS REST, pykis 불필요)"""
    # 최대 5개 동시 (API 한도 준수)
    semaphore = asyncio.Semaphore(5)
    async def _fetch(code):
        async with semaphore:
            await asyncio.sleep(0.05)
            return code, await fetch_daily_chart(code)
    tasks = [_fetch(c) for c in codes]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out = {}
    for r in results:
        if isinstance(r, tuple):
            code, data = r
            if isinstance(data, dict) and "bars" in data:
                out[code] = data
    return out
