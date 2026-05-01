# -*- coding: utf-8 -*-
"""
tracker.py
NEXUS 추천 종목 성과 추적 모듈

기능:
  - 추천 시점 가격 자동 저장 (JSON 파일)
  - 1일/3일/5일/10일 후 수익률 자동 계산
  - 등급(HIGH/MID/LOW)별 통계
  - /performance 엔드포인트로 프론트에 노출

저장 위치: /tmp/nexus_track.json (Railway ephemeral storage)
영구 보존 필요 시: Railway Volume 마운트 또는 외부 DB 연동 권장
"""

import json
import os
from datetime import datetime, timedelta

TRACK_FILE = os.getenv("TRACK_FILE", "/tmp/nexus_track.json")


def _load() -> dict:
    """추적 데이터 로드"""
    try:
        with open(TRACK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"records": [], "version": 2}


def _save(data: dict):
    """추적 데이터 저장"""
    try:
        with open(TRACK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[TRACKER] 저장 실패: {e}")


def save_recommendations(nexus_top: list, analyzed_at: str = None):
    """
    NEXUS top 추천 종목 저장
    - 이미 오늘 저장된 종목은 중복 저장 안 함
    """
    if not nexus_top:
        return

    data  = _load()
    today = (analyzed_at or datetime.now().isoformat())[:10]  # YYYY-MM-DD

    # 오늘 이미 저장된 코드 목록
    already = {
        r["code"]
        for r in data["records"]
        if r.get("rec_date", "")[:10] == today
    }

    new_count = 0
    for item in nexus_top:
        code = item.get("code", "")
        if not code or code in already:
            continue

        record = {
            "code":       code,
            "name":       item.get("name", ""),
            "rec_date":   analyzed_at or datetime.now().isoformat(),
            "rec_price":  item.get("price", 0),
            "mktcap":     item.get("mktcap", 0),
            "grade":      item.get("nexus", {}).get("grade", ""),
            "score":      item.get("nexus", {}).get("total", 0),
            "sector":     item.get("sector_key", ""),
            "returns":    {},   # 수익률 채워질 공간
            "updated_at": "",
        }
        data["records"].append(record)
        new_count += 1

    if new_count > 0:
        _save(data)
        print(f"[TRACKER] {new_count}개 신규 추천 저장 완료 ({today})")


def update_returns(price_fetcher_fn):
    """
    저장된 추천 종목의 수익률 업데이트
    price_fetcher_fn: code → current_price (동기 함수)

    1일/3일/5일/10일 후 수익률 계산
    """
    data    = _load()
    today   = datetime.now().date()
    updated = 0

    for rec in data["records"]:
        rec_date = datetime.fromisoformat(rec["rec_date"]).date()
        delta    = (today - rec_date).days
        rec_price = rec.get("rec_price", 0)
        if rec_price <= 0:
            continue

        targets = {}
        if delta >= 1  and "d1"  not in rec["returns"]: targets["d1"]  = 1
        if delta >= 3  and "d3"  not in rec["returns"]: targets["d3"]  = 3
        if delta >= 5  and "d5"  not in rec["returns"]: targets["d5"]  = 5
        if delta >= 10 and "d10" not in rec["returns"]: targets["d10"] = 10

        if not targets:
            continue

        cur_price = price_fetcher_fn(rec["code"])
        if not cur_price or cur_price <= 0:
            continue

        ret_pct = round((cur_price - rec_price) / rec_price * 100, 2)
        for key in targets:
            rec["returns"][key] = ret_pct

        rec["updated_at"] = datetime.now().isoformat()
        updated += 1

    if updated > 0:
        _save(data)
        print(f"[TRACKER] {updated}개 수익률 업데이트")


async def update_returns_async(batch_price_fn):
    """
    비동기 수익률 업데이트 — /analyze 호출 시 자동 실행
    batch_price_fn: [codes] → {code: {price: ...}} (KIS batch_fetch_prices)

    주말/공휴일엔 전일 종가가 그대로 유지되므로 거래일 기준 delta 계산
    """
    data    = _load()
    today   = datetime.now().date()
    weekday = today.weekday()

    # 업데이트 대상 선별 (수익률이 아직 채워지지 않은 구간이 있는 것만)
    targets_by_code: dict = {}
    for rec in data["records"]:
        try:
            rec_date  = datetime.fromisoformat(rec["rec_date"]).date()
            delta     = (today - rec_date).days
            rec_price = rec.get("rec_price", 0)
        except Exception:
            continue
        if rec_price <= 0 or delta <= 0:
            continue

        # 주말엔 가격 조회 불가 → 스킵
        if weekday >= 5:
            continue

        needed = []
        if delta >= 1  and "d1"  not in rec["returns"]: needed.append("d1")
        if delta >= 3  and "d3"  not in rec["returns"]: needed.append("d3")
        if delta >= 5  and "d5"  not in rec["returns"]: needed.append("d5")
        if delta >= 10 and "d10" not in rec["returns"]: needed.append("d10")

        if needed:
            targets_by_code[rec["code"]] = {
                "rec": rec,
                "needed": needed,
                "rec_price": rec_price,
            }

    if not targets_by_code:
        return

    # 현재가 일괄 조회
    try:
        prices = await batch_price_fn(list(targets_by_code.keys()))
    except Exception as e:
        print(f"[TRACKER] 가격 조회 실패: {e}")
        return

    updated = 0
    for code, info in targets_by_code.items():
        cur_price = prices.get(code, {}).get("price", 0)
        if not cur_price or cur_price <= 0:
            continue
        ret_pct = round((cur_price - info["rec_price"]) / info["rec_price"] * 100, 2)
        for key in info["needed"]:
            info["rec"]["returns"][key] = ret_pct
        info["rec"]["updated_at"] = datetime.now().isoformat()
        updated += 1

    if updated > 0:
        _save(data)
        print(f"[TRACKER] {updated}개 수익률 자동 업데이트 완료")


def get_performance_stats() -> dict:
    """
    성과 통계 계산 및 반환
    반환값: 등급별/섹터별 평균 수익률 + 최근 추천 목록
    """
    data    = _load()
    records = data.get("records", [])

    if not records:
        return {"total_count": 0, "records": [], "stats": {}}

    # 등급별 수익률 집계
    grade_stats: dict = {}
    sector_stats: dict = {}

    for rec in records:
        grade  = rec.get("grade", "UNKNOWN")
        sector = rec.get("sector", "unknown")
        rets   = rec.get("returns", {})

        for period in ["d1", "d3", "d5", "d10"]:
            if period not in rets:
                continue
            ret = rets[period]

            # 등급별
            if grade not in grade_stats:
                grade_stats[grade] = {}
            if period not in grade_stats[grade]:
                grade_stats[grade][period] = []
            grade_stats[grade][period].append(ret)

            # 섹터별
            if sector not in sector_stats:
                sector_stats[sector] = {}
            if period not in sector_stats[sector]:
                sector_stats[sector][period] = []
            sector_stats[sector][period].append(ret)

    def avg(lst): return round(sum(lst) / len(lst), 2) if lst else None
    def win(lst): return round(sum(1 for x in lst if x > 0) / len(lst) * 100, 1) if lst else None

    # 평균 및 승률 계산
    grade_summary  = {}
    for g, periods in grade_stats.items():
        grade_summary[g] = {
            p: {"avg": avg(v), "win_rate": win(v), "count": len(v)}
            for p, v in periods.items()
        }

    sector_summary = {}
    for s, periods in sector_stats.items():
        sector_summary[s] = {
            p: {"avg": avg(v), "win_rate": win(v), "count": len(v)}
            for p, v in periods.items()
        }

    # 최근 30개 추천만 반환 (프론트 표시용)
    recent = sorted(records, key=lambda x: x.get("rec_date", ""), reverse=True)[:30]

    return {
        "total_count":    len(records),
        "grade_stats":    grade_summary,
        "sector_stats":   sector_summary,
        "records":        recent,
        "last_updated":   datetime.now().isoformat(),
    }
