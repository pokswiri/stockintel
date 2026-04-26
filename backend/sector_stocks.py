# -*- coding: utf-8 -*-
"""
sector_stocks.py v2
검증 기준:
- 시총 500억↑ (코스닥) / 1000억↑ (코스피) 이상만 포함
- 사명변경·잘못분류 종목 제거
- 섹터별 8개, 실질적 대표종목 위주
"""

SECTOR_MAP = {
    "반도체": "semiconductor", "semiconductor": "semiconductor",
    "방산": "defense", "defense": "defense", "방위": "defense",
    "ai플랫폼": "ai_platform", "ai_platform": "ai_platform",
    "플랫폼": "ai_platform", "ai": "ai_platform",
    "배터리": "battery", "battery": "battery", "이차전지": "battery",
    "자동차": "auto_ev", "auto_ev": "auto_ev", "automotive": "auto_ev", "전기차": "auto_ev",
    "신재생": "renewable", "renewable": "renewable", "재생에너지": "renewable", "태양광": "renewable",
    "바이오": "healthcare", "헬스케어": "healthcare", "healthcare": "healthcare", "제약": "healthcare",
    "금융": "finance", "finance": "finance", "은행": "finance", "보험": "finance",
    "철강": "steel", "소재": "steel", "steel": "steel",
}

SECTOR_STOCKS = {
    "semiconductor": [
        {"code": "005930", "name": "삼성전자",     "cap": "large"},  # 시총 1위
        {"code": "000660", "name": "SK하이닉스",   "cap": "large"},  # 시총 2위
        {"code": "042700", "name": "한미반도체",   "cap": "mid"},    # HBM 핵심
        {"code": "240810", "name": "원익IPS",      "cap": "mid"},    # 반도체 장비
        {"code": "336370", "name": "솔루스첨단소재","cap": "mid"},    # 소재
        {"code": "036830", "name": "솔브레인",     "cap": "mid"},    # 반도체 소재
        {"code": "058470", "name": "리노공업",     "cap": "mid"},    # 소켓·테스트
        {"code": "089030", "name": "테크윙",       "cap": "mid"},    # 반도체 핸들러
    ],
    "defense": [
        {"code": "012450", "name": "한화에어로스페이스","cap": "large"}, # K9·엔진
        {"code": "079550", "name": "LIG넥스원",    "cap": "mid"},    # 미사일·유도무기
        {"code": "047810", "name": "한국항공우주", "cap": "large"},  # KF-21·헬기
        {"code": "064350", "name": "현대로템",     "cap": "mid"},    # K2전차·수소
        {"code": "272210", "name": "한화시스템",   "cap": "mid"},    # 레이더·전자전
        {"code": "000880", "name": "한화",         "cap": "large"},  # 방산 지주
        {"code": "047560", "name": "이스트소프트", "cap": "mid"},    # 방위 SW
        {"code": "065450", "name": "빅텍",         "cap": "mid"},    # 방산 전자
    ],
    "ai_platform": [
        {"code": "035420", "name": "NAVER",        "cap": "large"},
        {"code": "035720", "name": "카카오",       "cap": "large"},
        {"code": "259960", "name": "크래프톤",     "cap": "mid"},
        {"code": "067160", "name": "아프리카TV",   "cap": "mid"},
        {"code": "377300", "name": "카카오페이",   "cap": "mid"},
        {"code": "293490", "name": "카카오게임즈", "cap": "mid"},
        {"code": "263750", "name": "펄어비스",     "cap": "mid"},
        {"code": "012510", "name": "더존비즈온",   "cap": "mid"},    # AI ERP
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
        {"code": "011210", "name": "현대위아",     "cap": "mid"},    # 엔진·부품
        {"code": "007340", "name": "LS전선아시아", "cap": "mid"},
        {"code": "009540", "name": "HD현대중공업", "cap": "large"},
    ],
    "renewable": [
        {"code": "009830", "name": "한화솔루션",   "cap": "large"},  # 태양광
        {"code": "010060", "name": "OCI홀딩스",    "cap": "mid"},    # 폴리실리콘
        {"code": "112610", "name": "씨에스윈드",   "cap": "mid"},    # 풍력타워
        {"code": "298040", "name": "효성중공업",   "cap": "mid"},    # 전력기기
        {"code": "322000", "name": "HD현대에너지솔루션","cap": "mid"},
        {"code": "336260", "name": "두산퓨얼셀",  "cap": "mid"},    # 수소연료전지
        {"code": "034020", "name": "두산에너빌리티","cap": "large"}, # 원전·풍력
        {"code": "010120", "name": "LS일렉트릭",   "cap": "mid"},    # 전력기기
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
    sector_keys = set()
    for name in sector_names:
        if not name:
            continue
        name_lower = name.lower().strip()
        if name_lower in SECTOR_MAP:
            sector_keys.add(SECTOR_MAP[name_lower])
            continue
        if name_lower in SECTOR_STOCKS:
            sector_keys.add(name_lower)
            continue
        matched = False
        for kw, key in SECTOR_MAP.items():
            if kw in name_lower or name_lower in kw:
                sector_keys.add(key)
                matched = True
                break
        if matched:
            continue
        name_clean = name_lower.replace("_", "").replace(" ", "")
        for kw, key in SECTOR_MAP.items():
            kw_clean = kw.replace("_", "").replace(" ", "")
            if kw_clean in name_clean or name_clean in kw_clean:
                sector_keys.add(key)
                break

    if not sector_keys:
        sector_keys = {"semiconductor"}

    result = []
    for key in sector_keys:
        stocks = SECTOR_STOCKS.get(key, [])
        for s in stocks[:max_per_sector]:
            result.append({**s, "sector_key": key})

    return result


def get_all_sector_keys() -> list:
    return list(SECTOR_STOCKS.keys())


def get_all_codes() -> list:
    codes = []
    for stocks in SECTOR_STOCKS.values():
        codes.extend(s["code"] for s in stocks)
    return list(set(codes))
