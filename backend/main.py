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
    {"code": "005930", "isin": "KR7005930003", "name": "Samsung Electronics", "sector": "semiconductor", "cap": "large"},
    {"code": "000660", "isin": "KR7000660001", "name": "SK Hynix", "sector": "semiconductor", "cap": "large"},
    {"code": "042700", "isin": "KR7042700002", "name": "Hanmi Semiconductor", "sector": "semiconductor", "cap": "mid"},
    {"code": "240810", "isin": "KR7240810006", "name": "Wonik IPS", "sector": "semiconductor", "cap": "mid"},
    {"code": "012450", "isin": "KR7012450001", "name": "Hanwha Aerospace", "sector": "defense", "cap": "large"},
    {"code": "079550", "isin": "KR7079550005", "name": "LIG Nex1", "sector": "defense", "cap": "mid"},
    {"code": "047810", "isin": "KR7047810005", "name": "Korea Aerospace Industries", "sector": "defense", "cap": "large"},
    {"code": "064350", "isin": "KR7064350005", "name": "Hyundai Rotem", "sector": "defense", "cap": "mid"},
    {"code": "035420", "isin": "KR7035420009", "name": "NAVER", "sector": "ai_platform", "cap": "large"},
    {"code": "035720", "isin": "KR7035720002", "name": "Kakao", "sector": "ai_platform", "cap": "large"},
    {"code": "005380", "isin": "KR7005380001", "name": "Hyundai Motor", "sector": "auto_ev", "cap": "large"},
    {"code": "000270", "isin": "KR7000270009", "name": "Kia", "sector": "auto_ev", "cap": "large"},
    {"code": "373220", "isin": "KR7373220003", "name": "LG Energy Solution", "sector": "battery", "cap": "large"},
    {"code": "006400", "isin": "KR7006400006", "name": "Samsung SDI", "sector": "battery", "cap": "large"},
    {"code": "051910", "isin": "KR7051910008", "name": "LG Chem", "sector": "battery", "cap": "large"},
    {"code": "009830", "isin": "KR7009830001", "name": "Hanwha Solutions", "sector": "renewable", "cap": "large"},
    {"code": "105560", "isin": "KR7105560007", "name": "KB Financial", "sector": "finance", "cap": "large"},
    {"code": "055550", "isin": "KR7055550008", "name": "Shinhan Financial", "sector": "finance", "cap": "large"},
    {"code": "068270", "isin": "KR7068270008", "name": "Celltrion", "sector": "healthcare", "cap": "large"},
    {"code": "207940", "isin": "KR7207940008", "name": "Samsung Biologics", "sector": "healthcare", "cap": "large"},
    {"code": "005490", "isin": "KR7005490008", "name": "POSCO Holdings", "sector": "steel", "cap": "large"},
]
KR_STOCKS_BY_CODE = {s["code"]: s for s in KR_STOCKS}


async def fetch_google_news(hours: int) -> list:
    if not GOOGLE_KEY or not GOOGLE_CX:
        return []
    date_restrict = "d" + str(max(1, hours // 24))
    results = []
    async with httpx.AsyncClient(timeout=12) as client:
        for kw in KEYWORDS_EN[:5]:
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
        for kw in KEYWORDS_KO[:5]:
            try:
                r = await client.get(
                    "https://openapi.naver.com/v1/search/news.json",
                    headers=headers,
                    params={"query": kw, "display": 5, "sort": "date"},
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


def dedup_news(news_list: list) -> list:
    seen_urls = set()
    seen_titles = set()
    result = []
    for item in news_list:
        url = item.get("link", "")
        title = item.get("title", "").strip()[:50]
        if url and url in seen_urls:
            continue
        if title and title in seen_titles:
            continue
        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        result.append(item)
    return result


def parse_krx_item(d: dict) -> dict:
    def clean(v):
        return v.replace(",", "").replace("-", "0").strip() if v else "0"
    try:
        close = int(clean(d.get("TDD_CLSPRC", "0")))
    except Exception:
        close = 0
    try:
        chg = float(clean(d.get("FLUC_RT", "0")))
    except Exception:
        chg = 0.0
    try:
        mktcap = int(clean(d.get("MKTCAP", "0")))
    except Exception:
        mktcap = 0
    try:
        volume = int(clean(d.get("ACC_TRDVOL", "0")))
    except Exception:
        volume = 0
    return {
        "code": d.get("ISU_CD", ""),
        "name": d.get("ISU_NM", ""),
        "close": close,
        "chg_pct": chg,
        "open": d.get("TDD_OPNPRC", ""),
        "high": d.get("TDD_HGPRC", ""),
        "low": d.get("TDD_LWPRC", ""),
        "volume": volume,
        "mktcap": mktcap,
        "list_shrs": d.get("LIST_SHRS", ""),
    }


async def fetch_krx_market(today: str) -> dict:
    """Fetch all KOSPI + KOSDAQ stocks for a given date. Returns dict keyed by ISU_CD."""
    if not KRX_AUTH_KEY:
        return {}
    result = {}
    endpoints = [
        "https://data-dbg.krx.co.kr/svc/apis/sto/stk_bydd_trd",
        "https://data-dbg.krx.co.kr/svc/apis/sto/ksq_bydd_trd",
    ]
    headers = {
        "AUTH_KEY": KRX_AUTH_KEY,
        "Content-Type": "application/json",
    }
    payload = {"basDd": today}
    async with httpx.AsyncClient(timeout=20) as client:
        for url in endpoints:
            try:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                for d in r.json().get("OutBlock_1", []):
                    code = d.get("ISU_CD", "")
                    if code:
                        result[code] = parse_krx_item(d)
            except Exception:
                continue
    return result


async def fetch_krx_indices(today: str) -> dict:
    """Fetch KOSPI + KOSDAQ index data. Returns dict with kospi and kosdaq keys."""
    if not KRX_AUTH_KEY:
        return {}
    result = {}
    endpoints = {
        "kospi": "https://data-dbg.krx.co.kr/svc/apis/idx/kospi_dd_trd",
        "kosdaq": "https://data-dbg.krx.co.kr/svc/apis/idx/kosdaq_dd_trd",
    }
    headers = {"AUTH_KEY": KRX_AUTH_KEY, "Content-Type": "application/json"}
    payload = {"basDd": today}
    async with httpx.AsyncClient(timeout=15) as client:
        for key, url in endpoints.items():
            try:
                r = await client.post(url, headers=headers, json=payload)
                r.raise_for_status()
                items = r.json().get("OutBlock_1", [])
                # Find main index (KOSPI or KOSDAQ composite)
                for d in items:
                    nm = d.get("IDX_NM", "")
                    if key == "kospi" and nm == "KOSPI":
                        def cl(v): return v.replace(",", "").strip() if v else "0"
                        result[key] = {
                            "name": nm,
                            "close": cl(d.get("CLSPRC_IDX", "0")),
                            "chg_pct": cl(d.get("FLUC_RT", "0")),
                            "chg": cl(d.get("CMPPREVDD_IDX", "0")),
                        }
                        break
                    elif key == "kosdaq" and nm == "KOSDAQ":
                        def cl2(v): return v.replace(",", "").strip() if v else "0"
                        result[key] = {
                            "name": nm,
                            "close": cl2(d.get("CLSPRC_IDX", "0")),
                            "chg_pct": cl2(d.get("FLUC_RT", "0")),
                            "chg": cl2(d.get("CMPPREVDD_IDX", "0")),
                        }
                        break
            except Exception:
                continue
    return result


async def fetch_krx_etf_sector(today: str) -> dict:
    """Fetch ETF data and extract key sector ETFs by name matching."""
    if not KRX_AUTH_KEY:
        return {}
    # Sector keywords to ETF name mapping
    sector_keywords = {
        "semiconductor": ["반도체", "IT", "테크"],
        "defense": ["방산", "항공우주"],
        "battery": ["2차전지", "배터리", "전기차"],
        "renewable": ["태양광", "신재생", "그린"],
        "healthcare": ["헬스케어", "바이오", "제약"],
        "finance": ["금융", "은행", "증권"],
    }
    result = {}
    headers = {"AUTH_KEY": KRX_AUTH_KEY, "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://data-dbg.krx.co.kr/svc/apis/etp/etf_bydd_trd",
                headers=headers,
                json={"basDd": today},
            )
            r.raise_for_status()
            items = r.json().get("OutBlock_1", [])
            for d in items:
                nm = d.get("ISU_NM", "")
                for sector, keywords in sector_keywords.items():
                    if any(kw in nm for kw in keywords):
                        if sector not in result:
                            def cl(v): return v.replace(",", "").strip() if v else "0"
                            try:
                                mktcap = int(cl(d.get("MKTCAP", "0")))
                            except Exception:
                                mktcap = 0
                            result[sector] = {
                                "name": nm,
                                "code": d.get("ISU_CD", ""),
                                "close": cl(d.get("TDD_CLSPRC", "0")),
                                "chg_pct": cl(d.get("FLUC_RT", "0")),
                                "mktcap": mktcap,
                                "nav": cl(d.get("NAV", "0")),
                            }
                        break
    except Exception:
        pass
    return result


def build_news_text(news_items: list) -> str:
    text = ""
    for i, item in enumerate(news_items[:30], 1):
        lang = "[EN]" if item.get("lang") == "en" else "[KO]"
        text += str(i) + ". " + lang + " " + item.get("title", "") + "\n"
        if item.get("snippet"):
            text += "   " + item["snippet"][:100] + "\n"
        if item.get("link"):
            text += "   URL: " + item["link"] + "\n"
        text += "\n"
    return text


def build_prompt(news_items: list, hours: int) -> str:
    news_text = build_news_text(news_items)
    count = len(news_items)

    # Sector-based stock reference: name:code:isin:cap(large/mid)
    kr_ref = (
        "SEMICONDUCTOR:Samsung Electronics:005930:large,SK Hynix:000660:large,Hanmi Semiconductor:042700:mid|"
        "DEFENSE:Hanwha Aerospace:012450:large,LIG Nex1:079550:mid,Korea Aerospace:047810:large|"
        "AI_PLATFORM:NAVER:035420:large,Kakao:035720:large|"
        "AUTO_EV:Hyundai Motor:005380:large,Kia:000270:large|"
        "BATTERY:LG Energy Solution:373220:large,Samsung SDI:006400:large,LG Chem:051910:large|"
        "RENEWABLE:Hanwha Solutions:009830:large|"
        "FINANCE:KB Financial:105560:large,Shinhan Financial:055550:large|"
        "HEALTHCARE:Celltrion:068270:large,Samsung Biologics:207940:large|"
        "STEEL:POSCO Holdings:005490:large"
    )

    prompt = (
        "You are a professional Korean stock market analyst.\n"
        "Read the news articles carefully and generate a JSON analysis.\n"
        "Return ONLY raw JSON. No markdown, no code fences, no explanation text.\n\n"

        "=== OUTPUT FORMAT ===\n"
        "Generate a JSON object with these exact keys:\n"
        "summary, key_issues, top_news, us_market, kr_market, risks\n\n"

        "summary: object with keys:\n"
        "  headline (string, Korean, under 30 chars)\n"
        "  sentiment (string: bullish OR bearish OR neutral)\n"
        "  score (integer: -100 to 100)\n"
        "  market_overview (string, Korean, 3 sentences)\n\n"

        "key_issues: array of 3 to 5 objects, each with keys:\n"
        "  category (string: person_statement OR economic_indicator OR geopolitics OR commodity OR corporate)\n"
        "  person_or_event (string: name of person or event)\n"
        "  title (string, Korean)\n"
        "  detail (string, Korean, 3 sentences)\n"
        "  impact (string: positive OR negative OR neutral)\n"
        "  affected_sectors (array of 2 Korean sector name strings)\n"
        "  news_url (string: actual URL copied from news list)\n\n"

        "top_news: array of EXACTLY 5 objects, each with keys:\n"
        "  title (string, Korean translation if English)\n"
        "  url (string: actual URL from the news list - REQUIRED)\n"
        "  source (string: media outlet name)\n"
        "  lang (string: en OR ko)\n"
        "  impact (string: positive OR negative OR neutral)\n"
        "  category (string: person_statement OR economic_indicator OR geopolitics OR commodity OR corporate OR market)\n"
        "  summary (string, Korean, 2-3 sentences including investment implication)\n\n"

        "us_market: object with keys:\n"
        "  outlook (string, Korean, 2 sentences)\n"
        "  sectors: array of 2 to 3 objects, each with keys:\n"
        "    name (string: English sector name)\n"
        "    name_ko (string: Korean sector name)\n"
        "    etf (string: representative ETF ticker)\n"
        "    strength (integer: 1 to 5)\n"
        "    signal (string: buy OR hold OR watch)\n"
        "    news_trigger (string: specific news headline that caused this recommendation)\n"
        "    reason (string, Korean, 2 sentences)\n"
        "  stocks: array of EXACTLY 2 objects, each with keys:\n"
        "    ticker (string: real NYSE/NASDAQ ticker)\n"
        "    name (string: company name)\n"
        "    sector (string: which sector above)\n"
        "    signal (string: buy OR hold OR watch)\n"
        "    news_trigger (string: specific news that triggered this)\n"
        "    reason (string, Korean, 2 sentences)\n"
        "    risk (string: low OR medium OR high)\n\n"

        "kr_market: object with keys:\n"
        "  outlook (string, Korean, 2 sentences)\n"
        "  sectors: array of 2 to 3 objects, each with keys:\n"
        "    name (string: Korean sector name)\n"
        "    strength (integer: 1 to 5)\n"
        "    signal (string: buy OR hold OR watch)\n"
        "    news_trigger (string: ONE specific news headline from the news list that directly caused this sector recommendation)\n"
        "    reason (string, Korean, 2 sentences explaining the news-to-sector connection)\n"
        "    key_stocks (array of exactly 2 Korean company name strings: first=large cap leader, second=mid cap)\n"
        "  stocks: array of EXACTLY 2 objects picked from KNOWN KOREAN STOCKS list above.\n"
        "    IMPORTANT: stock[0] must be the large-cap leader of the top recommended sector.\n"
        "    IMPORTANT: stock[1] must be a mid-cap stock from the same or second sector.\n"
        "    IMPORTANT: Do NOT always pick Samsung/SK Hynix. Choose based on which sector the news points to.\n"
        "    Each stock object has these keys:\n"
        "    code (string: 6-digit code from KNOWN KOREAN STOCKS)\n"
        "    isin (string: KR7 format ISIN from KNOWN KOREAN STOCKS)\n"
        "    name (string: company name from KNOWN KOREAN STOCKS)\n"
        "    sector (string: Korean sector name from sectors above)\n"
        "    signal (string: buy OR hold OR watch)\n"
        "    news_trigger (string: ONE specific news headline that triggered this stock pick)\n"
        "    reason (string, Korean, 2 sentences: explain why THIS stock in THIS sector based on the news)\n"
        "    risk (string: low OR medium OR high)\n"
        "    target_price (string: number only, no commas)\n\n"

        "risks: array of 2 to 3 objects, each with keys:\n"
        "  title (string, Korean)\n"
        "  detail (string, Korean, 2-3 sentences)\n"
        "  severity (string: high OR medium OR low)\n"
        "  related_sectors (array of Korean sector name strings)\n\n"

        "=== KNOWN KOREAN STOCKS (name:code:isin) ===\n"
        + kr_ref + "\n\n"

        "=== NEWS ARTICLES (" + str(count) + " articles, last " + str(hours) + " hours) ===\n\n"
        + news_text
        + "\n=== END OF NEWS ===\n"
        "Now generate the JSON analysis based on the news above:"
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
        "/models/gemini-2.0-flash:generateContent?key=" + GEMINI_KEY
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 4000},
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
        "max_tokens": 4000,
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
        "max_tokens": 4000,
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
    all_news = dedup_news(google_news + naver_news)
    fallback = len(all_news) == 0

    analysis, ai_engine = await run_analysis(all_news, hours)

    kr_stocks = analysis.get("kr_market", {}).get("stocks", [])
    today = datetime.now().strftime("%Y%m%d")

    # Fetch market data in parallel (stocks + indices + ETFs)
    krx_market, krx_indices, krx_etfs = await asyncio.gather(
        fetch_krx_market(today),
        fetch_krx_indices(today),
        fetch_krx_etf_sector(today),
    )

    # Match AI-recommended stocks with real KRX data
    for s in kr_stocks:
        code = s.get("code", "")
        if code and code in krx_market:
            s["price_data"] = krx_market[code]
        elif code:
            # Try ISIN fallback: find by code in market data
            for mcode, mdata in krx_market.items():
                if mcode == code or mdata.get("code", "") == code:
                    s["price_data"] = mdata
                    break

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
        "market_index": krx_indices,
        "sector_etfs": krx_etfs,
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
