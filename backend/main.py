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

# 성과 추적 모듈
try:
    from tracker import save_recommendations, get_performance_stats, update_returns_async, delete_record
    _TRACKER_LOADED = True
except Exception:
    _TRACKER_LOADED = False
    def save_recommendations(*a, **kw): pass
    def get_performance_stats(): return {"total_count": 0, "records": [], "stats": {}}
    async def update_returns_async(*a, **kw): pass
    def delete_record(*a, **kw): return False

try:
    from sector_tracker import record_daily_sectors, get_rotation_status, get_sector_trend
    _SECTOR_TRACKER_LOADED = True
except Exception:
    _SECTOR_TRACKER_LOADED = False
    async def record_daily_sectors(*a, **kw): return {}
    def get_rotation_status(*a, **kw): return {"available": False, "message": "sector_tracker 비활성화"}
    def get_sector_trend(*a, **kw): return []

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
    '"FOMC" interest rate decision',
    '"CPI" OR "inflation" data 2026',
    '"semiconductor" export ban AI',
    '"AI" data center investment spending',
    '"LNG" OR "shipbuilding" order contract',
    '"biotech" OR "FDA" approval clinical trial',
    '"K-pop" OR "webtoon" OR "K-content" global',
]

KEYWORDS_KO = [
    "코스피 코스닥 주식 시장",             # 시장 전반
    "트럼프 관세 무역 한국",               # 지정학
    "삼성전자 SK하이닉스 반도체 실적",     # 반도체
    "외국인 기관 순매수 순매도",           # 수급
    "방산 한화에어로 현대로템 수주",        # 방산
    "바이오 제약 임상 FDA 승인",           # 헬스케어
    "현대차 기아 자동차 전기차 실적",       # 자동차
    "이차전지 배터리 양극재 LFP",          # 배터리
    "조선 LNG선 수주 HD현대 한화오션",     # 조선 (신규)
    "엔터 K팝 콘텐츠 드라마 흥행",         # 엔터 (신규)
    "게임 신작 출시 넥슨 크래프톤",         # 게임 (신규)
    "환율 원달러 외환",                    # 환율
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

    # Sector-based stock reference: name:code:cap(large/mid)
    kr_ref = (
        "SEMICONDUCTOR:Samsung Electronics:005930:large,SK Hynix:000660:large,Hanmi Semiconductor:042700:mid|"
        "DEFENSE:Hanwha Aerospace:012450:large,LIG Nex1:079550:mid,Korea Aerospace:047810:large|"
        "AI_PLATFORM:NAVER:035420:large,Kakao:035720:large|"
        "AUTO_EV:Hyundai Motor:005380:large,Kia:000270:large|"
        "BATTERY:LG Energy Solution:373220:large,Samsung SDI:006400:large,LG Chem:051910:large|"
        "RENEWABLE:Hanwha Solutions:009830:large|"
        "FINANCE:KB Financial:105560:large,Shinhan Financial:055550:large|"
        "HEALTHCARE:Celltrion:068270:large,Samsung Biologics:207940:large|"
        "STEEL:POSCO Holdings:005490:large|"
        "SHIPBUILDING:HD Hyundai Heavy:009540:large,Hanwha Ocean:042660:large,Samsung Heavy:010140:large"
    )

    # 섹터 키 목록 (kr_market.sectors[].name 필드에 반드시 아래 값 중 하나를 사용)
    sector_key_list = (
        "semiconductor | defense | ai_platform | battery | auto_ev | "
        "renewable | finance | healthcare | steel | shipbuilding"
    )

    prompt = (
        "You are a Korean stock market analyst. Analyze the news below and return ONLY a JSON object. No explanation, no markdown, no code blocks.\n\n"
        "CRITICAL: All text fields marked (Korean) MUST be written in Korean (한국어). DO NOT use empty strings or spaces for Korean fields.\n\n"
        "SECTOR NAME RULE: In kr_market.sectors[].name, you MUST use EXACTLY one of these keys:\n"
        f"  {sector_key_list}\n"
        "  Example: if news is about semiconductors → name: \"semiconductor\"\n"
        "           if news is about shipbuilding/해운/조선 → name: \"shipbuilding\"\n"
        "           if news is about biotech/pharma → name: \"healthcare\"\n"
        "  DO NOT use free-form text like '반도체', 'IT하드웨어', '2차전지' — use the exact key above.\n\n"
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
        "  \"kr_market\": { outlook(Korean 2 sentences), sectors[2-3]{name(MUST use sector key from list above),strength(1-5),signal,news_trigger(Korean),reason(Korean),key_stocks[2 codes]}, stocks[2]{code(6digits),isin,name(Korean),sector,signal,news_trigger(Korean),reason(Korean),risk,target_price} },\n"
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


def build_groq_prompt(news_items: list, hours: int) -> str:
    """
    Groq(llama) 전용 경량 프롬프트
    - 전체 JSON 구조 대신 핵심 필드만 요청 (토큰 절감, 400/413 방지)
    - 섹터 키 형식 동일하게 강제
    """
    news_text = build_news_text(news_items[:10])  # 최대 10개로 제한
    sector_key_list = "semiconductor|defense|ai_platform|battery|auto_ev|renewable|finance|healthcare|steel|shipbuilding"

    return (
        "Korean stock analyst. Analyze news, return ONLY JSON. No markdown.\n\n"
        "SECTOR KEYS (use exactly): " + sector_key_list + "\n\n"
        "JSON structure:\n"
        "{\n"
        "  \"summary\": {\"headline\":\"(Korean 20chars)\",\"sentiment\":\"bullish|bearish|neutral\",\"score\":-100~100,\"market_overview\":\"(Korean 2 sentences)\"},\n"
        "  \"key_issues\": [{\"title\":\"(Korean)\",\"detail\":\"(Korean)\",\"impact\":\"positive|negative|neutral\",\"affected_sectors\":[\"sector_key\"]}],\n"
        "  \"top_news\": [{\"title\":\"(Korean)\",\"url\":\"\",\"source\":\"\",\"lang\":\"ko\",\"impact\":\"positive\",\"category\":\"\",\"summary\":\"(Korean)\"}],\n"
        "  \"us_market\": {\"outlook\":\"(Korean)\",\"sectors\":[],\"stocks\":[]},\n"
        "  \"kr_market\": {\n"
        "    \"outlook\":\"(Korean 2 sentences)\",\n"
        "    \"sectors\":[{\"name\":\"EXACT_SECTOR_KEY\",\"strength\":1-5,\"signal\":\"buy|hold|sell\",\"news_trigger\":\"(Korean)\",\"reason\":\"(Korean)\",\"key_stocks\":[\"code\"]}],\n"
        "    \"stocks\":[{\"code\":\"6digits\",\"isin\":\"\",\"name\":\"(Korean)\",\"sector\":\"EXACT_SECTOR_KEY\",\"signal\":\"buy\",\"news_trigger\":\"(Korean)\",\"reason\":\"(Korean)\",\"risk\":\"(Korean)\",\"target_price\":0}]\n"
        "  },\n"
        "  \"risks\": [{\"title\":\"(Korean)\",\"detail\":\"(Korean)\",\"severity\":\"high|medium|low\",\"related_sectors\":[]}]\n"
        "}\n\n"
        "NEWS (last " + str(hours) + "h):\n" + news_text + "\nJSON:"
    )


async def analyze_groq(prompt: str, news_items: list = None, hours: int = 24) -> dict:
    """
    Groq 폴백 분석
    - 먼저 경량 프롬프트로 시도 (400/413 방지)
    - 경량도 실패 시 원본 프롬프트로 재시도
    """
    # 모델 우선순위: 70b → 8b (400/413 에러 시 자동 폴백)
    models = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
    last_err = ""

    # Groq 전용 경량 프롬프트 우선 사용
    groq_prompt = build_groq_prompt(news_items, hours) if news_items else prompt

    for model in models:
        for use_prompt in [groq_prompt, prompt] if groq_prompt != prompt else [prompt]:
            body = {
                "model": model,
                "messages": [{"role": "user", "content": use_prompt}],
                "temperature": 0.3,
                "max_tokens": 2000,
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
                        break  # 다음 프롬프트/모델 시도
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
            return await analyze_groq(prompt, news_items=news, hours=hours), "groq"
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
        return {
            "label": "주말 휴장",
            "msg": "금요일 종가 기준 분석입니다. NEXUS Score는 최근 거래일 데이터를 반영합니다.",
            "highlight": False,
            "session": "weekend",
        }

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


# ── 분석 결과 캐시 (메모리, 30분) ────────────────────────────────
# Railway 재시작 시 초기화되지만 운영 중 API 한도 절감 효과 큼
_CACHE: dict = {}
_CACHE_TTL = 30 * 60  # 30분 (초)


def _cache_get(key: str):
    """캐시 조회 — 만료 시 None 반환"""
    if key not in _CACHE:
        return None
    data, saved_at = _CACHE[key]
    if (datetime.now() - saved_at).total_seconds() > _CACHE_TTL:
        del _CACHE[key]
        return None
    return data


def _cache_set(key: str, data):
    """캐시 저장"""
    _CACHE[key] = (data, datetime.now())


@app.get("/analyze")
async def analyze(
    hours: int = Query(default=24, ge=1, le=168),
    force: bool = Query(default=False, description="캐시 무시하고 강제 재분석"),
):
    # 캐시 확인 (force=true이면 무시)
    cache_key = f"analyze_{hours}"
    if not force:
        cached = _cache_get(cache_key)
        if cached:
            print(f"[CACHE] HIT — hours={hours} (30분 캐시)")
            # 캐시 HIT여도 tracker 수익률 업데이트는 실행
            if _TRACKER_LOADED and is_kis_available():
                try:
                    from kis_official import batch_fetch_prices as _bfp, fetch_daily_chart as _fdc
                    await update_returns_async(_bfp, fetch_chart_fn=_fdc)
                except Exception as e:
                    print(f"[TRACKER] 캐시HIT 수익률 업데이트 오류: {e}")
            return {**cached, "cached": True}

    print(f"[ANALYZE] 시작 — hours={hours} force={force}")
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
    kr_sectors   = analysis.get("kr_market", {}).get("sectors", [])
    sector_names = [s.get("name", "") for s in kr_sectors if s.get("name")]

    # AI 섹터 강도(strength 1~5) 추출 → NEXUS 모멘텀 가중치에 활용
    sector_strength = {
        s.get("name", ""): int(s.get("strength", 3))
        for s in kr_sectors
        if s.get("name") and s.get("strength")
    }

    # 4+5. AI 종목 주가 조회 + NEXUS + ETF/지수 병렬 실행
    nexus_result = {"available": False, "message": "초기화 전", "top": []}
    sector_etfs_live = {}
    sector_indices_live = {}

    if not _NEXUS_LOADED:
        nexus_result = {"available": False, "message": "nexus 모듈 로드 실패", "top": []}
    elif not is_kis_available():
        nexus_result = {"available": False, "message": "KIS API 키 미설정", "top": []}

    if _NEXUS_LOADED and is_kis_available():
        ai_failed   = (ai_engine == "error" or not sector_names)
        safe_sectors = sector_names if sector_names else []

        # AI 종목 주가 조회 coroutine
        async def _fetch_ai_stock_prices():
            kr_stocks = analysis.get("kr_market", {}).get("stocks", [])
            if not kr_stocks: return
            try:
                from kis_official import batch_fetch_prices as _bfp
                ai_codes = [s.get("code","") for s in kr_stocks if s.get("code","")]
                ai_prices = await _bfp(ai_codes)
                for s in kr_stocks:
                    code = s.get("code", "")
                    if code and code in ai_prices:
                        pd = ai_prices[code]
                        s["price_data"] = {"close": pd.get("price", 0),
                                           "chg_pct": pd.get("change_rate", 0)}
            except Exception:
                pass

        async def _fetch_etfs():
            if not safe_sectors: return {}
            try:
                return await asyncio.wait_for(
                    fetch_sector_etfs(safe_sectors), timeout=10.0)
            except Exception: return {}

        async def _fetch_indices():
            if not safe_sectors: return {}
            try:
                return await asyncio.wait_for(
                    fetch_sector_indices(safe_sectors), timeout=10.0)
            except Exception: return {}

        # NEXUS + AI주가 + ETF + 지수 동시 실행
        try:
            results = await asyncio.gather(
                asyncio.wait_for(
                    run_nexus(
                        safe_sectors,
                        top_n=3,
                        ai_failed=ai_failed,
                        sector_strength=sector_strength,
                    ),
                    timeout=80.0,
                ),
                _fetch_ai_stock_prices(),
                _fetch_etfs(),
                _fetch_indices(),
                return_exceptions=True,
            )
            nx, _, etf_r, idx_r = results
            nexus_result      = nx if isinstance(nx, dict) else {"available": False, "message": str(nx)[:80], "top": []}
            sector_etfs_live  = etf_r if isinstance(etf_r, dict) else {}
            sector_indices_live = idx_r if isinstance(idx_r, dict) else {}
        except Exception as e:
            nexus_result = {"available": False, "message": f"NEXUS 오류: {str(e)[:80]}", "top": []}

    analyzed_at = datetime.now().isoformat()

    # NEXUS 추천 종목 성과 추적 저장 + 기존 추천 수익률 자동 업데이트
    if _TRACKER_LOADED:
        try:
            if nexus_result.get("available") and nexus_result.get("top"):
                save_recommendations(nexus_result["top"], analyzed_at)
            # 기존 추천 종목 수익률 업데이트 (거래일 기반 정확한 d1/d3/d5/d10)
            if is_kis_available():
                from kis_official import batch_fetch_prices as _bfp, fetch_daily_chart as _fdc
                await update_returns_async(_bfp, fetch_chart_fn=_fdc)
        except Exception as e:
            print(f"[TRACKER] 오류: {e}")

    # 순환매 섹터 트래킹 — 장 마감 후 분석 시 자동 기록
    if _SECTOR_TRACKER_LOADED and not nexus_result.get("market_open", True):
        try:
            ai_sectors = nexus_result.get("sectors_searched", [])
            kospi_chg  = krx_indices.get("kospi", {}).get("chg_pct", 0)
            top3_names = [s["name"] for s in nexus_result.get("top", [])]
            asyncio.create_task(
                record_daily_sectors(ai_sectors, kospi_chg, top3_names)
            )
            print(f"[SECTOR_TRACKER] 기록 태스크 시작 — 섹터={ai_sectors}")
        except Exception as e:
            print(f"[SECTOR_TRACKER] 트리거 오류: {e}")

    result = {
        "analyzed_at": analyzed_at,
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
        "cached": False,
    }

    # 캐시 저장 (NEXUS 성공 시에만 캐싱 — 실패 결과는 캐싱 안 함)
    if nexus_result.get("available") or ai_engine != "error":
        _cache_set(cache_key, result)
        print(f"[CACHE] STORED — hours={hours}")

    return result


@app.get("/rotation")
def rotation(days: int = Query(default=10, ge=1, le=90)):
    """
    순환매 섹터 현황 + 매집 감지 + 예측
    - 최근 N일 섹터 성과 트렌드
    - 비주목 섹터 매집 경보 (accum_alert)
    - 내일 주목 섹터 예측 (데이터 7일 이상 시)
    """
    if not _SECTOR_TRACKER_LOADED:
        return JSONResponse({"error": "sector_tracker 비활성화"}, status_code=503)
    try:
        return get_rotation_status(days)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/rotation/sector/{sector_key}")
def rotation_sector(sector_key: str, days: int = Query(default=14, ge=1, le=90)):
    """특정 섹터의 N일 트렌드 조회"""
    if not _SECTOR_TRACKER_LOADED:
        return JSONResponse({"error": "sector_tracker 비활성화"}, status_code=503)
    try:
        return {
            "sector": sector_key,
            "days":   days,
            "trend":  get_sector_trend(sector_key, days),
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/rotation/record")
async def rotation_record_manual():
    """수동으로 오늘 섹터 성과 기록 (테스트/강제 실행용)"""
    if not _SECTOR_TRACKER_LOADED:
        return JSONResponse({"error": "sector_tracker 비활성화"}, status_code=503)
    if not is_kis_available():
        return JSONResponse({"error": "KIS API 미설정"}, status_code=503)
    try:
        record = await record_daily_sectors([], 0.0, [])
        return {"success": True, "date": record.get("date"), "sectors": len(record.get("sectors", {}))}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/etf/compositions/{etf_code}")
async def etf_compositions(etf_code: str):
    """
    ETF 구성종목 조회 (KIS FHPST02400000)
    etf_code: ETF 종목코드 6자리 (예: 487240)
    """
    if not is_kis_available():
        return JSONResponse({"error": "KIS API 미설정"}, status_code=503)
    try:
        from kis_official import fetch_etf_compositions
        stocks = await fetch_etf_compositions(etf_code)
        return {
            "etf_code": etf_code,
            "count":    len(stocks),
            "stocks":   stocks,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/performance")
def performance():
    """
    NEXUS 추천 성과 조회
    - 등급별(HIGH/MID/LOW) 평균 수익률 및 승률
    - 섹터별 성과 통계
    - 최근 30개 추천 이력
    """
    if not _TRACKER_LOADED:
        return JSONResponse({"error": "tracker 모듈 비활성화"}, status_code=503)
    try:
        return get_performance_stats()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/performance/{code}")
def performance_delete(code: str, rec_date: str = Query(..., description="삭제할 추천일 (YYYY-MM-DD)")):
    """
    특정 추천 기록 삭제
    code: 종목코드 (예: 005930)
    rec_date: 추천일 (예: 2026-05-05)
    """
    if not _TRACKER_LOADED:
        return JSONResponse({"error": "tracker 모듈 비활성화"}, status_code=503)
    try:
        ok = delete_record(code, rec_date)
        if ok:
            return {"success": True, "message": f"{code} ({rec_date}) 삭제 완료"}
        return JSONResponse({"success": False, "message": "해당 기록 없음"}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


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


# ── 종목 검색 사전 (sector_stocks + 주요 대형주) ─────────────────────────
def _build_stock_dict() -> dict:
    """코드→이름 사전 구성"""
    from sector_stocks import SECTOR_STOCKS
    d = {}
    for sk, stocks in SECTOR_STOCKS.items():
        for s in stocks:
            d[s["code"]] = s["name"]
    # 주요 대형주 보완 (sector_stocks 미등록 종목)
    extra = [
        ("005930","삼성전자"),("000660","SK하이닉스"),("005380","현대차"),
        ("035420","NAVER"),("035720","카카오"),("000270","기아"),
        ("051910","LG화학"),("068270","셀트리온"),("105560","KB금융"),
        ("055550","신한지주"),("086790","하나금융지주"),("138040","메리츠금융지주"),
        ("032830","삼성생명"),("009830","한화솔루션"),("010950","S-Oil"),
        ("012330","현대모비스"),("028260","삼성물산"),("096770","SK이노베이션"),
        ("017670","SK텔레콤"),("030200","KT"),("032640","LG유플러스"),
        ("066570","LG전자"),("003550","LG"),("034730","SK"),
        ("011200","HMM"),("042660","한화오션"),("009540","HD현대중공업"),
        ("003490","대한항공"),("248070","솔루엠"),("240810","원익IPS"),
        ("095340","ISC"),("058470","리노공업"),("042700","한미반도체"),
        ("036830","솔브레인홀딩스"),("006120","SK디스커버리"),
    ]
    for code, name in extra:
        if code not in d:
            d[code] = name
    return d

_STOCK_DICT: dict = {}


@app.get("/search")
def stock_search(q: str = Query(..., description="종목명 또는 코드")):
    """종목명/코드 자동완성 — 최대 8개 반환"""
    global _STOCK_DICT
    if not _STOCK_DICT:
        _STOCK_DICT = _build_stock_dict()

    q = q.strip()
    if not q:
        return []

    # 6자리 숫자 → 코드 직접 조회
    if q.isdigit() and len(q) == 6:
        name = _STOCK_DICT.get(q, "")
        return [{"code": q, "name": name or q}]

    # 종목명 부분 일치 검색
    results = [
        {"code": c, "name": n}
        for c, n in _STOCK_DICT.items()
        if q in n
    ][:8]
    return results


@app.get("/score")
async def score(code: str = Query(..., description="종목코드 6자리")):
    """
    개별 종목 NEXUS 점수 조회
    기존 분석 파이프라인과 동일한 산식 적용
    """
    global _STOCK_DICT
    if not _STOCK_DICT:
        _STOCK_DICT = _build_stock_dict()

    code = code.strip().zfill(6)

    if not is_kis_available():
        return JSONResponse({"error": "KIS API 미설정"}, status_code=503)

    try:
        from kis_official import fetch_daily_chart, batch_fetch_prices, fetch_investor_trend
        from technical import calc_nexus_score
        from datetime import datetime, time as dtime

        # 병렬 조회
        chart_task    = fetch_daily_chart(code)
        price_task    = batch_fetch_prices([code])
        inv_task      = fetch_investor_trend(code)

        chart, price_map, inv_map = await asyncio.gather(
            chart_task, price_task, inv_task,
            return_exceptions=True
        )

        # 차트 데이터
        if isinstance(chart, Exception) or not chart:
            return JSONResponse({"error": "차트 데이터 조회 실패"}, status_code=404)

        bars = chart.get("bars", [])
        if len(bars) < 20:
            return JSONResponse({"error": f"데이터 부족 ({len(bars)}일)"}, status_code=404)

        # 현재가 데이터
        pd_ = price_map.get(code, {}) if isinstance(price_map, dict) else {}
        inv = inv_map if isinstance(inv_map, dict) else {}

        # 종목명
        name = pd_.get("name") or chart.get("name") or _STOCK_DICT.get(code, code)

        # 52주 고저 / 시총
        w52h = pd_.get("high_52w") or chart.get("week52_high", 0)
        w52l = pd_.get("low_52w")  or chart.get("week52_low", 0)
        mktcap = pd_.get("mktcap", 0)

        stock_meta = {
            "week52_high": w52h,
            "week52_low":  w52l,
            "mktcap":      mktcap,
        }

        # 장 중 여부
        now = datetime.now()
        market_open = (
            dtime(9, 0) <= now.time() <= dtime(15, 30)
            and now.weekday() < 5
        )

        # NEXUS 점수 계산 (기존 산식 그대로)
        nexus = calc_nexus_score(bars, stock_meta, inv, pd_, market_open)

        return {
            "code":        code,
            "name":        name,
            "price":       pd_.get("price", bars[-1]["close"] if bars else 0),
            "change_rate": pd_.get("change_rate", 0),
            "mktcap":      mktcap,
            "total":       nexus["total"],
            "grade":       nexus["grade"],
            "breakdown":   nexus["breakdown"],
            "candles":     nexus.get("candles", []),
            "market_open": market_open,
        }

    except Exception as e:
        import traceback
        return JSONResponse({"error": str(e), "trace": traceback.format_exc()[:300]}, status_code=500)


@app.get("/")
def root():
    return {"status": "ok", "service": "StockIntel", "version": "4.1"}
