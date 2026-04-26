# -*- coding: utf-8 -*-
"""
nexus.py v3
NEXUS Score 파이프라인 — HIGH 등급 우선 추출

핵심 설계 원칙:
1. "주목 섹터" (AI 선정) + "보완 섹터" (항상 강세인 반도체·금융) 함께 스캔
2. 외국인 순매수는 1차 점수 상위 10개에만 조회 (정확도 vs 속도 균형)
3. HIGH 등급만 추출 → 부족 시 MID로 채움 → 절대로 LOW 표시 안 함
4. 섹터 중복 허용 (같은 섹터에 HIGH가 몰려있으면 그냥 보여줌)
5. 최종 결과: HIGH 위주 0~3개 (기준 미달 시 0개도 가능)
"""

import asyncio
from datetime import datetime
from kis_official import (
    batch_fetch_charts, batch_fetch_prices,
    batch_fetch_investors, is_kis_available
)
from technical import calc_nexus_score
from sector_stocks import get_sector_stocks, SECTOR_STOCKS

# 항상 포함할 보완 섹터 (뉴스와 무관하게 강세 가능성 높은 섹터)
ANCHOR_SECTORS = ["semiconductor", "finance"]


def _is_market_open() -> bool:
    """정규장 또는 야간장 거래 시간 판단"""
    t = datetime.now().hour * 60 + datetime.now().minute
    return (9*60 <= t <= 15*60+30) or (16*60 <= t <= 20*60)


def _build_scan_list(ai_sector_names: list) -> list:
    """
    스캔 대상 종목 목록 구성
    
    AI 주목 섹터 + ANCHOR 섹터 합집합으로 후보 구성
    - AI 주목 섹터: 뉴스 관련성 높음 → 섹터당 8개 전부
    - ANCHOR 섹터: 기본 포함 → 섹터당 6개 (상위 시총 우선)
    - 중복 종목 제거
    """
    from sector_stocks import get_sector_stocks, SECTOR_STOCKS, SECTOR_MAP

    seen_codes = set()
    result = []

    # AI 주목 섹터 먼저 (뉴스 관련성 높음, 전량)
    ai_stocks = get_sector_stocks(ai_sector_names, max_per_sector=8)
    for s in ai_stocks:
        if s["code"] not in seen_codes:
            seen_codes.add(s["code"])
            result.append({**s, "source": "ai"})

    # ANCHOR 섹터 추가 (AI 섹터에 없는 것만, 상위 6개)
    for sk in ANCHOR_SECTORS:
        # AI가 이미 선택한 섹터면 스킵 (이미 전량 포함됨)
        ai_keys = set()
        for name in ai_sector_names:
            n = name.lower().strip()
            if n in SECTOR_MAP:
                ai_keys.add(SECTOR_MAP[n])
        if sk in ai_keys:
            continue
        for stock in SECTOR_STOCKS.get(sk, [])[:6]:
            if stock["code"] not in seen_codes:
                seen_codes.add(stock["code"])
                result.append({**stock, "sector_key": sk, "source": "anchor"})

    return result


async def run_nexus(sector_names: list, top_n: int = 3) -> dict:
    """
    NEXUS Score 파이프라인 — HIGH 우선 추출

    sector_names: AI가 선정한 주목 섹터명 리스트
    top_n: 최대 추천 종목 수 (기본 3)
    """
    if not is_kis_available():
        return {
            "available": False,
            "message": "KIS API 키가 설정되지 않았습니다",
            "top": [],
        }

    # ── 1. 스캔 대상 종목 구성 ─────────────────────────────
    candidates = _build_scan_list(sector_names)
    if not candidates:
        return {"available": True, "message": "후보 종목 없음", "top": []}

    codes = [c["code"] for c in candidates]
    code_to_meta = {c["code"]: c for c in candidates}

    # ── 2. 일봉 차트 병렬 조회 ────────────────────────────
    charts = await batch_fetch_charts(codes)
    valid_codes = [
        c for c in codes
        if c in charts
        and "bars" in charts[c]
        and len(charts[c]["bars"]) >= 15
    ]

    if not valid_codes:
        return {
            "available": True,
            "message": "차트 조회 실패 — KIS 토큰 또는 API 오류",
            "candidates_tried": len(codes),
            "top": [],
        }

    # ── 3. 현재가 병렬 조회 (prdy_vrss_vol_rate 포함) ────
    price_data = await batch_fetch_prices(valid_codes)

    # ── 4. 1차 점수 계산 (외국인 없이) ───────────────────
    market_open = _is_market_open()
    prelim = []
    for code in valid_codes:
        bars = charts[code]["bars"]
        pd   = price_data.get(code, {})
        s    = calc_nexus_score(bars, charts[code], {}, pd, market_open)
        prelim.append((code, s["total"]))

    prelim.sort(key=lambda x: x[1], reverse=True)

    # ── 5. 외국인 순매수 조회 (1차 상위 10개) ────────────
    # 상위 10개로 넓혀서 외국인 점수 반영 정확도 향상
    top10_codes = [c for c, _ in prelim[:10]]
    investor_data = {}
    if top10_codes:
        investor_data = await batch_fetch_investors(top10_codes)

    # ── 6. 최종 NEXUS Score 계산 ──────────────────────────
    scored = []
    errors = []
    for code in valid_codes:
        meta       = code_to_meta.get(code, {})
        bars       = charts[code]["bars"]
        pd         = price_data.get(code, {})
        inv        = investor_data.get(code, {})
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
                "code":         code,
                "name":         chart_meta.get("name") or meta.get("name", ""),
                "sector":       meta.get("name", ""),
                "sector_key":   meta.get("sector_key", ""),
                "cap":          meta.get("cap", ""),
                "source":       meta.get("source", "ai"),   # ai | anchor
                "price":        round(current_price),
                "change_rate":  round(change_rate, 2),
                "nexus":        nexus,
                "has_investor": bool(inv),
            })
        except Exception as e:
            errors.append({"code": code, "error": str(e)})

    # ── 7. HIGH 우선, 없으면 MID 관심 종목으로 별도 반환 ──
    scored.sort(key=lambda x: x["nexus"]["total"], reverse=True)

    high_list = [s for s in scored if s["nexus"]["grade"] == "HIGH"]
    mid_list  = [s for s in scored if s["nexus"]["grade"] == "MID"]
    low_list  = [s for s in scored if s["nexus"]["grade"] == "LOW"]

    # HIGH만 최대 top_n개
    final_top = high_list[:top_n]

    # MID 관심 종목: HIGH가 top_n 미만일 때만, 최대 3개
    # 프론트에서 HIGH와 구분해서 "관심 종목" 섹션으로 표시
    watch_list = mid_list[:3] if len(high_list) < top_n else []

    # 통계 정보
    grade_counts = {
        "HIGH": len(high_list),
        "MID":  len(mid_list),
        "LOW":  len(low_list),
    }

    return {
        "available":        True,
        "candidates_count": len(valid_codes),
        "scored_count":     len(scored),
        "sectors_searched": sector_names,
        "anchor_sectors":   ANCHOR_SECTORS,
        "market_open":      market_open,
        "grade_counts":     grade_counts,
        "top":              final_top,   # HIGH 등급만
        "watch":            watch_list,  # MID 관심 종목 (HIGH 없을 때)
        "all":              scored,
        "errors":           errors,
    }
