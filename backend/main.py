import os, httpx, asyncio, json, re
from datetime import datetime
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="StockIntel API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ── 환경변수 ──────────────────────────────────────────────────────
GEMINI_KEY      = os.getenv("GEMINI_API_KEY", "")
GROQ_KEY        = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_KEY   = os.getenv("ANTHROPIC_API_KEY", "")   # 선택사항
GOOGLE_KEY      = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CX       = os.getenv("GOOGLE_CX", "")
NAVER_ID        = os.getenv("NAVER_CLIENT_ID", "")
NAVER_SECRET    = os.getenv("NAVER_CLIENT_SECRET", "")
KRX_AUTH_KEY    = os.getenv("KRX_AUTH_KEY", "")

# ── 뉴스 키워드 ───────────────────────────────────────────────────
KEYWORDS_EN = [
    '"Trump" tariff OR trade 2026',
    '"Jerome Powell" Fed rate statement',
    '"Jensen Huang" Nvidia AI chip',
    '"Elon Musk" Tesla xAI',
    '"FOMC" interest rate decision',
    '"CPI" OR "inflation" data 2026',
    '"nonfarm payrolls" OR "jobs report"',
    '"semiconductor" export ban AI',
    '"earnings" S&P 500 results',
    '"AI" data center investment spending',
]
KEYWORDS_KO = [
    '트럼프 관세 무역',
    '연준 파월 금리',
    '삼성전자 반도체 HBM',
    'SK하이닉스 실적 주가',
    '코스피 외국인 순매수',
    '원달러 환율',
    '한국은행 기준금리',
    '젠슨황 엔비디아 AI',
]

KR_STOCKS = [
    {"code": "005930", "isin": "KR7005930003", "name": "삼성전자"},
    {"code": "000660", "isin": "KR7000660001", "name": "SK하이닉스"},
    {"code": "012450", "isin": "KR7012450001", "name": "한화에어로스페이스"},
    {"code": "035420", "isin": "KR7035420009", "name": "NAVER"},
    {"code": "005380", "isin": "KR7005380001", "name": "현대차"},
    {"code": "373220", "isin": "KR7373220003", "name": "LG에너지솔루션"},
]

# ── 구글 뉴스 수집 ────────────────────────────────────────────────
async def fetch_google_news(hours: int) -> list[dict]:
    if not GOOGLE_KEY or not GOOGLE_CX:
        return []
    date_restrict = f"d{max(1, hours // 24)}"
    results = []
    async with httpx.AsyncClient(timeout=12) as client:
        for kw in KEYWORDS_EN[:8]:
            try:
                r = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={"key": GOOGLE_KEY, "cx": GOOGLE_CX, "q": kw,
                            "num": 5, "dateRestrict": date_restrict, "lr": "lang_en"}
                )
                for item in r.json().get("items", []):
                    results.append({
                        "title":   item.get("title", ""),
                        "link":    item.get("link", ""),
                        "snippet": item.get("snippet", "")[:200],
                        "source":  item.get("displayLink", ""),
                        "lang":    "en",
                    })
            except Exception:
                continue
    return results

# ── 네이버 뉴스 수집 ──────────────────────────────────────────────
async def fetch_naver_news() -> list[dict]:
    if not NAVER_ID or not NAVER_SECRET:
        return []
    results = []
    headers = {"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SECRET}
    async with httpx.AsyncClient(timeout=12) as client:
        for kw in KEYWORDS_KO[:8]:
            try:
                r = await client.get(
                    "https://openapi.naver.com/v1/search/news.json",
                    headers=headers,
                    params={"query": kw, "display": 8, "sort": "date"}
                )
                for item in r.json().get("items", []):
                    results.append({
                        "title":   re.sub(r"<[^>]+>", "", item.get("title", "")),
                        "link":    item.get("originallink") or item.get("link", ""),
                        "snippet": re.sub(r"<[^>]+>", "", item.get("description", ""))[:200],
                        "source":  item.get("link", "").split("/")[2] if item.get("link") else "",
                        "lang":    "ko",
                        "pubDate": item.get("pubDate", ""),
                    })
            except Exception:
                continue
    return results

# ── KRX 주가 조회 ─────────────────────────────────────────────────
async def fetch_krx_price(isin: str, today: str) -> dict:
    if not KRX_AUTH_KEY:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tr = await client.post(
                "https://openapi.krx.co.kr/contents/COM/GenerateToken.jspx",
                data={"AUTH_KEY": KRX_AUTH_KEY}
            )
            token = tr.json().get("output", {}).get("token", "")
            if not token:
                return {}
            dr = await client.get(
                "https://openapi.krx.co.kr/contents/SVC/OPP20001",
                headers={"AUTH_KEY": token},
                params={"ISU_CD": isin, "BAS_DD": today}
            )
            items = dr.json().get("OutBlock_1", [])
            if items:
                d = items[0]
                close = int(d.get("TDD_CLSPRC", "0").replace(",", ""))
                chg   = float(d.get("FLUC_RT", "0").replace(",", ""))
                return {"close": close, "chg_pct": chg, "volume": d.get("ACC_TRDVOL", "0")}
    except Exception:
        pass
    return {}

# ── AI 분석 프롬프트 빌더 ─────────────────────────────────────────
def build_prompt(news_items: list[dict], hours: int) -> str:
    news_text = ""
    for i, item in enumerate(news_items[:50], 1):
        lang = "[EN]" if item.get("lang") == "en" else "[KO]"
        news_text += f"{i}. {lang} {item['title']}\n"
        if item.get("snippet"):
            news_text += f"   내용: {item['snippet'][:200]}\n"
        if item.get("link"):
            news_text += f"   URL: {item['link']}\n"
        news_text += "\n"

    return f"""당신은 전문 주식 시장 애널리스트입니다.
아래는 최근 {hours}시간 이내 수집된 글로벌·국내 뉴스 {len(news_items)}건입니다.

{news_text}

[분석 지침]
1. 주요 인물 발언(트럼프·머스크·젠슨황·파월 등), 경제지표(CPI·PPI·고용·GDP), 지정학(전쟁·협상), 원자재(유가·금·환율), 기업 실적·이슈를 각각 분리해서 분석하라.
2. 각 이슈가 어떤 산업·섹터에 영향을 주는지 인과관계를 명확히 설명하라.
   예) "젠슨황 AI 데이터센터 확장 발언 → 전력·냉각·반도체 수요 증가 → 관련 국내 종목 수혜"
3. 국내 추천 종목은 반드시 실제 코스피·코스닥 상장 종목으로 6개 이상 제시하라.
4. 미국 추천 종목도 실제 NYSE·NASDAQ 상장 종목으로 5개 이상 제시하라.
5. 뉴스 하이라이트는 7개 이상, 각각 실제 URL 포함하라.

아래 JSON 형식으로만 응답하라. JSON 외 텍스트 절대 금지.

{{
  "summary": {{
    "headline": "오늘 시장 핵심 한줄 요약 30자 이내",
    "sentiment": "bullish 또는 bearish 또는 neutral",
    "score": -100에서 100 사이 정수,
    "market_overview": "전반적 시장 상황 3문장 요약"
  }},
  "key_issues": [
    {{
      "category": "인물발언 또는 경제지표 또는 지정학 또는 원자재 또는 기업이슈",
      "person_or_event": "트럼프 또는 파월 또는 젠슨황 등 또는 이벤트명",
      "title": "이슈 제목",
      "detail": "이슈 상세 설명 3문장",
      "impact": "positive 또는 negative 또는 neutral",
      "affected_sectors": ["영향받는 섹터1", "섹터2"],
      "news_url": "관련 뉴스 URL"
    }}
  ],
  "top_news": [
    {{
      "title": "뉴스 제목",
      "url": "실제 URL 필수",
      "source": "출처매체명",
      "lang": "en 또는 ko",
      "impact": "positive 또는 negative 또는 neutral",
      "category": "인물발언 또는 경제지표 또는 지정학 또는 원자재 또는 기업이슈 또는 시장동향",
      "summary": "핵심 내용 2~3문장 요약. 투자 관점에서 왜 중요한지 포함"
    }}
  ],
  "us_market": {{
    "outlook": "미국 시장 전반 전망 2~3문장",
    "sectors": [
      {{
        "name": "섹터 영문명",
        "name_ko": "섹터 한글명",
        "etf": "대표 ETF 티커",
        "strength": 1에서 5 사이 정수,
        "signal": "buy 또는 hold 또는 watch",
        "news_trigger": "이 섹터를 추천하게 된 뉴스 이슈 한줄",
        "reason": "투자 근거 2문장"
      }}
    ],
    "stocks": [
      {{
        "ticker": "티커심볼",
        "name": "회사명",
        "sector": "속한 섹터",
        "signal": "buy 또는 hold 또는 watch",
        "news_trigger": "추천 근거가 된 뉴스 이슈",
        "reason": "투자 근거 2문장",
        "risk": "low 또는 medium 또는 high"
      }}
    ]
  }},
  "kr_market": {{
    "outlook": "국내 시장 전반 전망 2~3문장",
    "sectors": [
      {{
        "name": "섹터명",
        "strength": 1에서 5 사이 정수,
        "signal": "buy 또는 hold 또는 watch",
        "news_trigger": "이 섹터를 추천하게 된 뉴스 이슈 한줄",
        "reason": "투자 근거 2문장",
        "key_stocks": ["종목명1", "종목명2", "종목명3"]
      }}
    ],
    "stocks": [
      {{
        "code": "종목코드 6자리",
        "isin": "KR7로 시작하는 ISIN",
        "name": "종목명",
        "sector": "속한 섹터",
        "signal": "buy 또는 hold 또는 watch",
        "news_trigger": "추천 근거가 된 뉴스 이슈 한줄",
        "reason": "투자 근거 2문장",
        "risk": "low 또는 medium 또는 high",
        "target_price": "목표주가 숫자만"
      }}
    ]
  }},
  "risks": [
    {{
      "title": "리스크 제목",
      "detail": "상세 설명 2~3문장",
      "severity": "high 또는 medium 또는 low",
      "related_sectors": ["영향 섹터1", "섹터2"]
    }}
  ]
}}

# ── Gemini AI 분석 ────────────────────────────────────────────────
async def analyze_gemini(prompt: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 2500}
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return parse_json(text)

# ── Groq AI 분석 ──────────────────────────────────────────────────
async def analyze_groq(prompt: str) -> dict:
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2500,
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
            json=body
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return parse_json(text)

# ── Claude AI 분석 (선택) ─────────────────────────────────────────
async def analyze_claude(prompt: str) -> dict:
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 2500,
        "messages": [{"role": "user", "content": prompt}]
    }
    async with httpx.AsyncClient(timeout=45) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01",
                     "content-type": "application/json"},
            json=body
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        return parse_json(text)

# ── JSON 파싱 ─────────────────────────────────────────────────────
def parse_json(text: str) -> dict:
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("JSON 없음")
    raw = text[s:e+1]
    raw = re.sub(r",\s*([}\]])", r"\1", raw)  # trailing comma 제거
    return json.loads(raw)

# ── AI 분석 실행 (우선순위: Claude > Gemini > Groq) ───────────────
async def run_analysis(news: list[dict], hours: int) -> tuple[dict, str]:
    prompt = build_prompt(news, hours)
    errors = []

    # 1순위: Claude (있을 때만)
    if ANTHROPIC_KEY:
        try:
            return await analyze_claude(prompt), "claude"
        except Exception as e:
            errors.append(f"Claude: {e}")

    # 2순위: Gemini
    if GEMINI_KEY:
        try:
            return await analyze_gemini(prompt), "gemini"
        except Exception as e:
            errors.append(f"Gemini: {e}")

    # 3순위: Groq
    if GROQ_KEY:
        try:
            return await analyze_groq(prompt), "groq"
        except Exception as e:
            errors.append(f"Groq: {e}")

    raise RuntimeError(f"모든 AI 실패: {' | '.join(errors)}")

# ── 메인 엔드포인트 ───────────────────────────────────────────────
@app.get("/analyze")
async def analyze(hours: int = Query(default=24, ge=1, le=168)):
    # 뉴스 병렬 수집
    google_news, naver_news = await asyncio.gather(
        fetch_google_news(hours),
        fetch_naver_news(),
    )
    all_news = google_news + naver_news
    fallback = len(all_news) == 0

    # AI 분석
    analysis, ai_engine = await run_analysis(all_news, hours)

    # KRX 주가 조회 (추천 종목)
    kr_stocks = analysis.get("kr_market", {}).get("stocks", [])
    today = datetime.now().strftime("%Y%m%d")
    isin_map = {s["code"]: s["isin"] for s in KR_STOCKS}

    price_tasks = {}
    for s in kr_stocks:
        code = s.get("code", "")
        isin = s.get("isin") or isin_map.get(code, "")
        if isin:
            price_tasks[code] = fetch_krx_price(isin, today)

    prices = {}
    for code, coro in price_tasks.items():
        prices[code] = await coro

    for s in kr_stocks:
        pd = prices.get(s.get("code", ""))
        if pd:
            s["price_data"] = pd

    return {
        "analyzed_at":  datetime.now().isoformat(),
        "hours":        hours,
        "ai_engine":    ai_engine,
        "news_count":   {"en": len(google_news), "ko": len(naver_news), "total": len(all_news)},
        "fallback_mode": fallback,
        "analysis":     analysis,
        "top_news_raw": all_news[:15],
    }

@app.get("/health")
def health():
    return {
        "status": "ok",
        "apis": {
            "gemini":  bool(GEMINI_KEY),
            "groq":    bool(GROQ_KEY),
            "claude":  bool(ANTHROPIC_KEY),
            "google":  bool(GOOGLE_KEY and GOOGLE_CX),
            "naver":   bool(NAVER_ID and NAVER_SECRET),
            "krx":     bool(KRX_AUTH_KEY),
        }
    }

@app.get("/")
def root():
    return {"status": "ok", "service": "StockIntel", "version": "2.0"}
