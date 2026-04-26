# -*- coding: utf-8 -*-
"""
nexus.py v5
NEXUS Score 파이프라인 — 실시간 수급 기반 후보 선정

흐름:
  뉴스 → AI 섹터 결정
    ↓
  KIS foreign_institution_total
  → 해당 업종 외국인+기관 순매수 상위 30개 실시간 수신
    ↓
  30개 → 일봉 차트 조회 → NEXUS Score 계산
  (VCP 수축 + Stage2 정배열 + RSI + 52주 위치)
    ↓
  수급도 들어오고 기술적으로도 준비된 종목 → HIGH 등급
    ↓
  HIGH 우선 3개 추천 (부족 시 MID 보충)

폴백:
  API 실패 / 후보 없음 → sector_stocks.py 하드코딩 목록으로 대체
  AI 실패 → 전체 시장(코스피+코스닥) 외국인/기관 순매수 상위 조회
"""

import asyncio
from datetime import datetime
from kis_official import (
    fetch_sector_candidates, fetch_all_market_candidates,
    batch_fetch_charts, batch_fetch_prices,
    batch_fetch_investors, is_kis_available,
)
from technical import calc_nexus_score
from sector_stocks import get_sector_stocks, SECTOR_STOCKS, SECTOR_MAP

ANCHOR_SECTORS = ["semiconductor", "finance"]
MKTCAP_MIN = 500  # 억원, 시총 필터


def _is_market_open() -> bool:
    t  = datetime.now().hour * 60 + datetime.now().minute
    wd = datetime.now().weekday()
    if wd >= 5:
        return False
    return (9*60 <= t <= 15*60+30) or (16*60 <= t <= 20*60)


def _sector_names_to_keys(sector_names: list) -> list:
    """AI 섹터명 → 내부 키 변환"""
    keys = []
    for name in sector_names:
        n = name.lower().strip()
        if n in SECTOR_MAP:
            keys.append(SECTOR_MAP[n])
        elif n in SECTOR_STOCKS:
            keys.append(n)
        else:
            for kw, key in SECTOR_MAP.items():
                if kw in n or n in kw:
                    keys.append(key)
                    break
    # 중복 제거 + ANCHOR 항상 포함
    result = list(dict.fromkeys(keys))  # 순서 유지 중복 제거
    for a in ANCHOR_SECTORS:
        if a not in result:
            result.append(a)
    return result


def _fallback_candidates(sector_keys: list, ai_failed: bool) -> list:
    """
    KIS API 실패 시 sector_stocks.py 하드코딩 목록으로 폴백
    """
    seen = set()
    result = []
    if ai_failed:
        # AI 실패: 전체 섹터 상위 5개씩
        for sk, stocks in SECTOR_STOCKS.items():
            for s in stocks[:5]:
                if s["code"] not in seen:
                    seen.add(s["code"])
                    result.append({**s, "sector_key": sk,
                                   "source": "fallback_full"})
    else:
        for sk in sector_keys:
            for s in SECTOR_STOCKS.get(sk, []):
                if s["code"] not in seen:
                    seen.add(s["code"])
                    result.append({**s, "sector_key": sk,
                                   "source": "fallback_sector"})
    return result


async def run_nexus(
    sector_names: list,
    top_n: int = 3,
    ai_failed: bool = False,
) -> dict:
    """
    NEXUS Score 파이프라인
    sector_names : AI 선정 섹터명 리스트
    ai_failed    : True → 전체 시장 스캔
    """
    if not is_kis_available():
        return {"available": False,
                "message": "KIS API 키가 설정되지 않았습니다", "top": []}

    market_open  = _is_market_open()
    sector_keys  = _sector_names_to_keys(sector_names)

    # ── 1. 후보 종목 실시간 수신 (KIS foreign_institution_total) ──────
    api_candidates = []
    try:
        if ai_failed or not sector_names:
            # AI 실패: 전체 시장 외국인+기관 순매수 상위
            raw = await fetch_all_market_candidates(top_n=40)
        else:
            # AI 성공: 해당 업종 외국인+기관 순매수 상위
            raw = await fetch_sector_candidates(
                sector_keys=sector_keys, top_n=30)

        # 가집계 데이터: 장외(주말 포함)에는 전일 데이터 반환
        api_candidates = [
            {
                "code":       c["code"],
                "name":       c["name"],
                "sector_key": _guess_sector(c["code"]),
                "cap":        "unknown",
                "source":     "realtime_frgn",
                "frgn_qty":   c.get("frgn_qty", 0),
                "inst_qty":   c.get("inst_qty", 0),
            }
            for c in raw
            if c.get("code")
        ]
    except Exception as _api_err:
        api_candidates = []
        print(f"[NEXUS] fetch_sector_candidates 오류: {_api_err}")

    # API 후보 없으면 하드코딩 폴백
    if not api_candidates:
        api_candidates = _fallback_candidates(sector_keys, ai_failed)
        scan_source = "fallback"
    else:
        scan_source = "realtime"

    if not api_candidates:
        return {"available": True, "message": "후보 종목 없음", "top": []}

    codes = list(dict.fromkeys(c["code"] for c in api_candidates))
    code_to_meta = {c["code"]: c for c in api_candidates}

    # ── 2. 일봉 차트 병렬 조회 ────────────────────────────────────────
    charts = await batch_fetch_charts(codes)
    valid_codes = [
        c for c in codes
        if c in charts
        and "bars" in charts[c]
        and len(charts[c]["bars"]) >= 20
    ]

    if not valid_codes:
        # 디버그: 어떤 코드들이 실패했는지 확인
        chart_errors = {
            code: charts.get(code, {}).get("error", "응답없음")
            for code in codes[:5]  # 처음 5개만
        }
        return {
            "available": True,
            "message": "차트 조회 실패",
            "debug_codes": codes[:10],
            "debug_charts_sample": chart_errors,
            "scan_source": scan_source,
            "top": [],
        }

    # ── 3. 현재가 + 시총 조회 ────────────────────────────────────────
    price_data = await batch_fetch_prices(valid_codes)

    # ── 4. 1차 점수 (외국인 없이) → 상위 15개만 외국인 상세 조회 ────
    prelim = []
    for code in valid_codes:
        bars = charts[code]["bars"]
        pd   = price_data.get(code, {})
        s    = calc_nexus_score(bars, charts[code], {}, pd, market_open)
        prelim.append((code, s["total"]))
    prelim.sort(key=lambda x: x[1], reverse=True)
    top15 = [c for c, _ in prelim[:15]]

    investor_data = await batch_fetch_investors(top15)

    # ── 5. 최종 NEXUS Score ──────────────────────────────────────────
    scored = []
    errors = []
    for code in valid_codes:
        meta       = code_to_meta.get(code, {})
        bars       = charts[code]["bars"]
        pd_        = price_data.get(code, {})
        inv        = investor_data.get(code, {})

        # 가집계에서 받은 수급 정보를 investor_data에 보완
        if not inv and meta.get("frgn_qty", 0) > 0:
            inv = {
                "frgn_5d":             meta["frgn_qty"],
                "frgn_20d":            meta["frgn_qty"],
                "inst_5d":             meta.get("inst_qty", 0),
                "inst_20d":            meta.get("inst_qty", 0),
                "frgn_consec_days":    1,
                "frgn_positive_days_5": 1,
                "latest_date":         "",
            }

        # ── 시총 필터 ──────────────────────────────────────
        mktcap = pd_.get("mktcap", 0)
        price_now = pd_.get("price", 0) or (bars[-1]["close"] if bars else 0)

        # 시총이 확인된 경우: MKTCAP_MIN(500억) 미만 제외
        if mktcap > 0 and mktcap < MKTCAP_MIN:
            continue

        # 시총 미수신(0)인 경우: 주가 500원 미만 초저가 종목 제외
        # (저가주는 외국인 가집계 노이즈 많음)
        if mktcap == 0 and price_now < 500:
            continue

        # ── 당일 급등/급락 종목 제외 ────────────────────────
        # 이미 터진 종목은 "시세 분출 전"이 아님
        # ±10% 이상 당일 변동 종목 제외 (장 마감 기준)
        # 단, 장외(주말) 에는 전일 종가 기준이므로 완화
        chg_now = abs(pd_.get("change_rate", 0))
        chg_threshold = 15.0 if not market_open else 10.0
        if chg_now >= chg_threshold:
            continue  # 이미 급등/급락 → 진입 타이밍 아님

        try:
            nexus = calc_nexus_score(
                bars, charts[code], inv, pd_, market_open)

            price = pd_.get("price") or (bars[-1]["close"] if bars else 0)
            chg   = (pd_.get("change_rate")
                     or ((bars[-1]["close"] - bars[-2]["close"])
                         / bars[-2]["close"] * 100
                         if len(bars) >= 2 else 0))

            # sector_key: 하드코딩 목록에 없으면 현재가 업종명으로 매핑
            sector_key = meta.get("sector_key", "")
            if not sector_key or sector_key == "unknown":
                sector_key = _guess_sector_from_price(code, pd_)

            scored.append({
                "code":         code,
                "name":         charts[code].get("name") or meta.get("name",""),
                "sector_key":   sector_key,
                "cap":          meta.get("cap", ""),
                "source":       meta.get("source", ""),
                "price":        round(price),
                "change_rate":  round(chg, 2),
                "mktcap":       mktcap,
                "frgn_today":   meta.get("frgn_qty", 0),
                "inst_today":   meta.get("inst_qty", 0),
                "nexus":        nexus,
                "has_investor": bool(inv),
            })
        except Exception as e:
            errors.append({"code": code, "error": str(e)})

    scored.sort(key=lambda x: x["nexus"]["total"], reverse=True)

    # ── 6. HIGH 우선 + MID 보충 ──────────────────────────────────────
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

    wd = datetime.now().weekday()
    scan_mode = ("전체시장·전일기준" if (wd >= 5 and ai_failed)
                 else "전체시장" if ai_failed
                 else f"AI섹터({','.join(sector_keys[:3])})")

    return {
        "available":        True,
        "scan_source":      scan_source,   # "realtime" or "fallback"
        "scan_mode":        scan_mode,
        "candidates_count": len(valid_codes),
        "scored_count":     len(scored),
        "sectors_searched": sector_keys,
        "market_open":      market_open,
        "grade_counts":     {
            "HIGH": len(high_list),
            "MID":  len(mid_list),
            "LOW":  len(low_list),
        },
        "top":    final_top,
        "all":    scored,
        "errors": errors,
    }


# KIS 업종 코드 → 내부 섹터 키 매핑
UPJONG_TO_SECTOR = {
    "0011": "semiconductor",  # 전기전자
    "0021": "auto_ev",        # 운수장비
    "0027": "healthcare",     # 의약품
    "0024": "finance",        # 금융업
    "0007": "steel",          # 철강금속
    "0014": "renewable",      # 비금속광물
    "0017": "defense",        # 기계 (방산 포함)
    "0023": "finance",        # 증권
    "0026": "finance",        # 보험
    "0028": "healthcare",     # 의료정밀
    "0010": "steel",          # 화학
    "0005": "battery",        # 음식료 (제외 후 battery 기본)
}

# KIS hts_kor_isnm 업종명 키워드 → 섹터 매핑
NAME_TO_SECTOR = {
    "반도체": "semiconductor", "전자": "semiconductor",
    "방산": "defense",  "항공": "defense", "조선": "defense",
    "바이오": "healthcare", "제약": "healthcare", "의료": "healthcare",
    "금융": "finance", "은행": "finance", "보험": "finance", "증권": "finance",
    "배터리": "battery", "이차전지": "battery",
    "자동차": "auto_ev", "부품": "auto_ev",
    "태양광": "renewable", "풍력": "renewable", "에너지": "renewable",
    "철강": "steel", "소재": "steel",
    "플랫폼": "ai_platform", "인터넷": "ai_platform", "소프트웨어": "ai_platform",
    "해운": "auto_ev",  # 해운/물류
    "전선": "renewable",  # 전력인프라
    "엔지니어링": "auto_ev",
}


def _guess_sector(code: str) -> str:
    """종목코드 → 섹터 추정 (sector_stocks.py 기반)"""
    for sk, stocks in SECTOR_STOCKS.items():
        for s in stocks:
            if s["code"] == code:
                return sk
    return "unknown"


def _guess_sector_from_price(code: str, price_data: dict) -> str:
    """KIS 현재가 응답의 업종 정보로 섹터 추정"""
    # 1. sector_stocks.py 직접 확인
    result = _guess_sector(code)
    if result != "unknown":
        return result

    # 2. KIS 업종명(hts_kor_isnm) 키워드 매칭
    name = price_data.get("name", "")
    for kw, sk in NAME_TO_SECTOR.items():
        if kw in name:
            return sk

    # 3. 종목명으로도 추정 시도
    return "기타"
