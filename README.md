# StockIntel v2 — 완전 무료 버전

Google News + Naver News 수집 → Gemini/Groq AI 분석 → KRX 주가 연동
**Claude API 불필요 — 완전 무료 운영 가능**

---

## 필요한 API 키 (모두 무료)

| API | 발급 주소 | 비용 |
|-----|----------|------|
| **Gemini API** ← AI 분석 | aistudio.google.com | 완전 무료 (분당 15회) |
| **Groq API** ← AI 백업 | console.groq.com | 완전 무료 (일 14,400회) |
| Google Custom Search | console.cloud.google.com | 무료 100건/일 |
| Naver News | developers.naver.com | 무료 25,000건/일 |
| KRX OpenAPI | openapi.krx.co.kr | 무료 (승인 필요) |

---

## Gemini API 키 발급 (3분)

1. **aistudio.google.com** 접속
2. 구글 계정으로 로그인
3. 상단 **Get API Key** 클릭
4. **Create API key** → 키 복사 (AIza로 시작)

## Groq API 키 발급 (3분)

1. **console.groq.com** 접속
2. 구글/GitHub 계정으로 로그인
3. **API Keys → Create API Key**
4. 키 복사 (gsk_로 시작)

---

## 배포 순서

### STEP 1 — GitHub에 올리기
1. github.com → New Repository → 이름: `stockintel`
2. 이 폴더 내용 전체 업로드

### STEP 2 — 백엔드: Railway
1. **railway.app** → GitHub 로그인
2. New Project → Deploy from GitHub → `stockintel`
3. Root Directory: `backend`
4. Variables 탭에 입력:
```
GEMINI_API_KEY     = AIza...   ← 필수 (무료)
GROQ_API_KEY       = gsk_...   ← 추천 (무료 백업)
GOOGLE_API_KEY     = AIza...   ← 있으면 입력
GOOGLE_CX          = 017...    ← 있으면 입력
NAVER_CLIENT_ID    = ...       ← 있으면 입력
NAVER_CLIENT_SECRET= ...       ← 있으면 입력
KRX_AUTH_KEY       = ...       ← 승인 후 입력
```
5. Deploy → URL 복사 (예: `https://stockintel-xxx.railway.app`)

### STEP 3 — 프론트엔드: Vercel
1. `frontend/index.html` 열기
2. `const API_BASE = "https://your-app.railway.app"` → Railway URL로 교체
3. **vercel.com** → New Project → frontend 폴더 → Deploy
4. 완료! 공유 URL 생성됨

---

## 비용 요약

| 항목 | 비용 |
|------|------|
| Gemini API | **무료** |
| Groq API | **무료** |
| Google/Naver 뉴스 | **무료** |
| KRX API | **무료** |
| Railway 백엔드 | **무료** (월 500시간) / 상시: $5/월 |
| Vercel 프론트 | **무료** |
| **합계** | **0원** (상시 운영 시 월 7,000원) |
