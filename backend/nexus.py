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
    batch_fetch_charts, batch_fetch_prices,
    batch_fetch_investors, is_kis_available,
)
from technical import calc_nexus_score
from sector_stocks import get_sector_stocks, SECTOR_STOCKS, SECTOR_MAP

# fetch_sector_candidates는 최신 kis_official에만 있음 — 안전하게 임포트
try:
    from kis_official import fetch_sector_candidates, fetch_all_market_candidates
    _HAS_REALTIME_SCAN = True
except ImportError:
    _HAS_REALTIME_SCAN = False
    async def fetch_sector_candidates(sector_keys, top_n=30): return []
    async def fetch_all_market_candidates(top_n=40): return []

ANCHOR_SECTORS = ["semiconductor"]  # finance 제거 — 뉴스 기반 섹터로 충분

# ── 잡주 필터 기준 ──────────────────────────────────────────────
MKTCAP_MIN       = 2000   # 억원: 500→2000 (문배철강급 잡주 제거)
MKTCAP_MID_WARN  = 5000   # 억원: 2000~5000은 허용하되 점수 페널티(-5점)
PRICE_MIN        = 2000   # 원: 1000→2000 (동전주 추가 제거)
AVG_VOL_MIN      = 50000  # 주: 20일 평균거래량 5만주 미만 → 유동성 부족 제거


def _is_market_open() -> bool:
    t  = datetime.now().hour * 60 + datetime.now().minute
    wd = datetime.now().weekday()
    if wd >= 5:
        return False
    return (9*60 <= t <= 15*60+30) or (16*60 <= t <= 20*60)


def _sector_names_to_keys(sector_names: list, max_sectors: int = 3) -> list:
    """AI 섹터명 → 내부 키 변환 (최대 max_sectors개)"""
    if not sector_names:
        return list(ANCHOR_SECTORS)
    keys = []
    for name in (sector_names or []):
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
    # 중복 제거
    result = list(dict.fromkeys(keys))
    # ANCHOR 포함 (이미 있으면 추가 안 함)
    for a in ANCHOR_SECTORS:
        if a not in result:
            result.append(a)
    # 최대 3개로 제한 (과도한 스캔 방지)
    return result[:max_sectors]


def _fallback_candidates(sector_keys: list, ai_failed: bool,
                         max_per_sector: int = 15) -> list:
    """
    sector_stocks.py 기반 후보 목록
    - KIS API 실패 시 폴백 (주 역할)
    - AI 성공 시 API 결과 보완 (보조 역할)
    섹터당 최대 max_per_sector개 (기본값 30→15로 수정: 실제 호출 시 15 사용하므로 일치)
    """
    seen = set()
    result = []
    if ai_failed:
        # AI 실패: 전체 섹터 상위 5개씩 (속도 균형)
        for sk, stocks in SECTOR_STOCKS.items():
            for s in stocks[:5]:
                if s["code"] not in seen:
                    seen.add(s["code"])
                    result.append({**s, "sector_key": sk,
                                   "source": "fallback_full"})
    else:
        # AI 성공: 해당 섹터 전체 30개
        for sk in sector_keys:
            for s in SECTOR_STOCKS.get(sk, [])[:max_per_sector]:
                if s["code"] not in seen:
                    seen.add(s["code"])
                    result.append({**s, "sector_key": sk,
                                   "source": "fallback_sector"})
    return result


async def run_nexus(
    sector_names: list,
    top_n: int = 3,
    ai_failed: bool = False,
    sector_strength: dict = None,   # {"semiconductor": 5, "defense": 3} 형태
) -> dict:
    """
    NEXUS Score 파이프라인
    sector_names    : AI 선정 섹터명 리스트
    ai_failed       : True → 전체 시장 스캔
    sector_strength : AI 섹터별 강도(1~5) → 해당 섹터 종목 점수 가산
    """
    if not is_kis_available():
        print("[NEXUS] KIS API 키 미설정 — 종료")
        return {"available": False,
                "message": "KIS API 키가 설정되지 않았습니다", "top": []}

    market_open     = _is_market_open()
    sector_keys     = _sector_names_to_keys(sector_names)
    sector_strength = sector_strength or {}
    print(f"[NEXUS] 시작 | sector_keys={sector_keys} | strength={sector_strength} | market_open={market_open}")

    # ── 1. 후보 종목 실시간 수신 (KIS foreign_institution_total) ──────
    api_candidates = []
    try:
        if ai_failed or not sector_names:
            # AI 실패: 전체 시장 외국인+기관 순매수 상위
            raw = await fetch_all_market_candidates(top_n=50)
        else:
            # AI 성공: 해당 업종 외국인+기관 순매수 상위
            raw = await fetch_sector_candidates(
                sector_keys=sector_keys, top_n=40)

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

    # API 결과 + sector_stocks 핵심 종목 병합 (최대 60개로 제한)
    if not api_candidates:
        api_candidates = _fallback_candidates(sector_keys, ai_failed)
        scan_source = "fallback"
    else:
        scan_source = "realtime"
        # sector_stocks 30개를 API 결과에 보완 (최대 90개 제한)
        # → API: 실시간 수급 종목 / sector_stocks: 섹터 대표 종목
        fallback = _fallback_candidates(sector_keys, ai_failed, max_per_sector=15)
        existing_codes = {c["code"] for c in api_candidates}
        for s in fallback:
            if len(api_candidates) >= 50:  # 최대 50개 (속도 보장)
                break
            if s["code"] not in existing_codes:
                api_candidates.append(s)
                existing_codes.add(s["code"])

    if not api_candidates:
        print("[NEXUS] 후보 종목 없음 — 종료")
        return {"available": True, "message": "후보 종목 없음", "top": []}

    codes = list(dict.fromkeys(c["code"] for c in api_candidates))
    code_to_meta = {c["code"]: c for c in api_candidates}
    print(f"[NEXUS] 후보 {len(codes)}개 확보 (source={scan_source})")

    # ── 2. 일봉 차트 병렬 조회 ────────────────────────────────────────
    charts = await batch_fetch_charts(codes)
    valid_codes = [
        c for c in codes
        if c in charts
        and "bars" in charts[c]
        and len(charts[c]["bars"]) >= 20
    ]
    print(f"[NEXUS] 차트 조회 완료 | 유효={len(valid_codes)}/{len(codes)}개")

    if not valid_codes:
        chart_errors = {
            code: charts.get(code, {}).get("error", "응답없음")
            for code in codes[:5]
        }
        print(f"[NEXUS] 차트 조회 전체 실패 | 샘플={chart_errors}")
        return {
            "available": False,
            "message": f"차트 조회 실패 ({len(codes)}개 시도)",
            "debug_codes": codes[:10],
            "debug_charts_sample": chart_errors,
            "scan_source": scan_source,
            "top": [],
        }

    # ── 3. 현재가 + 시총 조회 ────────────────────────────────────────
    price_data = await batch_fetch_prices(valid_codes)

    # ── 4. 1차 점수 (외국인 없이) → 상위 15개만 외국인 상세 조회 ────
    prelim = []
    prelim_errors = []
    for code in valid_codes:
        bars = charts[code]["bars"]
        pd   = price_data.get(code, {})
        try:
            s = calc_nexus_score(bars, charts[code], {}, pd, market_open)
            prelim.append((code, s["total"]))
        except Exception as e:
            import traceback as _tb
            prelim_errors.append(code)
            if len(prelim_errors) <= 3:
                print(f"[NEXUS] 1차 점수 오류 ({code}): {e}\n{_tb.format_exc()[:400]}")
    if prelim_errors:
        print(f"[NEXUS] 1차 점수 오류 총 {len(prelim_errors)}개: {prelim_errors[:5]}")
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
        # is_estimated=True: 당일 1회 가집계 수치로 5일 데이터를 추정한 것임을 표시
        if not inv and meta.get("frgn_qty", 0) > 0:
            inv = {
                "frgn_5d":              meta["frgn_qty"],
                "frgn_20d":             meta["frgn_qty"],
                "inst_5d":              meta.get("inst_qty", 0),
                "inst_20d":             meta.get("inst_qty", 0),
                "frgn_consec_days":     1,
                "frgn_positive_days_5": 1,
                "latest_date":          "",
                "is_estimated":         True,   # 가집계 추정치 플래그
            }

        # ── 잡주 필터 ────────────────────────────────────────────
        mktcap    = pd_.get("mktcap", 0)
        price_now = pd_.get("price", 0) or (bars[-1]["close"] if bars else 0)

        # 1) 시총 2000억 미만 제거 (확인된 경우만)
        if mktcap > 0 and mktcap < MKTCAP_MIN:
            continue

        # 2) 주가 2000원 미만 동전주 제거
        if price_now > 0 and price_now < PRICE_MIN:
            continue

        # 3) 20일 평균거래량 5만주 미만 → 유동성 부족 제거
        if len(bars) >= 20:
            avg_vol_20 = sum(b["volume"] for b in bars[-20:]) / 20
            if avg_vol_20 < AVG_VOL_MIN:
                continue
        elif bars:
            avg_vol_20 = sum(b["volume"] for b in bars) / len(bars)
            if avg_vol_20 < AVG_VOL_MIN:
                continue
        else:
            avg_vol_20 = 0

        # 시총 2000~5000억 구간: 통과하되 페널티 플래그 세팅
        is_small_cap = (0 < mktcap < MKTCAP_MID_WARN)

        # ── 급등/급락 필터 (RSI + 등락률 조합으로 개선) ─────────────
        chg_bars = 0.0
        if len(bars) >= 2 and bars[-2]["close"] > 0:
            chg_bars = (bars[-1]["close"] - bars[-2]["close"]) / bars[-2]["close"] * 100
        chg_api = pd_.get("change_rate", 0) or 0
        chg_now = max(abs(chg_bars), abs(chg_api))

        # 과열 판단: 단순 등락률이 아닌 RSI + 등락률 조합
        # - RSI 80 이상 + 등락률 8% 이상 → 과열 (양방향)
        # - 등락률 20% 이상 → 무조건 제외 (상한가/하한가 근접)
        # - 등락률 15% 이상 + RSI 75 이상 → 과열 제외
        # - 등락률 15% 이내 + RSI 75 미만 → 돌파 진입 허용
        closes_list = [b["close"] for b in bars]
        rsi_now = 50.0
        try:
            from technical import calc_rsi
            rsi_now = calc_rsi(closes_list)
        except Exception:
            pass

        if chg_now >= 20.0:
            continue  # 상한가/하한가 근접 → 무조건 제외
        if chg_now >= 15.0 and rsi_now >= 75.0:
            continue  # 급등 + 과열 RSI → 제외
        if chg_now >= 8.0 and rsi_now >= 80.0:
            continue  # 중간 급등 + 극과열 → 제외

        try:
            # sector_key를 먼저 정의 (이후 모멘텀 가중치 및 scored.append에서 사용)
            sector_key = meta.get("sector_key", "")
            if not sector_key or sector_key == "unknown":
                sector_key = _guess_sector_from_price(code, pd_)

            nexus = calc_nexus_score(
                bars, charts[code], inv, pd_, market_open)

            # 시총 2000~5000억 소형주 페널티 -5점
            if is_small_cap:
                nexus["total"] = max(0, nexus["total"] - 5)
                nexus["small_cap_penalty"] = True
                if nexus["total"] >= 65:
                    nexus["grade"] = "HIGH"
                elif nexus["total"] >= 50:
                    nexus["grade"] = "MID"
                else:
                    nexus["grade"] = "LOW"

            # ── 섹터 모멘텀 가중치 ──────────────────────────────────
            sk = sector_key or meta.get("sector_key", "")
            if sk and sector_strength:
                st = sector_strength.get(sk, 0)
                if st >= 5:
                    momentum_bonus = 5
                elif st == 4:
                    momentum_bonus = 3
                elif st == 3:
                    momentum_bonus = 1
                else:
                    momentum_bonus = 0
                if momentum_bonus > 0:
                    nexus["total"] = nexus["total"] + momentum_bonus
                    nexus["sector_momentum_bonus"] = momentum_bonus
                    nexus["sector_strength"] = st
                    if nexus["total"] >= 65:
                        nexus["grade"] = "HIGH"
                    elif nexus["total"] >= 50:
                        nexus["grade"] = "MID"

            price = pd_.get("price") or (bars[-1]["close"] if bars else 0)
            chg   = (pd_.get("change_rate")
                     or ((bars[-1]["close"] - bars[-2]["close"])
                         / bars[-2]["close"] * 100
                         if len(bars) >= 2 else 0))

            scored.append({
                "code":         code,
                "name":         charts[code].get("name") or meta.get("name",""),
                "sector_key":   sector_key,
                "cap":          meta.get("cap", ""),
                "source":       meta.get("source", ""),
                "price":        round(price),
                "change_rate":  round(chg, 2),
                "mktcap":       mktcap,
                "avg_vol_20":   round(avg_vol_20),
                "is_small_cap": is_small_cap,
                "frgn_today":   meta.get("frgn_qty", 0),
                "inst_today":   meta.get("inst_qty", 0),
                "nexus":        nexus,
                "has_investor": bool(inv),
            })
        except Exception as e:
            import traceback
            err_detail = traceback.format_exc()
            errors.append({"code": code, "error": str(e)})
            # 첫 번째 에러만 상세 출력 (반복 방지)
            if len(errors) == 1:
                print(f"[NEXUS] 스코어링 오류 샘플 ({code}): {e}\n{err_detail[:500]}")

    scored.sort(key=lambda x: x["nexus"]["total"], reverse=True)
    print(f"[NEXUS] 스코어링 완료 | scored={len(scored)} | HIGH={len([s for s in scored if s['nexus']['grade']=='HIGH'])} MID={len([s for s in scored if s['nexus']['grade']=='MID'])} errors={len(errors)}")

    # ── 6. 섹터 다양성 보장 + 점수순 top_n개 ────────────────────────
    # 원칙: 같은 섹터에서 1개만 선택 (동일 섹터 독점 방지)
    # 순서: 점수 높은 것부터, 해당 섹터 첫 번째만 선택
    # 보완: top_n 미달 시 이미 선택한 섹터에서 추가로 채움
    high_list = [s for s in scored if s["nexus"]["grade"] == "HIGH"]
    mid_list  = [s for s in scored if s["nexus"]["grade"] == "MID"]
    low_list  = [s for s in scored if s["nexus"]["grade"] == "LOW"]

    # 1단계: 섹터별 1개씩 (점수순)
    seen_sectors = set()
    diverse_top  = []
    for s in scored:
        sk = s.get("sector_key", "") or "기타"
        if sk not in seen_sectors:
            seen_sectors.add(sk)
            diverse_top.append(s)
        if len(diverse_top) >= top_n:
            break

    # 2단계: top_n 미달이면 이미 선택된 섹터에서 점수순으로 보완
    if len(diverse_top) < top_n:
        selected_codes = {s["code"] for s in diverse_top}
        for s in scored:
            if s["code"] not in selected_codes:
                diverse_top.append(s)
                selected_codes.add(s["code"])
            if len(diverse_top) >= top_n:
                break

    final_top = diverse_top[:top_n]

    for s in final_top:
        s["display_grade"] = s["nexus"]["grade"]  # HIGH/MID/LOW 뱃지

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
    "방산": "defense", "항공": "defense", "엔진": "defense",
    "조선": "shipbuilding", "해양": "shipbuilding", "중공업": "shipbuilding",  # shipbuilding으로 수정
    "해운": "shipbuilding",   # 해운도 shipbuilding으로 통합
    "바이오": "healthcare", "제약": "healthcare", "의료": "healthcare",
    "금융": "finance", "은행": "finance", "보험": "finance", "증권": "finance",
    "배터리": "battery", "이차전지": "battery",
    "자동차": "auto_ev", "부품": "auto_ev",
    "태양광": "renewable", "풍력": "renewable", "에너지": "renewable",
    "전력": "renewable", "전선": "renewable",
    "철강": "steel", "소재": "steel",
    "플랫폼": "ai_platform", "인터넷": "ai_platform", "소프트웨어": "ai_platform",
    "신탁": "finance", "투자": "finance",
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
