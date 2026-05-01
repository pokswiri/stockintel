# -*- coding: utf-8 -*-
"""
technical.py v2
기술적 지표 계산 - 외부 라이브러리 없이 순수 Python 산술
버그 수정:
  - VCP 고점/저점 시간 순서 매칭 재설계
  - 등급 기준 현실화 (HIGH>=65, MID>=50)
  - 거래량 이중 계산 정리
"""


def _sma(values: list, n: int) -> float:
    if len(values) < n:
        return sum(values) / len(values) if values else 0.0
    return sum(values[-n:]) / n


def calc_rsi(closes: list, period: int = 14) -> float:
    """RSI 계산 (Wilder 방식)"""
    if len(closes) < period + 1:
        return 50.0
    changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains  = [max(c, 0.0) for c in changes]
    losses = [abs(min(c, 0.0)) for c in changes]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(changes)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    return round(100.0 - (100.0 / (1.0 + avg_gain / avg_loss)), 2)


def _find_swings(closes: list, window: int = 5):
    """
    시간 순서 보장 스윙 고점/저점 탐지
    반환: [(idx, price, type)] type='peak'|'trough' 시간순
    window=5: ±5일 기준으로 단기 노이즈 스윙 필터링 (기존 3→5)
    """
    swings = []
    n = len(closes)
    for i in range(window, n - window):
        is_peak   = all(closes[i] >= closes[i-j] and closes[i] >= closes[i+j] for j in range(1, window+1))
        is_trough = all(closes[i] <= closes[i-j] and closes[i] <= closes[i+j] for j in range(1, window+1))
        if is_peak:
            swings.append((i, closes[i], "peak"))
        elif is_trough:
            swings.append((i, closes[i], "trough"))
    return swings


def calc_vcp_score(bars: list) -> tuple:
    """
    VCP (Volatility Contraction Pattern) 점수 (0~30)
    핵심: 시간 순서대로 고점→저점 구간 조정폭이 점점 줄어드는지
    + 돌파 캔들 거래량 폭증 감지 (수축 종료 후 첫 강한 양봉)
    최대 점수 25→30으로 상향 (돌파 거래량 보너스 +5)
    """
    if len(bars) < 25:
        return 0, {}

    closes  = [b["close"]  for b in bars]
    volumes = [b["volume"] for b in bars]
    score = 0
    detail = {}

    # 스윙 포인트 시간 순으로 추출
    swings = _find_swings(closes, window=5)

    # 연속 고점→저점 구간(조정 구간)을 시간순으로 추출
    corrections = []
    i = 0
    while i < len(swings) - 1:
        if swings[i][2] == "peak":
            # 다음 trough 찾기
            for j in range(i+1, len(swings)):
                if swings[j][2] == "trough":
                    peak_price   = swings[i][1]
                    trough_price = swings[j][1]
                    if peak_price > 0:
                        corr = (peak_price - trough_price) / peak_price * 100
                        if corr > 0:  # 음수 조정폭 제외 (실제 하락만)
                            corrections.append(corr)
                    i = j
                    break
            else:
                i += 1
        else:
            i += 1

    # 최근 3개 조정 구간 추출 후 2% 미만 노이즈 제거
    recent_raw = corrections[-3:] if corrections else []
    recent = [c for c in recent_raw if c >= 2.0]

    if len(recent) >= 2:
        fully_contracting = all(recent[k] > recent[k+1] for k in range(len(recent)-1))
        if fully_contracting and recent[-1] < recent[0] * 0.8:
            score += 15
            detail["vcp_contracting"] = [round(c, 1) for c in recent]
        elif recent[-1] < recent[0]:
            score += 8
            detail["vcp_partial"] = True
            detail["corrections"] = [round(c, 1) for c in recent]

    # 거래량 수축 (VCP 핵심 요소)
    if len(volumes) >= 20:
        vol_20avg = _sma(volumes, 20)
        vol_5avg  = _sma(volumes, 5)
        if vol_20avg > 0:
            vol_ratio = vol_5avg / vol_20avg
            detail["vol_ratio"] = round(vol_ratio, 2)
            if vol_ratio < 0.65:
                score += 5
                detail["vol_squeeze_vcp"] = True

    # 현재가 > 20일선 (기본 필터)
    if len(closes) >= 20:
        ma20 = _sma(closes, 20)
        if closes[-1] > ma20:
            score += 5
            detail["above_ma20"] = True

    # ── 돌파 캔들 거래량 폭증 감지 (+5보너스) ──────────────────────
    # 수축 구간 종료 후 최근 3일 내 강한 양봉 + 거래량 폭증 = 진짜 돌파 시그널
    # 조건: 최근 3일 중 하루라도 종가>시가(양봉) AND 해당일 거래량 > 20일평균 * 2.0
    if len(bars) >= 20 and score >= 5:  # above_ma20 이상이면 체크
        vol_20avg_b = _sma(volumes, 20)
        breakout_found = False
        for i in range(-3, 0):  # 최근 3봉 체크
            if abs(i) > len(bars):
                continue
            b = bars[i]
            is_bullish  = b["close"] > b["open"]                        # 양봉
            vol_surge   = b["volume"] > vol_20avg_b * 2.0              # 거래량 2배
            price_surge = (b["close"] - b["open"]) / b["open"] * 100 > 1.5  # 봉 크기 1.5% 이상
            if is_bullish and vol_surge and price_surge:
                breakout_found = True
                detail["breakout_candle"] = {
                    "idx": i,
                    "vol_ratio": round(b["volume"] / vol_20avg_b, 1) if vol_20avg_b else 0,
                    "body_pct":  round((b["close"] - b["open"]) / b["open"] * 100, 1),
                }
                break
        if breakout_found:
            score += 5
            detail["breakout_vol"] = True

    return min(score, 30), detail


def calc_stage2_score(bars: list) -> tuple:
    """Stage 2 정배열 점수 (0~20)"""
    if len(bars) < 20:
        return 0, {}

    closes = [b["close"] for b in bars]
    score = 0
    detail = {}

    ma5  = _sma(closes, 5)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, min(60, len(closes)))
    current = closes[-1]

    if current > ma5 > ma20 > ma60 and ma60 > 0:
        score += 15          # 완전 정배열 (12→15)
        detail["perfect_alignment"] = True
    elif current > ma20 > ma60 and ma60 > 0:
        score += 10          # 부분 정배열 (7→10)
        detail["partial_alignment"] = True
    elif current > ma20:
        score += 5           # 최소 요건 (3→5)

    detail["ma5"]  = round(ma5, 0)
    detail["ma20"] = round(ma20, 0)
    detail["ma60"] = round(ma60, 0)

    # 60일선 우상향
    if len(closes) >= 65:
        ma60_old = _sma(closes[:-5], min(60, len(closes) - 5))
        if ma60 > ma60_old:
            score += 5
            detail["ma60_rising"] = True

    # 52주 위치 보너스 제거 — position_score(0~10점)에서 이미 반영하므로 이중 계산 방지

    return min(score, 20), detail


def calc_rsi_score(bars: list) -> tuple:
    """RSI 점수 (0~15)"""
    if len(bars) < 15:
        return 0, {}

    closes = [b["close"] for b in bars]
    rsi = calc_rsi(closes)
    detail = {"rsi": rsi}

    if 50 <= rsi <= 70:
        score = 15
    elif 45 <= rsi < 50:
        score = 10
    elif 70 < rsi <= 78:
        score = 7
    elif 40 <= rsi < 45:
        score = 4
    else:
        score = 0

    if len(closes) >= 18:
        rsi_prev = calc_rsi(closes[:-3])
        if rsi > rsi_prev and 40 <= rsi <= 75:
            score = min(score + 2, 15)
            detail["rsi_rising"] = True

    return score, detail


def calc_volume_score(bars: list, is_market_open: bool = True) -> tuple:
    """
    거래량 수축·회복 패턴 점수 (0~15)
    VCP와 중복 피해 수축 후 회복(돌파 시작)에 집중
    is_market_open: 장중이면 당일봉 미완성이므로 vol_surge는 volumes[-2] 기준
    """
    if len(bars) < 20:
        return 0, {}

    volumes = [b["volume"] for b in bars]
    score = 0
    detail = {}

    vol_20avg = _sma(volumes, 20)
    vol_10avg = _sma(volumes, 10)
    vol_5avg  = _sma(volumes, 5)

    if vol_20avg > 0:
        ratio_5_20  = vol_5avg  / vol_20avg
        ratio_10_20 = vol_10avg / vol_20avg
        detail["vol_ratio_5_20"] = round(ratio_5_20, 2)

        # 수축 후 회복 패턴: 10일 평균은 낮은데 최근 5일 살아나는 패턴
        if ratio_10_20 < 0.8 and ratio_5_20 > ratio_10_20:
            score += 10
            detail["vol_recovery"] = True
        elif 0.4 <= ratio_5_20 <= 0.75:
            score += 8
            detail["vol_squeeze"] = True

        # 직전 확정봉 거래량 급증 (돌파 시작 신호)
        # 장중: 당일봉 미완성 → volumes[-2](전일 최종) 기준
        # 장마감: volumes[-1](어제 최종) 기준
        if len(volumes) >= 6:
            if is_market_open:
                # 장중: 전일봉[-2] vs 그 이전 5일[-7:-2] 비교
                ref_vol  = volumes[-2] if len(volumes) >= 2 else 0
                avg_base = _sma(volumes[-7:-2], min(5, len(volumes)-2)) if len(volumes) >= 7 else 0
            else:
                # 장마감: 최신봉[-1] vs 직전 5일[-6:-1] 비교
                ref_vol  = volumes[-1]
                avg_base = _sma(volumes[-6:-1], 5) if len(volumes) >= 6 else 0
            if avg_base > 0 and ref_vol >= avg_base * 1.5:
                score += 5
                detail["vol_surge"] = True
                detail["vol_surge_basis"] = "prev_day" if is_market_open else "latest"

    return min(score, 15), detail


def calc_position_score(bars: list, week52_high: float = 0, week52_low: float = 0) -> tuple:
    """52주 위치 점수 (0~10) - KIS API 실제 값 우선"""
    if not bars:
        return 0, {}

    closes  = [b["close"] for b in bars]
    current = closes[-1]
    score   = 0
    detail  = {}

    # KIS API 실제 52주 고저가 우선, 없으면 bars 추정
    h = week52_high if week52_high > 0 else max(closes)
    l = week52_low  if week52_low  > 0 else min(closes)

    if h > l > 0:
        position = (current - l) / (h - l) * 100
        detail["week52_position"] = round(position, 1)
        detail["week52_high"]     = round(h, 0)
        detail["week52_low"]      = round(l, 0)
        detail["using_api_data"]  = week52_high > 0

        if 75 <= position <= 95:
            score = 10
            detail["near_breakout"] = True
        elif 55 <= position < 75:
            score = 6
        elif 40 <= position < 55:
            score = 3

    return score, detail


def calc_frgn_score(investor_data: dict) -> tuple:
    """
    외국인 순매수 점수 (0~10)
    - frgn_5d(5일 합계)가 음수이면 positive_days 점수를 절반으로 제한
      (3일 많이 사고 2일 크게 판 경우 수급 방향성 불일치 방지)
    """
    if not investor_data:
        return 0, {}

    score  = 0
    detail = {}
    positive_days = investor_data.get("frgn_positive_days_5", 0)
    consec        = investor_data.get("frgn_consec_days", 0)
    frgn_5d       = investor_data.get("frgn_5d", 0)
    inst_5d       = investor_data.get("inst_5d", 0)

    detail["frgn_5d"]          = frgn_5d
    detail["frgn_consec_days"] = consec
    detail["inst_5d"]          = inst_5d
    detail["positive_days"]    = positive_days

    # 5일 중 순매수 일수 기준
    if positive_days == 5:
        base = 8
    elif positive_days == 4:
        base = 6
    elif positive_days == 3:
        base = 4
    elif positive_days >= 1:
        base = 2
    else:
        base = 0

    # frgn_5d 합계가 음수 → 일수 점수 절반 (매수일이 있어도 전체 방향이 매도)
    if frgn_5d < 0 and base > 0:
        base = base // 2
        detail["frgn_net_negative"] = True

    score += base

    # 외국인+기관 동시 매수 보너스 (합계 모두 양수인 경우만)
    if frgn_5d > 0 and inst_5d > 0:
        score += 2
        detail["dual_buy"] = True

    return min(score, 10), detail


def calc_vol_rate_score(price_data: dict, is_market_open: bool = True) -> tuple:
    """
    전일 거래량 비율 점수 (0~5)
    장 마감 후엔 의미없으므로 is_market_open=False 시 0점
    """
    if not price_data or not is_market_open:
        return 0, {"note": "장외시간" if not is_market_open else "데이터없음"}

    vol_rate = price_data.get("volume_rate", 0)
    detail   = {"volume_rate": vol_rate}

    if vol_rate >= 150:
        score = 5
        detail["vol_surge_today"] = True
    elif vol_rate >= 100:
        score = 2
    else:
        score = 0

    return score, detail


def calc_nexus_score(
    bars: list,
    stock_meta: dict,
    investor_data: dict,
    price_data: dict,
    is_market_open: bool = True,
) -> dict:
    """
    NEXUS Score 종합 계산
    등급 기준: HIGH>=65 / MID>=50 / LOW<50 (현실화)
    """
    w52h = stock_meta.get("week52_high", 0) or 0
    w52l = stock_meta.get("week52_low",  0) or 0

    vcp_s,    vcp_d    = calc_vcp_score(bars)
    stage2_s, stage2_d = calc_stage2_score(bars)
    rsi_s,    rsi_d    = calc_rsi_score(bars)
    vol_s,    vol_d    = calc_volume_score(bars, is_market_open)
    pos_s,    pos_d    = calc_position_score(bars, w52h, w52l)
    frgn_s,   frgn_d   = calc_frgn_score(investor_data)
    vrate_s,  vrate_d  = calc_vol_rate_score(price_data, is_market_open)

    total = vcp_s + stage2_s + rsi_s + vol_s + pos_s + frgn_s + vrate_s

    # 등급 기준 현실화
    if total >= 65:
        grade = "HIGH"
    elif total >= 50:
        grade = "MID"
    else:
        grade = "LOW"

    candles = [
        {
            "d": b["date"][4:],
            "o": b["open"],
            "h": b["high"],
            "l": b["low"],
            "c": b["close"],
            "v": b["volume"],
        }
        for b in bars[-20:]
    ]

    return {
        "total": total,
        "grade": grade,
        "breakdown": {
            "vcp":     {"score": vcp_s,    "max": 25, **vcp_d},
            "stage2":  {"score": stage2_s, "max": 20, **stage2_d},
            "rsi":     {"score": rsi_s,    "max": 15, **rsi_d},
            "volume":  {"score": vol_s,    "max": 15, **vol_d},
            "position":{"score": pos_s,    "max": 10, **pos_d},
            "frgn":    {"score": frgn_s,   "max": 10, **frgn_d},
            "vol_rate":{"score": vrate_s,  "max": 5,  **vrate_d},
        },
        "candles": candles,
    }
