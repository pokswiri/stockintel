# -*- coding: utf-8 -*-
"""
nexus.py v4
NEXUS Score 파이프라인

핵심 변경사항:
1. AI 독립 구조 — AI 분석 실패해도 전체 섹터 스캔 실행
2. 시총 필터 — KIS API 응답의 mktcap 기반 소형주 제외
   코스피: 1000억↑ / 코스닥: 500억↑ (구분 불가 시 500억↑)
3. 외국인 조회 전체 확대 — top10 → 전체 valid_codes
4. 섹터 선정 전략:
   - AI 성공 시: AI 주목 섹터(전량) + ANCHOR 섹터(보완)
   - AI 실패 시: 전체 9개 섹터 스캔
5. HIGH 우선, MID 보충으로 최대 3개
"""

import asyncio
from datetime import datetime
from kis_official import (
    batch_fetch_charts, batch_fetch_prices,
    batch_fetch_investors, is_kis_available
)
from technical import calc_nexus_score
from sector_stocks import (
    get_sector_stocks, get_all_sector_keys,
    SECTOR_STOCKS, SECTOR_MAP
)

# 뉴스 무관하게 항상 포함할 보완 섹터
ANCHOR_SECTORS = ["semiconductor", "finance"]

# 시총 필터 기준 (단위: 억원)
MKTCAP_MIN = 500  # 500억 미만 제외


def _is_market_open() -> bool:
    t = datetime.now().hour * 60 + datetime.now().minute
    wd = datetime.now().weekday()
    if wd >= 5:
        return False
    return (9*60 <= t <= 15*60+30) or (16*60 <= t <= 20*60)


def _build_scan_list(ai_sector_names: list, ai_failed: bool = False) -> list:
    """
    스캔 대상 종목 목록 구성
    - ai_failed=True: 전체 9개 섹터 스캔
    - ai_failed=False: AI 주목 섹터 + ANCHOR 섹터
    """
    seen_codes = set()
    result = []

    if ai_failed or not ai_sector_names:
        # AI 실패 시 전체 섹터 스캔
        for sk, stocks in SECTOR_STOCKS.items():
            for stock in stocks:
                if stock["code"] not in seen_codes:
                    seen_codes.add(stock["code"])
                    result.append({**stock, "sector_key": sk, "source": "full_scan"})
        return result

    # AI 주목 섹터 먼저 (전량)
    ai_stocks = get_sector_stocks(ai_sector_names, max_per_sector=8)
    for s in ai_stocks:
        if s["code"] not in seen_codes:
            seen_codes.add(s["code"])
            result.append({**s, "source": "ai"})

    # AI가 이미 선택한 섹터 키 목록
    ai_keys = set()
    for name in ai_sector_names:
        n = name.lower().strip()
        if n in SECTOR_MAP:
            ai_keys.add(SECTOR_MAP[n])
        elif n in SECTOR_STOCKS:
            ai_keys.add(n)

    # ANCHOR 섹터 보완 (AI 섹터에 없는 것만, 상위 6개)
    for sk in ANCHOR_SECTORS:
        if sk in ai_keys:
            continue
        for stock in SECTOR_STOCKS.get(sk, [])[:6]:
            if stock["code"] not in seen_codes:
                seen_codes.add(stock["code"])
                result.append({**stock, "sector_key": sk, "source": "anchor"})

    return result


def _filter_by_mktcap(scored: list, price_data: dict) -> list:
    """시총 필터: MKTCAP_MIN 억원 미만 제외"""
    filtered = []
    removed = []
    for s in scored:
        code = s["code"]
        pd = price_data.get(code, {})
        # mktcap은 억원 단위 (KIS hts_avls 필드: 억원)
        mktcap = pd.get("mktcap", 0)
        if mktcap > 0 and mktcap < MKTCAP_MIN:
            removed.append(f"{s['name']}({code}): {mktcap}억")
            continue
        filtered.append(s)
    if removed:
        print(f"[NEXUS] 시총 필터 제외: {removed}")
    return filtered


async def run_nexus(
    sector_names: list,
    top_n: int = 3,
    ai_failed: bool = False,
) -> dict:
    """
    NEXUS Score 파이프라인
    sector_names: AI 선정 섹터 (빈 리스트 가능)
    ai_failed: True면 전체 섹터 스캔
    """
    if not is_kis_available():
        return {
            "available": False,
            "message": "KIS API 키가 설정되지 않았습니다",
            "top": [],
        }

    # ── 1. 스캔 대상 구성 ─────────────────────────────────
    candidates = _build_scan_list(sector_names, ai_failed)
    if not candidates:
        return {"available": True, "message": "후보 종목 없음", "top": []}

    codes = [c["code"] for c in candidates]
    code_to_meta = {c["code"]: c for c in candidates}
    scan_mode = "전체" if ai_failed else "AI+보완"

    # ── 2. 일봉 차트 병렬 조회 ────────────────────────────
    charts = await batch_fetch_charts(codes)
    valid_codes = [
        c for c in codes
        if c in charts
        and "bars" in charts[c]
        and len(charts[c]["bars"]) >= 20  # 최소 20일 (VCP 계산 기준)
    ]

    if not valid_codes:
        return {
            "available": True,
            "message": "차트 조회 실패",
            "top": [],
        }

    # ── 3. 현재가 + 시총 병렬 조회 ───────────────────────
    price_data = await batch_fetch_prices(valid_codes)

    # ── 4. 1차 점수 계산 (외국인 없이) ───────────────────
    market_open = _is_market_open()
    prelim = []
    for code in valid_codes:
        bars = charts[code]["bars"]
        pd = price_data.get(code, {})
        s = calc_nexus_score(bars, charts[code], {}, pd, market_open)
        prelim.append((code, s["total"]))

    prelim.sort(key=lambda x: x[1], reverse=True)

    # ── 5. 외국인 순매수 전체 조회 ───────────────────────
    # 전체 valid_codes 조회 (순차, 0.12초 딜레이)
    investor_data = await batch_fetch_investors(valid_codes)

    # ── 6. 최종 NEXUS Score 계산 ──────────────────────────
    scored_raw = []
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

            scored_raw.append({
                "code":         code,
                "name":         chart_meta.get("name") or meta.get("name", ""),
                "sector_key":   meta.get("sector_key", ""),
                "cap":          meta.get("cap", ""),
                "source":       meta.get("source", "ai"),
                "price":        round(current_price),
                "change_rate":  round(change_rate, 2),
                "mktcap":       pd.get("mktcap", 0),
                "nexus":        nexus,
                "has_investor": bool(inv),
            })
        except Exception as e:
            errors.append({"code": code, "error": str(e)})

    # ── 7. 시총 필터 ──────────────────────────────────────
    scored = _filter_by_mktcap(scored_raw, price_data)
    scored.sort(key=lambda x: x["nexus"]["total"], reverse=True)

    # ── 8. HIGH 우선 + MID 보충으로 최대 top_n개 ─────────
    high_list = [s for s in scored if s["nexus"]["grade"] == "HIGH"]
    mid_list  = [s for s in scored if s["nexus"]["grade"] == "MID"]
    low_list  = [s for s in scored if s["nexus"]["grade"] == "LOW"]

    final_top = list(high_list[:top_n])
    if len(final_top) < top_n:
        top_codes  = {s["code"] for s in final_top}
        supplement = [s for s in mid_list if s["code"] not in top_codes]
        final_top += supplement[:(top_n - len(final_top))]

    for s in final_top:
        s["display_grade"] = s["nexus"]["grade"]

    return {
        "available":        True,
        "scan_mode":        scan_mode,
        "candidates_count": len(valid_codes),
        "filtered_count":   len(scored),
        "scored_count":     len(scored),
        "sectors_searched": sector_names if not ai_failed else list(SECTOR_STOCKS.keys()),
        "market_open":      market_open,
        "grade_counts":     {
            "HIGH": len(high_list),
            "MID":  len(mid_list),
            "LOW":  len(low_list),
        },
        "top":   final_top,
        "all":   scored,
        "errors": errors,
    }
