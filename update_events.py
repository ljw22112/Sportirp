#!/usr/bin/env python3
"""
스포트립 대회 데이터 자동 업데이트 스크립트
실행: python scripts/update_events.py
- 스포츠지원포털 크롤링
- TourAPI 축제 데이터 조회
- index.html EVENTS 배열 자동 교체
"""

import re
import json
import os
import datetime
import requests
from bs4 import BeautifulSoup

TODAY = datetime.date.today()
THREE_MONTHS_LATER = TODAY + datetime.timedelta(days=90)
TOUR_API_KEY = os.environ.get("TOUR_API_KEY", "")
SPORT_ICONS = {
    "마라톤": "🏃", "축구": "⚽", "배드민턴": "🏸", "수영": "🏊",
    "사이클": "🚴", "테니스": "🎾", "농구": "🏀", "배구": "🏐",
    "야구": "⚾", "태권도": "🥋", "유도": "🥋", "육상": "🏃",
    "골프": "⛳", "양궁": "🏹", "종합": "🏅", "기타": "🏆"
}
REGION_MAP = {
    "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천",
    "광주": "광주", "대전": "대전", "울산": "울산", "세종": "세종",
    "경기": "경기", "강원": "강원", "충북": "충북", "충남": "충남",
    "전북": "전북", "전남": "전남", "경북": "경북", "경남": "경남",
    "제주": "제주"
}

# ── 고정 대회 (항상 포함) ──────────────────────────────
FIXED_EVENTS = [
    {
        "title": "2026 서울마라톤 (제96회 동아마라톤)",
        "sport": "마라톤", "icon": "🏃",
        "venue": "광화문 광장 (출발) → 잠실올림픽주경기장",
        "address": "서울 종로구 세종대로 172 광화문광장",
        "start": "2026-03-15", "end": "2026-03-15",
        "status": "upcoming", "region": "서울",
        "desc": "국내 최대 공인 풀코스 마라톤. 풀코스 2만명·10km 2만명. IAAF 골드 라벨.",
        "url": "https://www.seoulmarathon.com",
        "participants": "40,000명",
        "lat": 37.5716, "lng": 126.9768
    },
    {
        "title": "2026 경주국제마라톤 (벚꽃마라톤)",
        "sport": "마라톤", "icon": "🏃",
        "venue": "경주 보문단지 (출발·도착)",
        "address": "경북 경주시 보문로 213-1",
        "start": "2026-04-05", "end": "2026-04-05",
        "status": "upcoming", "region": "경북",
        "desc": "벚꽃 만개 시즌 경주 유적지 코스. 불국사·석굴암 인근. 풀·하프·10K.",
        "url": "https://www.gyeongjumarathon.com",
        "participants": "15,000명",
        "lat": 35.8528, "lng": 129.2692
    },
    {
        "title": "2026 JTBC 서울마라톤",
        "sport": "마라톤", "icon": "🏃",
        "venue": "잠실올림픽주경기장",
        "address": "서울 송파구 올림픽로 25",
        "start": "2026-10-18", "end": "2026-10-18",
        "status": "upcoming", "region": "서울",
        "desc": "추첨제 운영, 초보자 친화적 마라톤. 풀코스·하프·10km.",
        "url": "https://www.jtbcmarathon.com",
        "participants": "30,000명",
        "lat": 37.5149, "lng": 127.0738
    },
    {
        "title": "2026 춘천마라톤 (가을의 전설)",
        "sport": "마라톤", "icon": "🏃",
        "venue": "의암호 순환 코스 (춘천종합운동장 출발)",
        "address": "강원 춘천시 스포츠타운길 99",
        "start": "2026-10-25", "end": "2026-10-25",
        "status": "upcoming", "region": "강원",
        "desc": "의암호 절경 코스. 풀코스·하프코스. 국내 대표 가을 마라톤.",
        "url": "https://www.chuncheonmarathon.com",
        "participants": "15,000명",
        "lat": 37.8813, "lng": 127.7298
    },
]

# ── 스포츠지원포털 크롤링 ─────────────────────────────
def crawl_sports_portal():
    """스포츠지원포털 대회 일정 크롤링"""
    events = []
    headers = {"User-Agent": "Mozilla/5.0 (compatible; SpoTrip-Bot/1.0)"}
    urls = [
        "https://www.sports.or.kr/sports/competition/schedule.do",
        "https://sportal.or.kr/",
    ]
    for url in urls:
        try:
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "lxml")
            # 대회명·날짜·장소 패턴 추출 (포털 구조에 따라 조정)
            rows = soup.select("table.tbl_list tbody tr, .schedule-item, .event-item")
            for row in rows[:20]:
                cells = row.find_all(["td", "div"])
                if len(cells) < 3:
                    continue
                title = cells[0].get_text(strip=True)
                date_text = cells[1].get_text(strip=True)
                venue = cells[2].get_text(strip=True)
                if not title or len(title) < 4:
                    continue
                start, end = parse_date_range(date_text)
                if not start:
                    continue
                sport = detect_sport(title)
                region = detect_region(venue)
                events.append({
                    "title": title,
                    "sport": sport,
                    "icon": SPORT_ICONS.get(sport, "🏆"),
                    "venue": venue,
                    "address": venue,
                    "start": start,
                    "end": end,
                    "status": calc_status(start, end),
                    "region": region,
                    "desc": f"{sport} 대회. {venue}에서 개최.",
                    "url": url,
                    "participants": "",
                    "lat": 0, "lng": 0
                })
        except Exception as e:
            print(f"  크롤링 실패 ({url}): {e}")
    return events


def crawl_badminton():
    """배드민턴게임 대회 일정 크롤링"""
    events = []
    try:
        url = "https://www.badmintongame.co.kr/match/list"
        resp = requests.get(url, timeout=8,
                            headers={"User-Agent": "Mozilla/5.0"})
        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select(".match-list-item, table tbody tr")
        for row in rows[:15]:
            cells = row.find_all(["td","div","span"])
            texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]
            if len(texts) < 3:
                continue
            title = texts[0]
            date_text = next((t for t in texts if re.search(r'\d{4}[-./]\d{1,2}', t)), "")
            venue = texts[-1] if len(texts) > 2 else ""
            start, end = parse_date_range(date_text)
            if not start:
                continue
            region = detect_region(venue or title)
            events.append({
                "title": title,
                "sport": "배드민턴", "icon": "🏸",
                "venue": venue, "address": venue,
                "start": start, "end": end,
                "status": calc_status(start, end),
                "region": region,
                "desc": f"배드민턴 대회. {venue}에서 개최.",
                "url": url,
                "participants": "",
                "lat": 0, "lng": 0
            })
    except Exception as e:
        print(f"  배드민턴 크롤링 실패: {e}")
    return events


# ── TourAPI 축제 데이터 ───────────────────────────────
def fetch_festivals():
    """TourAPI searchFestival1 로 향후 3개월 축제 조회"""
    if not TOUR_API_KEY:
        print("  TOUR_API_KEY 없음 → 축제 조회 스킵")
        return []
    try:
        url = "https://apis.data.go.kr/B551011/KorService2/searchFestival1"
        params = {
            "serviceKey": TOUR_API_KEY,
            "MobileOS": "ETC", "MobileApp": "SpoTrip",
            "_type": "json",
            "eventStartDate": TODAY.strftime("%Y%m%d"),
            "eventEndDate": THREE_MONTHS_LATER.strftime("%Y%m%d"),
            "numOfRows": "20",
            "arrange": "A",
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        items = data.get("response",{}).get("body",{}).get("items",{}).get("item",[])
        if isinstance(items, dict):
            items = [items]
        festivals = []
        for item in items:
            festivals.append({
                "title": item.get("title",""),
                "sport": "축제", "icon": "🎪",
                "venue": item.get("addr1",""),
                "address": item.get("addr1",""),
                "start": fmt_date(item.get("eventstartdate","")),
                "end":   fmt_date(item.get("eventenddate","")),
                "status": "upcoming",
                "region": detect_region(item.get("addr1","")),
                "desc": f"지역 축제·행사. {item.get('addr1','')}",
                "url": "",
                "participants": "",
                "lat": float(item.get("mapy",0) or 0),
                "lng": float(item.get("mapx",0) or 0),
            })
        print(f"  TourAPI 축제 {len(festivals)}건 조회")
        return festivals
    except Exception as e:
        print(f"  TourAPI 축제 조회 실패: {e}")
        return []


# ── 유틸 함수 ────────────────────────────────────────
def parse_date_range(text):
    """날짜 문자열에서 시작일·종료일 추출"""
    text = text.replace("/", "-").replace(".", "-")
    # 2026-03-15 ~ 2026-03-17
    m = re.search(r'(\d{4}-\d{1,2}-\d{1,2})\s*[~\-~]\s*(\d{4}-\d{1,2}-\d{1,2})', text)
    if m:
        return fmt_date(m.group(1)), fmt_date(m.group(2))
    # 단일 날짜
    m = re.search(r'(\d{4}-\d{1,2}-\d{1,2})', text)
    if m:
        d = fmt_date(m.group(1))
        return d, d
    # 20260315
    m = re.search(r'(\d{8})', text)
    if m:
        d = fmt_date(m.group(1))
        return d, d
    return None, None

def fmt_date(s):
    s = re.sub(r'[^0-9]', '', s)
    if len(s) == 8:
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    if len(s) >= 10:
        return s[:10]
    return s

def detect_sport(title):
    for k in SPORT_ICONS:
        if k in title:
            return k
    return "기타"

def detect_region(text):
    for k, v in REGION_MAP.items():
        if k in text:
            return v
    return "기타"

def calc_status(start, end):
    try:
        s = datetime.date.fromisoformat(start)
        e = datetime.date.fromisoformat(end)
        if e < TODAY:   return "done"
        if s <= TODAY:  return "ongoing"
        return "upcoming"
    except:
        return "upcoming"


# ── HTML EVENTS 배열 교체 ─────────────────────────────
def build_events_js(events):
    """Python list → JS EVENTS 배열 문자열"""
    lines = ["let EVENTS=[\n"]
    for i, e in enumerate(events):
        desc  = e.get('desc','').replace("'", "\\'")
        title = e.get('title','').replace("'", "\\'")
        venue = e.get('venue','').replace("'", "\\'")
        addr  = e.get('address','').replace("'", "\\'")
        lines.append(f"""  {{
    id:{i}, title:'{title}',
    sport:'{e.get('sport','기타')}', icon:'{e.get('icon','🏆')}',
    venue:'{venue}',
    address:'{addr}',
    start:'{e.get('start','')}', end:'{e.get('end','')}',
    status:'{e.get('status','upcoming')}', region:'{e.get('region','기타')}',
    desc:'{desc}',
    url:'{e.get('url','')}', participants:'{e.get('participants','')}',
    lat:{e.get('lat',0)}, lng:{e.get('lng',0)}
  }}""")
        if i < len(events)-1:
            lines.append(",\n")
    lines.append("\n];")
    return "".join(lines)


def update_html(events):
    """index.html의 EVENTS 배열 교체"""
    path = "index.html"
    if not os.path.exists(path):
        print(f"  ❌ {path} 파일 없음")
        return False
    with open(path, encoding="utf-8") as f:
        html = f.read()

    # EVENTS 배열 찾아서 교체
    pattern = r'let EVENTS=\[.*?\];'
    new_events_js = build_events_js(events)
    new_html, n = re.subn(pattern, new_events_js, html, flags=re.DOTALL)
    if n == 0:
        print("  ❌ EVENTS 배열 패턴 못 찾음")
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_html)
    print(f"  ✅ index.html 업데이트 완료 ({n}곳 교체)")
    return True


def save_last_update(events):
    """마지막 업데이트 정보 저장"""
    info = {
        "updated_at": datetime.datetime.now().isoformat(),
        "event_count": len(events),
        "events_summary": [
            {"title": e["title"], "start": e["start"], "region": e["region"]}
            for e in events
        ]
    }
    os.makedirs("scripts", exist_ok=True)
    with open("scripts/last_update.json", "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=2)
    print(f"  ✅ last_update.json 저장")


# ── 메인 ────────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"스포트립 대회 데이터 자동 업데이트")
    print(f"실행일: {TODAY}  |  수집 범위: ~{THREE_MONTHS_LATER}")
    print(f"{'='*50}\n")

    all_events = []

    # 1) 고정 대회 (항상 포함)
    fixed = [e for e in FIXED_EVENTS if e["status"] != "done" or
             datetime.date.fromisoformat(e["end"]) >= TODAY - datetime.timedelta(days=30)]
    print(f"[1] 고정 대회: {len(fixed)}건")
    all_events.extend(fixed)

    # 2) 스포츠지원포털 크롤링
    print("[2] 스포츠지원포털 크롤링...")
    portal_events = crawl_sports_portal()
    print(f"    수집: {len(portal_events)}건")
    all_events.extend(portal_events)

    # 3) 배드민턴게임 크롤링
    print("[3] 배드민턴게임 크롤링...")
    bmt_events = crawl_badminton()
    print(f"    수집: {len(bmt_events)}건")
    all_events.extend(bmt_events)

    # 4) TourAPI 축제
    print("[4] TourAPI 축제 조회...")
    festivals = fetch_festivals()
    all_events.extend(festivals)

    # 5) 중복 제거 (제목 유사도 기준)
    seen_titles = set()
    unique_events = []
    for e in all_events:
        key = re.sub(r'\s+', '', e["title"])[:15]
        if key not in seen_titles:
            seen_titles.add(key)
            unique_events.append(e)

    # 6) 날짜순 정렬 (종료 대회는 뒤로)
    def sort_key(e):
        status_order = {"ongoing": 0, "upcoming": 1, "done": 2}
        return (status_order.get(e["status"], 9), e.get("start","9999"))
    unique_events.sort(key=sort_key)

    # 상위 20개만 유지
    unique_events = unique_events[:20]

    print(f"\n[결과] 최종 대회: {len(unique_events)}건")
    for i, e in enumerate(unique_events):
        print(f"  {i:2d}. [{e['status']:8s}] {e['title'][:30]} ({e['region']} / {e['start']})")

    # 7) HTML 업데이트
    print("\n[5] index.html 업데이트...")
    update_html(unique_events)
    save_last_update(unique_events)

    print(f"\n✅ 완료! {len(unique_events)}개 대회 데이터가 업데이트되었습니다.\n")


if __name__ == "__main__":
    main()
