#!/usr/bin/env python3
"""
스포트립 (SpoTrip) — 스포츠 대회 자동 크롤러
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
대상 포털:
  1) 스포츠지원포털  g1.sports.or.kr
  2) 체육포털        sportal.or.kr
  3) 배드민턴게임    badmintongame.co.kr
  4) 마라톤온라인    marathon.pe.kr
  5) 대한수영연맹    korswim.co.kr

실행:
  pip install playwright beautifulsoup4 lxml requests schedule
  playwright install chromium
  python scripts/crawler.py          # 1회 즉시 실행
  python scripts/crawler.py --watch  # 매일 새벽 3시 자동 반복
"""

import re, json, os, time, datetime, logging, argparse
from pathlib import Path

import requests
from bs4 import BeautifulSoup

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    PLAYWRIGHT_OK = True
except ImportError:
    PLAYWRIGHT_OK = False
    print("[WARN] playwright 미설치 → requests 폴백 모드로 실행")

# ── 로깅 ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scripts/crawler.log", encoding="utf-8"),
    ]
)
log = logging.getLogger("sportrip.crawler")

# ── 설정 ──────────────────────────────────────────────
TODAY         = datetime.date.today()
CUTOFF_PAST   = TODAY - datetime.timedelta(days=14)
CUTOFF_FUTURE = TODAY + datetime.timedelta(days=180)
OUT_JSON      = Path("scripts/events.json")
OUT_LOG       = Path("scripts/crawler.log")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9",
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}

SPORT_ICONS = {
    "마라톤":"🏃","달리기":"🏃","하프마라톤":"🏃","10km":"🏃","육상":"🏃",
    "축구":"⚽","풋살":"⚽",
    "배드민턴":"🏸",
    "수영":"🏊","다이빙":"🏊","오픈워터":"🏊",
    "사이클":"🚴","자전거":"🚴","MTB":"🚴",
    "테니스":"🎾","스쿼시":"🎾",
    "농구":"🏀","3x3":"🏀",
    "배구":"🏐","비치발리볼":"🏐",
    "야구":"⚾","소프트볼":"⚾",
    "태권도":"🥋","유도":"🥋","레슬링":"🥋","복싱":"🥋",
    "골프":"⛳","양궁":"🏹","탁구":"🏓","볼링":"🎳",
    "체전":"🏅","체육대회":"🏅","종합":"🏅",
    "기타":"🏆",
}

REGION_MAP = {
    "서울":"서울","부산":"부산","대구":"대구","인천":"인천",
    "광주":"광주","대전":"대전","울산":"울산","세종":"세종",
    "경기":"경기","강원":"강원","충북":"충북","충남":"충남",
    "전북":"전북","전남":"전남","경북":"경북","경남":"경남","제주":"제주",
    "수원":"경기","성남":"경기","용인":"경기","고양":"경기","안산":"경기",
    "춘천":"강원","원주":"강원","강릉":"강원","속초":"강원",
    "청주":"충북","충주":"충북","제천":"충북",
    "천안":"충남","아산":"충남","공주":"충남",
    "전주":"전북","익산":"전북","군산":"전북",
    "목포":"전남","순천":"전남","여수":"전남","나주":"전남",
    "포항":"경북","경주":"경북","구미":"경북","안동":"경북","영주":"경북",
    "창원":"경남","진주":"경남","김해":"경남","통영":"경남","거제":"경남",
    "제주시":"제주","서귀포":"제주",
}


# ═══════════════════════════════════════════════════
# 유틸 함수
# ═══════════════════════════════════════════════════

def clean(el):
    if el is None: return ""
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip()

def fmt_date(s):
    digits = re.sub(r"\D", "", str(s))
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    m = re.match(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", str(s))
    if m:
        return f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
    return ""

def parse_date_range(text):
    if not text: return None, None
    text = re.sub(r"[./]", "-", str(text))
    dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", text)
    if len(dates) >= 2: return fmt_date(dates[0]), fmt_date(dates[1])
    if len(dates) == 1: return fmt_date(dates[0]), fmt_date(dates[0])
    digits = re.findall(r"\d{8}", text)
    if digits: return fmt_date(digits[0]), fmt_date(digits[-1])
    return None, None

def is_in_range(start, end):
    try:
        s = datetime.date.fromisoformat(start)
        e = datetime.date.fromisoformat(end)
        return e >= CUTOFF_PAST and s <= CUTOFF_FUTURE
    except: return False

def calc_status(start, end):
    try:
        s = datetime.date.fromisoformat(start)
        e = datetime.date.fromisoformat(end)
        if e < TODAY:   return "done"
        if s <= TODAY:  return "ongoing"
        return "upcoming"
    except: return "upcoming"

def detect_sport(title):
    title_lower = title.lower()
    for k in SPORT_ICONS:
        if k in title or k in title_lower:
            return k
    if any(k in title for k in ["체전","체육대회","올림픽","전국대회"]): return "종합"
    return "기타"

def detect_region(text):
    for k, v in REGION_MAP.items():
        if k in text: return v
    return "기타"

def make_event(title, sport, venue, address, start, end,
               region, url="", desc="", source="", lat=0.0, lng=0.0):
    return {
        "title":    title.strip()[:80],
        "sport":    sport,
        "icon":     SPORT_ICONS.get(sport, "🏆"),
        "venue":    venue.strip()[:60],
        "address":  address.strip()[:80],
        "start":    start,
        "end":      end,
        "status":   calc_status(start, end),
        "region":   region,
        "desc":     desc.strip()[:120],
        "url":      url,
        "participants": "",
        "lat":      lat,
        "lng":      lng,
        "_source":  source,
        "_scraped": TODAY.isoformat(),
    }


# ═══════════════════════════════════════════════════
# Playwright 페이지 가져오기 (공통)
# ═══════════════════════════════════════════════════

class PlaywrightSession:
    def __init__(self, headless=True):
        self.headless = headless
        self._pw = None
        self._browser = None

    def __enter__(self):
        if not PLAYWRIGHT_OK:
            return None
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(
            headless=self.headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        return self

    def __exit__(self, *_):
        if self._browser: self._browser.close()
        if self._pw:      self._pw.stop()

    def get_html(self, url, wait_selector=None, timeout=20000):
        if not self._browser: return None
        page = self._browser.new_page()
        page.set_extra_http_headers({"Accept-Language": "ko-KR"})
        try:
            page.goto(url, timeout=timeout, wait_until="domcontentloaded")
            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=timeout)
            time.sleep(1.5)
            html = page.content()
            page.close()
            return html
        except PWTimeout:
            log.warning(f"    타임아웃: {url}")
            page.close()
            return None
        except Exception as e:
            log.warning(f"    오류({url}): {e}")
            page.close()
            return None


def fetch_html_requests(url, timeout=12):
    """Playwright 없을 때 requests 폴백"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        log.warning(f"    requests 실패({url}): {e}")
        return None


# ═══════════════════════════════════════════════════
# 크롤러 구현
# ═══════════════════════════════════════════════════

class SportsPortalCrawler:
    """스포츠지원포털 g1.sports.or.kr"""
    name = "스포츠지원포털"
    urls = [
        "https://g1.sports.or.kr/sports/competition/schedule.do",
        "https://g1.sports.or.kr/sports/competition/scheduleList.do",
        "https://www.sports.or.kr/sports/competition/schedule.do",
    ]

    def parse(self, html_text, source_url):
        events = []
        soup = BeautifulSoup(html_text, "lxml")

        # 패턴 1: 표 구조
        for row in soup.select("table tbody tr"):
            tds = row.find_all("td")
            if len(tds) < 3: continue
            title    = clean(tds[0])
            date_raw = clean(tds[1])
            venue    = clean(tds[2])
            host     = clean(tds[3]) if len(tds) > 3 else ""
            if not title or len(title) < 3: continue
            link_tag = row.select_one("a[href]")
            link = link_tag["href"] if link_tag else source_url
            if link.startswith("/"): link = "https://g1.sports.or.kr" + link
            start, end = parse_date_range(date_raw)
            if not start or not is_in_range(start, end): continue
            sport  = detect_sport(title)
            region = detect_region(venue + title)
            events.append(make_event(
                title=title, sport=sport,
                venue=venue, address=venue,
                start=start, end=end,
                region=region, url=link,
                desc=f"{sport} 대회. 주최: {host}",
                source=self.name
            ))

        # 패턴 2: 리스트형
        for item in soup.select(".schedule-item, .event-item, .list-item"):
            title    = clean(item.select_one(".title, .subject, h4, h3"))
            date_raw = clean(item.select_one(".date, .period, .schedule-date"))
            venue    = clean(item.select_one(".place, .venue, .location"))
            if not title: continue
            start, end = parse_date_range(date_raw or "")
            if not start or not is_in_range(start, end): continue
            link_tag = item.select_one("a[href]")
            link = link_tag["href"] if link_tag else source_url
            if link.startswith("/"): link = "https://g1.sports.or.kr" + link
            sport  = detect_sport(title)
            region = detect_region((venue or "") + title)
            events.append(make_event(
                title=title, sport=sport,
                venue=venue or "", address=venue or "",
                start=start, end=end,
                region=region, url=link,
                desc=f"{sport} 대회",
                source=self.name
            ))
        return events

    def run(self, session):
        events = []
        for url in self.urls:
            log.info(f"    크롤링: {url}")
            html_text = None
            if session:
                html_text = session.get_html(url, timeout=15000)
            if not html_text:
                html_text = fetch_html_requests(url)
            if not html_text:
                continue
            parsed = self.parse(html_text, url)
            log.info(f"    → {len(parsed)}건")
            events.extend(parsed)
            time.sleep(2)
        return events


class SporTalCrawler:
    """생활체육 포털 sportal.or.kr"""
    name = "생활체육포털"
    base = "https://sportal.or.kr"

    def run(self, session):
        events = []
        urls = [
            f"{self.base}/match/list.do",
            f"{self.base}/match/schedule.do",
            f"{self.base}/common/main.do",
        ]
        for url in urls:
            log.info(f"    크롤링: {url}")
            html_text = session.get_html(url, timeout=15000) if session else None
            if not html_text:
                html_text = fetch_html_requests(url)
            if not html_text: continue
            soup = BeautifulSoup(html_text, "lxml")

            # 페이지 1~3 수집
            for pg in range(1, 4):
                if pg > 1:
                    pg_url = f"{url}?pageIndex={pg}"
                    html_text = session.get_html(pg_url) if session else None
                    if not html_text: html_text = fetch_html_requests(pg_url)
                    if not html_text: break
                    soup = BeautifulSoup(html_text, "lxml")

                rows = soup.select("table tbody tr, .match-list li, .event-row")
                if not rows: break
                for row in rows:
                    title    = clean(row.select_one(".title, td:nth-child(1), h4"))
                    date_raw = clean(row.select_one(".date, td:nth-child(2), .period"))
                    venue    = clean(row.select_one(".place, td:nth-child(3), .venue"))
                    if not title or len(title) < 3: continue
                    start, end = parse_date_range(date_raw or "")
                    if not start or not is_in_range(start, end): continue
                    link_tag = row.select_one("a[href]")
                    link = link_tag["href"] if link_tag else url
                    if link.startswith("/"): link = self.base + link
                    sport  = detect_sport(title)
                    region = detect_region((venue or "") + title)
                    events.append(make_event(
                        title=title, sport=sport,
                        venue=venue or "", address=venue or "",
                        start=start, end=end,
                        region=region, url=link,
                        desc=f"생활체육 {sport} 대회",
                        source=self.name
                    ))
                time.sleep(1)
        log.info(f"  [{self.name}] 총 {len(events)}건")
        return events


class BadmintonCrawler:
    """배드민턴게임 badmintongame.co.kr"""
    name = "배드민턴게임"

    def run(self, session):
        events = []
        urls = [
            "https://www.badmintongame.co.kr/match/list",
            "https://www.badmintongame.co.kr/game/schedule",
            "https://www.badmintongame.co.kr/",
        ]
        for url in urls:
            log.info(f"    크롤링: {url}")
            html_text = session.get_html(
                url, wait_selector="table, .match-list, .game-list",
                timeout=15000
            ) if session else None
            if not html_text:
                html_text = fetch_html_requests(url)
            if not html_text: continue

            soup = BeautifulSoup(html_text, "lxml")
            for row in soup.select("table tbody tr, .match-item, .game-item, li.list"):
                cells = row.find_all(["td","div","span"], recursive=False)
                texts = [c.get_text(" ", strip=True) for c in cells
                         if c.get_text(strip=True) and len(c.get_text(strip=True)) > 1]
                if len(texts) < 2: continue
                title    = texts[0]
                date_raw = next((t for t in texts if re.search(r"\d{4}[-./]\d{1,2}", t)), "")
                venue    = texts[-1] if len(texts) >= 3 else ""
                if not title or len(title) < 4: continue
                start, end = parse_date_range(date_raw)
                if not start or not is_in_range(start, end): continue
                link_tag = row.select_one("a[href]")
                link = link_tag["href"] if link_tag else url
                if link.startswith("/"): link = "https://www.badmintongame.co.kr" + link
                region = detect_region(venue + title)
                events.append(make_event(
                    title=title, sport="배드민턴",
                    venue=venue, address=venue,
                    start=start, end=end,
                    region=region, url=link,
                    desc="배드민턴 대회",
                    source=self.name
                ))
            time.sleep(2)
        log.info(f"  [{self.name}] 총 {len(events)}건")
        return events


class MarathonCrawler:
    """마라톤온라인 marathon.pe.kr"""
    name = "마라톤온라인"

    def run(self, session):
        events = []
        urls = [
            "http://www.marathon.pe.kr/schedule",
            "http://www.marathon.pe.kr/",
        ]
        for url in urls:
            log.info(f"    크롤링: {url}")
            html_text = session.get_html(url, timeout=15000) if session else None
            if not html_text: html_text = fetch_html_requests(url)
            if not html_text: continue

            soup = BeautifulSoup(html_text, "lxml")
            for row in soup.select("table.tbl tbody tr, .schedule-row, table tbody tr"):
                tds = row.find_all("td")
                if len(tds) < 3: continue
                title    = clean(tds[0])
                date_raw = clean(tds[1])
                venue    = clean(tds[2])
                if not title or len(title) < 3: continue
                start, end = parse_date_range(date_raw)
                if not start or not is_in_range(start, end): continue
                link_tag = row.select_one("a[href]")
                link = link_tag["href"] if link_tag else url
                sport  = "마라톤" if any(k in title for k in ["마라톤","달리기","러닝"]) else "육상"
                region = detect_region(venue + title)
                events.append(make_event(
                    title=title, sport=sport,
                    venue=venue, address=venue,
                    start=start, end=end,
                    region=region, url=link,
                    desc=f"{sport}. {venue} 개최",
                    source=self.name
                ))
            time.sleep(2)
        log.info(f"  [{self.name}] 총 {len(events)}건")
        return events


class SwimmingCrawler:
    """대한수영연맹 korswim.co.kr"""
    name = "대한수영연맹"

    def run(self, session):
        events = []
        urls = [
            "https://www.korswim.co.kr/board/list.do?bid=schedule",
            "https://www.korswim.co.kr/",
        ]
        for url in urls:
            log.info(f"    크롤링: {url}")
            html_text = session.get_html(url, timeout=15000) if session else None
            if not html_text: html_text = fetch_html_requests(url)
            if not html_text: continue

            soup = BeautifulSoup(html_text, "lxml")
            for row in soup.select("table tbody tr, .schedule-row"):
                tds = row.find_all("td")
                if len(tds) < 3: continue
                title    = clean(tds[0])
                date_raw = clean(tds[1])
                venue    = clean(tds[2])
                if not title or len(title) < 3: continue
                start, end = parse_date_range(date_raw)
                if not start or not is_in_range(start, end): continue
                link_tag = row.select_one("a[href]")
                link = link_tag["href"] if link_tag else url
                if link.startswith("/"): link = "https://www.korswim.co.kr" + link
                region = detect_region(venue + title)
                events.append(make_event(
                    title=title, sport="수영",
                    venue=venue, address=venue,
                    start=start, end=end,
                    region=region, url=link,
                    desc="수영 대회",
                    source=self.name
                ))
            time.sleep(2)
        log.info(f"  [{self.name}] 총 {len(events)}건")
        return events


# ═══════════════════════════════════════════════════
# 중복 제거
# ═══════════════════════════════════════════════════

def dedup(events):
    seen = {}
    result = []
    for e in events:
        key = re.sub(r"[^\w]", "", e["title"])[:12]
        if key not in seen:
            seen[key] = e
            result.append(e)
        else:
            old = seen[key]
            # 더 정보가 풍부한 항목으로 교체
            if (e["lat"] != 0 and old["lat"] == 0) or \
               len(e.get("desc","")) > len(old.get("desc","")) or \
               (e["url"] and not old["url"]):
                idx = result.index(old)
                result[idx] = e
                seen[key] = e
    return result


# ═══════════════════════════════════════════════════
# 고정 대회 (항상 포함)
# ═══════════════════════════════════════════════════

FIXED_EVENTS = [
    make_event(
        "2026 서울마라톤 (제96회 동아마라톤)", "마라톤",
        "광화문광장 (출발) → 잠실올림픽주경기장",
        "서울 종로구 세종대로 172",
        "2026-03-15","2026-03-15","서울",
        url="https://www.seoulmarathon.com",
        desc="국내 최대 풀코스 마라톤. IAAF 골드 라벨. 풀코스·10km 각 2만명.",
        lat=37.5716, lng=126.9768, source="고정"
    ),
    make_event(
        "2026 경주국제마라톤 (벚꽃마라톤)", "마라톤",
        "경주 보문단지 (출발·도착)",
        "경북 경주시 보문로 213-1",
        "2026-04-05","2026-04-05","경북",
        url="https://www.gyeongjumarathon.com",
        desc="벚꽃 시즌 경주 유적지 코스. 풀·하프·10K. 약 1.5만명.",
        lat=35.8528, lng=129.2692, source="고정"
    ),
    make_event(
        "2026 JTBC 서울마라톤", "마라톤",
        "잠실올림픽주경기장",
        "서울 송파구 올림픽로 25",
        "2026-10-18","2026-10-18","서울",
        url="https://www.jtbcmarathon.com",
        desc="추첨제 운영. 풀코스·하프·10km. 약 3만명.",
        lat=37.5149, lng=127.0738, source="고정"
    ),
    make_event(
        "2026 춘천마라톤 (가을의 전설)", "마라톤",
        "의암호 순환 코스 (춘천종합운동장 출발)",
        "강원 춘천시 스포츠타운길 99",
        "2026-10-25","2026-10-25","강원",
        url="https://www.chuncheonmarathon.com",
        desc="의암호 절경 코스. 풀·하프코스. 국내 대표 가을 마라톤.",
        lat=37.8813, lng=127.7298, source="고정"
    ),
]


# ═══════════════════════════════════════════════════
# HTML index.html 업데이트
# ═══════════════════════════════════════════════════

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
            f"participants:'',lat:{e['lat']},lng:{e['lng']}}}{comma}\n"
        )
    lines.append("];")
    return "".join(lines)


def update_index_html(events, html_path="index.html"):
    if not Path(html_path).exists():
        log.warning(f"{html_path} 없음 — HTML 업데이트 스킵")
        return False
    with open(html_path, encoding="utf-8") as f:
        html = f.read()
    new_js = events_to_js(events)
    stamp  = f"// 자동 업데이트: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M KST')}\n"
    # 기존 타임스탬프 제거
    html = re.sub(r"// 자동 업데이트:.*\n", "", html)
    new_html, n = re.subn(r"let EVENTS\s*=\s*\[[\s\S]*?\];", stamp + new_js, html)
    if n == 0:
        log.error("EVENTS 배열 패턴 못 찾음")
        return False
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(new_html)
    log.info(f"✅ {html_path} 업데이트 완료 (EVENTS {len(events)}개)")
    return True


# ═══════════════════════════════════════════════════
# 메인 실행
# ═══════════════════════════════════════════════════

def run_once():
    log.info("=" * 55)
    log.info(f"스포트립 크롤러 시작  {TODAY}")
    log.info(f"수집 범위: {CUTOFF_PAST} ~ {CUTOFF_FUTURE}")
    log.info("=" * 55)

    all_events = list(FIXED_EVENTS)
    log.info(f"[STEP 1] 고정 대회: {len(FIXED_EVENTS)}건")

    crawlers = [
        SportsPortalCrawler(),
        SporTalCrawler(),
        BadmintonCrawler(),
        MarathonCrawler(),
        SwimmingCrawler(),
    ]

    with PlaywrightSession(headless=True) as session:
        for crawler in crawlers:
            log.info(f"\n[크롤러] {crawler.name}")
            try:
                result = crawler.run(session)
                all_events.extend(result)
            except Exception as e:
                log.error(f"  [{crawler.name}] 오류: {e}")

    # 중복 제거
    before = len(all_events)
    all_events = dedup(all_events)
    log.info(f"\n[중복 제거] {before} → {len(all_events)}건")

    # 날짜순 정렬 (진행중 → 예정 → 종료)
    status_order = {"ongoing":0, "upcoming":1, "done":2}
    all_events.sort(key=lambda e: (status_order.get(e["status"],9), e.get("start","9999")))

    # 최대 30개
    all_events = all_events[:30]

    # 결과 출력
    log.info(f"\n{'─'*55}")
    log.info(f"최종 결과: {len(all_events)}건")
    for i, e in enumerate(all_events):
        log.info(f"  {i:2d}. [{e['status']:8s}] {e['title'][:28]:28s} | {e['region']:4s} | {e['start']} | {e.get('_source','')}")

    # events.json 저장
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "updated_at": datetime.datetime.now().isoformat(),
        "total":      len(all_events),
        "by_source":  {},
        "by_sport":   {},
        "by_status":  {"upcoming":0,"ongoing":0,"done":0},
        "events":     [{k:v for k,v in e.items() if not k.startswith("_")}
                       for e in all_events],
    }
    for e in all_events:
        src = e.get("_source","unknown")
        sp  = e.get("sport","기타")
        st  = e.get("status","upcoming")
        report["by_source"][src] = report["by_source"].get(src,0) + 1
        report["by_sport"][sp]   = report["by_sport"].get(sp,0)   + 1
        report["by_status"][st]  = report["by_status"].get(st,0)  + 1

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    log.info(f"\n✅ {OUT_JSON} 저장 완료")

    # index.html 업데이트
    update_index_html(all_events)
    log.info("=" * 55)

    return all_events


def main():
    parser = argparse.ArgumentParser(description="스포트립 크롤러")
    parser.add_argument("--watch", action="store_true", help="매일 새벽 3시 자동 반복")
    parser.add_argument("--hour",  type=int, default=3, help="실행 시간 (기본: 3시)")
    args = parser.parse_args()

    if args.watch:
        try:
            import schedule
        except ImportError:
            print("pip install schedule")
            return

        log.info(f"스케줄러 모드 — 매일 {args.hour:02d}:00 실행")
        schedule.every().day.at(f"{args.hour:02d}:00").do(run_once)
        run_once()  # 시작 시 1회 즉시 실행
        while True:
            schedule.run_pending()
            time.sleep(60)
    else:
        run_once()


if __name__ == "__main__":
    main()
