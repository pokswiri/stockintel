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

# KIS NEXUS Score 모듈 (키가 없으면 graceful 비활성화)
try:
    from nexus import run_nexus
    from kis_official import (
        is_kis_available, fetch_all_indices,
        fetch_sector_indices, fetch_sector_etfs,
    )
    _NEXUS_LOADED = True
except Exception:
    _NEXUS_LOADED = False
    def is_kis_available(): return False
    async def fetch_all_indices(): return {}
    async def fetch_sector_indices(s): return {}
    async def fetch_sector_etfs(s): return {}

app = FastAPI(title="StockIntel API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup_event():
    """서버 시작 시 pykis 백그라운드 초기화 (첫 분석 속도 향상)"""
    if _NEXUS_LOADED and is_kis_available():
        try:
            from kis_client import get_kis
            asyncio.create_task(get_kis())
        except Exception:
            pass

GEMINI_KEY    = os.getenv("GEMINI_API_KEY", "")
GROQ_KEY      = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GOOGLE_KEY    = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CX     = os.getenv("GOOGLE_CX", "")
NAVER_ID      = os.getenv("NAVER_CLIENT_ID", "")
NAVER_SECRET  = os.getenv("NAVER_CLIENT_SECRET", "")
KRX_AUTH_KEY  = os.getenv("KRX_AUTH_KEY", "")
KIS_APP_KEY   = os.getenv("KIS_APP_KEY", "")
KIS_APP_SECRET= os.getenv("KIS_APP_SECRET", "")

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
    "코스피 코스닥 주식 시장",          # 시장 전반
    "트럼프 관세 무역 한국",             # 지정학
    "연준 파월 금리 FOMC",              # 통화정책
    "삼성전자 SK하이닉스 반도체 실적",   # 반도체
    "외국인 기관 순매수 순매도",         # 수급
    "방산 한화에어로 현대로템 수주",      # 방산
    "바이오 제약 임상 FDA 승인",         # 헬스케어
    "현대차 기아 자동차 실적 판매",      # 자동차 (실적 정확히 반영)
    "이차전지 배터리 양극재",           # 배터리
    "환율 원달러 외환",                 # 환율
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
    for i, item in enumerate(news_items[:20], 1):
        lang = "[EN]" if item.get("lang") == "en" else "[KO]"
        url = item.get("link", "")
        text += str(i) + ". " + lang + " " + item.get("title", "")
        if url:
            text += " | " + url
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
        "You are a Korean stock market analyst. Analyze the news below and return ONLY a JSON object. No explanation, no markdown, no code blocks.\n\n"
        "CRITICAL: All text fields marked (Korean) MUST be written in Korean (한국어). DO NOT use empty strings or spaces for Korean fields.\n\n"
        "Required JSON structure:\n"
        "{\n"
        "  \"summary\": {\n"
        "    \"headline\": \"(Korean, max 30 chars, e.g. 코스피 상승세 지속)\",\n"
        "    \"sentiment\": \"bullish|bearish|neutral\",\n"
        "    \"score\": -100 to 100,\n"
        "    \"market_overview\": \"(Korean, 2-3 sentences about current market)\",\n"
        "  },\n"
        "  \"key_issues\": [ 3-4 items: {category(person_statement|economic_indicator|geopolitics|commodity|corporate|market), person_or_event(Korean), title(Korean), detail(Korean 2 sentences from actual news), impact(positive|negative|neutral), affected_sectors[2], news_url} ],\n"
        "  \"top_news\": [ 5 items: {title(Korean), url, source, lang:\"ko\", impact, category, summary(Korean 2 sentences)} ],\n"
        "  \"us_market\": { outlook(Korean 2 sentences), sectors[2-3]{name,name_ko(Korean),etf,strength(1-5),signal,news_trigger(Korean),reason(Korean)}, stocks[2]{ticker,name,sector,signal,news_trigger(Korean),reason(Korean),risk} },\n"
        "  \"kr_market\": { outlook(Korean 2 sentences), sectors[2-3]{name,strength(1-5),signal,news_trigger(Korean),reason(Korean),key_stocks[2 codes]}, stocks[2]{code(6digits),isin,name(Korean),sector,signal,news_trigger(Korean),reason(Korean),risk,target_price} },\n"
        "  \"risks\": [ 2-3 items: {title(Korean), detail(Korean 2 sentences), severity:high|medium|low, related_sectors[1-2]} ]\n"
        "}\n\n"
        "STRICT RULE: Korean stocks MUST be directly mentioned or clearly implied by the news above. Do NOT pick stocks without news evidence. stocks[0]=large cap of most news-relevant sector, stocks[1]=different sector if possible. Available: "
        + kr_ref + "\n\n"
        "NEWS (last " + str(hours) + "h):\n"
        + news_text
        + "\nJSON:"
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
    for attempt in range(2):
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(url, json=body)
            if r.status_code == 429 and attempt == 0:
                await asyncio.sleep(15)
                continue
            r.raise_for_status()
            text = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            return parse_json(text)
    raise RuntimeError("Gemini: rate limit after retry")


async def analyze_groq(prompt: str) -> dict:
    # 모델 우선순위: 70b → 8b (400/413 에러 시 자동 폴백)
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    last_err = ""
    for model in models:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 3000,
        }
        for attempt in range(2):
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": "Bearer " + GROQ_KEY,
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                if r.status_code == 429 and attempt == 0:
                    await asyncio.sleep(15)
                    continue
                if r.status_code in (400, 413):
                    last_err = f"Groq {model}: {r.status_code}"
                    break  # 다음 모델 시도
                r.raise_for_status()
                text = r.json()["choices"][0]["message"]["content"]
                return parse_json(text)
    raise RuntimeError("Groq: all models failed. " + last_err)


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

    # 모든 AI 실패 시 빈 결과 반환 (서버 크래시 방지)
    fallback = {
        "summary": {
            "headline": "AI 분석 일시 오류",
            "sentiment": "neutral",
            "score": 0,
            "market_overview": "AI 분석 서비스에 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.",
        },
        "key_issues": [],
        "top_news": [],
        "us_market": {"outlook": "", "sectors": [], "stocks": []},
        "kr_market": {"outlook": "", "sectors": [], "stocks": []},
        "risks": [],
        "_errors": errors,
    }
    return fallback, "error"


def _get_bet_timing() -> dict:
    """현재 시각 기준 종가 베팅 타이밍 안내
    정규장: 09:00~15:30 / 종가베팅타임: 14:30~15:20
    넥스트레이드(야간장): 16:00~20:00 / 종가베팅타임: 19:10~19:50
    주말·공휴일은 별도 처리
    """
    now = datetime.now()
    h, m = now.hour, now.minute
    t = h * 60 + m
    weekday = now.weekday()  # 0=월 ... 4=금 / 5=토 / 6=일

    # 주말 (토·일)
    if weekday >= 5:
        return {"label": "주말 휴장", "msg": "주식 시장이 휴장 중입니다. 월요일 시초가 전략을 준비하세요.", "highlight": False, "session": "weekend"}

    if t < 9 * 60:
        return {"label": "장 전", "msg": "정규장 시작 전입니다. 어제 기준 분석입니다.", "highlight": False, "session": "pre"}
    elif t < 14 * 60 + 30:
        return {"label": "정규장 진행중", "msg": "장 마감 전 재분석 시 당일 수급이 반영됩니다.", "highlight": False, "session": "regular"}
    elif t < 15 * 60 + 20:
        return {"label": "🔔 정규장 종가 베팅 타임", "msg": "정규장 종가 매수 검토 시간입니다 (14:30~15:20). 추천 종목 현재가를 확인하세요.", "highlight": True, "session": "regular_close"}
    elif t < 15 * 60 + 30:
        return {"label": "정규장 마감 직전", "msg": "정규장 마감 5분 전입니다.", "highlight": False, "session": "regular_end"}
    elif t < 16 * 60:
        return {"label": "정규장 마감", "msg": "정규장이 마감됐습니다. 넥스트레이드(야간장) 16:00 시작 예정입니다.", "highlight": False, "session": "after_regular"}
    elif t < 19 * 60 + 10:
        return {"label": "넥스트레이드 진행중", "msg": "야간장(넥스트레이드) 거래 중입니다. 오후 8시 마감입니다.", "highlight": False, "session": "night"}
    elif t < 19 * 60 + 50:
        return {"label": "🔔 야간장 종가 베팅 타임", "msg": "넥스트레이드(야간장) 종가 매수 검토 시간입니다 (19:10~19:50). 마감 20:00.", "highlight": True, "session": "night_close"}
    elif t < 20 * 60:
        return {"label": "야간장 마감 직전", "msg": "넥스트레이드(야간장) 마감 10분 전입니다.", "highlight": False, "session": "night_end"}
    else:
        return {"label": "전 장 마감", "msg": "정규장·야간장 모두 마감됐습니다. 내일 전략을 준비하세요.", "highlight": False, "session": "closed"}


@app.get("/analyze")
async def analyze(hours: int = Query(default=24, ge=1, le=168)):
    # 1. 뉴스 수집
    google_news, naver_news = await asyncio.gather(
        fetch_google_news(hours),
        fetch_naver_news(),
    )
    all_news = dedup_news(google_news + naver_news)
    fallback = len(all_news) == 0

    # 2. AI 분석 + KRX 시장 데이터 병렬
    # KRX: 당일 데이터 없으면 직전 거래일(1~3일 이내) 자동 폴백
    from datetime import timedelta
    def _recent_trading_days(n=3):
        days = []
        d = datetime.now()
        while len(days) < n:
            if d.weekday() < 5:  # 월~금
                days.append(d.strftime("%Y%m%d"))
            d -= timedelta(days=1)
        return days

    trading_days = _recent_trading_days(3)
    today = trading_days[0]

    async def fetch_krx_indices_with_fallback():
        for day in trading_days:
            r = await fetch_krx_indices(day)
            if r:
                return r
        return {}

    async def fetch_krx_etf_with_fallback():
        for day in trading_days:
            r = await fetch_krx_etf_sector(day)
            if r:
                return r
        return {}

    # KIS API로 실시간 지수 조회 (KRX 대체)
    async def _empty(): return {}
    (analysis, ai_engine), kis_indices = await asyncio.gather(
        run_analysis(all_news, hours),
        fetch_all_indices() if is_kis_available() else _empty(),
    )
    krx_indices = kis_indices  # 변수명 호환 유지
    krx_etfs    = {}

    # 3. AI 추천 섹터 추출 (NEXUS 입력용)
    kr_sectors = analysis.get("kr_market", {}).get("sectors", [])
    sector_names = [s.get("name", "") for s in kr_sectors if s.get("name")]

    # 4. AI 추천 종목 주가 KIS API로 직접 조회
    kr_stocks = analysis.get("kr_market", {}).get("stocks", [])
    if is_kis_available() and kr_stocks:
        try:
            from kis_official import batch_fetch_prices as _bfp
            ai_codes = [s.get("code","") for s in kr_stocks if s.get("code","")]
            ai_prices = await _bfp(ai_codes)
            for s in kr_stocks:
                code = s.get("code", "")
                if code and code in ai_prices:
                    pd = ai_prices[code]
                    s["price_data"] = {
                        "close":   pd.get("price", 0),
                        "chg_pct": pd.get("change_rate", 0),
                    }
        except Exception:
            pass

    # 5. NEXUS Score + 섹터 ETF/업종지수 실시간 (KIS API)
    nexus_result = None
    sector_etfs_live = {}
    sector_indices_live = {}

    if _NEXUS_LOADED and is_kis_available() and sector_names:
        try:
            # 섹터 ETF, 업종지수, NEXUS Score 병렬 실행
            nexus_result, sector_etfs_live, sector_indices_live = await asyncio.gather(
                asyncio.wait_for(run_nexus(sector_names, top_n=3), timeout=60.0),
                fetch_sector_etfs(sector_names),
                fetch_sector_indices(sector_names),
                return_exceptions=True,
            )
            # 예외 처리
            if isinstance(nexus_result, Exception):
                nexus_result = {"available": False, "message": str(nexus_result)}
            if isinstance(sector_etfs_live, Exception):
                sector_etfs_live = {}
            if isinstance(sector_indices_live, Exception):
                sector_indices_live = {}
        except asyncio.TimeoutError:
            nexus_result = {"available": False, "message": "NEXUS 분석 시간 초과"}
        except Exception as e:
            nexus_result = {"available": False, "message": str(e)}

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
        "nexus": nexus_result,
        "sector_etfs_live": sector_etfs_live,
        "sector_indices_live": sector_indices_live,
        "bet_timing": _get_bet_timing(),
        "kis_available": is_kis_available(),
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
            "kis": bool(KIS_APP_KEY and KIS_APP_SECRET),
        },
    }


@app.get("/")
def root():
    return {"status": "ok", "service": "StockIntel", "version": "4.0"}
