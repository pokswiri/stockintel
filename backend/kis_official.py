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

            def to_signed_int(v):
                """음수(매도) 포함 정수 변환 - 콤마만 제거, 부호 유지"""
                try:
                    return int(str(v).replace(",", ""))
                except Exception:
                    return 0

            # 최근 5일, 20일 외국인/기관 순매수 합산 (음수=매도 정상 반영)
            frgn_5d = sum(to_signed_int(d.get("frgn_ntby_qty", 0)) for d in items[:5])
            frgn_20d = sum(to_signed_int(d.get("frgn_ntby_qty", 0)) for d in items[:20])
            inst_5d = sum(to_signed_int(d.get("orgn_ntby_qty", 0)) for d in items[:5])
            inst_20d = sum(to_signed_int(d.get("orgn_ntby_qty", 0)) for d in items[:20])

            # 연속 외국인 순매수 일수 (실제 양수인 날만 카운트)
            consec_days = 0
            for d in items:
                val = to_signed_int(d.get("frgn_ntby_qty", 0))
                if val > 0:
                    consec_days += 1
                else:
                    break

            # 최근 5일 외국인 순매수 양수 일수
            frgn_positive_days = sum(
                1 for d in items[:5]
                if to_signed_int(d.get("frgn_ntby_qty", 0)) > 0
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

            def to_signed_int2(v):
                try:
                    return int(str(v).replace(",", ""))
                except Exception:
                    return 0

            return {
                "frgn_today": to_signed_int2(d.get("frgn_ntby_qty", 0)),
                "inst_today": to_signed_int2(d.get("orgn_ntby_qty", 0)),
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


# ── 실시간 지수·업종·ETF 조회 (KIS API, KRX 대체) ─────────────────────────

# 업종코드 매핑
# KIS inquire-index-price: FID_COND_MRKT_DIV_CODE="U", FID_INPUT_ISCD=코드
INDEX_CODES = {
    "kospi":  ("U", "0001"),   # 코스피 종합
    "kosdaq": ("U", "1001"),   # 코스닥 종합
    "kospi200": ("U", "2001"), # 코스피200
}

# 섹터 업종코드 (코스피 업종)
SECTOR_INDEX_CODES = {
    "semiconductor": ("U", "0011"),   # 전기전자
    "defense":       ("U", "0021"),   # 운수장비(방산 포함)
    "healthcare":    ("U", "0027"),   # 의약품
    "finance":       ("U", "0024"),   # 금융업
    "steel":         ("U", "0007"),   # 철강금속
    "battery":       ("U", "0011"),   # 전기전자 (배터리 포함)
    "auto_ev":       ("U", "0021"),   # 운수장비
    "renewable":     ("U", "0014"),   # 비금속광물 → 신재생 근접
    "ai_platform":   ("U", "0011"),   # 전기전자
}


async def fetch_index_price(market_div: str, iscd: str, label: str) -> dict:
    """
    국내업종 현재지수 조회
    TR_ID: FHPUP02100000
    FID_COND_MRKT_DIV_CODE: U (업종)
    FID_INPUT_ISCD: 0001(코스피), 1001(코스닥), 섹터코드 등
    """
    token = await get_token()
    if not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                BASE_URL + "/uapi/domestic-stock/v1/quotations/inquire-index-price",
                headers=_headers(token, "FHPUP02100000"),
                params={
                    "FID_COND_MRKT_DIV_CODE": market_div,
                    "FID_INPUT_ISCD": iscd,
                },
            )
            r.raise_for_status()
            o = r.json().get("output", {})
            if not o:
                return {}

            def tf(v):
                try: return float(str(v).replace(",", ""))
                except: return 0.0

            prpr  = tf(o.get("bstp_nmix_prpr",  0))  # 현재지수
            prdy  = tf(o.get("bstp_nmix_prdy_vrss", 0))  # 전일대비
            rate  = tf(o.get("bstp_nmix_prdy_ctrt", 0))  # 등락률
            vol   = tf(o.get("acml_vol", 0))             # 누적거래량
            name  = o.get("hts_kor_isnm", label)         # 지수명

            return {
                "label":    label,
                "name":     name,
                "close":    prpr,
                "chg":      prdy,
                "chg_pct":  rate,
                "volume":   vol,
                "sign":     o.get("bstp_nmix_prdy_vrss_sign", ""),
            }
    except Exception:
        return {}


async def fetch_all_indices() -> dict:
    """코스피·코스닥·코스피200 동시 조회"""
    tasks = {
        key: fetch_index_price(mc, ic, key)
        for key, (mc, ic) in INDEX_CODES.items()
    }
    results = {}
    fetched = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for key, val in zip(tasks.keys(), fetched):
        if isinstance(val, dict) and val:
            results[key] = val
    return results


async def fetch_sector_indices(sector_keys: list) -> dict:
    """AI가 선정한 섹터의 업종지수 실시간 조회"""
    unique = {}
    for sk in sector_keys:
        if sk in SECTOR_INDEX_CODES:
            mc, ic = SECTOR_INDEX_CODES[sk]
            unique[sk] = (mc, ic)

    if not unique:
        return {}

    results = {}
    for sk, (mc, ic) in unique.items():
        await asyncio.sleep(0.05)
        d = await fetch_index_price(mc, ic, sk)
        if d:
            results[sk] = d
    return results


async def fetch_etf_price(code: str, name: str) -> dict:
    """ETF 현재가 조회 (종목코드 6자리)"""
    token = await get_token()
    if not token:
        return {}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
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
            def tf(v):
                try: return float(str(v).replace(",", ""))
                except: return 0.0
            return {
                "code":    code,
                "name":    o.get("hts_kor_isnm", name),
                "price":   tf(o.get("stck_prpr", 0)),
                "chg_pct": tf(o.get("prdy_ctrt", 0)),
                "volume":  tf(o.get("acml_vol", 0)),
            }
    except Exception:
        return {}


# 섹터별 대표 ETF 코드
SECTOR_ETF_CODES = {
    "semiconductor": ("091160", "KODEX 반도체"),
    "defense":       ("443810", "TIGER 방산"),
    "healthcare":    ("143860", "KODEX 바이오"),
    "battery":       ("305720", "KODEX 2차전지산업"),
    "auto_ev":       ("261060", "KODEX 자동차"),
    "finance":       ("091170", "KODEX 은행"),
    "renewable":     ("278540", "KODEX 글로벌클린에너지"),
    "ai_platform":   ("364980", "TIGER Fn인터넷"),
    "steel":         ("NONE",   ""),
}


async def fetch_sector_etfs(sector_keys: list) -> dict:
    """AI 선정 섹터의 ETF 현재가 실시간 조회"""
    results = {}
    for sk in sector_keys:
        if sk not in SECTOR_ETF_CODES:
            continue
        code, name = SECTOR_ETF_CODES[sk]
        if code == "NONE":
            continue
        await asyncio.sleep(0.05)
        d = await fetch_etf_price(code, name)
        if d:
            results[sk] = d
    return results


# ── 업종별 외국인/기관 순매수 종목 실시간 조회 ─────────────────────────

# 섹터 → KIS 업종코드 매핑
SECTOR_TO_UPJONG = {
    "semiconductor": ["0011"],          # 전기전자
    "defense":       ["0021"],          # 운수장비
    "healthcare":    ["0027"],          # 의약품
    "finance":       ["0024"],          # 금융업
    "battery":       ["0011"],          # 전기전자 (배터리 포함)
    "auto_ev":       ["0021"],          # 운수장비
    "renewable":     ["0007", "0014"],  # 철강금속 + 비금속 (신재생 분산)
    "ai_platform":   ["0011"],          # 전기전자
    "steel":         ["0007"],          # 철강금속
    # 전체 시장 (섹터 미결정 시)
    "all_kospi":     ["0001"],          # 코스피 전체
    "all_kosdaq":    ["1001"],          # 코스닥 전체
}


async def fetch_sector_candidates(
    sector_keys: list,
    top_n: int = 30,
    sort_type: str = "frgn",  # "frgn": 외국인순매수, "inst": 기관순매수
) -> list:
    """
    업종별 외국인/기관 순매수 상위 종목 실시간 조회
    TR_ID: FHPTJ04400000 (국내기관_외국인 매매종목 가집계)
    
    반환: [{"code": "005930", "name": "삼성전자", "frgn_qty": 1234567, ...}, ...]
    """
    token = await get_token()
    if not token:
        return []

    # 섹터 → 업종코드 변환 (중복 제거)
    upjong_codes = set()
    for sk in sector_keys:
        sk_lower = sk.lower().strip()
        codes = SECTOR_TO_UPJONG.get(sk_lower, [])
        upjong_codes.update(codes)
    
    # 섹터 매핑 실패 시 코스피+코스닥 전체 조회
    if not upjong_codes:
        upjong_codes = {"0001", "1001"}

    all_candidates = {}  # code → 데이터 (중복 제거)

    for upjong_code in upjong_codes:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                r = await client.get(
                    BASE_URL + "/uapi/domestic-stock/v1/quotations/foreign-institution-total",
                    headers=_headers(token, "FHPTJ04400000"),
                    params={
                        "FID_COND_MRKT_DIV_CODE": "V",
                        "FID_COND_SCR_DIV_CODE":  "16449",
                        "FID_INPUT_ISCD":          upjong_code,
                        "FID_DIV_CLS_CODE":        "0",   # 수량 정렬
                        "FID_RANK_SORT_CLS_CODE":  "0",   # 순매수 상위
                        "FID_ETC_CLS_CODE":        "0",   # 전체 (외국인+기관)
                    },
                )
                r.raise_for_status()
                items = r.json().get("output", [])

                def to_int(v):
                    try:
                        return int(str(v).replace(",", ""))
                    except Exception:
                        return 0

                for item in items:
                    code = item.get("mksc_shrn_iscd", "").strip()
                    if not code or len(code) != 6:
                        continue
                    name = item.get("hts_kor_isnm", "")
                    frgn = to_int(item.get("frgn_ntby_qty", 0))
                    inst = to_int(item.get("orgn_ntby_qty", 0))
                    # 순매도 종목 제외 (둘 다 음수면 제외)
                    if frgn <= 0 and inst <= 0:
                        continue
                    if code not in all_candidates:
                        all_candidates[code] = {
                            "code":     code,
                            "name":     name,
                            "frgn_qty": frgn,
                            "inst_qty": inst,
                            "total_net": frgn + inst,
                            "upjong":   upjong_code,
                        }
                    else:
                        # 같은 종목이 여러 업종에 있으면 합산
                        all_candidates[code]["frgn_qty"] += frgn
                        all_candidates[code]["inst_qty"] += inst
                        all_candidates[code]["total_net"] += (frgn + inst)

        except Exception:
            continue
        
        await asyncio.sleep(0.1)  # API 호출 간격

    # 외국인+기관 합산 순매수 상위 top_n개
    sorted_list = sorted(
        all_candidates.values(),
        key=lambda x: x["total_net"],
        reverse=True,
    )
    return sorted_list[:top_n]


async def fetch_all_market_candidates(top_n: int = 40) -> list:
    """
    AI 실패 시: 코스피+코스닥 전체에서 외국인/기관 순매수 상위 종목 조회
    """
    return await fetch_sector_candidates(
        sector_keys=["all_kospi", "all_kosdaq"],
        top_n=top_n,
    )
