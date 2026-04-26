# -*- coding: utf-8 -*-
"""
nexus.py
NEXUS Score 파이프라인
섹터 후보 종목 → 차트 조회 → 기술적 지표 → 외국인수급 → 종합 점수 → 상위 3개
"""

import asyncio
from kis_client import fetch_charts_parallel, is_pykis_available
from kis_official import batch_fetch_prices, batch_fetch_investors, is_kis_available
from technical import calc_nexus_score
from sector_stocks import get_sector_stocks


async def run_nexus(sector_names: list, top_n: int = 3) -> dict:
    """
    NEXUS Score 전체 파이프라인 실행
    sector_names: AI가 결정한 섹터 리스트
    반환: {candidates, top, errors}
    """
    if not is_pykis_available():
        return {
            "available": False,
            "message": "KIS API 키가 설정되지 않았습니다",
            "candidates": [],
            "top": [],
        }

    # 1. 섹터별 후보 종목
    candidates = get_sector_stocks(sector_names, max_per_sector=8)
    if not candidates:
        return {
            "available": True,
            "message": "후보 종목 없음",
            "candidates": [],
            "top": [],
        }

    codes = [c["code"] for c in candidates]
    code_to_meta = {c["code"]: c for c in candidates}

    # 2. 일봉 차트 병렬 조회 (pykis)
    charts = await fetch_charts_parallel(codes)

    # 차트 조회 성공한 코드만 필터
    valid_codes = [code for code in codes if code in charts and "bars" in charts[code]]

    if not valid_codes:
        return {
            "available": True,
            "message": "차트 조회 실패",
            "candidates": [],
            "top": [],
        }

    # 3. 현재가 + 거래량비율 병렬 조회 (공식 KIS)
    price_data = {}
    if is_kis_available():
        price_data = await batch_fetch_prices(valid_codes)

    # 4. 외국인 순매수는 상위 후보만 (API 호출 최소화)
    # 우선 차트 기반 점수로 1차 필터링 → 상위 6개만 외국인 조회
    prelim_scores = []
    for code in valid_codes:
        chart = charts[code]
        bars = chart.get("bars", [])
        if len(bars) < 15:
            continue
        pd = price_data.get(code, {})
        # 외국인 데이터 없이 1차 점수 계산
        score = calc_nexus_score(bars, chart, {}, pd)
        prelim_scores.append((code, score["total"]))

    prelim_scores.sort(key=lambda x: x[1], reverse=True)
    top6_codes = [c for c, _ in prelim_scores[:6]]

    # 5. 외국인 순매수 조회 (상위 6개만)
    investor_data = {}
    if is_kis_available() and top6_codes:
        investor_data = await batch_fetch_investors(top6_codes)

    # 6. 최종 NEXUS Score 계산 (외국인 반영)
    scored = []
    errors = []
    for code in valid_codes:
        chart = charts[code]
        bars = chart.get("bars", [])
        if len(bars) < 15:
            continue

        meta = code_to_meta.get(code, {})
        pd = price_data.get(code, {})
        inv = investor_data.get(code, {})

        try:
            nexus = calc_nexus_score(bars, chart, inv, pd)

            # 현재가 결정 (KIS 현재가 우선, 없으면 차트 마지막 종가)
            current_price = (
                pd.get("price")
                or (bars[-1]["close"] if bars else 0)
            )
            change_rate = (
                pd.get("change_rate")
                or (
                    (bars[-1]["close"] - bars[-2]["close"]) / bars[-2]["close"] * 100
                    if len(bars) >= 2 else 0
                )
            )

            scored.append({
                "code": code,
                "name": chart.get("name") or meta.get("name", ""),
                "sector": meta.get("name", ""),
                "sector_key": meta.get("sector_key", ""),
                "cap": meta.get("cap", ""),
                "price": round(current_price),
                "change_rate": round(change_rate, 2),
                "market_cap": chart.get("market_cap", 0),
                "nexus": nexus,
                "has_investor": bool(inv),
            })
        except Exception as e:
            errors.append({"code": code, "error": str(e)})

    # 7. NEXUS Score 내림차순 정렬
    scored.sort(key=lambda x: x["nexus"]["total"], reverse=True)

    return {
        "available": True,
        "candidates_count": len(valid_codes),
        "scored_count": len(scored),
        "sectors_searched": sector_names,
        "top": scored[:top_n],
        "all": scored,
        "errors": errors,
    }
