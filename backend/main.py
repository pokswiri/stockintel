# -*- coding: utf-8 -*-
import os
import httpx
import asyncio
import json
import re
from datetime import datetime
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI(title="StockIntel API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
GROQ_KEY      = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_KEY    = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CX     = os.getenv("GOOGLE_CX", "")
NAVER_ID      = os.getenv("NAVER_CLIENT_ID", "")
NAVER_SECRET  = os.getenv("NAVER_CLIENT_SECRET", "")
KRX_AUTH_KEY  = os.getenv("KRX_AUTH_KEY", "")

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
    "트럼프 관세 무역",
    "연준 파월 금리",
    "삼성전자 반도체 HBM",
    "SK하이닉스 실적 주가",
    "코스피 외국인 순매수",
    "원달러 환율",
    "한국은행 기준금리",
    "젠슨황 엔비디아 AI",
]

KR_STOCKS = [
    {"code": "005930", "isin": "KR7005930003", "name": "Samsung"},
    {"code": "000660", "isin": "KR7000660001", "name": "SK Hynix"},
    {"code": "012450", "isin": "KR7012450001", "name": "Hanwha Aerospace"},
    {"code": "035420", "isin": "KR7035420009", "name": "NAVER"},
    {"code": "005380", "isin": "KR7005380001", "name": "Hyundai Motor"},
    {"code": "373220", "isin": "KR7373220003", "name": "LG Energy Solution"},
]


async def fetch_google_news(hours: int) -> list:
    if not GOOGLE_KEY or not GOOGLE_CX:
        return []
    date_restrict = "d" + str(max(1, hours // 24))
    results = []
    async with httpx.AsyncClient(timeout=12) as client:
        for kw in KEYWORDS_EN[:8]:
            try:
                r = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={
                        "key": GOOGLE_KEY,
                        "cx": GOOGLE_CX,
                        "q": kw,
                        "num": 5,
                        "dateRestrict": date_restrict,
                        "lr": "lang_en",
                    }
                )
                for item in r.json().get("items", []):
                    results.append({
                        "title": item.get("title", ""),
                        "link": item.get("link", ""),
                        "snippet": item.get("snippet", "")[:200],
                        "source": item.get("displayLink", ""),
                        "lang": "en",
                    })
            except Exception:
                continue
    return results


async def fetch_naver_news() -> list:
    if not NAVER_ID or not NAVER_SECRET:
        return []
    results = []
    headers = {
        "X-Naver-Client-Id": NAVER_ID,
        "X-Naver-Client-Secret": NAVER_SECRET,
    }
    async with httpx.AsyncClient(timeout=12) as client:
        for kw in KEYWORDS_KO[:8]:
            try:
                r = await client.get(
                    "https://openapi.naver.com/v1/search/news.json",
                    headers=headers,
                    params={"query": kw, "display": 8, "sort": "date"},
                )
                for item in r.json().get("items", []):
                    results.append({
                        "title": re.sub(r"<[^>]+>", "", item.get("title", "")),
                        "link": item.get("originallink") or item.get("link", ""),
                        "snippet": re.sub(r"<[^>]+>", "", item.get("description", ""))[:200],
                        "source": (item.get("link", "") or "").split("/")[2] if item.get("link") else "",
                        "lang": "ko",
                    })
            except Exception:
                continue
    return results


async def fetch_krx_price(isin: str, today: str) -> dict:
    if not KRX_AUTH_KEY:
        return {}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            tr = await client.post(
                "https://openapi.krx.co.kr/contents/COM/GenerateToken.jspx",
                data={"AUTH_KEY": KRX_AUTH_KEY},
            )
            token = tr.json().get("output", {}).get("token", "")
            if not token:
                return {}
            dr = await client.get(
                "https://openapi.krx.co.kr/contents/SVC/OPP20001",
                headers={"AUTH_KEY": token},
                params={"ISU_CD": isin, "BAS_DD": today},
            )
            items = dr.json().get("OutBlock_1", [])
            if items:
                d = items[0]
                close_str = d.get("TDD_CLSPRC", "0").replace(",", "")
                chg_str = d.get("FLUC_RT", "0").replace(",", "")
                return {
                    "close": int(close_str),
                    "chg_pct": float(chg_str),
                    "volume": d.get("ACC_TRDVOL", "0"),
                }
    except Exception:
        pass
    return {}


def build_news_text(news_items: list) -> str:
    text = ""
    for i, item in enumerate(news_items[:50], 1):
        lang = "[EN]" if item.get("lang") == "en" else "[KO]"
        text += str(i) + ". " + lang + " " + item.get("title", "") + "\n"
        if item.get("snippet"):
            text += "   " + item["snippet"][:150] + "\n"
        if item.get("link"):
            text += "   URL: " + item["link"] + "\n"
        text += "\n"
    return text


def build_json_schema() -> str:
    # RULE: top_news exactly 5, sectors max 3, stocks max 2 per market
    # RULE: each sector must have exactly 2 stocks in key_stocks
    # RULE: stocks array max 2 items (most impactful only)
    schema = {
        "summary": {
            "headline": "market summary under 30 chars",
            "sentiment": "bullish or bearish or neutral",
            "score": 0,
            "market_overview": "3 sentence overview"
        },
        "key_issues": [
            {
                "category": "person_statement or economic_indicator or geopolitics or commodity or corporate",
                "person_or_event": "Trump or Powell or Jensen Huang etc",
                "title": "issue title",
                "detail": "3 sentence explanation",
                "impact": "positive or negative or neutral",
                "affected_sectors": ["sector1", "sector2"],
                "news_url": "actual URL from news list"
            }
        ],
        "top_news": [
            {
                "title": "news title (translate to Korean if English)",
                "url": "REQUIRED: actual URL from news list",
                "source": "media name",
                "lang": "en or ko",
                "impact": "positive or negative or neutral",
                "category": "person_statement or economic_indicator or geopolitics or commodity or corporate or market",
                "summary": "2-3 sentence Korean summary. Include investment implication."
            },
            {
                "title": "news title 2",
                "url": "actual URL",
                "source": "media name",
                "lang": "en or ko",
                "impact": "positive or negative or neutral",
                "category": "category",
                "summary": "2-3 sentence Korean summary"
            },
            {
                "title": "news title 3",
                "url": "actual URL",
                "source": "media name",
                "lang": "en or ko",
                "impact": "positive or negative or neutral",
                "category": "category",
                "summary": "2-3 sentence Korean summary"
            },
            {
                "title": "news title 4",
                "url": "actual URL",
                "source": "media name",
                "lang": "en or ko",
                "impact": "positive or negative or neutral",
                "category": "category",
                "summary": "2-3 sentence Korean summary"
            },
            {
                "title": "news title 5",
                "url": "actual URL",
                "source": "media name",
                "lang": "en or ko",
                "impact": "positive or negative or neutral",
                "category": "category",
                "summary": "2-3 sentence Korean summary"
            }
        ],
        "us_market": {
            "outlook": "2 sentence US market outlook in Korean",
            "sectors": [
                {
                    "name": "sector english name",
                    "name_ko": "sector Korean name",
                    "etf": "ETF ticker",
                    "strength": 4,
                    "signal": "buy or hold or watch",
                    "news_trigger": "one line: which news triggered this recommendation",
                    "reason": "2 sentence investment rationale in Korean"
                },
                {
                    "name": "sector2 english name",
                    "name_ko": "sector2 Korean name",
                    "etf": "ETF2 ticker",
                    "strength": 3,
                    "signal": "buy or hold or watch",
                    "news_trigger": "one line news trigger",
                    "reason": "2 sentence rationale in Korean"
                }
            ],
            "stocks": [
                {
                    "ticker": "TICKER1",
                    "name": "company name",
                    "sector": "which sector above",
                    "signal": "buy or hold or watch",
                    "news_trigger": "one line news trigger",
                    "reason": "2 sentence rationale in Korean",
                    "risk": "low or medium or high"
                },
                {
                    "ticker": "TICKER2",
                    "name": "company name 2",
                    "sector": "which sector above",
                    "signal": "buy or hold or watch",
                    "news_trigger": "one line news trigger",
                    "reason": "2 sentence rationale in Korean",
                    "risk": "low or medium or high"
                }
            ]
        },
        "kr_market": {
            "outlook": "2 sentence Korean market outlook in Korean",
            "sectors": [
                {
                    "name": "sector Korean name",
                    "strength": 4,
                    "signal": "buy or hold or watch",
                    "news_trigger": "one line: which news triggered this",
                    "reason": "2 sentence rationale in Korean",
                    "key_stocks": ["stock name 1", "stock name 2"]
                },
                {
                    "name": "sector2 Korean name",
                    "strength": 3,
                    "signal": "buy or hold or watch",
                    "news_trigger": "one line news trigger",
                    "reason": "2 sentence rationale in Korean",
                    "key_stocks": ["stock name 3", "stock name 4"]
                }
            ],
            "stocks": [
                {
                    "code": "005930",
                    "isin": "KR7005930003",
                    "name": "Korean stock name",
                    "sector": "which sector above",
                    "signal": "buy or hold or watch",
                    "news_trigger": "one line news trigger",
                    "reason": "2 sentence rationale in Korean",
                    "risk": "low or medium or high",
                    "target_price": "150000"
                },
                {
                    "code": "000660",
                    "isin": "KR7000660001",
                    "name": "Korean stock name 2",
                    "sector": "which sector above",
                    "signal": "buy or hold or watch",
                    "news_trigger": "one line news trigger",
                    "reason": "2 sentence rationale in Korean",
                    "risk": "low or medium or high",
                    "target_price": "120000"
                }
            ]
        },
        "risks": [
            {
                "title": "risk title in Korean",
                "detail": "2-3 sentence explanation in Korean",
                "severity": "high or medium or low",
                "related_sectors": ["sector1"]
            }
        ]
    }
    return json.dumps(schema, ensure_ascii=False, indent=2)


def build_prompt(news_items: list, hours: int) -> str:
    news_text = build_news_text(news_items)
    schema = build_json_schema()
    count = len(news_items)

    prompt = (
        "You are a professional stock market analyst. Analyze the news below and respond ONLY with valid JSON.\n"
        "NO text before or after JSON. NO markdown. NO code blocks.\n\n"
        "STRICT COUNT RULES (must follow exactly):\n"
        "- top_news: EXACTLY 5 items. Pick the 5 most impactful news.\n"
        "- us_market.sectors: 2 to 3 items maximum. Only sectors clearly supported by news.\n"
        "- us_market.stocks: EXACTLY 2 items. One per top sector.\n"
        "- kr_market.sectors: 2 to 3 items maximum. Only sectors clearly supported by news.\n"
        "- kr_market.stocks: EXACTLY 2 items. Real KOSPI/KOSDAQ stocks with 6-digit codes.\n"
        "- key_issues: 3 to 5 items. Each must link to a news URL.\n"
        "- risks: 2 to 3 items.\n\n"
        "ANALYSIS RULES:\n"
        "1. Extract key issues by person (Trump/Powell/Jensen Huang/Musk), economic indicators, geopolitics, commodities.\n"
        "2. For each sector recommendation, cite the specific news that triggered it in news_trigger field.\n"
        "3. Korean stocks must be real KOSPI/KOSDAQ listed companies with correct 6-digit codes.\n"
        "4. sentiment: bullish/bearish/neutral only. score: integer -100 to 100.\n"
        "5. signal: buy/hold/watch only. risk: low/medium/high only.\n"
        "6. All explanatory text (reason, summary, detail, outlook) must be in Korean.\n\n"
        "NEWS (" + str(count) + " articles, last " + str(hours) + " hours):\n\n"
        + news_text
        + "\n\nRespond with this exact JSON structure:\n"
        + schema
    )
    return prompt


def parse_json(text: str) -> dict:
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1:
        raise ValueError("No JSON found")
    raw = text[s:e + 1]
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return json.loads(raw)


async def analyze_gemini(prompt: str) -> dict:
    url = (
        "https://generativelanguage.googleapis.com/v1beta"
        "/models/gemini-1.5-flash:generateContent?key=" + GEMINI_KEY
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 3000},
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(url, json=body)
        r.raise_for_status()
        text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
        return parse_json(text)


async def analyze_groq(prompt: str) -> dict:
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 3000,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + GROQ_KEY,
                "Content-Type": "application/json",
            },
            json=body,
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
        return parse_json(text)


async def analyze_claude(prompt: str) -> dict:
    body = {
        "model": "claude-haiku-4-5-20251001",
        "max_tokens": 3000,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json=body,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        return parse_json(text)


async def run_analysis(news: list, hours: int):
    prompt = build_prompt(news, hours)
    errors = []

    if ANTHROPIC_KEY:
        try:
            return await analyze_claude(prompt), "claude"
        except Exception as ex:
            errors.append("Claude: " + str(ex))

    if GEMINI_KEY:
        try:
            return await analyze_gemini(prompt), "gemini"
        except Exception as ex:
            errors.append("Gemini: " + str(ex))

    if GROQ_KEY:
        try:
            return await analyze_groq(prompt), "groq"
        except Exception as ex:
            errors.append("Groq: " + str(ex))

    raise RuntimeError("All AI failed: " + " | ".join(errors))


@app.get("/analyze")
async def analyze(hours: int = Query(default=24, ge=1, le=168)):
    google_news, naver_news = await asyncio.gather(
        fetch_google_news(hours),
        fetch_naver_news(),
    )
    all_news = google_news + naver_news
    fallback = len(all_news) == 0

    analysis, ai_engine = await run_analysis(all_news, hours)

    kr_stocks = analysis.get("kr_market", {}).get("stocks", [])
    today = datetime.now().strftime("%Y%m%d")
    isin_map = {s["code"]: s["isin"] for s in KR_STOCKS}

    prices = {}
    for s in kr_stocks:
        code = s.get("code", "")
        isin = s.get("isin") or isin_map.get(code, "")
        if isin:
            prices[code] = await fetch_krx_price(isin, today)

    for s in kr_stocks:
        pd = prices.get(s.get("code", ""))
        if pd:
            s["price_data"] = pd

    return {
        "analyzed_at": datetime.now().isoformat(),
        "hours": hours,
        "ai_engine": ai_engine,
        "news_count": {
            "en": len(google_news),
            "ko": len(naver_news),
            "total": len(all_news),
        },
        "fallback_mode": fallback,
        "analysis": analysis,
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "apis": {
            "gemini": bool(GEMINI_KEY),
            "groq": bool(GROQ_KEY),
            "claude": bool(ANTHROPIC_KEY),
            "google": bool(GOOGLE_KEY and GOOGLE_CX),
            "naver": bool(NAVER_ID and NAVER_SECRET),
            "krx": bool(KRX_AUTH_KEY),
        },
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "StockIntel", "version": "3.0"}
