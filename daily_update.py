#!/usr/bin/env python3
"""
스포트립 일별 자동 업데이트 스크립트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
매일 GitHub Actions에서 실행:
  1) 기존 EVENTS 상태(upcoming/ongoing/done) 자동 갱신
  2) TourAPI에서 신규 스포츠·축제 이벤트 추가
  3) 스포츠 포털 RSS/HTML에서 신규 대회 수집
  4) index.html EVENTS 배열 업데이트
  5) scripts/events_log.json 에 이력 저장
"""

import re, json, os, datetime, logging, time
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# ── 로깅 ──────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scripts/update.log", encoding="utf-8", mode="a"),
    ]
)
log = logging.getLogger("sportrip")

# ── 환경 변수 ─────────────────────────────────────
TOUR_API_KEY = os.environ.get("TOUR_API_KEY", "")
TODAY        = datetime.date.today()
CUTOFF_PAST  = TODAY - datetime.timedelta(days=7)
CUTOFF_FUTURE= TODAY + datetime.timedelta(days=180)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SpoTrip-Bot/2.0; +https://ljw22112.github.io/Sportirip/)",
    "Accept-Language": "ko-KR,ko;q=0.9",
}

SPORT_ICONS = {
    "마라톤":"🏃","달리기":"🏃","하프마라톤":"🏃","육상":"🏃",
    "축구":"⚽","풋살":"⚽",
    "배드민턴":"🏸",
    "수영":"🏊","다이빙":"🏊",
    "사이클":"🚴","자전거":"🚴",
    "테니스":"🎾","스쿼시":"🎾",
    "농구":"🏀","배구":"🏐","야구":"⚾",
    "태권도":"🥋","유도":"🥋","레슬링":"🥋",
    "골프":"⛳","양궁":"🏹","탁구":"🏓","볼링":"🎳",
    "종합":"🏅","체전":"🏅","체육대회":"🏅",
    "축제":"🎪","기타":"🏆",
}

REGION_MAP = {
    "서울":"서울","부산":"부산","대구":"대구","인천":"인천",
    "광주":"광주","대전":"대전","울산":"울산","세종":"세종",
    "경기":"경기","강원":"강원","충북":"충북","충남":"충남",
    "전북":"전북","전남":"전남","경북":"경북","경남":"경남","제주":"제주",
    "수원":"경기","성남":"경기","용인":"경기","고양":"경기",
    "춘천":"강원","원주":"강원","강릉":"강원",
    "청주":"충북","충주":"충북",
    "천안":"충남","아산":"충남",
    "전주":"전북","익산":"전북",
    "목포":"전남","순천":"전남","여수":"전남",
    "포항":"경북","경주":"경북","구미":"경북","안동":"경북",
    "창원":"경남","진주":"경남","김해":"경남","통영":"경남",
    "제주시":"제주","서귀포":"제주",
}

# ─────────────────────────────────────────────────
# 고정 대회 목록 (항상 포함)
# ─────────────────────────────────────────────────
FIXED_EVENTS = [
    {
        "title":"2026 서울마라톤 (제96회 동아마라톤)",
        "sport":"마라톤","icon":"🏃",
        "venue":"광화문광장 (출발) → 잠실올림픽주경기장 (도착)",
        "address":"서울 종로구 세종대로 172 광화문광장",
        "start":"2026-03-15","end":"2026-03-15","region":"서울",
        "desc":"국내 최대 공인 풀코스 마라톤. 풀코스 2만명·10km 2만명. IAAF 골드 라벨.",
        "url":"https://www.seoulmarathon.com","participants":"40,000명",
        "lat":37.5716,"lng":126.9768,
    },
    {
        "title":"제106회 전국체육대회 (부산)",
        "sport":"종합","icon":"🏅",
        "venue":"부산 아시아드주경기장",
        "address":"부산 서구 월드컵대로 344",
        "start":"2025-10-17","end":"2025-10-23","region":"부산",
        "desc":"25년 만에 부산 개최. 82개 경기장·50개 종목·약 3만명 참가.",
        "url":"https://meet.sports.or.kr","participants":"30,000명",
        "lat":35.1318,"lng":129.0140,
    },
    {
        "title":"2026 경주국제마라톤 (벚꽃마라톤)",
        "sport":"마라톤","icon":"🏃",
        "venue":"경주 보문단지 (출발·도착)",
        "address":"경북 경주시 보문로 213-1 경주보문관광단지",
        "start":"2026-04-05","end":"2026-04-05","region":"경북",
        "desc":"벚꽃 만개 시즌 경주 유적지 코스. 불국사·석굴암 인근. 풀·하프·10K.",
        "url":"https://www.gyeongjumarathon.com","participants":"15,000명",
        "lat":35.8528,"lng":129.2692,
    },
    {
        "title":"2025 전국생활체육대축전 배드민턴",
        "sport":"배드민턴","icon":"🏸",
        "venue":"충주 실내배드민턴장",
        "address":"충북 충주시 충원대로 268",
        "start":"2026-02-07","end":"2026-02-08","region":"충북",
        "desc":"전국 동호인 배드민턴 오픈대회. 급수별 복식·혼합복식 운영.",
        "url":"https://www.badmintongame.co.kr","participants":"500명",
        "lat":36.9910,"lng":127.9259,
    },
    {
        "title":"2025 제20회 제주 한라배 전국수영대회",
        "sport":"수영","icon":"🏊",
        "venue":"제주실내수영장",
        "address":"제주 제주시 오남로 14",
        "start":"2025-04-12","end":"2025-04-16","region":"제주",
        "desc":"전국 규모 공인 수영 대회. 다이빙 포함. 초등~일반부.",
        "url":"https://www.korswim.co.kr","participants":"1,200명",
        "lat":33.5007,"lng":126.5237,
    },
    {
        "title":"2026 JTBC 서울마라톤",
        "sport":"마라톤","icon":"🏃",
        "venue":"잠실올림픽주경기장",
        "address":"서울 송파구 올림픽로 25",
        "start":"2026-10-18","end":"2026-10-18","region":"서울",
        "desc":"추첨제 운영. 초보자 친화적. 풀·하프·10km. 잠실 올림픽공원 코스.",
        "url":"https://www.jtbcmarathon.com","participants":"30,000명",
        "lat":37.5149,"lng":127.0738,
    },
    {
        "title":"2026 제8회 세종협회장기 배드민턴",
        "sport":"배드민턴","icon":"🏸",
        "venue":"세종 한솔체육관",
        "address":"세종특별자치시 한솔동 8",
        "start":"2026-02-07","end":"2026-02-08","region":"세종",
        "desc":"세종특별자치시 배드민턴협회 주최. 전국 참가 가능.",
        "url":"https://www.badmintongame.co.kr","participants":"300명",
        "lat":36.4800,"lng":127.2890,
    },
    {
        "title":"2026 춘천마라톤 (가을의 전설)",
        "sport":"마라톤","icon":"🏃",
        "venue":"의암호 순환 코스 (춘천종합운동장 출발)",
        "address":"강원 춘천시 스포츠타운길 99",
        "start":"2026-10-25","end":"2026-10-25","region":"강원",
        "desc":"의암호 절경 코스. 풀·하프코스. 국내 대표 가을 마라톤.",
        "url":"https://www.chuncheonmarathon.com","participants":"15,000명",
        "lat":37.8813,"lng":127.7298,
    },
]

# ─────────────────────────────────────────────────
# 유틸 함수
# ─────────────────────────────────────────────────

def fmt_date(s):
    digits = re.sub(r"\D","",str(s))
    if len(digits)==8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    m = re.match(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(s))
    if m: return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    return str(s)[:10]

def parse_date_range(text):
    if not text: return None, None
    text = re.sub(r"[./]","-",str(text))
    dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", text)
    if len(dates)>=2: return fmt_date(dates[0]), fmt_date(dates[1])
    if len(dates)==1: return fmt_date(dates[0]), fmt_date(dates[0])
    digits = re.findall(r"\d{8}", text)
    if digits: return fmt_date(digits[0]), fmt_date(digits[-1])
    return None, None

def calc_status(start, end):
    try:
        s = datetime.date.fromisoformat(start)
        e = datetime.date.fromisoformat(end)
        if e < TODAY:   return "done"
        if s <= TODAY:  return "ongoing"
        return "upcoming"
    except: return "upcoming"

def is_in_range(start, end):
    try:
        s = datetime.date.fromisoformat(start)
        e = datetime.date.fromisoformat(end)
        return e >= CUTOFF_PAST and s <= CUTOFF_FUTURE
    except: return False

def detect_sport(title):
    for k in SPORT_ICONS:
        if k in title and k not in ("기타","종합"):
            return k
    if any(k in title for k in ["체전","체육대회","종합대회"]): return "종합"
    return "기타"

def detect_region(text):
    for k,v in REGION_MAP.items():
        if k in text: return v
    return "기타"

def make_event(title, sport, venue, address, start, end,
               region, url="", desc="", lat=0.0, lng=0.0,
               participants="", source="수집"):
    return {
        "title":    title.strip()[:80],
        "sport":    sport,
        "icon":     SPORT_ICONS.get(sport,"🏆"),
        "venue":    venue.strip()[:60],
        "address":  address.strip()[:80],
        "start":    start,
        "end":      end,
        "status":   calc_status(start, end),
        "region":   region,
        "desc":     desc.strip()[:120],
        "url":      url,
        "participants": participants,
        "lat":      lat,
        "lng":      lng,
        "_source":  source,
        "_date":    TODAY.isoformat(),
    }

def fetch(url, timeout=10):
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        r.raise_for_status()
        return r
    except Exception as e:
        log.warning(f"  fetch 실패 ({url[:60]}): {e}")
        return None

# ─────────────────────────────────────────────────
# STEP 1: 기존 이벤트 상태 갱신
# ─────────────────────────────────────────────────

def refresh_statuses(events):
    """기존 EVENTS의 status 필드를 오늘 날짜 기준으로 갱신"""
    updated = 0
    for e in events:
        new_status = calc_status(e.get("start",""), e.get("end",""))
        if e.get("status") != new_status:
            e["status"] = new_status
            updated += 1
    log.info(f"  상태 갱신: {updated}건")
    return events

# ─────────────────────────────────────────────────
# STEP 2: TourAPI 신규 축제·스포츠 이벤트
# ─────────────────────────────────────────────────

def fetch_tourapi_events():
    if not TOUR_API_KEY:
        log.info("  TOUR_API_KEY 없음 → 스킵")
        return []
    events = []
    # 스포츠 행사 (contentTypeId=15 축제·행사)
    params = {
        "serviceKey"    : TOUR_API_KEY,
        "MobileOS"      : "ETC",
        "MobileApp"     : "SpoTrip",
        "_type"         : "json",
        "eventStartDate": TODAY.strftime("%Y%m%d"),
        "eventEndDate"  : CUTOFF_FUTURE.strftime("%Y%m%d"),
        "numOfRows"     : "30",
        "arrange"       : "B",
    }
    url = "https://apis.data.go.kr/B551011/KorService2/searchFestival1"
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data  = resp.json()
        items = data.get("response",{}).get("body",{}).get("items",{}).get("item",[])
        if isinstance(items, dict): items = [items]
        for item in items:
            title = item.get("title","").strip()
            if not title: continue
            start = fmt_date(item.get("eventstartdate",""))
            end   = fmt_date(item.get("eventenddate",""))
            if not start or not is_in_range(start, end): continue
            addr  = item.get("addr1","")
            # 스포츠 키워드 포함된 것만 필터
            sport_keywords = ["마라톤","달리기","배드민턴","수영","축구","테니스","사이클","야구","농구","체전","체육대회","스포츠"]
            if not any(kw in title for kw in sport_keywords):
                continue
            events.append(make_event(
                title=title,
                sport=detect_sport(title),
                venue=addr, address=addr,
                start=start, end=end,
                region=detect_region(addr),
                desc=f"한국관광공사 TourAPI 등록 행사. {addr}",
                lat=float(item.get("mapy",0) or 0),
                lng=float(item.get("mapx",0) or 0),
                source="TourAPI"
            ))
        log.info(f"  TourAPI 신규: {len(events)}건")
    except Exception as e:
        log.error(f"  TourAPI 오류: {e}")
    return events

# ─────────────────────────────────────────────────
# STEP 3: 스포츠 포털 경량 크롤링
# ─────────────────────────────────────────────────

def crawl_sports_portal():
    """스포츠지원포털 경량 크롤링 (requests only)"""
    events = []
    urls = [
        "https://g1.sports.or.kr/sports/competition/schedule.do",
        "https://www.sports.or.kr/sports/competition/schedule.do",
    ]
    for url in urls:
        resp = fetch(url)
        if not resp: continue
        soup = BeautifulSoup(resp.text, "lxml")
        for row in soup.select("table tbody tr"):
            tds = row.find_all("td")
            if len(tds) < 3: continue
            title    = tds[0].get_text(" ", strip=True)
            date_raw = tds[1].get_text(" ", strip=True)
            venue    = tds[2].get_text(" ", strip=True)
            if not title or len(title) < 3: continue
            start, end = parse_date_range(date_raw)
            if not start or not is_in_range(start, end): continue
            link = row.select_one("a[href]")
            href = link["href"] if link else url
            if href.startswith("/"): href = "https://g1.sports.or.kr" + href
            events.append(make_event(
                title=title, sport=detect_sport(title),
                venue=venue, address=venue,
                start=start, end=end,
                region=detect_region(venue+title),
                url=href, source="스포츠지원포털"
            ))
        time.sleep(1.5)
    log.info(f"  스포츠지원포털: {len(events)}건")
    return events

def crawl_badminton():
    """배드민턴게임 크롤링"""
    events = []
    resp = fetch("https://www.badmintongame.co.kr/match/list")
    if not resp: return events
    soup = BeautifulSoup(resp.text, "lxml")
    for row in soup.select("table tbody tr, .match-item"):
        tds = row.find_all(["td","div"], recursive=False)
        texts = [t.get_text(" ",strip=True) for t in tds if t.get_text(strip=True)]
        if len(texts) < 2: continue
        title = texts[0]
        date_raw = next((t for t in texts if re.search(r"\d{4}[-./]\d{1,2}",t)), "")
        venue    = texts[-1] if len(texts)>=3 else ""
        if not title or len(title)<4: continue
        start, end = parse_date_range(date_raw)
        if not start or not is_in_range(start, end): continue
        link = row.select_one("a[href]")
        href = link["href"] if link else "https://www.badmintongame.co.kr"
        if href.startswith("/"): href = "https://www.badmintongame.co.kr" + href
        events.append(make_event(
            title=title, sport="배드민턴",
            venue=venue, address=venue,
            start=start, end=end,
            region=detect_region(venue+title),
            url=href, source="배드민턴게임"
        ))
    log.info(f"  배드민턴게임: {len(events)}건")
    return events

def crawl_marathon():
    """마라톤온라인 크롤링"""
    events = []
    resp = fetch("http://www.marathon.pe.kr/schedule")
    if not resp: return events
    soup = BeautifulSoup(resp.text, "lxml")
    for row in soup.select("table tbody tr"):
        tds = row.find_all("td")
        if len(tds) < 3: continue
        title    = tds[0].get_text(" ",strip=True)
        date_raw = tds[1].get_text(" ",strip=True)
        venue    = tds[2].get_text(" ",strip=True)
        if not title or len(title)<3: continue
        start, end = parse_date_range(date_raw)
        if not start or not is_in_range(start, end): continue
        link = row.select_one("a[href]")
        href = link["href"] if link else ""
        sport = "마라톤" if any(k in title for k in ["마라톤","달리기","러닝"]) else "육상"
        events.append(make_event(
            title=title, sport=sport,
            venue=venue, address=venue,
            start=start, end=end,
            region=detect_region(venue+title),
            url=href, source="마라톤온라인"
        ))
    log.info(f"  마라톤온라인: {len(events)}건")
    return events

# ─────────────────────────────────────────────────
# STEP 4: 중복 제거
# ─────────────────────────────────────────────────

def dedup(events):
    seen = {}
    result = []
    for e in events:
        key = re.sub(r"[^\w]","",e["title"])[:12]
        if key not in seen:
            seen[key] = e
            result.append(e)
        else:
            old = seen[key]
            # 정보가 더 풍부하면 교체
            if (e["lat"] != 0 and old["lat"] == 0) or \
               len(e.get("desc","")) > len(old.get("desc","")) or \
               (e.get("url") and not old.get("url")):
                idx = result.index(old)
                result[idx] = e
                seen[key] = e
    return result

# ─────────────────────────────────────────────────
# STEP 5: HTML 업데이트
# ─────────────────────────────────────────────────

def events_to_js(events):
    def esc(s): return str(s or "").replace("\\","\\\\").replace("'","\\'").replace("\n"," ")
    lines = ["let EVENTS=[\n"]
    for i, e in enumerate(events):
        comma = "," if i < len(events)-1 else ""
        lines.append(
            f"  {{id:{i},title:'{esc(e['title'])}',sport:'{esc(e['sport'])}',"
            f"icon:'{e['icon']}',venue:'{esc(e['venue'])}',address:'{esc(e['address'])}',"
            f"start:'{e['start']}',end:'{e['end']}',status:'{e['status']}',"
            f"region:'{e['region']}',desc:'{esc(e['desc'])}',url:'{esc(e['url'])}',"
            f"participants:'{esc(e.get('participants',''))}',lat:{e.get('lat',0)},lng:{e.get('lng',0)}}}{comma}\n"
        )
    lines.append("];")
    return "".join(lines)

def update_html(events, path="index.html"):
    p = Path(path)
    if not p.exists():
        log.error(f"{path} 없음")
        return False
    html = p.read_text(encoding="utf-8")
    stamp   = f"// 자동 업데이트: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')} ({len(events)}개 대회)\n"
    html    = re.sub(r"// 자동 업데이트:.*\n", "", html)
    new_js  = stamp + events_to_js(events)
    new_html, n = re.subn(r"let EVENTS\s*=\s*\[[\s\S]*?\];", new_js, html)
    if n == 0:
        log.error("EVENTS 패턴 없음")
        return False
    p.write_text(new_html, encoding="utf-8")
    log.info(f"✅ {path} 업데이트 (EVENTS {len(events)}개)")
    return True

# ─────────────────────────────────────────────────
# STEP 6: 이력 저장
# ─────────────────────────────────────────────────

def save_log(events, added, updated_count):
    log_path = Path("scripts/events_log.json")
    history  = []
    if log_path.exists():
        try: history = json.loads(log_path.read_text(encoding="utf-8"))
        except: pass

    entry = {
        "date":          TODAY.isoformat(),
        "time":          datetime.datetime.now().strftime("%H:%M:%S"),
        "total":         len(events),
        "newly_added":   added,
        "status_updated":updated_count,
        "by_status":     {"upcoming":0,"ongoing":0,"done":0},
        "by_sport":      {},
        "by_source":     {},
    }
    for e in events:
        entry["by_status"][e.get("status","upcoming")] = \
            entry["by_status"].get(e.get("status","upcoming"),0) + 1
        sp  = e.get("sport","기타")
        src = e.get("_source","unknown")
        entry["by_sport"][sp]   = entry["by_sport"].get(sp,0)   + 1
        entry["by_source"][src] = entry["by_source"].get(src,0) + 1

    history.insert(0, entry)
    history = history[:30]  # 최근 30일만 보관
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"✅ scripts/events_log.json 저장 ({len(history)}일 이력)")

# ─────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────

def main():
    log.info("=" * 55)
    log.info(f"스포트립 일별 업데이트  {TODAY}")
    log.info("=" * 55)

    # ── 기존 이벤트 로드 (고정 데이터 기준) ──
    all_events = [dict(e) for e in FIXED_EVENTS]
    log.info(f"\n[STEP 1] 고정 대회 로드: {len(all_events)}건")

    # ── 상태 갱신 ──
    log.info("[STEP 2] 상태(status) 갱신")
    before_statuses = {e["title"]: e.get("status") for e in all_events}
    all_events = refresh_statuses(all_events)
    updated_count = sum(
        1 for e in all_events
        if before_statuses.get(e["title"]) != e.get("status")
    )

    # ── 신규 이벤트 수집 ──
    log.info("[STEP 3] 신규 이벤트 수집")
    new_events = []
    new_events.extend(fetch_tourapi_events())
    new_events.extend(crawl_sports_portal())
    new_events.extend(crawl_badminton())
    new_events.extend(crawl_marathon())
    all_events.extend(new_events)

    # ── 중복 제거 ──
    before = len(all_events)
    all_events = dedup(all_events)
    added = len(all_events) - len(FIXED_EVENTS)
    log.info(f"\n[STEP 4] 중복 제거: {before} → {len(all_events)}건 (신규 +{max(0,added)}건)")

    # ── 정렬 ──
    order = {"ongoing":0,"upcoming":1,"done":2}
    all_events.sort(key=lambda e: (order.get(e.get("status","upcoming"),9), e.get("start","9999")))
    all_events = all_events[:25]

    # ── 결과 출력 ──
    log.info(f"\n{'─'*55}")
    log.info(f"최종: {len(all_events)}건  (신규 +{max(0,added)}건, 상태갱신 {updated_count}건)")
    for i, e in enumerate(all_events):
        src = e.get("_source","")
        log.info(f"  {i:2d}. [{e['status']:8s}] {e['title'][:28]:28s} | {e['region']:4s} | {e['start']} | {src}")

    # ── HTML 업데이트 ──
    log.info("\n[STEP 5] index.html 업데이트")
    update_html(all_events)

    # ── 이력 저장 ──
    log.info("[STEP 6] 이력 저장")
    save_log(all_events, max(0,added), updated_count)

    log.info(f"\n{'='*55}")
    log.info("✅ 일별 업데이트 완료")
    log.info(f"{'='*55}\n")

if __name__ == "__main__":
    main()
