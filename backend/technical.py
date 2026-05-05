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


def _bars_to_weekly(bars: list) -> list:
    """
    일봉 → 주봉 변환 (월~금 기준 5일 묶음)
    KIS API의 날짜(stck_bsop_date) 기준으로 주차 구분
    bars는 시간순 정렬(오래된 것 먼저) 가정
    """
    if not bars:
        return []

    weekly = []
    week_bars = []

    for bar in bars:
        dt_str = bar.get("date", "")
        try:
            from datetime import datetime as _dt
            dt = _dt.strptime(dt_str, "%Y%m%d")
            week_num = dt.isocalendar()[1]  # ISO 주차
            year_num = dt.isocalendar()[0]
            key = (year_num, week_num)
        except Exception:
            continue

        if not week_bars:
            week_bars = [(key, bar)]
        elif week_bars[-1][0] == key:
            week_bars.append((key, bar))
        else:
            # 주차 변경 → 이전 주 마감
            wk = [b for _, b in week_bars]
            weekly.append({
                "date":   wk[0]["date"],
                "open":   wk[0]["open"],
                "high":   max(b["high"]   for b in wk),
                "low":    min(b["low"]    for b in wk),
                "close":  wk[-1]["close"],
                "volume": sum(b["volume"] for b in wk),
            })
            week_bars = [(key, bar)]

    # 마지막 주 처리
    if week_bars:
        wk = [b for _, b in week_bars]
        weekly.append({
            "date":   wk[0]["date"],
            "open":   wk[0]["open"],
            "high":   max(b["high"]   for b in wk),
            "low":    min(b["low"]    for b in wk),
            "close":  wk[-1]["close"],
            "volume": sum(b["volume"] for b in wk),
        })

    return weekly


def calc_weekly_vcp_bonus(bars: list) -> tuple:
    """
    주봉 VCP 병행 검증 — 일봉 VCP 신뢰도 강화용 보너스 점수
    반환: (bonus_score, detail)
    bonus_score: 0 / 3 / 5
      - 0: 주봉 조건 미충족 (일봉 VCP 점수 그대로)
      - 3: 주봉 부분 정배열 + 수축 확인 (신뢰도 보통)
      - 5: 주봉 완전 정배열 + VCP 수축 + MA10주 우상향 (신뢰도 높음)

    주봉 데이터가 20개(약 5개월) 미만이면 0점 반환
    """
    weekly = _bars_to_weekly(bars)
    if len(weekly) < 20:
        return 0, {"weekly_bars": len(weekly), "skip": "주봉 데이터 부족"}

    w_closes  = [w["close"]  for w in weekly]
    w_volumes = [w["volume"] for w in weekly]
    detail    = {"weekly_bars": len(weekly)}
    bonus     = 0

    # 1) 주봉 이동평균 정배열 확인
    w_ma5  = _sma(w_closes, 5)
    w_ma10 = _sma(w_closes, 10)
    w_ma20 = _sma(w_closes, min(20, len(w_closes)))
    current = w_closes[-1]

    detail["w_ma5"]  = round(w_ma5,  0)
    detail["w_ma10"] = round(w_ma10, 0)
    detail["w_ma20"] = round(w_ma20, 0)

    perfect_w  = current > w_ma5 > w_ma10 > w_ma20 > 0
    partial_w  = current > w_ma10 > w_ma20 > 0

    if not (perfect_w or partial_w):
        detail["weekly_trend"] = "하락/횡보"
        return 0, detail

    detail["weekly_trend"] = "완전정배열" if perfect_w else "부분정배열"

    # 2) 주봉 거래량 수축 확인 (최근 4주 < 이전 10주 평균)
    if len(w_volumes) >= 14:
        vol_recent4 = _sma(w_volumes[-4:], 4)
        vol_prev10  = _sma(w_volumes[-14:-4], 10)
        if vol_prev10 > 0:
            w_vol_ratio = vol_recent4 / vol_prev10
            detail["w_vol_ratio"] = round(w_vol_ratio, 2)
            vol_contracting = w_vol_ratio < 0.8
        else:
            vol_contracting = False
    else:
        vol_contracting = False

    # 3) 주봉 MA10 우상향
    if len(w_closes) >= 15:
        w_ma10_old = _sma(w_closes[:-4], 10)
        w_ma10_rising = w_ma10 > w_ma10_old
        detail["w_ma10_rising"] = w_ma10_rising
    else:
        w_ma10_rising = False

    # 4) 주봉 VCP 수축 패턴 (간이)
    w_swings = _find_swings(w_closes, window=2)  # 주봉은 window=2
    w_corrections = []
    i = 0
    while i < len(w_swings) - 1:
        if w_swings[i][2] == "peak":
            for j in range(i+1, len(w_swings)):
                if w_swings[j][2] == "trough":
                    p, t = w_swings[i][1], w_swings[j][1]
                    if p > 0:
                        c = (p - t) / p * 100
                        if c >= 3.0:
                            w_corrections.append(c)
                    i = j
                    break
            else:
                i += 1
        else:
            i += 1

    w_recent = [c for c in w_corrections[-3:] if c >= 3.0]
    w_vcp = (len(w_recent) >= 2 and
             all(w_recent[k] > w_recent[k+1] for k in range(len(w_recent)-1)))
    detail["w_vcp"] = w_vcp
    if w_vcp:
        detail["w_corrections"] = [round(c, 1) for c in w_recent]

    # 점수 결정
    if perfect_w and w_vcp and w_ma10_rising:
        bonus = 5
        detail["weekly_signal"] = "강함"
    elif (perfect_w or partial_w) and (w_vcp or vol_contracting):
        bonus = 3
        detail["weekly_signal"] = "보통"
    elif partial_w and w_ma10_rising:
        bonus = 2
        detail["weekly_signal"] = "약함"

    return bonus, detail


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
    """
    Stage 2 정배열 점수 (0~20)
    개선: MA60 기울기 단순 여부 → 각도 세분화 (강/중/약)
         최근 N일 이내 정배열 전환 감지 (진입 초기 가산)
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

    if current > ma5 > ma20 > ma60 and ma60 > 0:
        score += 15
        detail["perfect_alignment"] = True
    elif current > ma20 > ma60 and ma60 > 0:
        score += 10
        detail["partial_alignment"] = True
    elif current > ma20:
        score += 5

    detail["ma5"]  = round(ma5, 0)
    detail["ma20"] = round(ma20, 0)
    detail["ma60"] = round(ma60, 0)

    # ── MA60 기울기 세분화 (단순 여부 → 각도 등급) ──────────────────
    # 기존: 우상향이면 무조건 +5점
    # 개선: 기울기 강도에 따라 +2 / +3 / +5점으로 세분화
    #   - 강: 10일 기준 기울기 > 0.3% → +5점 (뚜렷한 상승 추세)
    #   - 중: 0.1~0.3%              → +3점 (완만한 상승)
    #   - 약: 0~0.1%                → +2점 (수평 근접, 최소 확인)
    #   - 하락                      → 0점 (정배열이어도 MA60 하락 시 감점 없음, 점수 미부여)
    if len(closes) >= 65:
        ma60_5ago  = _sma(closes[:-5],  min(60, len(closes) - 5))
        ma60_10ago = _sma(closes[:-10], min(60, len(closes) - 10))

        if ma60_10ago > 0:
            slope_10d = (ma60 - ma60_10ago) / ma60_10ago * 100  # 10일 기울기(%)
            detail["ma60_slope_10d"] = round(slope_10d, 3)

            if slope_10d >= 0.3:
                score += 5
                detail["ma60_rising"] = "강"
            elif slope_10d >= 0.1:
                score += 3
                detail["ma60_rising"] = "중"
            elif slope_10d >= 0.0:
                score += 2
                detail["ma60_rising"] = "약"
            else:
                detail["ma60_rising"] = False

    # ── 정배열 전환 시점 보너스 (+2점) ──────────────────────────────
    # 최근 10일 이내에 정배열로 전환된 경우 (진입 초기 = 가장 유리한 타이밍)
    # 조건: 10일 전엔 MA5 < MA20이었는데 현재 MA5 > MA20
    if len(closes) >= 30 and score >= 10:  # 기본 정배열 조건 충족 시만
        ma5_10ago  = _sma(closes[:-10], 5)
        ma20_10ago = _sma(closes[:-10], 20)
        was_below = ma5_10ago <= ma20_10ago  # 10일 전엔 역배열/횡보
        is_above  = ma5 > ma20               # 현재 정배열
        if was_below and is_above:
            score += 2
            detail["alignment_breakout"] = True  # 정배열 전환 신호

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

    # ── RSI 베어리시 다이버전스 감지 (경고 플래그 + 감점) ──────────
    # 조건: 최근 가격이 신고점인데 RSI 고점이 낮아지는 경우
    # 의미: 상승 모멘텀 약화 → 조만간 조정 가능성
    # 처리: 감점 -3점 + divergence 경고 플래그 (추천에서 제외는 안 함, 신호만 표시)
    if len(closes) >= 30:
        # 최근 15일 내 가격 신고점 여부
        recent_high  = max(closes[-15:])
        prev_high    = max(closes[-30:-15])
        price_new_high = recent_high > prev_high * 1.02  # 2% 이상 신고점

        if price_new_high:
            # RSI 고점 비교 (같은 기간)
            rsi_recent = calc_rsi(closes[-15:])
            rsi_prev15 = calc_rsi(closes[-30:-15])
            rsi_lower  = rsi_recent < rsi_prev15 - 5  # RSI 5pt 이상 낮아짐

            if rsi_lower:
                score = max(0, score - 3)
                detail["bearish_divergence"] = True
                detail["divergence_detail"] = {
                    "price_new_high": round(recent_high, 0),
                    "rsi_recent":     round(rsi_recent, 1),
                    "rsi_prev":       round(rsi_prev15, 1),
                }

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
    외국인 순매수 점수 (0~10) — 하위 호환 유지용 (money_flow_score로 대체됨)
    - frgn_5d(5일 합계)가 음수이면 positive_days 점수를 절반으로 제한
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

    if frgn_5d < 0 and base > 0:
        base = base // 2
        detail["frgn_net_negative"] = True

    score += base

    if frgn_5d > 0 and inst_5d > 0:
        score += 2
        detail["dual_buy"] = True

    return min(score, 10), detail


def calc_candle_signal_score(bars: list) -> tuple:
    """
    캔들 패턴 기반 '분출 직전' 시그널 점수 (0~25)

    ① 매집 도지 + 장대양봉 + 지지 확인 시퀀스 (최대 12점)
       낮은 가격대에서 거래량 많은 윗꼬리 캔들 → 장대양봉 → 지지 유지
       = 매물대 소화 후 상승 직전 패턴

    ② 쌍바닥 + 넥라인 돌파 (최대 8점)
       두 유사 저점 → 중간 고점(넥라인) 돌파 + 거래량

    ③ 적삼병 (최대 5점)
       3일 연속 양봉, 각 봉 시가가 전봉 몸통 내 시작

    ④ 컵앤핸들 간이 감지 (최대 8점)
       U자 회복 + 얕은 핸들 조정 + 돌파

    총합 cap: 25점
    """
    if len(bars) < 25:
        return 0, {}

    score  = 0
    detail = {}

    closes  = [b["close"]  for b in bars]
    opens   = [b["open"]   for b in bars]
    highs   = [b["high"]   for b in bars]
    lows    = [b["low"]    for b in bars]
    volumes = [b["volume"] for b in bars]
    n = len(bars)

    vol_20avg = _sma(volumes, 20) or 1

    # ── ① 매집 도지 + 장대양봉 + 지지 확인 ─────────────────────────
    # 최근 40일 내에서 시퀀스 탐색
    search_range = min(40, n - 5)
    doji_idx     = None
    bigbull_idx  = None

    for i in range(n - search_range, n - 3):
        # 매집 도지 조건
        body  = abs(closes[i] - opens[i])
        upper = highs[i] - max(closes[i], opens[i])
        lower = lows[i]  - min(closes[i], opens[i]) if False else (min(closes[i], opens[i]) - lows[i])
        total_range = highs[i] - lows[i] or 1

        is_doji    = body / total_range < 0.35           # 몸통이 전체의 35% 미만
        has_upper  = upper > body * 2                    # 윗꼬리 > 몸통 × 2
        high_vol   = volumes[i] > vol_20avg * 1.5        # 거래량 1.5배 이상
        low_price  = closes[i] < _sma(closes[:i+1], min(20, i+1))  # 20일선 아래 (낮은 가격대)

        if is_doji and has_upper and high_vol and low_price:
            doji_idx = i
            break  # 가장 오래된 것 기준

    if doji_idx is not None:
        detail["accum_doji_idx"] = doji_idx - n  # 음수 인덱스로 표기
        # 도지 이후 장대양봉 탐색
        for i in range(doji_idx + 1, n - 1):
            body_pct = (closes[i] - opens[i]) / opens[i] * 100 if opens[i] > 0 else 0
            is_bullish_big = closes[i] > opens[i] and body_pct >= 3.0
            big_vol        = volumes[i] > vol_20avg * 2.0

            if is_bullish_big and big_vol:
                bigbull_idx = i
                detail["bigbull_idx"]  = bigbull_idx - n
                detail["bigbull_body"] = round(body_pct, 1)
                break

    if doji_idx is not None and bigbull_idx is not None:
        # 지지 확인: 장대양봉 이후 현재까지 장대양봉 저가 이탈 없음
        support_level = lows[bigbull_idx]
        days_since    = n - 1 - bigbull_idx
        min_low_after = min(lows[bigbull_idx+1:]) if bigbull_idx + 1 < n else closes[-1]
        support_ok    = min_low_after >= support_level * 0.98  # 2% 이내 이탈 허용

        if support_ok and 2 <= days_since <= 30:
            score += 12
            detail["accum_seq"] = "완성"
            detail["support_ok"] = True
            detail["days_since_bigbull"] = days_since
        elif bigbull_idx is not None:
            score += 7
            detail["accum_seq"] = "부분(지지미확인)"
    elif doji_idx is not None:
        score += 3
        detail["accum_seq"] = "도지만"

    # ── ② 쌍바닥 + 넥라인 돌파 ──────────────────────────────────────
    swings = _find_swings(closes, window=4)
    troughs = [(idx, price) for idx, price, t in swings if t == "trough"]
    peaks   = [(idx, price) for idx, price, t in swings if t == "peak"]

    double_bottom = False
    if len(troughs) >= 2:
        t1_idx, t1_price = troughs[-2]
        t2_idx, t2_price = troughs[-1]
        gap_days = t2_idx - t1_idx

        # 두 저점 유사 수준 (±5% 이내) + 간격 10~50일
        if 10 <= gap_days <= 50 and abs(t1_price - t2_price) / (t1_price or 1) <= 0.05:
            # 두 저점 사이 고점(넥라인) 찾기
            neckline_peaks = [p for idx, p in peaks if t1_idx < idx < t2_idx]
            if neckline_peaks:
                neckline = max(neckline_peaks)
                current  = closes[-1]

                # 현재가가 넥라인 돌파 중 (0~5% 위)
                if neckline < current <= neckline * 1.08:
                    neckline_vol = volumes[-1] > vol_20avg * 1.5
                    if neckline_vol:
                        score += 8
                    else:
                        score += 4
                    double_bottom = True
                    detail["double_bottom"] = {
                        "t1": round(t1_price, 0),
                        "t2": round(t2_price, 0),
                        "neckline": round(neckline, 0),
                        "current": round(current, 0),
                        "gap_days": gap_days,
                    }

    # ── ③ 적삼병 ─────────────────────────────────────────────────────
    if n >= 5:
        b1, b2, b3 = bars[-3], bars[-2], bars[-1]
        c1, c2, c3 = b1["close"], b2["close"], b3["close"]
        o1, o2, o3 = b1["open"],  b2["open"],  b3["open"]

        all_bullish  = c1 > o1 and c2 > o2 and c3 > o3
        rising       = c1 < c2 < c3
        # 각 봉 시가가 전봉 몸통 내 시작
        o2_in_body1  = o1 <= o2 <= c1
        o3_in_body2  = o2 <= o3 <= c2
        # 각 봉 2% 이상 몸통
        body1_pct = (c1 - o1) / o1 * 100 if o1 > 0 else 0
        body2_pct = (c2 - o2) / o2 * 100 if o2 > 0 else 0
        body3_pct = (c3 - o3) / o3 * 100 if o3 > 0 else 0
        big_bodies = body1_pct >= 1.5 and body2_pct >= 1.5 and body3_pct >= 1.5

        if all_bullish and rising and o2_in_body1 and o3_in_body2 and big_bodies:
            score += 5
            detail["three_white_soldiers"] = True

    # ── ④ 컵앤핸들 간이 감지 ─────────────────────────────────────────
    if n >= 40:
        # 최근 40~80일 구간에서 컵 탐색
        scan = bars[-min(80, n):]
        sc   = [b["close"] for b in scan]
        sn   = len(sc)

        if sn >= 30:
            left_peak_idx  = sc.index(max(sc[:sn//2]))       # 좌측 고점
            left_peak      = sc[left_peak_idx]
            trough_val     = min(sc[left_peak_idx:])          # 컵 바닥
            trough_idx_rel = sc[left_peak_idx:].index(trough_val) + left_peak_idx

            # 컵 조건: 하락 15~40%, U자 반등
            drop_pct = (left_peak - trough_val) / left_peak * 100
            if 12 <= drop_pct <= 45 and trough_idx_rel < sn - 5:
                recovery = sc[-1]
                recovery_pct = (recovery - trough_val) / (left_peak - trough_val) * 100

                # 80% 이상 회복 (컵 오른쪽)
                if recovery_pct >= 75:
                    # 핸들: 최근 5~15일 내 5~20% 조정
                    handle_range = sc[max(0, sn-15):]
                    handle_high  = max(handle_range)
                    handle_low   = min(handle_range)
                    handle_drop  = (handle_high - handle_low) / handle_high * 100 if handle_high > 0 else 0

                    if 3 <= handle_drop <= 20:
                        # 핸들 상단 돌파 여부
                        if sc[-1] >= handle_high * 0.97:
                            cup_vol = volumes[-1] > vol_20avg * 1.3
                            score += 8 if cup_vol else 5
                            detail["cup_handle"] = {
                                "drop_pct": round(drop_pct, 1),
                                "recovery_pct": round(recovery_pct, 1),
                                "handle_drop": round(handle_drop, 1),
                            }

    return min(score, 25), detail


def calc_money_flow_score(bars: list, investor_data: dict, mktcap: int = 0) -> tuple:
    """
    자금 흐름 집중도 점수 (0~20) — 기존 calc_frgn_score(0~10) 대체·확장

    ① 거래대금 이상 급증 (0~8점)
       bars의 amount(거래대금) 필드 활용
       거래대금은 거래량보다 "큰 손의 진입"을 더 정확히 반영

    ② 외국인+기관 동시 매집 강도 (0~8점)
       합산 순매수를 시총 대비 비율로 환산해 강도 측정

    ③ 기관 순매수 가속 (0~4점)
       최근 5일 기관이 20일 평균보다 빠르게 사고 있는지
    """
    detail = {}
    score  = 0

    # ── ① 거래대금 급증 ──────────────────────────────────────────────
    amounts = [b.get("amount", 0) for b in bars]
    amounts_nonzero = [a for a in amounts if a > 0]

    if len(amounts_nonzero) >= 20:
        amt_5avg  = _sma(amounts, 5)
        amt_20avg = _sma(amounts, 20)

        if amt_20avg > 0:
            amt_ratio = amt_5avg / amt_20avg
            detail["amt_ratio_5_20"] = round(amt_ratio, 2)

            if amt_ratio >= 2.5:
                score += 8
                detail["money_surge"] = "강"
            elif amt_ratio >= 1.8:
                score += 5
                detail["money_surge"] = "중"
            elif amt_ratio >= 1.3:
                score += 3
                detail["money_surge"] = "약"
            elif amt_ratio >= 1.0:
                score += 1
    elif amounts_nonzero:
        # 데이터 부족 시 거래량으로 대체
        vol_20avg = _sma([b["volume"] for b in bars], 20) or 1
        vol_5avg  = _sma([b["volume"] for b in bars], 5)
        ratio = vol_5avg / vol_20avg
        detail["amt_fallback_vol_ratio"] = round(ratio, 2)
        if ratio >= 1.8: score += 4
        elif ratio >= 1.3: score += 2

    # ── ② 외국인+기관 동시 매집 강도 ────────────────────────────────
    if investor_data:
        frgn_5d   = investor_data.get("frgn_5d", 0)
        inst_5d   = investor_data.get("inst_5d", 0)
        frgn_20d  = investor_data.get("frgn_20d", 0)
        inst_20d  = investor_data.get("inst_20d", 0)
        pos_days  = investor_data.get("frgn_positive_days_5", 0)
        consec    = investor_data.get("frgn_consec_days", 0)
        is_estimated = investor_data.get("is_estimated", False)

        detail["frgn_5d"]   = frgn_5d
        detail["inst_5d"]   = inst_5d
        detail["pos_days"]  = pos_days
        detail["consec"]    = consec
        detail["is_estimated"] = is_estimated

        combined_5d = frgn_5d + inst_5d

        if combined_5d > 0:
            # 시총 대비 비율로 강도 환산 (시총 없으면 절대값 기준)
            if mktcap > 0:
                # mktcap 단위: 억원 → 주식수 추정 (현재가로 역산)
                cur_price = bars[-1]["close"] if bars else 0
                if cur_price > 0:
                    total_shares = (mktcap * 1e8) / cur_price  # 추정 발행주식수
                    ratio = combined_5d / total_shares * 100   # % 비중
                    detail["smart_money_ratio"] = round(ratio, 3)

                    if ratio >= 0.5:
                        score += 8
                        detail["smart_money"] = "강"
                    elif ratio >= 0.2:
                        score += 5
                        detail["smart_money"] = "중"
                    elif ratio >= 0.05:
                        score += 3
                        detail["smart_money"] = "약"
                    else:
                        score += 1
                        detail["smart_money"] = "미약"
            else:
                # 시총 미수신: 연속 매수 일수 기준 폴백
                if pos_days == 5:   score += 6
                elif pos_days == 4: score += 4
                elif pos_days == 3: score += 3
                elif pos_days >= 1: score += 1
                if frgn_5d > 0 and inst_5d > 0:
                    score += 2
                    detail["dual_buy"] = True

        elif frgn_5d < 0 and inst_5d < 0:
            detail["smart_money"] = "쌍방매도"

        # ── ③ 기관 순매수 가속 ──────────────────────────────────────
        if inst_5d > 0 and inst_20d > 0:
            # 5일 기관 매수 속도가 20일 평균보다 빠른지
            inst_20d_rate = inst_20d / 4  # 5일 환산 기준값
            if inst_20d_rate > 0:
                accel = inst_5d / inst_20d_rate
                detail["inst_accel"] = round(accel, 2)
                if accel >= 1.5:
                    score += 4
                    detail["inst_accelerating"] = True
                elif accel >= 1.0:
                    score += 2

    return min(score, 20), detail


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
    예외 발생 시 0점 dict 반환 (파이프라인 중단 방지)
    """
    try:
        return _calc_nexus_score_inner(
            bars, stock_meta, investor_data, price_data, is_market_open
        )
    except Exception as e:
        import traceback as _tb
        print(f"[TECHNICAL] calc_nexus_score 예외: {e}\n{_tb.format_exc()[:400]}")
        return {
            "total": 0, "grade": "LOW",
            "breakdown": {
                "vcp":           {"score": 0, "max": 25},
                "stage2":        {"score": 0, "max": 20},
                "rsi":           {"score": 0, "max": 12, "error": str(e)[:80]},
                "volume":        {"score": 0, "max": 10},
                "position":      {"score": 0, "max":  8},
                "money_flow":    {"score": 0, "max": 20},
                "vol_rate":      {"score": 0, "max":  5},
                "weekly_vcp":    {"score": 0, "max":  5},
                "candle_signal": {"score": 0, "max": 25},
                "frgn":          {"score": 0, "max":  0},
            },
            "candles": [],
            "_error": str(e)[:100],
        }


def _calc_nexus_score_inner(
    bars: list,
    stock_meta: dict,
    investor_data: dict,
    price_data: dict,
    is_market_open: bool = True,
) -> dict:
    w52h    = stock_meta.get("week52_high", 0) or 0
    w52l    = stock_meta.get("week52_low",  0) or 0
    mktcap  = stock_meta.get("mktcap", 0) or price_data.get("mktcap", 0) or 0

    vcp_s,    vcp_d    = calc_vcp_score(bars)
    stage2_s, stage2_d = calc_stage2_score(bars)
    rsi_s,    rsi_d    = calc_rsi_score(bars)
    vol_s,    vol_d    = calc_volume_score(bars, is_market_open)
    pos_s,    pos_d    = calc_position_score(bars, w52h, w52l)
    vrate_s,  vrate_d  = calc_vol_rate_score(price_data, is_market_open)

    # 신규: 자금흐름 (기존 frgn 대체·확장)
    mflow_s,  mflow_d  = calc_money_flow_score(bars, investor_data, mktcap)

    # 신규: 캔들 시그널 (분출 직전 패턴)
    candle_s, candle_d = calc_candle_signal_score(bars)

    # 주봉 VCP 병행 검증 보너스
    weekly_bonus, weekly_d = 0, {}
    if vcp_s >= 8:
        try:
            weekly_bonus, weekly_d = calc_weekly_vcp_bonus(bars)
        except Exception as _we:
            weekly_d = {"skip": f"주봉 계산 오류: {str(_we)[:50]}"}

    # 기존 frgn_score는 money_flow_score로 대체됨 (하위 호환 표기용으로만 유지)
    _, frgn_d = calc_frgn_score(investor_data)

    # ── 점수 체계 v3 ────────────────────────────────────────────────
    # VCP(25) + Stage2(20) + RSI(12) + Volume(10) + Position(8)
    # + MoneyFlow(20) + VolRate(5) + WeeklyVCP(5) + CandleSignal(25)
    # 총 130점 만점
    # 등급 기준: HIGH≥80 / MID≥60 / LOW<60
    total = (
        min(vcp_s, 25)       +  # VCP 25점 cap
        stage2_s             +  # 20점
        min(rsi_s, 12)       +  # RSI 12점 cap
        min(vol_s, 10)       +  # 거래량 10점 cap
        min(pos_s, 8)        +  # 52주위치 8점 cap
        mflow_s              +  # 자금흐름 20점
        vrate_s              +  # 장중거래량비율 5점
        weekly_bonus         +  # 주봉VCP 5점
        candle_s                # 캔들시그널 25점
    )

    if total >= 80:
        grade = "HIGH"
    elif total >= 60:
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
            "vcp":          {"score": min(vcp_s,25), "max": 25, **vcp_d},
            "stage2":       {"score": stage2_s,      "max": 20, **stage2_d},
            "rsi":          {"score": min(rsi_s,12), "max": 12, **rsi_d},
            "volume":       {"score": min(vol_s,10), "max": 10, **vol_d},
            "position":     {"score": min(pos_s, 8), "max":  8, **pos_d},
            "money_flow":   {"score": mflow_s,       "max": 20, **mflow_d},
            "vol_rate":     {"score": vrate_s,        "max":  5, **vrate_d},
            "weekly_vcp":   {"score": weekly_bonus,   "max":  5, **weekly_d},
            "candle_signal":{"score": candle_s,       "max": 25, **candle_d},
            # 하위 호환: frgn 필드 유지 (프론트 표시용)
            "frgn":         {"score": 0,              "max":  0, **frgn_d},
        },
        "candles": candles,
    }
