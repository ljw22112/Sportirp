# 스포트립 자동 업데이트 시스템

## 구조
```
.github/workflows/update-events.yml  ← GitHub Actions (매주 월요일 실행)
scripts/update_events.py             ← 데이터 수집·업데이트 스크립트
scripts/last_update.json             ← 마지막 업데이트 정보 (자동 생성)
```

## 설정 방법

### 1. TourAPI 키 등록
GitHub 저장소 → Settings → Secrets → Actions → New repository secret
- Name: `TOUR_API_KEY`
- Value: `0c75600eb379ddec6179b713ae087d0739d3cb22e8cdddcb76e29c4ee664ad9e`

### 2. 파일 배치
```
저장소 루트/
├── index.html                        ← 스포트립 앱
├── .github/workflows/update-events.yml
└── scripts/
    └── update_events.py
```

### 3. 자동 실행 확인
- Actions 탭 → "대회 데이터 자동 업데이트" 워크플로우
- 매주 월요일 오전 9시 KST 자동 실행
- 수동: "Run workflow" 버튼

## 데이터 수집 우선순위
| 순위 | 출처 | 방식 |
|------|------|------|
| 1 | 고정 대회 (마라톤 등) | 하드코딩 |
| 2 | 스포츠지원포털 | 크롤링 |
| 3 | 배드민턴게임 | 크롤링 |
| 4 | TourAPI 축제 | REST API |

## 로컬 테스트
```bash
pip install requests beautifulsoup4 lxml
TOUR_API_KEY=your_key python scripts/update_events.py
```
