# -*- coding: utf-8 -*-
"""
sector_stocks.py v3
섹터별 시총 상위 종목 목록 — 섹터당 최대 30개
기준: 코스피+코스닥 시총 상위, 업종 대표성, 2026년 4월 기준 검증

역할:
  1. KIS API 실패 시 폴백 (주 역할)
  2. AI 섹터 선정 후 KIS API 결과 보완 (보조 역할)
  → 섹터당 30개로 확대해 NEXUS 산식 커버리지 확보
"""

SECTOR_MAP = {
    "반도체": "semiconductor", "semiconductor": "semiconductor", "hbm": "semiconductor",
    "방산": "defense", "defense": "defense", "방위": "defense", "무기": "defense",
    "ai플랫폼": "ai_platform", "ai_platform": "ai_platform", "it": "ai_platform",
    "플랫폼": "ai_platform", "ai": "ai_platform", "technology": "ai_platform",
    "배터리": "battery", "battery": "battery", "이차전지": "battery", "2차전지": "battery",
    "자동차": "auto_ev", "auto_ev": "auto_ev", "automotive": "auto_ev", "전기차": "auto_ev",
    "신재생": "renewable", "renewable": "renewable", "재생에너지": "renewable",
    "태양광": "renewable", "원전": "renewable", "수소": "renewable",
    "바이오": "healthcare", "헬스케어": "healthcare", "healthcare": "healthcare",
    "제약": "healthcare", "의약": "healthcare",
    "금융": "finance", "finance": "finance", "은행": "finance", "보험": "finance",
    "철강": "steel", "소재": "steel", "steel": "steel", "조선": "shipbuilding",
    "shipbuilding": "shipbuilding", "중공업": "shipbuilding",
}

SECTOR_STOCKS = {

    # ── 반도체 ─────────────────────────────────────────────────────
    # 코스피: 삼성전자·SK하이닉스 대형주 + 장비·소재 중견주
    # 코스닥: HBM 핵심 부품·장비·소켓 종목
    "semiconductor": [
        # 대형 (코스피)
        {"code": "005930", "name": "삼성전자",     "cap": "large"},
        {"code": "000660", "name": "SK하이닉스",   "cap": "large"},
        {"code": "009150", "name": "삼성전기",     "cap": "large"},  # MLCC·기판
        {"code": "006400", "name": "삼성SDI",      "cap": "large"},  # 반도체패키징 소재
        # 중견 (코스피)
        {"code": "011790", "name": "SKC",          "cap": "mid"},    # 동박·반도체소재
        {"code": "036830", "name": "솔브레인",     "cap": "mid"},    # HF·식각액
        {"code": "336370", "name": "솔루스첨단소재","cap": "mid"},   # 동박·전자소재
        {"code": "047050", "name": "포스코인터내셔널","cap": "mid"}, # 반도체소재
        # 장비·부품 (코스닥)
        {"code": "042700", "name": "한미반도체",   "cap": "mid"},    # HBM 핵심장비
        {"code": "240810", "name": "원익IPS",      "cap": "mid"},    # CVD 장비
        {"code": "058470", "name": "리노공업",     "cap": "mid"},    # 소켓·테스트
        {"code": "089030", "name": "테크윙",       "cap": "mid"},    # HBM핸들러
        {"code": "290660", "name": "SFA반도체",    "cap": "mid"},    # 패키징
        {"code": "095340", "name": "ISC",          "cap": "mid"},    # 소켓
        {"code": "140860", "name": "파크시스템스", "cap": "mid"},    # AFM장비
        {"code": "078070", "name": "에이엔피",     "cap": "mid"},    # 반도체장비부품
        {"code": "103590", "name": "일진전기",     "cap": "mid"},    # 전력기기
        {"code": "086390", "name": "유니테스트",   "cap": "mid"},    # 반도체테스트
        {"code": "033290", "name": "HPSP",         "cap": "mid"},    # 고압수소어닐링
        {"code": "089980", "name": "상아프론테크", "cap": "mid"},    # 반도체소재
        {"code": "039030", "name": "이오테크닉스", "cap": "mid"},    # 레이저장비
        {"code": "036490", "name": "에이피티씨",   "cap": "mid"},    # 반도체세정
        {"code": "029480", "name": "세진중공업",   "cap": "mid"},    # 반도체부품
        {"code": "092600", "name": "나노신소재",   "cap": "mid"},    # 반도체소재
        {"code": "005290", "name": "동진쎄미켐",   "cap": "mid"},    # 감광액·소재
        {"code": "253590", "name": "네오셈",       "cap": "mid"},    # 반도체테스트
        {"code": "102120", "name": "어보브반도체", "cap": "mid"},    # 팹리스
        {"code": "067310", "name": "하나마이크론", "cap": "mid"},    # 반도체패키징
        {"code": "353200", "name": "대덕전자",     "cap": "mid"},    # PCB
    ],

    # ── 방산 ───────────────────────────────────────────────────────
    "defense": [
        # 대형 (코스피)
        {"code": "012450", "name": "한화에어로스페이스","cap": "large"},
        {"code": "047810", "name": "한국항공우주", "cap": "large"},
        {"code": "000880", "name": "한화",         "cap": "large"},
        {"code": "064350", "name": "현대로템",     "cap": "mid"},
        {"code": "009540", "name": "HD현대중공업", "cap": "large"},  # 방산+조선
        {"code": "042660", "name": "한화오션",     "cap": "large"},  # 방산함정
        # 중견 (코스피)
        {"code": "079550", "name": "LIG넥스원",   "cap": "mid"},
        {"code": "272210", "name": "한화시스템",   "cap": "mid"},
        {"code": "077970", "name": "STX엔진",      "cap": "mid"},
        {"code": "071970", "name": "HD현대마린엔진","cap": "mid"},
        {"code": "267250", "name": "HD현대",       "cap": "large"},  # HD그룹 지주
        {"code": "329180", "name": "HD현대중공업", "cap": "large"},
        # 중견 (코스닥)
        {"code": "065450", "name": "빅텍",         "cap": "mid"},
        {"code": "014190", "name": "한국화인케미칼","cap": "mid"},   # 화약·방산
        {"code": "047560", "name": "퍼스텍",       "cap": "mid"},    # 항공부품
        {"code": "082600", "name": "동양에스텍",   "cap": "mid"},    # 방산전자
        {"code": "011210", "name": "현대위아",     "cap": "mid"},    # 자주포·엔진
        {"code": "012800", "name": "대창단조",     "cap": "mid"},    # 방산부품
        {"code": "003570", "name": "SNT다이내믹스","cap": "mid"},    # 파워팩·구동
        {"code": "073190", "name": "듀산테스나",   "cap": "mid"},    # 방산반도체
        {"code": "024900", "name": "덕산하이메탈", "cap": "mid"},    # 방산소재
        {"code": "071840", "name": "하이록코리아", "cap": "mid"},    # 방산배관
        {"code": "002990", "name": "금호건설",     "cap": "mid"},    # 방산시설
        {"code": "016740", "name": "두산",         "cap": "mid"},    # 방산지주
        {"code": "034020", "name": "두산에너빌리티","cap": "large"}, # 원전·방산
        {"code": "008355", "name": "한화솔루션우", "cap": "mid"},    # 방산화학
    ],

    # ── AI·플랫폼 ──────────────────────────────────────────────────
    "ai_platform": [
        # 대형 (코스피)
        {"code": "035420", "name": "NAVER",        "cap": "large"},
        {"code": "035720", "name": "카카오",       "cap": "large"},
        {"code": "259960", "name": "크래프톤",     "cap": "mid"},
        {"code": "012510", "name": "더존비즈온",   "cap": "mid"},
        {"code": "034220", "name": "LG디스플레이", "cap": "large"},  # AI디스플레이
        # 중견·소형 (코스피+코스닥)
        {"code": "067160", "name": "아프리카TV",   "cap": "mid"},
        {"code": "377300", "name": "카카오페이",   "cap": "mid"},
        {"code": "293490", "name": "카카오게임즈", "cap": "mid"},
        {"code": "263750", "name": "펄어비스",     "cap": "mid"},
        {"code": "251270", "name": "넷마블",       "cap": "mid"},
        {"code": "036570", "name": "엔씨소프트",   "cap": "mid"},
        {"code": "078340", "name": "컴투스",       "cap": "mid"},
        {"code": "054620", "name": "AhnLab",       "cap": "mid"},    # AI보안
        {"code": "079290", "name": "이노션",       "cap": "mid"},    # AI광고
        {"code": "035600", "name": "KG이니시스",   "cap": "mid"},    # 핀테크
        {"code": "053800", "name": "안랩",         "cap": "mid"},    # AI보안
        {"code": "119860", "name": "아이티엠반도체","cap": "mid"},   # AI반도체
        {"code": "214150", "name": "클래시스",     "cap": "mid"},    # AI의료기기
        {"code": "357780", "name": "솔브레인홀딩스","cap": "mid"},   # IT지주
        {"code": "122990", "name": "와이솔",       "cap": "mid"},    # AI통신부품
        {"code": "307950", "name": "현대오토에버", "cap": "mid"},    # AI자동차SW
        {"code": "053450", "name": "오스템임플란트","cap": "mid"},   # AI치과
        {"code": "041510", "name": "에스엠",       "cap": "mid"},    # AI엔터
        {"code": "035900", "name": "JYP엔터",      "cap": "mid"},    # AI콘텐츠
        {"code": "122870", "name": "와이지엔터테인먼트","cap": "mid"},
    ],

    # ── 배터리·이차전지 ────────────────────────────────────────────
    "battery": [
        # 대형 (코스피)
        {"code": "373220", "name": "LG에너지솔루션","cap": "large"},
        {"code": "006400", "name": "삼성SDI",      "cap": "large"},
        {"code": "051910", "name": "LG화학",       "cap": "large"},
        {"code": "003670", "name": "포스코퓨처엠", "cap": "mid"},
        {"code": "005490", "name": "POSCO홀딩스",  "cap": "large"},  # 양극재소재
        {"code": "011790", "name": "SKC",          "cap": "mid"},    # 동박
        # 중견 (코스닥)
        {"code": "247540", "name": "에코프로비엠", "cap": "mid"},
        {"code": "066970", "name": "엘앤에프",     "cap": "mid"},
        {"code": "086520", "name": "에코프로",     "cap": "mid"},
        {"code": "278280", "name": "천보",         "cap": "mid"},    # 전해질
        {"code": "336370", "name": "솔루스첨단소재","cap": "mid"},   # 동박
        {"code": "048260", "name": "오스코텍",     "cap": "mid"},    # 배터리소재
        {"code": "198080", "name": "에코프로이노베이션","cap": "mid"},
        {"code": "383310", "name": "에코프로머티리얼즈","cap": "mid"},
        {"code": "020150", "name": "롯데에너지머티리얼즈","cap": "mid"}, # 동박
        {"code": "298040", "name": "효성중공업",   "cap": "mid"},    # ESS
        {"code": "012400", "name": "한화갤러리아타임월드","cap": "mid"},
        {"code": "036490", "name": "에이피티씨",   "cap": "mid"},    # 배터리장비
        {"code": "007810", "name": "코리아써키트", "cap": "mid"},    # 배터리PCB
        {"code": "340570", "name": "수산인더스트리","cap": "mid"},   # 배터리장비
        {"code": "042670", "name": "HD현대인프라코어","cap": "mid"}, # 배터리장비
        {"code": "025560", "name": "미래산업",     "cap": "mid"},    # 배터리장비
        {"code": "011070", "name": "LG이노텍",     "cap": "mid"},    # 배터리부품
        {"code": "009830", "name": "한화솔루션",   "cap": "large"},  # ESS·배터리
        {"code": "121600", "name": "나노신소재",   "cap": "mid"},    # CNT도전재
        {"code": "294870", "name": "HDC현대산업개발","cap": "mid"},
        {"code": "306200", "name": "세아베스틸지주","cap": "mid"},   # 배터리소재
        {"code": "001430", "name": "세아베스틸지주","cap": "mid"},
        {"code": "267260", "name": "HD현대일렉트릭","cap": "mid"},   # ESS
    ],

    # ── 자동차·전기차 ──────────────────────────────────────────────
    "auto_ev": [
        # 대형 (코스피)
        {"code": "005380", "name": "현대차",       "cap": "large"},
        {"code": "000270", "name": "기아",         "cap": "large"},
        {"code": "012330", "name": "현대모비스",   "cap": "large"},
        {"code": "018880", "name": "한온시스템",   "cap": "mid"},
        {"code": "011210", "name": "현대위아",     "cap": "mid"},
        {"code": "204320", "name": "HL만도",       "cap": "mid"},
        {"code": "007340", "name": "DN오토모티브", "cap": "mid"},    # 사명변경
        {"code": "006260", "name": "LS",           "cap": "mid"},    # 전선·자동차
        # 중견 (코스피+코스닥)
        {"code": "003620", "name": "쌍용C&E",      "cap": "mid"},
        {"code": "023810", "name": "인팩",         "cap": "mid"},    # 자동차부품
        {"code": "025540", "name": "현대비앤지스틸","cap": "mid"},   # 자동차강판
        {"code": "002210", "name": "동성화인텍",   "cap": "mid"},    # 자동차단열
        {"code": "005850", "name": "에스엘",       "cap": "mid"},    # 자동차램프
        {"code": "033240", "name": "자화전자",     "cap": "mid"},    # EV부품
        {"code": "014680", "name": "한솔케미칼",   "cap": "mid"},    # 자동차소재
        {"code": "009540", "name": "HD현대중공업", "cap": "large"},
    ],

    # ── 신재생에너지·전력인프라 ────────────────────────────────────
    "renewable": [
        # 대형 (코스피)
        {"code": "009830", "name": "한화솔루션",   "cap": "large"},
        {"code": "010060", "name": "OCI홀딩스",    "cap": "mid"},
        {"code": "298040", "name": "효성중공업",   "cap": "mid"},
        {"code": "267260", "name": "HD현대일렉트릭","cap": "mid"},
        {"code": "010120", "name": "LS일렉트릭",   "cap": "mid"},
        {"code": "006260", "name": "LS",           "cap": "mid"},
        {"code": "034020", "name": "두산에너빌리티","cap": "large"},
        {"code": "336260", "name": "두산퓨얼셀",  "cap": "mid"},
        # 중견 (코스닥)
        {"code": "112610", "name": "씨에스윈드",   "cap": "mid"},
        {"code": "322000", "name": "HD현대에너지솔루션","cap": "mid"},
        {"code": "101530", "name": "한국전력기술", "cap": "mid"},    # 원전설계
        {"code": "001440", "name": "대한전선",     "cap": "mid"},    # 초전도케이블
        {"code": "018000", "name": "유니슨",       "cap": "mid"},    # 풍력
        {"code": "082640", "name": "동양이엔피",   "cap": "mid"},    # 태양광
        {"code": "006490", "name": "인스코비",     "cap": "mid"},    # 풍력부품
        {"code": "046310", "name": "백산",         "cap": "mid"},    # 태양광소재
        {"code": "003300", "name": "한일홀딩스",   "cap": "mid"},    # 신재생지주
        {"code": "013360", "name": "일진파워",     "cap": "mid"},    # 증기터빈
        {"code": "090350", "name": "노바텍",       "cap": "mid"},    # 원전부품
        {"code": "004490", "name": "세방전지",     "cap": "mid"},    # ESS배터리
        {"code": "047050", "name": "포스코인터내셔널","cap": "mid"},
    ],

    # ── 헬스케어·바이오 ────────────────────────────────────────────
    "healthcare": [
        # 대형 (코스피)
        {"code": "207940", "name": "삼성바이오로직스","cap": "large"},
        {"code": "068270", "name": "셀트리온",     "cap": "large"},
        {"code": "000100", "name": "유한양행",     "cap": "mid"},
        {"code": "128940", "name": "한미약품",     "cap": "mid"},
        {"code": "009420", "name": "한미사이언스", "cap": "mid"},
        {"code": "012670", "name": "여천NCC",      "cap": "mid"},
        # 중견 (코스닥)
        {"code": "196170", "name": "알테오젠",     "cap": "mid"},
        {"code": "028300", "name": "HLB",          "cap": "mid"},
        {"code": "145020", "name": "휴젤",         "cap": "mid"},
        {"code": "214150", "name": "클래시스",     "cap": "mid"},    # 의료기기
        {"code": "141080", "name": "레고켐바이오", "cap": "mid"},    # ADC
        {"code": "141170", "name": "리가켐바이오", "cap": "mid"},    # ADC
        {"code": "237690", "name": "에스티팜",     "cap": "mid"},    # CDMO
        {"code": "290740", "name": "케어젠",       "cap": "mid"},    # 펩타이드
        {"code": "298380", "name": "에이비엘바이오","cap": "mid"},   # 이중항체
        {"code": "226950", "name": "올릭스",       "cap": "mid"},    # RNAi치료제
        {"code": "241710", "name": "코오롱티슈진", "cap": "mid"},   # 세포유전자
        {"code": "214450", "name": "파마리서치",   "cap": "mid"},    # 히알루론산
        {"code": "106400", "name": "씨트리",       "cap": "mid"},    # 인체조직
        {"code": "185750", "name": "종근당",       "cap": "mid"},    # 제약
        {"code": "001360", "name": "삼성제약",     "cap": "mid"},
        {"code": "048530", "name": "오스코텍",     "cap": "mid"},    # 신약
        {"code": "011040", "name": "CJ바이오사이언스","cap": "mid"}, # 마이크로바이옴
        {"code": "950210", "name": "펩트론",       "cap": "mid"},    # 펩타이드신약
    ],

    # ── 금융 ───────────────────────────────────────────────────────
    "finance": [
        # 대형 (코스피)
        {"code": "105560", "name": "KB금융",       "cap": "large"},
        {"code": "055550", "name": "신한지주",     "cap": "large"},
        {"code": "086790", "name": "하나금융지주", "cap": "large"},
        {"code": "316140", "name": "우리금융지주", "cap": "large"},
        {"code": "138040", "name": "메리츠금융지주","cap": "mid"},
        {"code": "032830", "name": "삼성생명",     "cap": "large"},
        {"code": "000810", "name": "삼성화재",     "cap": "large"},
        {"code": "005830", "name": "DB손해보험",   "cap": "mid"},
        {"code": "088350", "name": "한화생명",     "cap": "mid"},
        {"code": "024110", "name": "기업은행",     "cap": "large"},
        # 중견
        {"code": "006800", "name": "미래에셋증권", "cap": "mid"},
        {"code": "071050", "name": "한국금융지주", "cap": "mid"},
        {"code": "003450", "name": "현대해상",     "cap": "mid"},
        {"code": "001450", "name": "현대해상화재보험","cap": "mid"},
        {"code": "005940", "name": "NH투자증권",   "cap": "mid"},
        {"code": "001720", "name": "신영증권",     "cap": "mid"},
        {"code": "016360", "name": "삼성증권",     "cap": "mid"},
        {"code": "078020", "name": "이베스트투자증권","cap": "mid"},
        {"code": "039490", "name": "키움증권",     "cap": "mid"},
        {"code": "003540", "name": "대신증권",     "cap": "mid"},
        {"code": "001500", "name": "현대차증권",   "cap": "mid"},
        {"code": "029780", "name": "삼성카드",     "cap": "mid"},
        {"code": "175330", "name": "JB금융지주",   "cap": "mid"},
        {"code": "138930", "name": "BNK금융지주",  "cap": "mid"},
        {"code": "279570", "name": "케이뱅크",     "cap": "mid"},
    ],

    # ── 철강·소재 ──────────────────────────────────────────────────
    "steel": [
        # 대형 (코스피)
        {"code": "005490", "name": "POSCO홀딩스",  "cap": "large"},
        {"code": "004020", "name": "현대제철",     "cap": "large"},
        {"code": "002140", "name": "고려아연",     "cap": "large"},
        {"code": "009150", "name": "삼성전기",     "cap": "large"},
        {"code": "047050", "name": "포스코인터내셔널","cap": "mid"},
        {"code": "001390", "name": "KG동국제강",   "cap": "mid"},
        {"code": "001430", "name": "세아베스틸지주","cap": "mid"},
        {"code": "004560", "name": "현대비앤지스틸","cap": "mid"},
        # 중견
        {"code": "006360", "name": "GS건설",       "cap": "mid"},
        {"code": "058430", "name": "포스코스틸리온", "cap": "mid"},    # 냉연강판
        {"code": "011500", "name": "한농화성",     "cap": "mid"},    # 화학소재
        {"code": "004000", "name": "롯데정밀화학", "cap": "mid"},    # 정밀화학
        {"code": "011790", "name": "SKC",          "cap": "mid"},    # 소재
        {"code": "014820", "name": "동원시스템즈", "cap": "mid"},    # 포장소재
        {"code": "002380", "name": "KCC",          "cap": "mid"},    # 소재
        {"code": "010060", "name": "OCI홀딩스",    "cap": "mid"},    # 화학소재
        {"code": "001070", "name": "대한방직",     "cap": "mid"},
        {"code": "011420", "name": "갑을메탈",     "cap": "mid"},    # 비철금속
        {"code": "010780", "name": "아이에스동서", "cap": "mid"},    # 환경소재
        {"code": "008350", "name": "남선알미늄",   "cap": "mid"},    # 알루미늄
        {"code": "005710", "name": "대주전자재료", "cap": "mid"},    # 전자소재
        {"code": "025560", "name": "미래산업",     "cap": "mid"},    # 특수소재
    ],

    # ── 조선·중공업 (신규 섹터) ────────────────────────────────────
    "shipbuilding": [
        {"code": "009540", "name": "HD현대중공업", "cap": "large"},
        {"code": "042660", "name": "한화오션",     "cap": "large"},
        {"code": "010140", "name": "삼성중공업",   "cap": "large"},
        {"code": "267250", "name": "HD현대",       "cap": "large"},
        {"code": "329180", "name": "HD현대중공업", "cap": "large"},
        {"code": "071970", "name": "HD현대마린엔진","cap": "mid"},
        {"code": "077970", "name": "STX엔진",      "cap": "mid"},
        {"code": "222870", "name": "HD현대마린솔루션","cap": "mid"},
        {"code": "405350", "name": "한화엔진",     "cap": "mid"},
        {"code": "075580", "name": "세진중공업",   "cap": "mid"},
        {"code": "011200", "name": "HMM",          "cap": "large"},  # 해운
        {"code": "005880", "name": "대한해운",     "cap": "mid"},    # 해운
        {"code": "028050", "name": "삼성E&A",      "cap": "mid"},    # EPC
        {"code": "047050", "name": "포스코인터내셔널","cap": "mid"},
        {"code": "006490", "name": "인스코비",     "cap": "mid"},
        {"code": "014190", "name": "한국화인케미칼","cap": "mid"},
        {"code": "016740", "name": "두산",         "cap": "mid"},
        {"code": "003570", "name": "SNT다이내믹스","cap": "mid"},
        {"code": "082260", "name": "HSD엔진",      "cap": "mid"},    # 선박엔진
        {"code": "034020", "name": "두산에너빌리티","cap": "large"},
        {"code": "267260", "name": "HD현대일렉트릭","cap": "mid"},
        {"code": "001440", "name": "대한전선",     "cap": "mid"},
        {"code": "103590", "name": "일진전기",     "cap": "mid"},
        {"code": "298040", "name": "효성중공업",   "cap": "mid"},
        {"code": "010120", "name": "LS일렉트릭",   "cap": "mid"},
        {"code": "023160", "name": "태광",         "cap": "mid"},    # 조선기자재
    ],
}

# SECTOR_MAP에 shipbuilding 추가
SECTOR_MAP["조선"] = "shipbuilding"
SECTOR_MAP["shipbuilding"] = "shipbuilding"
SECTOR_MAP["중공업"] = "shipbuilding"
SECTOR_MAP["해운"] = "shipbuilding"


def get_sector_stocks(sector_names: list, max_per_sector: int = 30) -> list:
    """섹터명 리스트 → 종목 리스트 반환 (중복 제거, 섹터당 max_per_sector개)"""
    sector_keys = set()
    for name in (sector_names or []):
        if not name:
            continue
        n = name.lower().strip()
        if n in SECTOR_MAP:
            sector_keys.add(SECTOR_MAP[n])
            continue
        if n in SECTOR_STOCKS:
            sector_keys.add(n)
            continue
        matched = False
        for kw, key in SECTOR_MAP.items():
            if kw in n or n in kw:
                sector_keys.add(key)
                matched = True
                break
        if matched:
            continue
        n_clean = n.replace("_", "").replace(" ", "")
        for kw, key in SECTOR_MAP.items():
            kw_clean = kw.replace("_", "").replace(" ", "")
            if kw_clean in n_clean or n_clean in kw_clean:
                sector_keys.add(key)
                break

    if not sector_keys:
        sector_keys = {"semiconductor"}

    seen = set()
    result = []
    for key in sector_keys:
        for s in SECTOR_STOCKS.get(key, [])[:max_per_sector]:
            if s["code"] not in seen:
                seen.add(s["code"])
                result.append({**s, "sector_key": key})
    return result


def get_all_sector_keys() -> list:
    return list(SECTOR_STOCKS.keys())


def get_all_codes() -> list:
    codes = []
    for stocks in SECTOR_STOCKS.values():
        codes.extend(s["code"] for s in stocks)
    return list(set(codes))
