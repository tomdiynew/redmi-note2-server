#!/data/data/com.termux/files/usr/bin/python3
"""LAN status dashboard for the Redmi Note 2 mini server (runs in Termux).

GET /             dashboard page
GET /api/status   current readings (JSON)
GET /api/history  last 24h of 1-minute samples (JSON)
GET /api/news/days  one entry per day (ok / partial / error / pending / missing)
GET /news/<date>.html  that day's stand-alone news page; batches are fetched
                  from each country's own outlets every day at 07:00 local time into ~/news/
                  (non-Chinese headlines get a Chinese machine translation)
GET /api/markets  index / commodity quotes from Sina (cached 30s) and
                  Brazilian beef/soy from CEPEA (daily, cached 1h) (JSON)

Root-only data (Wi-Fi SSID, IP, charge control) comes from ~/.phonestat.json,
written every 15s by the phonectl root service.
"""
import html
import json
import os
import re
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

PORT = int(os.environ.get("WEBSTAT_PORT", "8080"))
HOME = os.path.expanduser("~")
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT_JSON = os.path.join(HOME, ".phonestat.json")
HIST_FILE = os.path.join(HOME, ".webstat_history.json")
BAT = "/sys/class/power_supply/battery"
# thermal zone type -> label. Redmi Note 2 (MediaTek) and Pixel 2 XL (Snapdragon 835).
THERMAL_NAMES = {"mtktscpu": "CPU", "mtktsbattery": "电池", "mtktsAP": "主板",
                 "mtktspmic": "电源芯片", "mtktswmt": "Wi-Fi 芯片",
                 "battery": "电池", "pm8998_tz": "电源芯片", "xo_therm": "主板", "usb_port_temp": "USB 口"}
CPU_ZONE_PREFIX = "tsens_tz_sensor"  # Snapdragon: CPU = hottest tsens sensor


def celsius(raw):
    """Zones report °C, deci-°C or milli-°C depending on the driver."""
    v = abs(raw)
    return raw / 1000 if v >= 1000 else raw / 10 if v >= 150 else raw


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def num(path, scale=1.0):
    v = read(path)
    try:
        return float(v) * scale
    except (TypeError, ValueError):
        return None


def getprop(name):
    try:
        return subprocess.run(["getprop", name], capture_output=True, text=True, timeout=3).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def cpu_times():
    """(busy+idle, idle) jiffies. The MTK kernel's iowait counter is garbage
    (goes negative / astronomically large), so it is left out entirely."""
    with open("/proc/stat") as f:
        p = [int(x) for x in f.readline().split()[1:8]]
    user, nice, system, idle, _iowait, irq, softirq = p
    busy = user + nice + system + irq + softirq
    return busy + idle, idle


class Sampler:
    """Keeps CPU/network deltas between calls and a 24h minute history."""

    def __init__(self):
        self.lock = threading.Lock()
        self.prev_cpu = cpu_times()
        self.prev_net = (time.time(), *self.net_bytes())
        self.cpu_pct = 0.0
        self.net_rate = (0.0, 0.0)
        self.history = deque(maxlen=1440)
        try:
            with open(HIST_FILE) as f:
                self.history.extend(json.load(f))
        except (OSError, ValueError):
            pass

    @staticmethod
    def net_bytes():
        for line in read("/proc/net/dev", "").splitlines():
            if line.strip().startswith("wlan0:"):
                f = line.split(":", 1)[1].split()
                return int(f[0]), int(f[8])
        return 0, 0

    def tick(self):
        with self.lock:
            total, idle = cpu_times()
            dt, di = total - self.prev_cpu[0], idle - self.prev_cpu[1]
            if dt > 0:
                self.cpu_pct = round(100.0 * (dt - di) / dt, 1)
            self.prev_cpu = (total, idle)
            now, (rx, tx) = time.time(), self.net_bytes()
            el = now - self.prev_net[0]
            if el > 0.5:
                self.net_rate = (max(0, rx - self.prev_net[1]) / el, max(0, tx - self.prev_net[2]) / el)
                self.prev_net = (now, rx, tx)

    def record(self, st):
        with self.lock:
            self.history.append({"t": int(time.time()), "bat": st["battery"]["level"],
                                 "temp": st["temps"].get("CPU"), "cpu": st["cpu"]["usage_pct"]})

    def save(self):
        with self.lock:
            data = list(self.history)
        tmp = HIST_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, HIST_FILE)


sampler = Sampler()
# Site-name prefix, so the same code labels each phone's site ("Pixel 老汉移动信息网")
SITE = os.environ.get("WEBSTAT_SITE") or ("Pixel" if "Pixel" in getprop("ro.product.model") else "Redmi")

STATIC = {"model": getprop("ro.product.model"), "android": getprop("ro.build.version.release"),
          "rom": getprop("ro.lineage.version") or getprop("ro.cm.version") or getprop("ro.build.display.id"),
          "kernel": os.uname().release, "arch": os.uname().machine}


# (group, [(sina code, unit)]); Sina supplies the Chinese names
MARKETS = [
    ("美股", [("gb_$dji", ""), ("gb_$inx", ""), ("gb_$ixic", "")]),
    ("A 股", [("sh000001", ""), ("sz399001", ""), ("sz399006", ""), ("sh000300", "")]),
    ("港股", [("hkHSI", ""), ("hkHSTECH", ""), ("hkHSCEI", "")]),
    ("贵金属", [("hf_XAU", "美元/盎司"), ("hf_XAG", "美元/盎司"), ("hf_GC", "美元/盎司"), ("hf_SI", "美元/盎司"),
               ("hf_XPT", "美元/盎司"), ("hf_XPD", "美元/盎司"), ("nf_AU0", "元/克"), ("nf_AG0", "元/千克")]),
    ("能源", [("hf_CL", "美元/桶"), ("hf_OIL", "美元/桶"), ("hf_NG", "美元/百万英热")]),
    ("农产品", [("hf_C", "美分/蒲式耳"), ("hf_S", "美分/蒲式耳"), ("hf_W", "美分/蒲式耳")]),
    ("巴西农产品", [("cepea:boi-gordo", "雷亚尔/arroba (15 kg)"), ("cepea:soja", "雷亚尔/袋 (60 kg)")]),
    ("汇率", [("fx_susdcny", "")]),
]
# CEPEA (USP) daily indicators; the first table on each page is the headline one
CEPEA_NAMES = {"boi-gordo": "巴西肥牛（圣保罗）", "soja": "巴西大豆（巴拉那瓜港）"}
CEPEA_TTL = 3600
_cepea = {}
MARKET_TTL = 30
_markets = {"ts": 0, "data": None}
_markets_lock = threading.Lock()


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_sina(code, f):
    """-> (name, price, prev, high, low, quote time) or None. Field layouts differ per market."""
    try:
        if code.startswith("gb_"):
            return f[0], _f(f[1]), _f(f[26]), _f(f[6]), _f(f[7]), f[3][5:16]
        if code.startswith(("sh", "sz")):
            price = _f(f[3]) or _f(f[2])  # 0 before the open
            return f[0], price, _f(f[2]), _f(f[4]), _f(f[5]), f[30][5:] + " " + f[31][:5]
        if code.startswith("hk"):
            return f[1], _f(f[6]), _f(f[3]), _f(f[4]), _f(f[5]), f[17][5:].replace("/", "-") + " " + f[18]
        if code.startswith("hf_"):
            return re.sub(r"（现货.+）", "（现货）", f[13]), _f(f[0]), _f(f[7]), _f(f[4]), _f(f[5]), f[12][5:] + " " + f[6][:5]
        if code.startswith("nf_"):  # Shanghai futures main contract; prev = last settlement
            return "沪" + f[0][1] + "（主力）", _f(f[8]), _f(f[10]), _f(f[3]), _f(f[4]), f[17][5:] + " " + f[1][:2] + ":" + f[1][2:4]
        if code.startswith("fx_"):
            return "美元/人民币", _f(f[8]), _f(f[3]), _f(f[6]), _f(f[7]), f[17][5:] + " " + f[0][:5]
    except IndexError:
        pass
    return None


def fetch_cepea(slug):
    """-> same tuple as parse_sina, from the latest two rows of the indicator table."""
    req = Request(f"https://www.cepea.org.br/br/indicador/{slug}.aspx", headers={
        # a bare UA gets a 403
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36", "Accept-Language": "pt-BR"})
    with urlopen(req, timeout=15) as r:
        page = r.read().decode("utf-8", "replace")
    table = re.search(r"<table.*?</table>", page, re.S).group(0)
    rows = []
    for tr in re.findall(r"<tr.*?</tr>", table, re.S):
        cells = [html.unescape(re.sub(r"<[^>]+>", "", c)).strip() for c in re.findall(r"<td.*?</td>", tr, re.S)]
        if len(cells) >= 2 and re.match(r"\d\d/\d\d/\d{4}", cells[0]):
            rows.append((cells[0], float(cells[1].replace(".", "").replace(",", "."))))
    (day, price), (_, prev) = rows[0], rows[1]
    return CEPEA_NAMES[slug], price, prev, None, None, day[3:5] + "-" + day[:2] + " 收盘"


def cepea(slug):
    """Daily data: refetch hourly, keep the last good value if the site is down."""
    c = _cepea.get(slug)
    if not c or time.time() - c[0] > CEPEA_TTL:
        try:
            _cepea[slug] = c = (time.time(), fetch_cepea(slug))
        except Exception as e:
            print("cepea error:", slug, e, flush=True)
            if c:
                _cepea[slug] = c = (time.time() - CEPEA_TTL + 300, c[1])  # retry in 5 min
    return c[1] if c else None


def fetch_markets():
    codes = [c for _, items in MARKETS for c, _ in items if not c.startswith("cepea:")]
    req = Request("https://hq.sinajs.cn/list=" + ",".join(codes),
                  headers={"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=8) as r:
        raw = r.read().decode("gbk", "replace")
    quotes = {m.group(1): parse_sina(m.group(1), m.group(2).split(","))
              for m in re.finditer(r'hq_str_([^=]+)="([^"]*)"', raw)}
    for _, items in MARKETS:
        for code, _ in items:
            if code.startswith("cepea:"):
                quotes[code] = cepea(code[6:])
    groups = []
    for title, items in MARKETS:
        rows = []
        for code, unit in items:
            q = quotes.get(code)
            if not q or q[1] is None:
                continue
            name, price, prev, high, low, qt = q
            chg = price - prev if prev else None
            rows.append({"code": code, "name": name, "price": price, "prev": prev, "high": high, "low": low,
                         "chg": chg, "pct": chg / prev * 100 if chg is not None else None,
                         "unit": unit, "time": qt})
        groups.append({"title": title, "items": rows})
    return groups


def markets():
    """Shared 30s cache: every viewer polling Sina would swamp the single core."""
    with _markets_lock:
        if time.time() - _markets["ts"] > MARKET_TTL:
            try:
                _markets["data"] = fetch_markets()
                _markets["error"] = None
            except Exception as e:  # keep serving the last good quotes
                _markets["error"] = str(e)
            _markets["ts"] = time.time()
        return {"time": int(_markets["ts"]), "groups": _markets["data"] or [], "error": _markets.get("error")}


# ---- daily news: each country's own outlets (major Western ones for world news),
# NEWS_PER_GROUP headlines per group taken in turn from its sources; every
# non-Chinese headline also gets an automatic Chinese translation.
NEWS_FEEDS = [  # (group, [(source, rss url, language)])
    ("世界", [("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml", "en"),
              ("The Guardian", "https://www.theguardian.com/world/rss", "en"),
              ("The New York Times", "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "en")]),
    ("中国", [("中国新闻网", "https://www.chinanews.com.cn/rss/scroll-news.xml", "zh"),
              ("人民网", "http://www.people.com.cn/rss/politics.xml", "zh")]),
    ("韩国", [("연합뉴스", "https://www.yna.co.kr/rss/news.xml", "ko")]),
    ("日本", [("NHK", "https://www3.nhk.or.jp/rss/news/cat0.xml", "ja"),
              ("朝日新聞", "https://www.asahi.com/rss/asahi/newsheadlines.rdf", "ja")]),
    ("越南", [("VnExpress", "https://vnexpress.net/rss/tin-moi-nhat.rss", "vi"),
              ("Tuổi Trẻ", "https://tuoitre.vn/rss/tin-moi-nhat.rss", "vi")]),
    ("欧洲", [("DW", "https://rss.dw.com/rdf/rss-en-eu", "en"),
              ("Le Monde", "https://www.lemonde.fr/international/rss_full.xml", "fr"),
              ("Der Spiegel", "https://www.spiegel.de/international/index.rss", "en")]),
]
NEWS_PER_GROUP = 20
NEWS_HOUR = 7
NEWS_DIR = os.path.join(os.path.expanduser("~"), "news")   # <date>.html, <date>.json, index.json
NEWS_INDEX = os.path.join(NEWS_DIR, "index.json")
_news_lock = threading.Lock()


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def fetch_feed(url, limit):
    """RSS 2.0, RSS 1.0 (RDF) and Atom -> [{title, link, time}]"""
    import xml.etree.ElementTree as ET
    from email.utils import parsedate_to_datetime
    raw = urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read()
    out, seen = [], set()
    for it in ET.fromstring(raw).iter():
        if _local(it.tag) not in ("item", "entry"):
            continue
        f = {_local(c.tag): c for c in it}
        title = " ".join((f["title"].text or "").split()) if "title" in f else ""
        link = (f["link"].text or f["link"].get("href") or "").strip() if "link" in f else ""
        if not title or title in seen:
            continue
        seen.add(title)
        ts = None
        for k in ("pubDate", "date", "published", "updated"):
            if k in f and f[k].text:
                try:
                    ts = int(parsedate_to_datetime(f[k].text).timestamp())
                except Exception:
                    try:
                        from datetime import datetime
                        ts = int(datetime.fromisoformat(f[k].text.strip().replace("Z", "+00:00")).timestamp())
                    except Exception:
                        pass
                break
        out.append({"title": title, "link": link, "time": ts})
        if len(out) >= limit:
            break
    return out


def translate_zh(lines, lang):
    """Google Translate's keyless endpoint; one line per headline, batches of 10."""
    import urllib.parse
    out = []
    for i in range(0, len(lines), 10):
        chunk = lines[i:i + 10]
        body = urllib.parse.urlencode({"q": "\n".join(chunk)}).encode()
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl={lang}&tl=zh-CN&dt=t"
        d = json.loads(urlopen(Request(url, data=body, headers={"User-Agent": "Mozilla/5.0"}), timeout=20).read())
        res = "".join(seg[0] for seg in d[0] if seg[0]).split("\n")
        out += res if len(res) == len(chunk) else [None] * len(chunk)   # misaligned -> skip
    return out


def fetch_news_group(sources):
    """Headlines from every source of a group, interleaved, with Chinese translations."""
    per_src, errors = [], []
    for name, url, lang in sources:
        try:
            items = fetch_feed(url, NEWS_PER_GROUP)
        except Exception as e:
            errors.append(f"{name}: {e}"); continue
        for i in items:
            i.update(source=name, lang=lang, title_zh=None)
        per_src.append(items)
    picked = []
    while len(picked) < NEWS_PER_GROUP and any(per_src):
        for items in per_src:
            if items and len(picked) < NEWS_PER_GROUP:
                picked.append(items.pop(0))
    for lang in {i["lang"] for i in picked if i["lang"] != "zh"}:
        todo = [i for i in picked if i["lang"] == lang]
        try:
            for i, zh in zip(todo, translate_zh([i["title"] for i in todo], lang)):
                i["title_zh"] = zh
        except Exception as e:
            errors.append(f"翻译({lang}): {e}")
    if not picked and errors:
        raise RuntimeError("; ".join(errors))
    return picked, errors


def _news_index():
    try:
        with open(NEWS_INDEX) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write(path, text):
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def news_day_html(day, data):
    """Stand-alone page for one day's batch (also readable on its own)."""
    e = html.escape
    fmt = lambda ts: time.strftime("%m-%d %H:%M", time.localtime(ts)) if ts else ""
    cards = []
    for g in data["groups"]:
        if g["items"]:
            lis = "".join(f'<li><a href="{e(i["link"])}" target="_blank" rel="noopener">{e(i["title"])}</a>'
                          + (f'<div class="zh">{e(i["title_zh"])}</div>' if i.get("title_zh") else "")
                          + f'<div class="n">{e(i["source"])}{" · " + fmt(i["time"]) if i["time"] else ""}</div></li>'
                          for i in g["items"])
            body = f"<ol>{lis}</ol>" + (f'<div class="n err">{e(g["error"])}</div>' if g.get("error") else "")
        else:
            body = f'<div class="err">抓取失败：{e(g.get("error") or "无数据")}</div>'
        src = " · ".join(g.get("sources") or [])
        cards.append(f'<section><h2>{e(g["title"])} · {len(g["items"])} 条</h2><div class="n">{e(src)}</div>{body}</section>')
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>每日新闻 {day}</title>
<style>
:root {{ --bg:#0f1115; --card:#181b22; --fg:#e6e8ee; --muted:#8b93a7; --line:#262b36; --accent:#ff5a4f; }}
body {{ margin:0; background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system,"PingFang SC","Noto Sans CJK SC",sans-serif; }}
.wrap {{ max-width:1100px; margin:0 auto; padding:20px 16px 40px; }}
h1 {{ font-size:22px; margin:0 0 4px; }} h1 span {{ color:var(--accent); }}
.meta {{ color:var(--muted); font-size:13px; margin-bottom:16px; }} .meta a {{ color:var(--muted); }}
.grid {{ display:grid; gap:14px; grid-template-columns:repeat(auto-fill,minmax(320px,1fr)); }}
section {{ background:var(--card); border:1px solid var(--line); border-radius:12px; padding:14px 16px; }}
h2 {{ font-size:16px; margin:0 0 8px; }}
ol {{ margin:0; padding-left:22px; }} li {{ padding:6px 0; border-top:1px solid var(--line); }} li:first-child {{ border-top:0; }}
a {{ color:inherit; text-decoration:none; }} a:hover {{ text-decoration:underline; }}
.n {{ color:var(--muted); font-size:12px; }} .err {{ color:var(--accent); }}
.zh {{ color:#c9cfdc; font-size:14px; margin-top:2px; }}
</style></head><body><div class="wrap">
<h1>每日新闻 <span>{day}</span></h1>
<div class="meta">抓取于 {time.strftime("%Y-%m-%d %H:%M", time.localtime(data["time"]))} · 各国本地媒体原文 + 中文机器翻译 · <a href="/#news">返回日期列表</a></div>
<div class="grid">{"".join(cards)}</div></div></body></html>"""


def fetch_news(day=None):
    """Fetch every group, save <day>.json/.html and record the day's status in index.json."""
    day = day or time.strftime("%Y-%m-%d")
    groups, errors = [], []
    for name, sources in NEWS_FEEDS:
        try:
            items, errs = fetch_news_group(sources)
            groups.append({"title": name, "sources": [n for n, _, _ in sources], "items": items,
                           "error": "; ".join(errs) or None})
            errors += [f"{name} {x}" for x in errs]
        except Exception as e:  # keep the other groups
            groups.append({"title": name, "items": [], "error": str(e)}); errors.append(f"{name}: {e}")
    data = {"date": day, "time": int(time.time()), "groups": groups}
    count = sum(len(g["items"]) for g in groups)
    with _news_lock:
        os.makedirs(NEWS_DIR, exist_ok=True)
        idx = _news_index()
        if count:
            _write(os.path.join(NEWS_DIR, day + ".json"), json.dumps(data, ensure_ascii=False))
            _write(os.path.join(NEWS_DIR, day + ".html"), news_day_html(day, data))
            idx[day] = {"status": "partial" if errors else "ok", "time": data["time"], "count": count,
                        "error": "; ".join(errors) or None}
        elif not (idx.get(day, {}).get("status") in ("ok", "partial")):   # never overwrite a good batch
            idx[day] = {"status": "error", "time": data["time"], "count": 0, "error": "; ".join(errors) or "无数据"}
        _write(NEWS_INDEX, json.dumps(idx, ensure_ascii=False, indent=1))
    return count


def news_days():
    """Every day from the first batch until today, newest first, with its status."""
    with _news_lock:
        idx = _news_index()
    now = time.time(); lt = time.localtime(now)
    today = time.strftime("%Y-%m-%d", lt)
    first = min(list(idx) + [today])
    days, t = [], time.mktime(time.strptime(today, "%Y-%m-%d")) + 12 * 3600
    while True:
        d = time.strftime("%Y-%m-%d", time.localtime(t))
        if d < first:
            break
        e = dict(idx.get(d) or {})
        if not e:
            if d == today and lt.tm_hour < NEWS_HOUR:
                e = {"status": "pending", "error": f"未到 {NEWS_HOUR}:00，尚未生成"}
            elif d == today:
                e = {"status": "pending", "error": "还没生成（抓取中或正在重试）"}
            else:
                e = {"status": "missing", "error": "当天没有生成（可能关机或断网）"}
        e["date"] = d
        if e.get("status") in ("ok", "partial"):
            e["url"] = f"/news/{d}.html"
        days.append(e)
        t -= 86400
    return {"today": today, "hour": NEWS_HOUR, "days": days}


def news_loop():
    """Fetch at 07:00 local time every day (and at start if today's 07:00 batch is missing)."""
    # the dashboard is started without Termux's login env: take the phone's time zone
    tz = getprop("persist.sys.timezone")
    if tz:
        os.environ["TZ"] = tz; time.tzset()
    while True:
        now = time.time(); lt = time.localtime(now)
        today7 = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, NEWS_HOUR, 0, 0, 0, 0, -1))
        if now >= today7:
            day = time.strftime("%Y-%m-%d", lt)
            if _news_index().get(day, {}).get("status") not in ("ok", "partial"):
                for attempt in range(6):                       # retry for ~30 min if offline
                    if fetch_news(day):
                        break
                    time.sleep(300)
        nxt = today7 + 86400 if now >= today7 else today7
        time.sleep(max(60, nxt - time.time()))


def status():
    up = float(read("/proc/uptime", "0").split()[0])
    mem = {}
    for line in read("/proc/meminfo", "").splitlines():
        k, v = line.split(":", 1)
        mem[k] = int(v.split()[0]) * 1024
    vfs = os.statvfs(HOME)
    online = read("/sys/devices/system/cpu/online", "0")
    cores = []
    for part in online.split(","):
        a, _, b = part.partition("-")
        cores += range(int(a), int(b or a) + 1)
    freqs = {c: num(f"/sys/devices/system/cpu/cpu{c}/cpufreq/scaling_cur_freq", 1 / 1000) for c in cores}
    temps, tsens = {}, []
    for z in sorted(os.listdir("/sys/class/thermal")):
        if z.startswith("thermal_zone"):
            ztype = read(f"/sys/class/thermal/{z}/type", "")
            raw = num(f"/sys/class/thermal/{z}/temp")
            if raw is None:
                continue
            t = celsius(raw)
            if not -40 < t < 150:
                continue
            if ztype.startswith(CPU_ZONE_PREFIX):
                tsens.append(t)
            elif ztype in THERMAL_NAMES:
                temps[THERMAL_NAMES[ztype]] = round(t, 1)
    if tsens:
        temps["CPU"] = round(max(tsens), 1)
    try:
        with open(ROOT_JSON) as f:
            root = json.load(f)
        root["age_s"] = int(time.time() - root.get("ts", 0))
    except (OSError, ValueError):
        root = None
    load = read("/proc/loadavg", "0 0 0").split()[:3]
    return {
        "time": int(time.time()), "device": STATIC, "uptime_s": int(up),
        "cpu": {"usage_pct": sampler.cpu_pct, "load": [float(x) for x in load],
                "cores_online": len(cores),
                "cores_total": int(read("/sys/devices/system/cpu/possible", "0-0").split("-")[-1]) + 1,
                "freq_mhz": {str(c): round(v) for c, v in freqs.items() if v}},
        "temps": temps,
        "memory": {"total": mem.get("MemTotal"), "available": mem.get("MemAvailable", mem.get("MemFree"))},
        "storage": {"total": vfs.f_blocks * vfs.f_frsize, "free": vfs.f_bavail * vfs.f_frsize},
        "battery": {"level": num(f"{BAT}/capacity"), "status": read(f"{BAT}/status"),
                    "health": read(f"{BAT}/health"),
                    # MTK: batt_vol (mV), batt_temp (0.1 °C); Qualcomm: voltage_now (µV), temp (0.1 °C)
                    "voltage_mv": num(f"{BAT}/batt_vol") or num(f"{BAT}/voltage_now", 1 / 1000),
                    "temp_c": num(f"{BAT}/batt_temp", 0.1) or num(f"{BAT}/temp", 0.1),
                    "usb": read("/sys/class/power_supply/usb/online") == "1",
                    "ac": read("/sys/class/power_supply/ac/online") == "1"},
        "network": {"rx_bps": round(sampler.net_rate[0]), "tx_bps": round(sampler.net_rate[1]),
                    "rx_total": Sampler.net_bytes()[0], "tx_total": Sampler.net_bytes()[1]},
        "root": root,
    }


def tick_loop():
    """CPU/network rates are sampled on a fixed 5s clock, not per request:
    on this single-core 800 MHz phone a request's own work would dominate."""
    while True:
        time.sleep(5)
        sampler.tick()


def history_loop():
    n = 0
    while True:
        try:
            sampler.record(status())
            n += 1
            if n % 10 == 0:
                sampler.save()
        except Exception as e:  # never let the sampler thread die
            print("history error:", e, flush=True)
        time.sleep(60)


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/status":
            self._send(200, json.dumps(status(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        elif path == "/api/history":
            with sampler.lock:
                data = list(sampler.history)
            self._send(200, json.dumps(data).encode(), "application/json")
        elif path == "/api/news/days":
            self._send(200, json.dumps(news_days(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        elif re.fullmatch(r"/news/\d{4}-\d{2}-\d{2}\.html", path):
            f = os.path.join(NEWS_DIR, os.path.basename(path))
            if os.path.exists(f):
                with open(f, "rb") as fh:
                    self._send(200, fh.read(), "text/html; charset=utf-8")
            else:
                self._send(404, "这一天的新闻还没生成".encode(), "text/plain; charset=utf-8")
        elif path == "/api/markets":
            self._send(200, json.dumps(markets(), ensure_ascii=False).encode(), "application/json; charset=utf-8")
        elif path in ("/", "/index.html"):
            with open(os.path.join(HERE, "index.html"), "rb") as f:
                self._send(200, f.read().replace(b"__SITE__", SITE.encode()), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def log_message(self, *args):
        pass  # keep the Termux log quiet


if __name__ == "__main__":
    threading.Thread(target=tick_loop, daemon=True).start()
    threading.Thread(target=history_loop, daemon=True).start()
    threading.Thread(target=news_loop, daemon=True).start()
    print(f"webstat listening on 0.0.0.0:{PORT}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
