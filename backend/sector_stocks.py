# -*- coding: utf-8 -*-
"""
sector_stocks.py
AI가 결정한 섹터 → 후보 종목 매핑
섹터당 8개, 총 9개 섹터 = 72개 종목
"""

SECTOR_MAP = {
    # AI 섹터명 키워드 → 내부 섹터 키 (소문자 처리 후 매핑)
    # 한국어
    "반도체": "semiconductor",
    "방산": "defense",
    "방위": "defense",
    "ai플랫폼": "ai_platform",
    "플랫폼": "ai_platform",
    "배터리": "battery",
    "이차전지": "battery",
    "자동차": "auto_ev",
    "전기차": "auto_ev",
    "신재생": "renewable",
    "재생에너지": "renewable",
    "태양광": "renewable",
    "바이오": "healthcare",
    "헬스케어": "healthcare",
    "제약": "healthcare",
    "금융": "finance",
    "은행": "finance",
    "보험": "finance",
    "철강": "steel",
    "소재": "steel",
    # 영어 소문자
    "semiconductor": "semiconductor",
    "defense": "defense",
    "ai": "ai_platform",
    "ai_platform": "ai_platform",
    "battery": "battery",
    "auto_ev": "auto_ev",
    "automotive": "auto_ev",
    "renewable": "renewable",
    "healthcare": "healthcare",
    "finance": "finance",
    "steel": "steel",
}

SECTOR_STOCKS = {
    "semiconductor": [
        {"code": "005930", "name": "삼성전자",     "cap": "large"},
        {"code": "000660", "name": "SK하이닉스",   "cap": "large"},
        {"code": "042700", "name": "한미반도체",   "cap": "mid"},
        {"code": "240810", "name": "원익IPS",      "cap": "mid"},
        {"code": "336370", "name": "솔브레인홀딩스","cap": "mid"},
        {"code": "036830", "name": "솔브레인",     "cap": "mid"},
        {"code": "058470", "name": "리노공업",     "cap": "mid"},
        {"code": "104830", "name": "원익머트리얼즈","cap": "small"},
    ],
    "defense": [
        {"code": "012450", "name": "한화에어로스페이스","cap": "large"},
        {"code": "079550", "name": "LIG넥스원",    "cap": "mid"},
        {"code": "047810", "name": "한국항공우주", "cap": "large"},
        {"code": "064350", "name": "현대로템",     "cap": "mid"},
        {"code": "272210", "name": "한화시스템",   "cap": "mid"},
        {"code": "000880", "name": "한화",         "cap": "large"},
        {"code": "071970", "name": "STX엔진",      "cap": "small"},
        {"code": "004870", "name": "쌍용정보통신", "cap": "small"},
    ],
    "ai_platform": [
        {"code": "035420", "name": "NAVER",        "cap": "large"},
        {"code": "035720", "name": "카카오",       "cap": "large"},
        {"code": "259960", "name": "크래프톤",     "cap": "mid"},
        {"code": "067160", "name": "아프리카TV",   "cap": "mid"},
        {"code": "377300", "name": "카카오페이",   "cap": "mid"},
        {"code": "293490", "name": "카카오게임즈", "cap": "mid"},
        {"code": "263750", "name": "펄어비스",     "cap": "mid"},
        {"code": "095660", "name": "네오위즈",     "cap": "small"},
    ],
    "battery": [
        {"code": "373220", "name": "LG에너지솔루션","cap": "large"},
        {"code": "006400", "name": "삼성SDI",      "cap": "large"},
        {"code": "051910", "name": "LG화학",       "cap": "large"},
        {"code": "003670", "name": "포스코퓨처엠", "cap": "mid"},
        {"code": "247540", "name": "에코프로비엠", "cap": "mid"},
        {"code": "066970", "name": "엘앤에프",     "cap": "mid"},
        {"code": "086520", "name": "에코프로",     "cap": "mid"},
        {"code": "278280", "name": "천보",         "cap": "mid"},
    ],
    "auto_ev": [
        {"code": "005380", "name": "현대차",       "cap": "large"},
        {"code": "000270", "name": "기아",         "cap": "large"},
        {"code": "012330", "name": "현대모비스",   "cap": "large"},
        {"code": "018880", "name": "한온시스템",   "cap": "mid"},
        {"code": "204320", "name": "HL만도",       "cap": "mid"},
        {"code": "015260", "name": "야스",         "cap": "small"},
        {"code": "007340", "name": "LS전선아시아", "cap": "mid"},
        {"code": "009540", "name": "HD현대중공업", "cap": "large"},
    ],
    "renewable": [
        {"code": "009830", "name": "한화솔루션",   "cap": "large"},
        {"code": "010060", "name": "OCI홀딩스",    "cap": "mid"},
        {"code": "112610", "name": "씨에스윈드",   "cap": "mid"},
        {"code": "298040", "name": "효성중공업",   "cap": "mid"},
        {"code": "322000", "name": "HD현대에너지솔루션","cap": "mid"},
        {"code": "336260", "name": "두산퓨얼셀",  "cap": "mid"},
        {"code": "399720", "name": "에스퓨얼셀",  "cap": "small"},
        {"code": "175330", "name": "JB금융지주",   "cap": "mid"},  # 대체
    ],
    "healthcare": [
        {"code": "207940", "name": "삼성바이오로직스","cap": "large"},
        {"code": "068270", "name": "셀트리온",     "cap": "large"},
        {"code": "000100", "name": "유한양행",     "cap": "mid"},
        {"code": "128940", "name": "한미약품",     "cap": "mid"},
        {"code": "196170", "name": "알테오젠",     "cap": "mid"},
        {"code": "028300", "name": "HLB",          "cap": "mid"},
        {"code": "145020", "name": "휴젤",         "cap": "mid"},
        {"code": "009420", "name": "한미사이언스", "cap": "mid"},
    ],
    "finance": [
        {"code": "105560", "name": "KB금융",       "cap": "large"},
        {"code": "055550", "name": "신한지주",     "cap": "large"},
        {"code": "086790", "name": "하나금융지주", "cap": "large"},
        {"code": "316140", "name": "우리금융지주", "cap": "large"},
        {"code": "138040", "name": "메리츠금융지주","cap": "mid"},
        {"code": "032830", "name": "삼성생명",     "cap": "large"},
        {"code": "000810", "name": "삼성화재",     "cap": "large"},
        {"code": "005830", "name": "DB손해보험",   "cap": "mid"},
    ],
    "steel": [
        {"code": "005490", "name": "POSCO홀딩스",  "cap": "large"},
        {"code": "004020", "name": "현대제철",     "cap": "large"},
        {"code": "002140", "name": "고려아연",     "cap": "large"},
        {"code": "011790", "name": "SKC",          "cap": "mid"},
        {"code": "009150", "name": "삼성전기",     "cap": "large"},
        {"code": "047050", "name": "포스코인터내셔널","cap": "mid"},
        {"code": "001390", "name": "KG동국제강",   "cap": "mid"},
        {"code": "010780", "name": "아이에스동서", "cap": "mid"},
    ],
}


def get_sector_stocks(sector_names: list, max_per_sector: int = 8) -> list:
    """
    AI가 결정한 섹터명 리스트 → 후보 종목 리스트 반환
    sector_names: ["반도체", "방산", "SEMICONDUCTOR", "DEFENSE" ...] 한국어/영어 모두 지원
    """
    sector_keys = set()
    for name in sector_names:
        if not name:
            continue
        name_lower = name.lower().strip()
        # 1. 직접 매핑 (소문자 변환 후)
        if name_lower in SECTOR_MAP:
            sector_keys.add(SECTOR_MAP[name_lower])
            continue
        # 2. SECTOR_STOCKS 키 직접 매핑 (예: "semiconductor" 자체가 키인 경우)
        if name_lower in SECTOR_STOCKS:
            sector_keys.add(name_lower)
            continue
        # 3. 부분 매칭
        matched = False
        for kw, key in SECTOR_MAP.items():
            if kw in name_lower or name_lower in kw:
                sector_keys.add(key)
                matched = True
                break
        if matched:
            continue
        # 4. 언더스코어 제거 후 재시도 (예: "ai_platform" → "aiplatform")
        name_clean = name_lower.replace("_", "").replace(" ", "")
        for kw, key in SECTOR_MAP.items():
            kw_clean = kw.replace("_", "").replace(" ", "")
            if kw_clean in name_clean or name_clean in kw_clean:
                sector_keys.add(key)
                break

    # 매핑 실패 시 기본값
    if not sector_keys:
        sector_keys = {"semiconductor"}

    result = []
    for key in sector_keys:
        stocks = SECTOR_STOCKS.get(key, [])
        for s in stocks[:max_per_sector]:
            result.append({**s, "sector_key": key})

    return result


def get_all_codes() -> list:
    """전체 종목 코드 리스트"""
    codes = []
    for stocks in SECTOR_STOCKS.values():
        codes.extend(s["code"] for s in stocks)
    return list(set(codes))
