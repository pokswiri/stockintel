# -*- coding: utf-8 -*-
"""
sector_tracker.py v1
순환매 섹터 트래킹 + 매집 감지

역할:
  1. 매일 장 마감 후 25개 섹터 성과 기록 → /data/sector_history.json
  2. 각 섹터의 매집 강도 계산 (비주목 섹터 포함)
  3. 누적 데이터 기반 순환매 패턴 분석

저장 구조:
  {
    "records": [
      {
        "date": "2026-05-09",
        "sectors": {
          "semiconductor": {
            "etf_chg": 7.33,       # ETF 등락률
            "avg_chg": 5.1,         # 구성종목 평균 등락률
            "frgn_net": 1500,       # 외국인 순매수(억원)
            "volume_ratio": 1.8,    # ETF 거래량/20일평균
            "accum_score": 12,      # 매집 강도 점수 (0~30)
            "rank": 1,              # 당일 섹터 등락률 순위
            "signals": ["vol_surge","frgn_buy"]
          },
          ...
        },
        "ai_sectors": ["semiconductor"],  # 당일 AI 선정 섹터
        "kospi_chg": 6.45,
        "top3_sectors": ["semiconductor","electric_infra","finance"]
      }
    ],
    "version": 1
  }
"""

import os
import json
import asyncio
from datetime import datetime, timezone, timedelta

HISTORY_FILE = os.environ.get("SECTOR_HISTORY_FILE", "/data/sector_history.json")
BACKUP_FILE  = HISTORY_FILE + ".bak"
CURRENT_VERSION = 1

KST = timezone(timedelta(hours=9))


# ── 파일 I/O ────────────────────────────────────────────────────────

def _load() -> dict:
    for path in [HISTORY_FILE, BACKUP_FILE]:
        try:
            if not os.path.exists(path):
                continue
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "records" in data:
                return data
        except Exception:
            continue
    return {"records": [], "version": CURRENT_VERSION}


def _save(data: dict):
    os.makedirs(os.path.dirname(HISTORY_FILE) if os.path.dirname(HISTORY_FILE) else ".", exist_ok=True)
    try:
        if os.path.exists(HISTORY_FILE):
            import shutil
            shutil.copy2(HISTORY_FILE, BACKUP_FILE)
    except Exception:
        pass
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[SECTOR_TRACKER] 저장 실패: {e}")


# ── 매집 강도 산식 ────────────────────────────────────────────────────

def _calc_accum_score(
    etf_chg: float,
    volume_ratio: float,      # ETF 거래량 / 20일 평균
    frgn_net: float,          # 외국인 순매수 (억원)
    leader_vcp: bool,         # 섹터 내 선도주 VCP 수축 여부
    rsi_rising_low: bool,     # RSI 저점 상승 여부
    prev_vol_ratio: float,    # 전전일까지의 평균 거래량 비율
) -> tuple:
    """
    매집 강도 점수 계산 (0~30점)

    시그널 1: 거래량 수축 중 외국인 지속 순매수 (0~8점)
    시그널 2: 거래량 바닥 반등 (0~6점)
    시그널 3: 섹터 선도주 VCP 수축 (0~8점)
    시그널 4: RSI 저점 상승 (0~5점)
    보너스:   섹터 등락률 음수(비주목)인데 시그널 있음 (+3점)
    """
    score = 0
    signals = []

    # 시그널 1: 거래량 수축 + 외국인 순매수
    if volume_ratio < 0.7 and frgn_net > 0:
        score += 8
        signals.append("vol_squeeze_frgn")
    elif volume_ratio < 0.85 and frgn_net > 50:
        score += 4
        signals.append("low_vol_frgn")

    # 시그널 2: 거래량 바닥 반등
    # 이전에는 낮았다가 최근 반등
    if prev_vol_ratio < 0.5 and volume_ratio >= 0.8:
        score += 6
        signals.append("vol_bottom_reversal")
    elif prev_vol_ratio < 0.7 and volume_ratio >= 1.0:
        score += 3
        signals.append("vol_recovery")

    # 시그널 3: 선도주 VCP 수축
    if leader_vcp:
        score += 8
        signals.append("leader_vcp")

    # 시그널 4: RSI 저점 상승
    if rsi_rising_low:
        score += 5
        signals.append("rsi_rising_low")

    # 보너스: 비주목 섹터인데 시그널 있음 (역발상 포인트)
    if etf_chg < -0.5 and score >= 6:
        score += 3
        signals.append("neglected_accumulation")

    # 외국인 순매수만 있어도 기본 점수
    if frgn_net > 100 and score == 0:
        score += 2
        signals.append("frgn_buy")

    return min(score, 30), signals


# ── 섹터별 ETF/종목 데이터 조회 ─────────────────────────────────────

async def _fetch_sector_data(sector_key: str) -> dict:
    """단일 섹터의 오늘 성과 데이터 조회"""
    from kis_official import (
        SECTOR_ETF_CODES, fetch_etf_price,
        batch_fetch_prices, batch_fetch_investors,
        fetch_daily_chart,
    )
    from sector_stocks import SECTOR_STOCKS
    from technical import calc_vcp_score, calc_rsi

    result = {
        "etf_chg": 0.0,
        "avg_chg": 0.0,
        "frgn_net": 0.0,
        "volume_ratio": 1.0,
        "prev_vol_ratio": 1.0,
        "leader_vcp": False,
        "rsi_rising_low": False,
        "accum_score": 0,
        "signals": [],
        "rank": 0,
    }

    # ETF 데이터
    etf_code, etf_name = SECTOR_ETF_CODES.get(sector_key, ("NONE", ""))
    if etf_code and etf_code != "NONE":
        try:
            etf = await fetch_etf_price(etf_code, etf_name)
            result["etf_chg"] = etf.get("chg_pct", 0.0)
            # ETF 차트로 volume_ratio 계산 (20일 평균 대비 오늘 거래량)
            try:
                etf_chart = await fetch_daily_chart(etf_code)
                etf_bars  = etf_chart.get("bars", [])
                if len(etf_bars) >= 5:
                    vols = [b.get("volume", 0) for b in etf_bars[-21:]]
                    avg20 = sum(vols[:-1]) / len(vols[:-1]) if len(vols) > 1 else 0
                    today_vol = vols[-1]
                    if avg20 > 0:
                        result["volume_ratio"] = round(today_vol / avg20, 2)
            except Exception:
                pass
        except Exception:
            pass

    # 섹터 구성 종목 (상위 5개만)
    stocks = SECTOR_STOCKS.get(sector_key, [])
    if not stocks:
        return result

    large_stocks = [s for s in stocks if s.get("cap") == "large"]
    mid_stocks   = [s for s in stocks if s.get("cap") == "mid"]
    top_codes    = [s["code"] for s in (large_stocks or mid_stocks)[:5]]

    try:
        price_map = await batch_fetch_prices(top_codes)
    except Exception:
        return result

    # 평균 등락률
    chg_list = [v.get("change_rate", 0) for v in price_map.values() if v]
    if chg_list:
        result["avg_chg"] = round(sum(chg_list) / len(chg_list), 2)

    # 선도주 (시총 1위) VCP + RSI 분석
    leader_code = (large_stocks or mid_stocks)[0]["code"] if (large_stocks or mid_stocks) else None
    if leader_code:
        try:
            chart = await fetch_daily_chart(leader_code)
            bars  = chart.get("bars", [])
            if len(bars) >= 20:
                # VCP 수축 감지
                vcp_score, vcp_detail = calc_vcp_score(bars)
                contracting = vcp_detail.get("vcp_contracting") or vcp_detail.get("vcp_partial")
                result["leader_vcp"] = bool(contracting)

                # RSI 저점 상승: 최근 10일 RSI 저점이 이전 10일보다 높은지
                closes = [b["close"] for b in bars]
                if len(closes) >= 30:
                    rsi_recent = calc_rsi(closes[-10:], period=min(9, len(closes[-10:])-1))
                    rsi_prev   = calc_rsi(closes[-20:-10], period=min(9, len(closes[-20:-10])-1))
                    result["rsi_rising_low"] = bool(rsi_recent > rsi_prev and rsi_recent < 60)
        except Exception:
            pass

    # 외국인 순매수 (선도주 기준)
    if leader_code:
        try:
            inv_map = await batch_fetch_investors([leader_code])
            inv = inv_map.get(leader_code, {})
            frgn_5d = inv.get("frgn_5d", 0)
            # 주식 수 → 억원 근사 변환
            leader_price = price_map.get(leader_code, {}).get("price", 0)
            if leader_price > 0 and frgn_5d != 0:
                result["frgn_net"] = round(frgn_5d * leader_price / 1e8, 1)
        except Exception:
            pass

    return result


# ── 하루치 섹터 성과 저장 ────────────────────────────────────────────

async def record_daily_sectors(
    ai_sectors: list,
    kospi_chg: float = 0.0,
    top3_names: list = None,
) -> dict:
    """
    장 마감 후 호출 — 25개 섹터 전체 성과를 기록하고 매집 점수 계산

    Args:
        ai_sectors:  당일 AI가 선정한 섹터 키 목록
        kospi_chg:   당일 KOSPI 등락률
        top3_names:  당일 NEXUS top3 종목명
    Returns:
        저장된 record dict
    """
    from sector_stocks import SECTOR_STOCKS

    today = datetime.now(KST).strftime("%Y-%m-%d")
    data  = _load()

    # 이미 오늘 기록이 있으면 덮어쓰기
    data["records"] = [r for r in data["records"] if r.get("date") != today]

    # 전날 ETF 거래량 비율 조회 (시그널 2용)
    # 간략히 처리: history에서 어제 데이터 참조
    yesterday_record = None
    if data["records"]:
        yesterday_record = data["records"][-1]

    # 25개 섹터 병렬 조회 (과부하 방지 위해 5개씩 배치)
    sector_keys = list(SECTOR_STOCKS.keys())
    sector_results = {}

    print(f"[SECTOR_TRACKER] {today} 섹터 스캔 시작 ({len(sector_keys)}개)")

    batch_size = 5
    for i in range(0, len(sector_keys), batch_size):
        batch = sector_keys[i:i+batch_size]
        tasks = [_fetch_sector_data(sk) for sk in batch]
        try:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sk, res in zip(batch, results):
                if isinstance(res, Exception):
                    print(f"[SECTOR_TRACKER] {sk} 조회 실패: {res}")
                    sector_results[sk] = {}
                else:
                    sector_results[sk] = res
        except Exception as e:
            print(f"[SECTOR_TRACKER] 배치 조회 실패: {e}")
        await asyncio.sleep(0.5)  # API 부하 방지

    # 등락률 기준 순위 계산
    chg_rank = sorted(
        sector_keys,
        key=lambda sk: sector_results.get(sk, {}).get("etf_chg") or
                       sector_results.get(sk, {}).get("avg_chg", 0),
        reverse=True
    )

    # 매집 강도 점수 계산
    sectors_record = {}
    for sk in sector_keys:
        res = sector_results.get(sk, {})

        # 전날 거래량 비율
        prev_vol_ratio = 1.0
        if yesterday_record and sk in yesterday_record.get("sectors", {}):
            prev_vol_ratio = yesterday_record["sectors"][sk].get("volume_ratio", 1.0)

        accum_score, signals = _calc_accum_score(
            etf_chg        = res.get("etf_chg", 0),
            volume_ratio   = res.get("volume_ratio", 1.0),
            frgn_net       = res.get("frgn_net", 0),
            leader_vcp     = res.get("leader_vcp", False),
            rsi_rising_low = res.get("rsi_rising_low", False),
            prev_vol_ratio = prev_vol_ratio,
        )

        sectors_record[sk] = {
            "etf_chg":      round(res.get("etf_chg", 0), 2),
            "avg_chg":      round(res.get("avg_chg", 0), 2),
            "frgn_net":     res.get("frgn_net", 0),
            "volume_ratio": round(res.get("volume_ratio", 1.0), 2),
            "leader_vcp":   res.get("leader_vcp", False),
            "rsi_rising_low": res.get("rsi_rising_low", False),
            "accum_score":  accum_score,
            "signals":      signals,
            "rank":         chg_rank.index(sk) + 1,
            "is_ai_sector": sk in ai_sectors,
        }

    record = {
        "date":         today,
        "sectors":      sectors_record,
        "ai_sectors":   ai_sectors,
        "kospi_chg":    round(kospi_chg, 2),
        "top3_names":   top3_names or [],
        "recorded_at":  datetime.now(KST).isoformat(),
    }

    data["records"].append(record)

    # 최대 90일치만 보관
    data["records"] = data["records"][-90:]
    _save(data)

    # 상위 매집 섹터 로그
    top_accum = sorted(
        [(sk, v["accum_score"], v["signals"]) for sk, v in sectors_record.items()],
        key=lambda x: x[1], reverse=True
    )[:5]
    print(f"[SECTOR_TRACKER] {today} 저장 완료 | 상위 매집: {[(s,a) for s,a,_ in top_accum]}")

    return record


# ── 순환매 분석 ──────────────────────────────────────────────────────

def get_rotation_status(days: int = 10) -> dict:
    """
    최근 N일 섹터 성과 분석

    Returns:
        {
          "today": { 섹터별 오늘 성과 },
          "trend": { 섹터별 최근 N일 트렌드 },
          "accum_alert": [ 매집 감지 섹터 목록 ],
          "predict": [ 내일 주목 예측 섹터 ]
        }
    """
    from sector_stocks import SECTOR_STOCKS

    SECTOR_GROUPS = {
        "semiconductor":       "A", "semiconductor_parts": "A",
        "glass_substrate":     "A", "ai_software":         "A", "it_hardware": "A",
        "defense":             "B", "space":               "B",
        "robot":               "B", "shipbuilding":        "B",
        "battery":             "C", "electric_infra":      "C",
        "nuclear":             "C", "renewable":           "C",
        "auto_ev":             "C", "telecom":             "C",
        "steel":               "D", "chemical":            "D",
        "oil_gas":             "D", "construction":        "D", "logistics": "D",
        "healthcare":          "E", "content":             "E",
        "consumer":            "E", "bank":                "E", "securities": "E",
    }

    data = _load()
    records = data.get("records", [])

    if not records:
        return {
            "available": False,
            "message": "데이터 없음 — 장 마감 후 분석을 실행하면 수집 시작",
            "data_days": 0,
        }

    # 실제 거래일 수 계산 (오늘이 장 마감 후 기록된 날이면 아직 0거래일)
    # records[-1]이 오늘 날짜면 아직 오늘 장이 반영된 것이므로 실거래일 = len - 1
    from datetime import datetime, timezone, timedelta
    KST = timezone(timedelta(hours=9))
    today_str = datetime.now(KST).strftime("%Y-%m-%d")
    last_date = records[-1].get("date", "") if records else ""

    # 실제 유효 거래일 수: 오늘 장 마감 후 기록이면 len(records),
    # 아직 오늘 장이 안 열렸거나 장중이면 len(records) - 1 (어제까지가 마지막)
    # 단, 기록이 오늘 날짜로 되어 있어도 "오늘 장 마감 후" 수집이므로 정상 카운트
    trading_days = len(records)  # 실제로 마감 후 기록된 날 수가 진짜 거래일 수

    recent = records[-days:] if len(records) >= days else records
    today_record = records[-1] if records else {}
    today_sectors = today_record.get("sectors", {})

    # 섹터별 N일 트렌드 계산
    sector_keys = list(SECTOR_STOCKS.keys())
    trend = {}
    for sk in sector_keys:
        chg_list    = [r["sectors"].get(sk, {}).get("etf_chg") or
                       r["sectors"].get(sk, {}).get("avg_chg", 0) for r in recent]
        rank_list   = [r["sectors"].get(sk, {}).get("rank", 13) for r in recent]
        accum_list  = [r["sectors"].get(sk, {}).get("accum_score", 0) for r in recent]
        frgn_list   = [r["sectors"].get(sk, {}).get("frgn_net", 0) for r in recent]

        avg_chg  = sum(chg_list) / len(chg_list) if chg_list else 0
        avg_rank = sum(rank_list) / len(rank_list) if rank_list else 13
        avg_accum = sum(accum_list) / len(accum_list) if accum_list else 0
        frgn_consec = 0
        for f in reversed(frgn_list):
            if f > 0: frgn_consec += 1
            else: break

        # 연속 상위권 일수 (rank <= 5)
        top_consec = 0
        for r in reversed(rank_list):
            if r <= 5: top_consec += 1
            else: break

        # 연속 하위권 일수 (rank >= 20)
        bottom_consec = 0
        for r in reversed(rank_list):
            if r >= 20: bottom_consec += 1
            else: break

        trend[sk] = {
            "avg_chg":       round(avg_chg, 2),
            "avg_rank":      round(avg_rank, 1),
            "avg_accum":     round(avg_accum, 1),
            "frgn_consec":   frgn_consec,
            "top_consec":    top_consec,
            "bottom_consec": bottom_consec,
            "group":         SECTOR_GROUPS.get(sk, "?"),
        }

    # 매집 경보 — 비주목 섹터 중 매집 점수 높은 섹터
    accum_alert = []
    for sk, t in trend.items():
        today_s = today_sectors.get(sk, {})
        accum   = today_s.get("accum_score", 0)
        signals = today_s.get("signals", [])
        is_ai   = today_s.get("is_ai_sector", False)

        # 조건: 매집 점수 8점 이상 + 비주목(하위권) + 외국인 연속 매수
        if accum >= 8 and not is_ai and t["avg_rank"] >= 15:
            accum_alert.append({
                "sector":        sk,
                "group":         t["group"],
                "accum_score":   accum,
                "signals":       signals,
                "avg_rank":      t["avg_rank"],
                "frgn_consec":   t["frgn_consec"],
                "bottom_consec": t["bottom_consec"],
                "reason":        _build_accum_reason(sk, t, today_s),
            })

    accum_alert.sort(key=lambda x: x["accum_score"], reverse=True)

    # 순환매 예측 (데이터가 7일 이상 있을 때)
    predict = []
    if len(records) >= 7:
        predict = _predict_next_sectors(trend, today_sectors, records, SECTOR_GROUPS)

    # 그룹별 오늘 현황
    group_summary = {}
    for group in ["A", "B", "C", "D", "E"]:
        group_sectors = [sk for sk, g in SECTOR_GROUPS.items() if g == group]
        today_chgs = [today_sectors.get(sk, {}).get("etf_chg") or
                      today_sectors.get(sk, {}).get("avg_chg", 0) for sk in group_sectors]
        if today_chgs:
            group_summary[group] = {
                "avg_chg": round(sum(today_chgs) / len(today_chgs), 2),
                "best_sector": max(group_sectors, key=lambda sk:
                    today_sectors.get(sk, {}).get("etf_chg") or
                    today_sectors.get(sk, {}).get("avg_chg", 0)),
            }

    return {
        "available":     True,
        "data_days":     trading_days,
        "date":          today_record.get("date", ""),
        "kospi_chg":     today_record.get("kospi_chg", 0),
        "ai_sectors":    today_record.get("ai_sectors", []),
        "today":         today_sectors,
        "trend":         trend,
        "group_summary": group_summary,
        "accum_alert":   accum_alert,
        "predict":       predict,
        "reliability":   "낮음" if trading_days < 7 else
                         "보통" if trading_days < 20 else "높음",
    }


def _build_accum_reason(sk: str, trend: dict, today_s: dict) -> str:
    """매집 경보 이유 문자열 생성"""
    parts = []
    signals = today_s.get("signals", [])

    if "vol_squeeze_frgn" in signals:
        parts.append("거래량 수축 + 외국인 조용한 매집")
    if "vol_bottom_reversal" in signals:
        parts.append("거래량 바닥 반등 감지")
    if "leader_vcp" in signals:
        parts.append(f"선도주 VCP 수축 중")
    if "rsi_rising_low" in signals:
        parts.append("RSI 저점 상승 (하락 에너지 소진)")
    if "neglected_accumulation" in signals:
        parts.append(f"비주목 섹터 (평균순위 {trend['avg_rank']}위) 역발상 매집")

    frgn_c = trend.get("frgn_consec", 0)
    if frgn_c >= 3:
        parts.append(f"외국인 {frgn_c}일 연속 순매수")

    return " · ".join(parts) if parts else "매집 시그널 감지"


def _predict_next_sectors(
    trend: dict,
    today_sectors: dict,
    records: list,
    sector_groups: dict,
) -> list:
    """
    순환매 예측 로직

    규칙 1: 연속 강세 후 교체
      그룹 A 3일 연속 상위 → 그룹 B 또는 E 주목
    규칙 2: 매집 누적 후 폭발
      accum_score 7일 누적 합산 상위 + 최근 2일 거래량 반등
    규칙 3: 그룹 내 로테이션
      그룹 C에서 battery 강세 → electric_infra 후행
    """
    predictions = []
    sector_keys = list(trend.keys())

    # 규칙 1: 연속 강세 그룹 → 인접 그룹 예측
    ROTATION_MAP = {
        "A": ["B", "C"],   # 반도체 강세 후 → 방산·에너지
        "B": ["C", "A"],   # 방산 강세 후 → 에너지·반도체
        "C": ["D", "B"],   # 에너지 강세 후 → 원자재·방산
        "D": ["E", "C"],   # 원자재 강세 후 → 내수·에너지
        "E": ["A", "D"],   # 내수 강세 후 → 성장·원자재
    }

    # 지난 5일간 지배적 그룹 찾기
    recent_5 = records[-5:]
    group_scores = {"A": 0, "B": 0, "C": 0, "D": 0, "E": 0}
    for r in recent_5:
        for sk, sv in r.get("sectors", {}).items():
            g = sector_groups.get(sk, "?")
            if g in group_scores:
                rank = sv.get("rank", 13)
                group_scores[g] += (26 - rank)  # 1위=25점, 25위=1점

    dominant_group = max(group_scores, key=group_scores.get)
    next_groups = ROTATION_MAP.get(dominant_group, [])

    # 다음 그룹의 가장 매집 점수 높은 섹터
    for ng in next_groups:
        candidates = [(sk, t) for sk, t in trend.items()
                      if sector_groups.get(sk) == ng]
        if not candidates:
            continue
        best = max(candidates, key=lambda x: x[1]["avg_accum"])
        sk, t = best
        today_s = today_sectors.get(sk, {})

        predictions.append({
            "sector":      sk,
            "group":       ng,
            "confidence":  min(95, 40 + t["avg_accum"] * 3 + t["frgn_consec"] * 5),
            "rule":        f"그룹{dominant_group} {len(recent_5)}일 강세 후 그룹{ng} 로테이션",
            "accum_score": today_s.get("accum_score", 0),
            "signals":     today_s.get("signals", []),
        })

    # 규칙 2: 누적 매집 폭발 예측
    for sk in sector_keys:
        recent_accum = [r.get("sectors", {}).get(sk, {}).get("accum_score", 0)
                        for r in records[-7:]]
        accum_sum = sum(recent_accum)

        # 7일 누적 매집 합산 40점 이상 + 오늘 거래량 반등
        vol_ratio_today = today_sectors.get(sk, {}).get("volume_ratio", 1.0)
        prev_avg_vol = sum([r.get("sectors", {}).get(sk, {}).get("volume_ratio", 1.0)
                            for r in records[-5:-2]]) / 3 if len(records) >= 5 else 1.0

        if (accum_sum >= 40
                and vol_ratio_today >= 1.2
                and prev_avg_vol < 0.8
                and not any(p["sector"] == sk for p in predictions)):
            predictions.append({
                "sector":      sk,
                "group":       sector_groups.get(sk, "?"),
                "confidence":  min(90, 50 + accum_sum // 5),
                "rule":        f"7일 누적 매집({accum_sum}점) + 거래량 반등",
                "accum_score": today_sectors.get(sk, {}).get("accum_score", 0),
                "signals":     today_sectors.get(sk, {}).get("signals", []),
            })

    predictions.sort(key=lambda x: x["confidence"], reverse=True)
    return predictions[:5]


# ── 이력 조회 헬퍼 ────────────────────────────────────────────────────

def get_history(days: int = 30) -> list:
    """최근 N일 이력 반환"""
    data = _load()
    return data.get("records", [])[-days:]


def get_sector_trend(sector_key: str, days: int = 14) -> list:
    """특정 섹터의 N일 트렌드"""
    records = get_history(days)
    return [
        {
            "date":        r["date"],
            "etf_chg":     r["sectors"].get(sector_key, {}).get("etf_chg", 0),
            "accum_score": r["sectors"].get(sector_key, {}).get("accum_score", 0),
            "rank":        r["sectors"].get(sector_key, {}).get("rank", 0),
            "signals":     r["sectors"].get(sector_key, {}).get("signals", []),
        }
        for r in records
    ]


# ── 섹터 대장주 선별 ──────────────────────────────────────────────────

def get_sector_leaders(sector_key: str, max_n: int = 4) -> list:
    """
    섹터 대장주 선별 — large 우선, 부족하면 mid로 채움
    반환: [{"code": "010120", "name": "LS일렉트릭", "cap": "large"}, ...]
    """
    from sector_stocks import SECTOR_STOCKS
    stocks = SECTOR_STOCKS.get(sector_key, [])
    # 의도적 중복 종목(defense+space 등) 처리: 이미 중복 없으므로 그대로
    large = [s for s in stocks if s.get("cap") == "large"]
    mid   = [s for s in stocks if s.get("cap") == "mid"]
    return (large + mid)[:max_n]


def get_predict_sectors(days: int = 10) -> dict:
    """
    순환매 예측 + 섹터별 대장주 코드 목록 반환
    rotation_status를 호출하지 않고 내부에서 직접 계산 (순환 import 방지)
    """
    status = get_rotation_status(days)
    result = {
        "available":   status.get("available", False),
        "data_days":   status.get("data_days", 0),
        "reliability": status.get("reliability", "낮음"),
        "predict":     [],
        "accum_alert": [],
    }
    if not status.get("available"):
        return result

    # 예측 섹터 + 대장주
    for p in status.get("predict", []):
        sk = p["sector"]
        leaders = get_sector_leaders(sk, 4)
        result["predict"].append({
            **p,
            "leaders": leaders,
        })

    # 매집 경보 섹터 + 대장주
    for a in status.get("accum_alert", []):
        sk = a["sector"]
        leaders = get_sector_leaders(sk, 4)
        result["accum_alert"].append({
            **a,
            "leaders": leaders,
        })

    return result
