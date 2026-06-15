# 스포트립 자동 크롤러

스포츠 대회 포털에서 매일 자동으로 대회 데이터를 수집해 `index.html`을 업데이트합니다.

## 파일 구조

```
저장소 루트/
├── index.html                          ← 스포트립 앱
├── .github/
│   └── workflows/
│       └── crawl.yml                   ← GitHub Actions (매일 새벽 3시)
└── scripts/
    ├── crawler.py                      ← 크롤러 메인 스크립트
    ├── requirements.txt                ← Python 의존성
    ├── events.json                     ← 수집 결과 (자동 생성)
    └── crawler.log                     ← 실행 로그 (자동 생성)
```

## 수집 포털 (5곳)

| 포털 | URL | 수집 내용 |
|------|-----|----------|
| 스포츠지원포털 | g1.sports.or.kr | 전문체육 대회 일정 |
| 생활체육포털 | sportal.or.kr | 생활체육 대회 일정 |
| 배드민턴게임 | badmintongame.co.kr | 배드민턴 대회 |
| 마라톤온라인 | marathon.pe.kr | 마라톤·달리기 대회 |
| 대한수영연맹 | korswim.co.kr | 수영 대회 |

## 로컬 실행

```bash
# 1. 의존성 설치
pip install -r scripts/requirements.txt
playwright install chromium

# 2. 1회 즉시 실행
python scripts/crawler.py

# 3. 매일 새벽 3시 자동 반복 (서버 상시 실행 시)
python scripts/crawler.py --watch

# 4. 다른 시간으로 변경 (예: 오전 6시)
python scripts/crawler.py --watch --hour 6
```

## GitHub Actions 자동화

1. 이 파일들을 저장소에 Push
2. Actions 탭 → `crawl.yml` 워크플로우 확인
3. 매일 오전 3시 KST 자동 실행
4. 수동 실행: Actions → `Run workflow`

## 실행 흐름

```
매일 새벽 3시 KST
      ↓
GitHub Actions 서버에서 Playwright 실행
      ↓
5개 포털 순차 크롤링 (JS 렌더링 포함)
      ↓
고정 대회 + 크롤링 결과 병합 → 중복 제거
      ↓
날짜순 정렬 (진행중 → 예정 → 종료)
      ↓
index.html EVENTS 배열 자동 교체
scripts/events.json 저장
      ↓
"🤖 대회 데이터 자동 업데이트" 커밋 & 푸시
      ↓
GitHub Pages 자동 재배포
```

## 출력 형식 (events.json)

```json
{
  "updated_at": "2026-06-16T03:00:00",
  "total": 18,
  "by_source": { "스포츠지원포털": 5, "배드민턴게임": 3, "고정": 4 },
  "by_sport":  { "마라톤": 6, "배드민턴": 4 },
  "by_status": { "upcoming": 12, "ongoing": 2, "done": 4 },
  "events": [...]
}
```
