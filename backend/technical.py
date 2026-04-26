# -*- coding: utf-8 -*-
"""
technical.py
기술적 지표 계산 - 외부 라이브러리 없이 순수 Python 산술
- VCP (Volatility Contraction Pattern)
- Stage 2 정배열 분석
- RSI (14일)
- 거래량 수축·회복 패턴
- 52주 위치
"""


def _sma(values: list, n: int) -> float:
    """단순 이동평균"""
    if len(values) < n:
        return sum(values) / len(values) if values else 0.0
    return sum(values[-n:]) / n


def _find_peaks_troughs(closes: list):
    """간단한 고점/저점 탐지 (최소 3일 단위)"""
    peaks, troughs = [], []
    n = len(closes)
    for i in range(2, n - 2):
        if closes[i] > closes[i-1] and closes[i] > closes[i+1]:
            if closes[i] > closes[i-2] and closes[i] > closes[i+2]:
                peaks.append(i)
        if closes[i] < closes[i-1] and closes[i] < closes[i+1]:
            if closes[i] < closes[i-2] and closes[i] < closes[i+2]:
                troughs.append(i)
    return peaks, troughs


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
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)


def calc_vcp_score(bars: list) -> tuple:
    """
    VCP (Volatility Contraction Pattern) 점수 계산
    반환: (score 0~25, detail dict)
    """
    if len(bars) < 20:
        return 0, {}

    closes  = [b["close"]  for b in bars]
    volumes = [b["volume"] for b in bars]
    score = 0
    detail = {}

    peaks, troughs = _find_peaks_troughs(closes)

    # 조정폭 축소 검사 (최근 3개 조정 구간)
    if len(peaks) >= 2 and len(troughs) >= 2:
        corrections = []
        for i in range(min(3, min(len(peaks), len(troughs)))):
            if i < len(peaks) and i < len(troughs):
                p_idx = peaks[-(i+1)]
                t_idx = troughs[-(i+1)]
                if t_idx < p_idx:
                    # 고점 이후 저점 찾기
                    sub_troughs = [t for t in troughs if t > p_idx]
                    if sub_troughs:
                        t_idx = sub_troughs[0]
                peak_price  = closes[p_idx]
                trough_price = closes[t_idx]
                if peak_price > 0:
                    corr = (peak_price - trough_price) / peak_price * 100
                    corrections.append(corr)

        if len(corrections) >= 2:
            # 조정폭이 점점 작아지는지
            contracting = all(
                corrections[i] > corrections[i+1]
                for i in range(len(corrections) - 1)
            )
            if contracting:
                score += 12
                detail["vcp_contracting"] = [round(c, 1) for c in corrections]
            elif corrections and corrections[-1] < 15:
                score += 5
                detail["vcp_partial"] = True

    # 거래량 수축 검사 (최근 5일 vs 20일 평균)
    if len(volumes) >= 20:
        vol_20avg = _sma(volumes, 20)
        vol_5avg  = _sma(volumes, 5)
        if vol_20avg > 0:
            vol_ratio = vol_5avg / vol_20avg
            detail["vol_ratio"] = round(vol_ratio, 2)
            if 0.35 <= vol_ratio <= 0.75:
                score += 8
                detail["vol_squeeze"] = True
            elif vol_ratio < 0.35:
                score += 4  # 과도한 수축도 일부 점수

    # 현재가 > 20일 이동평균
    if len(closes) >= 20:
        ma20 = _sma(closes, 20)
        if closes[-1] > ma20:
            score += 5
            detail["above_ma20"] = True

    return min(score, 25), detail


def calc_stage2_score(bars: list) -> tuple:
    """
    Stan Weinstein Stage 2 정배열 점수
    반환: (score 0~20, detail dict)
    """
    if len(bars) < 20:
        return 0, {}

    closes = [b["close"] for b in bars]
    score = 0
    detail = {}

    ma5  = _sma(closes, 5)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, min(60, len(closes)))
    current = closes[-1]

    # 완전 정배열
    if current > ma5 > ma20 > ma60 and ma60 > 0:
        score += 12
        detail["perfect_alignment"] = True
    elif current > ma20 > ma60 and ma60 > 0:
        score += 7
        detail["partial_alignment"] = True
    elif current > ma20:
        score += 3

    detail["ma5"] = round(ma5, 0)
    detail["ma20"] = round(ma20, 0)
    detail["ma60"] = round(ma60, 0)

    # 60일선 우상향 (5일 전 대비)
    if len(closes) >= 65:
        ma60_old = _sma(closes[:-5], min(60, len(closes) - 5))
        if ma60 > ma60_old:
            score += 5
            detail["ma60_rising"] = True

    # 현재가 52주 고가의 75% 이상
    w52_high = max(closes)
    if w52_high > 0 and current >= w52_high * 0.75:
        score += 3
        detail["near_52w"] = True

    return min(score, 20), detail


def calc_rsi_score(bars: list) -> tuple:
    """RSI 점수 계산. 반환: (score 0~15, detail dict)"""
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
        score = 8
    elif 40 <= rsi < 45:
        score = 5
    else:
        score = 0

    # RSI 상승 추세 여부 (최근 3일 비교)
    if len(closes) >= 18:
        rsi_prev = calc_rsi(closes[:-3])
        if rsi > rsi_prev and 40 <= rsi <= 75:
            score = min(score + 2, 15)
            detail["rsi_rising"] = True

    return score, detail


def calc_volume_score(bars: list) -> tuple:
    """
    거래량 수축·회복 패턴 점수
    반환: (score 0~15, detail dict)
    """
    if len(bars) < 20:
        return 0, {}

    volumes = [b["volume"] for b in bars]
    score = 0
    detail = {}

    vol_20avg = _sma(volumes, 20)
    vol_5avg  = _sma(volumes, 5)

    if vol_20avg > 0:
        ratio = vol_5avg / vol_20avg
        detail["vol_ratio_5_20"] = round(ratio, 2)

        # 거래량 수축 구간 (매집 신호)
        if 0.4 <= ratio <= 0.7:
            score += 10
            detail["vol_squeeze"] = True
        elif 0.3 <= ratio < 0.4:
            score += 6

        # 전일 거래량 급증 (돌파 시작 신호)
        if len(volumes) >= 2:
            yesterday = volumes[-2]
            avg3 = _sma(volumes[:-1], min(3, len(volumes) - 1))
            if avg3 > 0 and yesterday / avg3 >= 1.5:
                score += 5
                detail["vol_surge"] = True

    return min(score, 15), detail


def calc_position_score(bars: list, week52_high: float = 0, week52_low: float = 0) -> tuple:
    """
    52주 위치 점수 (pykis quote.indicator 또는 bars 최고가 기반)
    반환: (score 0~10, detail dict)
    """
    if not bars:
        return 0, {}

    closes = [b["close"] for b in bars]
    current = closes[-1]
    score = 0
    detail = {}

    # week52_high/low가 없으면 bars에서 계산
    if week52_high <= 0:
        week52_high = max(closes)
    if week52_low <= 0:
        week52_low = min(closes)

    if week52_high > week52_low and week52_high > 0:
        position = (current - week52_low) / (week52_high - week52_low) * 100
        detail["week52_position"] = round(position, 1)
        detail["week52_high"] = round(week52_high, 0)
        detail["week52_low"] = round(week52_low, 0)

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
    외국인 순매수 점수 (KIS inquire-investor 데이터 기반)
    반환: (score 0~10, detail dict)
    """
    if not investor_data:
        return 0, {}

    score = 0
    detail = {}
    positive_days = investor_data.get("frgn_positive_days_5", 0)
    consec = investor_data.get("frgn_consec_days", 0)
    frgn_5d = investor_data.get("frgn_5d", 0)
    inst_5d = investor_data.get("inst_5d", 0)

    detail["frgn_5d"] = frgn_5d
    detail["frgn_consec_days"] = consec
    detail["inst_5d"] = inst_5d

    # 5일 중 양수 일수 기준
    if positive_days == 5:
        score += 8
    elif positive_days == 4:
        score += 6
    elif positive_days == 3:
        score += 4
    elif positive_days >= 1:
        score += 2

    # 기관도 같이 매수하면 보너스
    if inst_5d > 0 and frgn_5d > 0:
        score += 2
        detail["dual_buy"] = True

    return min(score, 10), detail


def calc_vol_rate_score(price_data: dict) -> tuple:
    """
    전일 거래량 비율 점수 (KIS inquire-price prdy_vrss_vol_rate 기반)
    반환: (score 0~5, detail dict)
    """
    if not price_data:
        return 0, {}

    vol_rate = price_data.get("volume_rate", 0)
    detail = {"volume_rate": vol_rate}

    if vol_rate >= 150:
        score = 5
        detail["vol_surge_today"] = True
    elif vol_rate >= 100:
        score = 2
    else:
        score = 0

    return score, detail


def calc_nexus_score(bars: list, stock_meta: dict, investor_data: dict, price_data: dict) -> dict:
    """
    NEXUS Score 종합 계산
    bars: 일봉 데이터 리스트
    stock_meta: kis_client에서 받은 종목 메타 (week52_high, week52_low 등)
    investor_data: kis_official.fetch_investor_trend() 결과
    price_data: kis_official.fetch_current_price() 결과

    반환: {total, grade, breakdown, candles(최근 20개)}
    """
    w52h = stock_meta.get("week52_high", 0) or 0
    w52l = stock_meta.get("week52_low", 0) or 0

    vcp_s,    vcp_d    = calc_vcp_score(bars)
    stage2_s, stage2_d = calc_stage2_score(bars)
    rsi_s,    rsi_d    = calc_rsi_score(bars)
    vol_s,    vol_d    = calc_volume_score(bars)
    pos_s,    pos_d    = calc_position_score(bars, w52h, w52l)
    frgn_s,   frgn_d   = calc_frgn_score(investor_data)
    vrate_s,  vrate_d  = calc_vol_rate_score(price_data)

    total = vcp_s + stage2_s + rsi_s + vol_s + pos_s + frgn_s + vrate_s

    if total >= 75:
        grade = "HIGH"
    elif total >= 55:
        grade = "MID"
    else:
        grade = "LOW"

    # 최근 20개 캔들 (프론트 차트용)
    candles = [
        {
            "d": b["date"][4:],  # MMDD
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
