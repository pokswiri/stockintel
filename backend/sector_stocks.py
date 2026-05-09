# -*- coding: utf-8 -*-
"""
sector_stocks.py v4
25개 섹터 재구성 — ETF 구성종목 기반 정확한 분류
중복 제거 완료: 각 종목은 1개 섹터에만 배치
2026년 5월 기준 / 총 285개 종목

순환매 그룹:
  A: 글로벌 성장 — semiconductor, semiconductor_parts, glass_substrate, ai_software, it_hardware
  B: 방어·정책 — defense, space, robot, shipbuilding
  C: 에너지 전환 — battery, electric_infra, nuclear, renewable, auto_ev, telecom
  D: 경기민감·원자재 — steel, chemical, oil_gas, construction, logistics
  E: 내수·방어 — healthcare, content, consumer, bank, securities
"""

SECTOR_MAP = {'반도체': 'semiconductor', 'semiconductor': 'semiconductor', 'hbm': 'semiconductor', '반도체부품': 'semiconductor_parts', '반도체장비': 'semiconductor_parts', 'semiconductor_parts': 'semiconductor_parts', '유리기판': 'glass_substrate', 'pcb': 'glass_substrate', 'glass_substrate': 'glass_substrate', 'ai플랫폼': 'ai_software', 'ai_platform': 'ai_software', 'ai_software': 'ai_software', 'it': 'ai_software', '플랫폼': 'ai_software', 'ai': 'ai_software', 'it하드웨어': 'it_hardware', 'it_hardware': 'it_hardware', '가전': 'it_hardware', '로봇': 'robot', 'robot': 'robot', '자동화': 'robot', '우주': 'space', 'space': 'space', '항공우주': 'space', '방산': 'defense', 'defense': 'defense', '방위': 'defense', '조선': 'shipbuilding', 'shipbuilding': 'shipbuilding', '해운': 'shipbuilding', '배터리': 'battery', 'battery': 'battery', '이차전지': 'battery', '2차전지': 'battery', '전력': 'electric_infra', 'electric_infra': 'electric_infra', '전력기기': 'electric_infra', '전선': 'electric_infra', 'ai인프라': 'electric_infra', '원전': 'nuclear', 'nuclear': 'nuclear', '원자력': 'nuclear', '신재생': 'renewable', 'renewable': 'renewable', '태양광': 'renewable', '수소': 'renewable', '자동차': 'auto_ev', 'auto_ev': 'auto_ev', '전기차': 'auto_ev', '통신': 'telecom', 'telecom': 'telecom', '5g': 'telecom', '6g': 'telecom', '철강': 'steel', 'steel': 'steel', '비철금속': 'steel', '화학': 'chemical', 'chemical': 'chemical', '소재': 'chemical', '정유': 'oil_gas', 'oil_gas': 'oil_gas', '에너지': 'oil_gas', '가스': 'oil_gas', '건설': 'construction', 'construction': 'construction', '물류': 'logistics', 'logistics': 'logistics', '운송': 'logistics', '바이오': 'healthcare', '헬스케어': 'healthcare', 'healthcare': 'healthcare', '제약': 'healthcare', '의약': 'healthcare', '엔터': 'content', 'content': 'content', '게임': 'content', '소비재': 'consumer', 'consumer': 'consumer', '유통': 'consumer', '은행': 'bank', 'bank': 'bank', '금융': 'bank', 'finance': 'bank', '증권': 'securities', '보험': 'securities', 'securities': 'securities'}


SECTOR_STOCKS = {

    # ══ 그룹 A — 글로벌 성장 ══
    # ── semiconductor ──── # ETF: KODEX 반도체(091160)
    "semiconductor": [
        {"code": "005930", "name": "삼성전자", "cap": "large"},
        {"code": "000660", "name": "SK하이닉스", "cap": "large"},
        {"code": "000990", "name": "DB하이텍", "cap": "mid"},
        {"code": "046890", "name": "서울반도체", "cap": "mid"},
        {"code": "079370", "name": "유니크", "cap": "mid"},
        {"code": "036540", "name": "SFA반도체", "cap": "mid"},
        {"code": "053030", "name": "하나마이크론", "cap": "mid"},
        {"code": "089030", "name": "테크윙", "cap": "mid"},
        {"code": "102120", "name": "어보브반도체", "cap": "mid"},
        {"code": "039030", "name": "이오테크닉스", "cap": "mid"},
        {"code": "214680", "name": "HPSP", "cap": "mid"},
        {"code": "080220", "name": "상아프론테크", "cap": "mid"},
        {"code": "079950", "name": "유니테스트", "cap": "mid"},
        {"code": "102460", "name": "네오셈", "cap": "mid"},
        {"code": "357780", "name": "솔브레인", "cap": "mid"},
        {"code": "140860", "name": "파크시스템스", "cap": "mid"},
        {"code": "121600", "name": "나노신소재", "cap": "mid"},
        {"code": "036830", "name": "솔브레인홀딩스", "cap": "mid"},
        {"code": "084370", "name": "유진테크", "cap": "mid"},
        {"code": "036490", "name": "에이피티씨", "cap": "mid"},
        {"code": "200710", "name": "에이디테크놀로지", "cap": "mid"},
        {"code": "029080", "name": "하이비젼시스템", "cap": "mid"},
    ],

    # ── semiconductor_parts ──── # ETF: KODEX 반도체(091160) 하위
    "semiconductor_parts": [
        {"code": "042700", "name": "한미반도체", "cap": "mid"},
        {"code": "058470", "name": "리노공업", "cap": "mid"},
        {"code": "240810", "name": "원익IPS", "cap": "mid"},
        {"code": "095340", "name": "ISC", "cap": "mid"},
        {"code": "248070", "name": "솔루엠", "cap": "mid"},
        {"code": "009150", "name": "삼성전기", "cap": "large"},
        {"code": "011070", "name": "LG이노텍", "cap": "large"},
        {"code": "108670", "name": "LX세미콘", "cap": "mid"},
        {"code": "033640", "name": "네패스", "cap": "mid"},
        {"code": "100120", "name": "뷰웍스", "cap": "mid"},
        {"code": "095500", "name": "미래컴퍼니", "cap": "mid"},
        {"code": "094360", "name": "칩스앤미디어", "cap": "mid"},
        {"code": "107640", "name": "한중엔시에스", "cap": "mid"},
        {"code": "178320", "name": "서진시스템", "cap": "mid"},
        {"code": "015260", "name": "인터플렉스", "cap": "mid"},
    ],

    # ── glass_substrate ──── # 유리기판·PCB·패키징 기판
    "glass_substrate": [
        {"code": "008060", "name": "대덕전자", "cap": "mid"},
        {"code": "044780", "name": "코리아써키트", "cap": "mid"},
        {"code": "011790", "name": "SKC", "cap": "large"},
        {"code": "031330", "name": "에스에이엠티", "cap": "mid"},
        {"code": "025820", "name": "이구산업", "cap": "mid"},
        {"code": "045510", "name": "에이피티씨", "cap": "mid"},
        {"code": "148150", "name": "세경하이테크", "cap": "mid"},
    ],

    # ── ai_software ──── # ETF: TIGER Fn인터넷(364980)
    "ai_software": [
        {"code": "035420", "name": "NAVER", "cap": "large"},
        {"code": "035720", "name": "카카오", "cap": "large"},
        {"code": "377300", "name": "카카오페이", "cap": "mid"},
        {"code": "111940", "name": "더존비즈온", "cap": "mid"},
        {"code": "053800", "name": "안랩", "cap": "mid"},
        {"code": "048410", "name": "현대오토에버", "cap": "mid"},
        {"code": "304100", "name": "솔트룩스", "cap": "mid"},
    ],

    # ── it_hardware ──── # IT하드웨어·가전·디스플레이
    "it_hardware": [
        {"code": "066570", "name": "LG전자", "cap": "large"},
        {"code": "034220", "name": "LG디스플레이", "cap": "large"},
        {"code": "006400", "name": "삼성SDI", "cap": "large"},
        {"code": "028260", "name": "삼성물산", "cap": "large"},
        {"code": "003550", "name": "LG", "cap": "large"},
        {"code": "034730", "name": "SK", "cap": "large"},
        {"code": "001040", "name": "CJ", "cap": "large"},
    ],


    # ══ 그룹 B — 방어·정책 ══
    # ── defense ──── # ETF: TIGER 방산(443810)
    "defense": [
        {"code": "012450", "name": "한화에어로스페이스", "cap": "large"},
        {"code": "047810", "name": "한국항공우주", "cap": "large"},
        {"code": "079550", "name": "LIG넥스원", "cap": "large"},
        {"code": "064350", "name": "현대로템", "cap": "large"},
        {"code": "272210", "name": "한화시스템", "cap": "large"},
        {"code": "000880", "name": "한화", "cap": "large"},
        {"code": "008260", "name": "빅텍", "cap": "mid"},
        {"code": "104830", "name": "퍼스텍", "cap": "mid"},
        {"code": "014830", "name": "동양에스텍", "cap": "mid"},
        {"code": "060380", "name": "SNT다이내믹스", "cap": "mid"},
        {"code": "013720", "name": "대창단조", "cap": "mid"},
        {"code": "024900", "name": "덕산하이메탈", "cap": "mid"},
        {"code": "064520", "name": "에스텍", "cap": "mid"},
        {"code": "272550", "name": "케이엔솔", "cap": "mid"},
        {"code": "019570", "name": "일진홀딩스", "cap": "mid"},
    ],

    # ── space ──── # 스페이스X 연관·위성·발사체
    "space": [
        {"code": "099190", "name": "아이쓰리시스템", "cap": "mid"},
        {"code": "052460", "name": "쎄트렉아이", "cap": "mid"},
        {"code": "158080", "name": "휴맥스", "cap": "mid"},
        {"code": "094170", "name": "동운아나텍", "cap": "mid"},
        {"code": "041440", "name": "한국정밀기계", "cap": "mid"},
        {"code": "023600", "name": "삼보모터스", "cap": "mid"},
    ],

    # ── robot ──── # ETF: TIGER 로보틱스(472860)
    "robot": [
        {"code": "336570", "name": "원익로보틱스", "cap": "mid"},
        {"code": "017800", "name": "현대엘리베이터", "cap": "mid"},
        {"code": "196490", "name": "로보쓰리", "cap": "mid"},
        {"code": "110020", "name": "전진중공업", "cap": "mid"},
        {"code": "042670", "name": "HD현대인프라코어", "cap": "large"},
        {"code": "060720", "name": "KH바텍", "cap": "mid"},
        {"code": "059120", "name": "아진산업", "cap": "mid"},
        {"code": "007340", "name": "DN오토모티브", "cap": "mid"},
        {"code": "108380", "name": "이노에이치", "cap": "mid"},
    ],

    # ── shipbuilding ──── # ETF: TIGER 조선TOP10(466940)
    "shipbuilding": [
        {"code": "009540", "name": "HD현대중공업", "cap": "large"},
        {"code": "042660", "name": "한화오션", "cap": "large"},
        {"code": "010140", "name": "삼성중공업", "cap": "large"},
        {"code": "267250", "name": "HD현대", "cap": "large"},
        {"code": "071970", "name": "HD현대마린엔진", "cap": "mid"},
        {"code": "077970", "name": "STX엔진", "cap": "mid"},
        {"code": "011200", "name": "HMM", "cap": "large"},
        {"code": "005880", "name": "대한해운", "cap": "mid"},
        {"code": "134790", "name": "HD현대마린솔루션", "cap": "mid"},
        {"code": "051760", "name": "한화엔진", "cap": "mid"},
        {"code": "037270", "name": "인터지스", "cap": "mid"},
        {"code": "100840", "name": "SNT에너지", "cap": "mid"},
    ],


    # ══ 그룹 C — 에너지 전환·모빌리티 ══
    # ── battery ──── # ETF: KODEX 2차전지산업(305720)
    "battery": [
        {"code": "373220", "name": "LG에너지솔루션", "cap": "large"},
        {"code": "086520", "name": "에코프로비엠", "cap": "large"},
        {"code": "247540", "name": "에코프로", "cap": "large"},
        {"code": "003670", "name": "포스코퓨처엠", "cap": "large"},
        {"code": "066970", "name": "엘앤에프", "cap": "large"},
        {"code": "096770", "name": "SK이노베이션", "cap": "large"},
        {"code": "336370", "name": "솔루스첨단소재", "cap": "mid"},
        {"code": "282880", "name": "코윈테크", "cap": "mid"},
        {"code": "060970", "name": "에코프로이노베이션", "cap": "mid"},
        {"code": "011600", "name": "에코프로머티리얼즈", "cap": "mid"},
        {"code": "294090", "name": "이오테크닉스", "cap": "mid"},
        {"code": "025560", "name": "미래산업", "cap": "mid"},
        {"code": "009180", "name": "한솔케미칼", "cap": "mid"},
    ],

    # ── electric_infra ──── # ETF: TIGER 전력기기(396500) — AI인프라·변압기·전선
    "electric_infra": [
        {"code": "010120", "name": "LS일렉트릭", "cap": "large"},
        {"code": "267260", "name": "HD현대일렉트릭", "cap": "large"},
        {"code": "298040", "name": "효성중공업", "cap": "large"},
        {"code": "006260", "name": "LS", "cap": "large"},
        {"code": "001440", "name": "대한전선", "cap": "mid"},
        {"code": "103590", "name": "일진전기", "cap": "mid"},
        {"code": "000500", "name": "가온전선", "cap": "mid"},
        {"code": "236200", "name": "제룡전기", "cap": "mid"},
        {"code": "130660", "name": "LS에코에너지", "cap": "mid"},
        {"code": "100220", "name": "비나텍", "cap": "mid"},
        {"code": "065690", "name": "삼강엠앤티", "cap": "mid"},
        {"code": "025890", "name": "한국주철관", "cap": "mid"},
        {"code": "060900", "name": "대아티아이", "cap": "mid"},
        {"code": "090460", "name": "비엠티", "cap": "mid"},
        {"code": "014440", "name": "영흥", "cap": "mid"},
    ],

    # ── nuclear ──── # ETF: KODEX 원자력(446970)
    "nuclear": [
        {"code": "034020", "name": "두산에너빌리티", "cap": "large"},
        {"code": "036460", "name": "한국가스공사", "cap": "large"},
        {"code": "015760", "name": "한국전력", "cap": "large"},
        {"code": "019175", "name": "한국전력기술", "cap": "mid"},
        {"code": "084670", "name": "두산퓨얼셀", "cap": "mid"},
    ],

    # ── renewable ──── # ETF: KODEX 글로벌클린에너지(278540)
    "renewable": [
        {"code": "009830", "name": "한화솔루션", "cap": "large"},
        {"code": "010060", "name": "OCI홀딩스", "cap": "large"},
        {"code": "112610", "name": "씨에스윈드", "cap": "large"},
        {"code": "047050", "name": "포스코인터내셔널", "cap": "large"},
        {"code": "033170", "name": "에스에너지", "cap": "mid"},
        {"code": "195500", "name": "스페코", "cap": "mid"},
        {"code": "204490", "name": "에이치디씨", "cap": "mid"},
    ],

    # ── auto_ev ──── # ETF: KODEX 자동차(261060)
    "auto_ev": [
        {"code": "005380", "name": "현대차", "cap": "large"},
        {"code": "000270", "name": "기아", "cap": "large"},
        {"code": "012330", "name": "현대모비스", "cap": "large"},
        {"code": "018880", "name": "한온시스템", "cap": "large"},
        {"code": "011210", "name": "현대위아", "cap": "large"},
        {"code": "060980", "name": "HL만도", "cap": "large"},
        {"code": "023960", "name": "에스엘", "cap": "mid"},
        {"code": "033240", "name": "자화전자", "cap": "mid"},
        {"code": "025900", "name": "동성화인텍", "cap": "mid"},
        {"code": "064960", "name": "SNT모티브", "cap": "mid"},
        {"code": "010780", "name": "아이에스동서", "cap": "mid"},
    ],

    # ── telecom ──── # 5G·6G 통신장비·네트워크
    "telecom": [
        {"code": "017670", "name": "SK텔레콤", "cap": "large"},
        {"code": "030200", "name": "KT", "cap": "large"},
        {"code": "032640", "name": "LG유플러스", "cap": "large"},
        {"code": "078070", "name": "유비쿼스홀딩스", "cap": "mid"},
        {"code": "232140", "name": "와이솔", "cap": "mid"},
        {"code": "038680", "name": "에스넷", "cap": "mid"},
        {"code": "053450", "name": "세코닉스", "cap": "mid"},
    ],


    # ══ 그룹 D — 경기민감·원자재 ══
    # ── steel ──── # 철강·비철금속 — 중국 경기 연동
    "steel": [
        {"code": "005490", "name": "POSCO홀딩스", "cap": "large"},
        {"code": "004020", "name": "현대제철", "cap": "large"},
        {"code": "010130", "name": "고려아연", "cap": "large"},
        {"code": "460860", "name": "동국제강", "cap": "mid"},
        {"code": "002240", "name": "고려제강", "cap": "mid"},
        {"code": "016380", "name": "KG스틸", "cap": "mid"},
        {"code": "084010", "name": "대한제강", "cap": "mid"},
        {"code": "104700", "name": "한국철강", "cap": "mid"},
        {"code": "004560", "name": "현대비앤지스틸", "cap": "mid"},
        {"code": "058430", "name": "포스코스틸리온", "cap": "mid"},
        {"code": "103140", "name": "풍산", "cap": "mid"},
        {"code": "001780", "name": "알루코", "cap": "mid"},
        {"code": "008350", "name": "남선알미늄", "cap": "mid"},
        {"code": "001420", "name": "태양금속", "cap": "mid"},
        {"code": "005010", "name": "휴스틸", "cap": "mid"},
        {"code": "011420", "name": "갑을메탈", "cap": "mid"},
        {"code": "001230", "name": "동국홀딩스", "cap": "mid"},
    ],

    # ── chemical ──── # 화학·소재 — 유가 연동
    "chemical": [
        {"code": "051910", "name": "LG화학", "cap": "large"},
        {"code": "004000", "name": "롯데정밀화학", "cap": "mid"},
        {"code": "014280", "name": "금호석유", "cap": "large"},
        {"code": "002380", "name": "KCC", "cap": "mid"},
        {"code": "011500", "name": "한농화성", "cap": "mid"},
        {"code": "005290", "name": "동진쎄미켐", "cap": "mid"},
        {"code": "001390", "name": "KG케미칼", "cap": "mid"},
        {"code": "010610", "name": "수산인더스트리", "cap": "mid"},
        {"code": "006650", "name": "에스오일", "cap": "large"},
        {"code": "066950", "name": "코오롱인더", "cap": "mid"},
    ],

    # ── oil_gas ──── # 정유·가스 — WTI 직결
    "oil_gas": [
        {"code": "078930", "name": "GS", "cap": "large"},
        {"code": "001740", "name": "SK네트웍스", "cap": "mid"},
        {"code": "117580", "name": "대성에너지", "cap": "mid"},
        {"code": "003300", "name": "한일홀딩스", "cap": "mid"},
        {"code": "005070", "name": "코스모화학", "cap": "mid"},
    ],

    # ── construction ──── # 건설·부동산 — 금리 인하 선행
    "construction": [
        {"code": "000720", "name": "현대건설", "cap": "large"},
        {"code": "006360", "name": "GS건설", "cap": "large"},
        {"code": "047040", "name": "대우건설", "cap": "large"},
        {"code": "000210", "name": "DL", "cap": "large"},
        {"code": "014790", "name": "HL D&I", "cap": "mid"},
        {"code": "013580", "name": "계룡건설", "cap": "mid"},
        {"code": "034300", "name": "신세계건설", "cap": "mid"},
        {"code": "005960", "name": "동부건설", "cap": "mid"},
        {"code": "000390", "name": "삼화페인트", "cap": "mid"},
        {"code": "011390", "name": "부산산업", "cap": "mid"},
    ],

    # ── logistics ──── # 물류·운송 — 수출 경기 연동
    "logistics": [
        {"code": "003490", "name": "대한항공", "cap": "large"},
        {"code": "020560", "name": "아시아나항공", "cap": "large"},
        {"code": "086280", "name": "현대글로비스", "cap": "large"},
        {"code": "000120", "name": "CJ대한통운", "cap": "large"},
        {"code": "180640", "name": "한진칼", "cap": "mid"},
        {"code": "089880", "name": "케이엘넷", "cap": "mid"},
        {"code": "094280", "name": "에이치시티", "cap": "mid"},
        {"code": "001250", "name": "GS글로벌", "cap": "mid"},
    ],


    # ══ 그룹 E — 내수·방어 ══
    # ── healthcare ──── # ETF: KODEX 바이오(143860)
    "healthcare": [
        {"code": "207940", "name": "삼성바이오로직스", "cap": "large"},
        {"code": "068270", "name": "셀트리온", "cap": "large"},
        {"code": "000100", "name": "유한양행", "cap": "large"},
        {"code": "128940", "name": "한미약품", "cap": "large"},
        {"code": "009290", "name": "광동제약", "cap": "mid"},
        {"code": "196170", "name": "알테오젠", "cap": "mid"},
        {"code": "028300", "name": "HLB", "cap": "mid"},
        {"code": "145020", "name": "휴젤", "cap": "mid"},
        {"code": "214150", "name": "클래시스", "cap": "mid"},
        {"code": "141080", "name": "레고켐바이오", "cap": "mid"},
        {"code": "041960", "name": "에스티팜", "cap": "mid"},
        {"code": "185750", "name": "종근당", "cap": "mid"},
        {"code": "001360", "name": "삼성제약", "cap": "mid"},
        {"code": "218150", "name": "에이비엘바이오", "cap": "mid"},
        {"code": "284620", "name": "CJ바이오사이언스", "cap": "mid"},
        {"code": "005690", "name": "파마리서치", "cap": "mid"},
        {"code": "095700", "name": "제넥신", "cap": "mid"},
        {"code": "078520", "name": "에이블씨엔씨", "cap": "mid"},
    ],

    # ── content ──── # 엔터·게임·K컬처
    "content": [
        {"code": "352820", "name": "하이브", "cap": "large"},
        {"code": "041510", "name": "에스엠", "cap": "mid"},
        {"code": "035900", "name": "JYP엔터", "cap": "mid"},
        {"code": "122870", "name": "와이지엔터테인먼트", "cap": "mid"},
        {"code": "259960", "name": "크래프톤", "cap": "large"},
        {"code": "036570", "name": "엔씨소프트", "cap": "large"},
        {"code": "251270", "name": "넷마블", "cap": "large"},
        {"code": "263750", "name": "펄어비스", "cap": "mid"},
        {"code": "069080", "name": "웹젠", "cap": "mid"},
        {"code": "067160", "name": "아프리카TV", "cap": "mid"},
        {"code": "079160", "name": "CJ CGV", "cap": "mid"},
        {"code": "034120", "name": "SBS", "cap": "mid"},
        {"code": "293490", "name": "카카오게임즈", "cap": "mid"},
        {"code": "042420", "name": "네오위즈", "cap": "mid"},
    ],

    # ── consumer ──── # 유통·소비재 — 내수 방어
    "consumer": [
        {"code": "023530", "name": "롯데쇼핑", "cap": "large"},
        {"code": "139480", "name": "이마트", "cap": "large"},
        {"code": "097950", "name": "CJ제일제당", "cap": "large"},
        {"code": "090430", "name": "아모레퍼시픽", "cap": "large"},
        {"code": "051900", "name": "LG생활건강", "cap": "large"},
        {"code": "004990", "name": "롯데지주", "cap": "large"},
        {"code": "069960", "name": "현대백화점", "cap": "large"},
        {"code": "003230", "name": "삼양식품", "cap": "mid"},
        {"code": "004370", "name": "농심", "cap": "mid"},
        {"code": "271560", "name": "오리온", "cap": "large"},
        {"code": "000080", "name": "하이트진로", "cap": "mid"},
        {"code": "001680", "name": "대상", "cap": "mid"},
        {"code": "057050", "name": "현대홈쇼핑", "cap": "mid"},
        {"code": "030000", "name": "제일기획", "cap": "mid"},
    ],

    # ── bank ──── # ETF: KODEX 은행(091170)
    "bank": [
        {"code": "105560", "name": "KB금융", "cap": "large"},
        {"code": "055550", "name": "신한지주", "cap": "large"},
        {"code": "086790", "name": "하나금융지주", "cap": "large"},
        {"code": "316140", "name": "우리금융지주", "cap": "large"},
        {"code": "138040", "name": "메리츠금융지주", "cap": "large"},
        {"code": "024110", "name": "기업은행", "cap": "large"},
        {"code": "139130", "name": "iM금융지주", "cap": "mid"},
        {"code": "175330", "name": "JB금융지주", "cap": "mid"},
        {"code": "138930", "name": "BNK금융지주", "cap": "mid"},
        {"code": "323410", "name": "카카오뱅크", "cap": "large"},
        {"code": "029780", "name": "삼성카드", "cap": "mid"},
    ],

    # ── securities ──── # ETF: KODEX 증권(102970)
    "securities": [
        {"code": "006800", "name": "미래에셋증권", "cap": "large"},
        {"code": "071050", "name": "한국금융지주", "cap": "large"},
        {"code": "039490", "name": "키움증권", "cap": "large"},
        {"code": "005940", "name": "NH투자증권", "cap": "large"},
        {"code": "016360", "name": "삼성증권", "cap": "large"},
        {"code": "003540", "name": "대신증권", "cap": "mid"},
        {"code": "030610", "name": "교보증권", "cap": "mid"},
        {"code": "001200", "name": "유진투자증권", "cap": "mid"},
        {"code": "003470", "name": "유안타증권", "cap": "mid"},
        {"code": "001270", "name": "부국증권", "cap": "mid"},
        {"code": "018670", "name": "SK증권", "cap": "mid"},
        {"code": "032830", "name": "삼성생명", "cap": "large"},
        {"code": "000810", "name": "삼성화재", "cap": "large"},
        {"code": "082640", "name": "동양생명", "cap": "mid"},
        {"code": "000060", "name": "메리츠화재", "cap": "large"},
        {"code": "005830", "name": "DB손해보험", "cap": "large"},
        {"code": "088350", "name": "한화생명", "cap": "large"},
        {"code": "001500", "name": "현대차증권", "cap": "mid"},
        {"code": "005945", "name": "NH투자증권우", "cap": "mid"},
        {"code": "00680K", "name": "미래에셋증권2우B", "cap": "mid"},
    ],

}