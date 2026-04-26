# -*- coding: utf-8 -*-
"""
nexus.py v2
NEXUS Score 파이프라인
- 섹터별 최소 1개 보장 (다양성)
- 52주 고저가 KIS API 값 정상 전달
- 장중 여부 판단 후 vol_rate 조건 처리
"""

import asyncio
from datetime import datetime
from kis_official import (
    batch_fetch_charts, batch_fetch_prices,
    batch_fetch_investors, is_kis_available
)
from technical import calc_nexus_score
from sector_stocks import get_sector_stocks


def _is_market_open() -> bool:
    """현재 정규장 또는 야간장 거래 시간인지 판단"""
    now = datetime.now()
    t = now.hour * 60 + now.minute
    regular = 9 * 60 <= t <= 15 * 60 + 30
    night   = 16 * 60 <= t <= 20 * 60
    return regular or night


async def run_nexus(sector_names: list, top_n: int = 3) -> dict:
    """NEXUS Score 전체 파이프라인"""
    if not is_kis_available():
        return {
            "available": False,
            "message": "KIS API 키가 설정되지 않았습니다",
            "top": [],
        }

    # 1. 섹터별 후보 종목
    candidates = get_sector_stocks(sector_names, max_per_sector=8)
    if not candidates:
        return {
            "available": True,
            "message": "후보 종목 없음",
            "top": [],
        }

    codes = [c["code"] for c in candidates]
    code_to_meta = {c["code"]: c for c in candidates}

    # 2. 일봉 차트 병렬 조회 (KIS REST API)
    charts = await batch_fetch_charts(codes)
    valid_codes = [
        code for code in codes
        if code in charts and "bars" in charts[code] and len(charts[code]["bars"]) >= 15
    ]

    if not valid_codes:
        return {
            "available": True,
            "message": "차트 조회 실패 - KIS 토큰 또는 API 오류",
            "candidates_tried": len(codes),
            "top": [],
        }

    # 3. 현재가 + 거래량비율 병렬 조회
    price_data = await batch_fetch_prices(valid_codes)

    # 4. 1차 점수로 상위 6개 추려서 외국인 순매수 조회
    market_open = _is_market_open()
    prelim = []
    for code in valid_codes:
        bars = charts[code]["bars"]
        pd   = price_data.get(code, {})
        s    = calc_nexus_score(bars, charts[code], {}, pd, market_open)
        prelim.append((code, s["total"]))

    prelim.sort(key=lambda x: x[1], reverse=True)
    top6_codes = [c for c, _ in prelim[:6]]

    # 5. 외국인 순매수 조회 (상위 6개)
    investor_data = {}
    if top6_codes:
        investor_data = await batch_fetch_investors(top6_codes)

    # 6. 최종 NEXUS Score 계산
    scored = []
    errors = []
    for code in valid_codes:
        meta = code_to_meta.get(code, {})
        bars = charts[code]["bars"]
        pd   = price_data.get(code, {})
        inv  = investor_data.get(code, {})

        # 52주 고저가: KIS fetch_daily_chart output1 값 우선
        chart_meta = charts[code]

        try:
            nexus = calc_nexus_score(bars, chart_meta, inv, pd, market_open)

            current_price = pd.get("price") or (bars[-1]["close"] if bars else 0)
            change_rate = (
                pd.get("change_rate")
                or ((bars[-1]["close"] - bars[-2]["close"]) / bars[-2]["close"] * 100
                    if len(bars) >= 2 else 0)
            )

            scored.append({
                "code":        code,
                "name":        chart_meta.get("name") or meta.get("name", ""),
                "sector":      meta.get("name", ""),
                "sector_key":  meta.get("sector_key", ""),
                "cap":         meta.get("cap", ""),
                "price":       round(current_price),
                "change_rate": round(change_rate, 2),
                "nexus":       nexus,
                "has_investor":bool(inv),
            })
        except Exception as e:
            errors.append({"code": code, "error": str(e)})

    scored.sort(key=lambda x: x["nexus"]["total"], reverse=True)

    # 7. 섹터별 1개 보장 (다양성)
    seen_sectors = set()
    diverse_top  = []
    remainder    = []

    for s in scored:
        sk = s["sector_key"]
        if sk not in seen_sectors:
            seen_sectors.add(sk)
            diverse_top.append(s)
        else:
            remainder.append(s)

    # 섹터별 1개씩 확보 후 남은 슬롯은 점수 상위로 채움
    final_top = diverse_top[:top_n]
    if len(final_top) < top_n:
        for s in remainder:
            if len(final_top) >= top_n:
                break
            if s not in final_top:
                final_top.append(s)

    # 최종 정렬 (점수순)
    final_top.sort(key=lambda x: x["nexus"]["total"], reverse=True)

    return {
        "available":        True,
        "candidates_count": len(valid_codes),
        "scored_count":     len(scored),
        "sectors_searched": sector_names,
        "market_open":      market_open,
        "top":              final_top,
        "all":              scored,
        "errors":           errors,
    }
