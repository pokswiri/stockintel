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
    for i, item in enumerate(news_items[:45], 1):
        lang = "[EN]" if item.get("lang") == "en" else "[KO]"
        news_text += f"{i}. {lang} {item['title']}\n"
        if item.get("snippet"):
            news_text += f"   {item['snippet'][:150]}\n"
        if item.get("link"):
            news_text += f"   URL: {item['link']}\n"
        news_text += "\n"

    return f"""다음은 최근 {hours}시간 이내의 글로벌·국내 주요 주식시장 뉴스 {len(news_items)}건입니다.

{news_text}

위 뉴스를 분석하여 아래 JSON만 출력하라. JSON 외 다른 텍스트 절대 금지. 배열은 항목별 최대 4개.

{{
  "summary": {{
    "headline": "한 줄 시장 요약 25자 이내",
    "sentiment": "bullish 또는 bearish 또는 neutral",
    "score": -100에서 100 사이 정수,
    "key_events": [
      {{"title": "이벤트명", "impact": "positive 또는 negative 또는 neutral", "detail": "2문장 설명"}}
    ]
  }},
  "us_market": {{
    "outlook": "미국시장 전망 2문장",
    "sectors": [
      {{"name": "섹터영문", "name_ko": "섹터한글", "etf": "ETF티커", "strength": 1~5정수, "signal": "buy 또는 hold 또는 watch", "reason": "이유 1문장"}}
    ],
    "stocks": [
      {{"ticker": "티커", "name": "회사명", "signal": "buy 또는 hold 또는 watch", "reason": "이유 1문장", "risk": "low 또는 medium 또는 high"}}
    ]
  }},
  "kr_market": {{
    "outlook": "국내시장 전망 2문장",
    "sectors": [
      {{"name": "섹터명", "strength": 1~5정수, "signal": "buy 또는 hold 또는 watch", "reason": "이유 1문장", "key_stock": "대표종목명"}}
    ],
    "stocks": [
      {{"code": "종목코드6자리", "isin": "KR7XXXXXX000", "name": "종목명", "signal": "buy 또는 hold 또는 watch", "reason": "이유 1문장", "risk": "low 또는 medium 또는 high", "target_price": "목표주가원단위"}}
    ]
  }},
  "risks": [
    {{"title": "리스크명", "detail": "설명 2문장", "severity": "high 또는 medium 또는 low"}}
  ],
  "top_news": [
    {{"title": "뉴스제목", "url": "실제URL", "source": "출처", "impact": "positive 또는 negative 또는 neutral", "category": "카테고리", "summary": "3문장 요약"}}
  ]
}}"""

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
