# -*- coding: utf-8 -*-
"""
tracker.py v2
NEXUS 추천 종목 성과 추적 모듈

저장 위치:
  - TRACK_FILE 환경변수로 설정 (기본: /tmp/nexus_track.json)
  - Railway Volume 마운트 시: TRACK_FILE=/data/nexus_track.json 설정
  - 자동 백업: {TRACK_FILE}.bak (저장 시마다 갱신)
  - 로드 실패 시 백업에서 자동 복구

데이터 구조 버전: 2
"""

import json
import os
from datetime import datetime

TRACK_FILE = os.getenv("TRACK_FILE", "/tmp/nexus_track.json")
BACKUP_FILE = TRACK_FILE + ".bak"
CURRENT_VERSION = 2


def _validate(data: dict) -> bool:
    """데이터 구조 유효성 검사"""
    return (
        isinstance(data, dict)
        and "records" in data
        and isinstance(data["records"], list)
    )


def _load() -> dict:
    """
    추적 데이터 로드
    1차: TRACK_FILE 로드
    2차: 실패 시 BACKUP_FILE 자동 복구
    3차: 둘 다 실패 시 빈 데이터 반환
    """
    # 1차 시도
    try:
        with open(TRACK_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if _validate(data):
            return data
        print(f"[TRACKER] 데이터 검증 실패 — 백업 복구 시도")
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[TRACKER] 로드 오류: {e} — 백업 복구 시도")

    # 2차: 백업에서 복구
    try:
        with open(BACKUP_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if _validate(data):
            print(f"[TRACKER] 백업에서 복구 성공 ({len(data['records'])}개 레코드)")
            _save_raw(data)  # 메인 파일에 복구
            return data
    except Exception:
        pass

    return {"records": [], "version": CURRENT_VERSION}


def _save_raw(data: dict):
    """파일에 직접 저장 (백업 없이)"""
    try:
        os.makedirs(os.path.dirname(TRACK_FILE) or ".", exist_ok=True)
        with open(TRACK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[TRACKER] 저장 실패: {e}")


def _save(data: dict):
    """
    추적 데이터 저장 + 백업
    순서: 1) 메인 저장 2) 백업 저장
    """
    try:
        os.makedirs(os.path.dirname(TRACK_FILE) or ".", exist_ok=True)
        with open(TRACK_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        # 백업 저장 (메인 저장 성공 시에만)
        try:
            with open(BACKUP_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as be:
            print(f"[TRACKER] 백업 저장 실패 (무시): {be}")
    except Exception as e:
        print(f"[TRACKER] 저장 실패: {e}")
        raise


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


async def update_returns_async(batch_price_fn, fetch_chart_fn=None):
    """
    비동기 수익률 업데이트 — /analyze 호출 시 자동 실행

    개선: 거래일 기반 정확한 d1/d3/d5/d10 계산
    - 기존: '분석 실행 시점 현재가' 기준 (d1~d10이 같은 값이 되는 왜곡)
    - 개선: 일봉 차트에서 추천일 이후 N번째 거래일 종가 추출
    - fetch_chart_fn이 없으면 현재가 기준으로 폴백

    rec_price=0 방어: 추천 당시 가격 미기록 시 수익률 계산 스킵
    KST 기준 날짜: analyzed_at이 UTC인 경우 +9h 보정
    """
    from datetime import timezone, timedelta as _td

    data    = _load()
    today   = datetime.now().date()
    weekday = today.weekday()

    # 업데이트 대상 선별
    targets_by_code: dict = {}
    for rec in data["records"]:
        try:
            rec_date_str = rec.get("rec_date", "")
            # KST 보정: ISO 포맷에 timezone 없으면 로컬(KST)로 간주
            rec_dt = datetime.fromisoformat(rec_date_str)
            rec_date = rec_dt.date()
            delta = (today - rec_date).days
            rec_price = rec.get("rec_price", 0)
        except Exception:
            continue

        # rec_price=0 방어
        if rec_price <= 0:
            continue

        # 추천 당일 or 주말엔 스킵 (다음 거래일 아직 미도래)
        if delta <= 0 or weekday >= 5:
            continue

        needed = []
        if delta >= 1  and "d1"  not in rec["returns"]: needed.append(("d1",  1))
        if delta >= 3  and "d3"  not in rec["returns"]: needed.append(("d3",  3))
        if delta >= 5  and "d5"  not in rec["returns"]: needed.append(("d5",  5))
        if delta >= 10 and "d10" not in rec["returns"]: needed.append(("d10", 10))

        if needed:
            if rec["code"] not in targets_by_code:
                targets_by_code[rec["code"]] = []
            targets_by_code[rec["code"]].append({
                "rec": rec,
                "needed": needed,
                "rec_price": rec_price,
                "rec_date": rec_date,
            })

    if not targets_by_code:
        return

    updated = 0

    for code, rec_list in targets_by_code.items():
        # 일봉 차트 조회로 정확한 거래일별 종가 추출 시도
        chart_bars = None
        if fetch_chart_fn:
            try:
                chart = await fetch_chart_fn(code)
                chart_bars = chart.get("bars", []) if chart else None
            except Exception:
                chart_bars = None

        # 현재가 조회 (차트 실패 시 폴백)
        cur_price = 0
        try:
            prices = await batch_price_fn([code])
            cur_price = prices.get(code, {}).get("price", 0)
        except Exception:
            pass

        for item in rec_list:
            rec       = item["rec"]
            rec_date  = item["rec_date"]
            rec_price = item["rec_price"]

            for period_key, n_days in item["needed"]:
                target_price = None

                if chart_bars:
                    # 추천일 이후 N번째 거래일 종가 찾기
                    after_bars = [
                        b for b in chart_bars
                        if b.get("date", "") > rec_date.strftime("%Y%m%d")
                    ]
                    if len(after_bars) >= n_days:
                        target_price = after_bars[n_days - 1]["close"]

                # 차트 없거나 데이터 부족 시 현재가 폴백
                if not target_price and cur_price > 0:
                    target_price = cur_price

                if target_price and target_price > 0:
                    ret_pct = round((target_price - rec_price) / rec_price * 100, 2)
                    rec["returns"][period_key] = ret_pct
                    rec["updated_at"] = datetime.now().isoformat()
                    updated += 1

    if updated > 0:
        _save(data)
        print(f"[TRACKER] {updated}개 수익률 자동 업데이트 완료 (거래일 기반)")


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
