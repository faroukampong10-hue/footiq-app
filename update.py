"""FootIQ weekly update. Downloads football-data.co.uk files, runs the model, writes data.json."""
import csv, io, json, math, random, datetime, time, urllib.error, urllib.request
from collections import defaultdict

BASE = "https://www.football-data.co.uk/"
LEAGUES = {
 "pl": dict(name="Premier League", f="E0", ng=38.0, prom=33.0, nrel=3, seed=7, lmode="fixed", nm={},
   codes={"Arsenal":"ARS","Aston Villa":"AVL","Bournemouth":"BOU","Brentford":"BRE","Brighton":"BHA","Chelsea":"CHE","Coventry":"COV","Crystal Palace":"CRY","Everton":"EVE","Fulham":"FUL","Hull":"HUL","Ipswich":"IPS","Leeds":"LEE","Liverpool":"LIV","Man City":"MCI","Man United":"MUN","Newcastle":"NEW","Nott'm Forest":"NFO","Sunderland":"SUN","Tottenham":"TOT"},
   hist=[["2016/17, first version","0.949","0.907"],["2017/18, improved version","0.955","0.941"]], histTitle="Tested on earlier seasons",
   histNote="Each version\u2019s settings were fixed before it saw the season shown. The market scored better both times."),
 "sp": dict(name="La Liga", f="SP1", ng=38.0, prom=33.0, nrel=3, seed=11, lmode="fixed",
   nm={"Ath Madrid":"Atl\u00e9tico Madrid","Ath Bilbao":"Athletic Club","Vallecano":"Rayo Vallecano","Espanol":"Espanyol","Sociedad":"Real Sociedad","La Coruna":"Deportivo","Santander":"Racing Santander","Betis":"Real Betis","Celta":"Celta Vigo","Alaves":"Alav\u00e9s","Malaga":"M\u00e1laga"},
   codes={"Alav\u00e9s":"ALA","Athletic Club":"ATH","Atl\u00e9tico Madrid":"ATM","Barcelona":"BAR","Real Betis":"BET","Celta Vigo":"CEL","Deportivo":"DEP","Elche":"ELC","Espanyol":"ESP","Getafe":"GET","Levante":"LEV","M\u00e1laga":"MAL","Osasuna":"OSA","Rayo Vallecano":"RAY","Real Madrid":"RMA","Real Sociedad":"RSO","Racing Santander":"RAC","Sevilla":"SEV","Valencia":"VAL","Villarreal":"VIL"},
   hist0=["2025/26 full season, no prior","0.994","0.964"], histTitle="Checks on La Liga",
   histNote="The settings were tuned on Premier League data, not La Liga. The market scored better in both checks."),
 "it": dict(name="Serie A", f="I1", ng=38.0, prom=33.0, nrel=3, seed=13, lmode="fixed", nm={},
   codes={"Atalanta":"ATA","Bologna":"BOL","Cagliari":"CAG","Como":"COM","Fiorentina":"FIO","Frosinone":"FRO","Genoa":"GEN","Inter":"INT","Juventus":"JUV","Lazio":"LAZ","Lecce":"LEC","Milan":"MIL","Monza":"MON","Napoli":"NAP","Parma":"PAR","Roma":"ROM","Sassuolo":"SAS","Torino":"TOR","Udinese":"UDI","Venezia":"VEN"},
   hist0=["2025/26 full season, no prior","1.022","0.980"], histTitle="Checks on Serie A",
   histNote="The settings were tuned on Premier League data. Serie A has been close to the market over a short run, but the full-season check had the market clearly ahead, so treat this as a small sample."),
 "de": dict(name="Bundesliga", f="D1", ng=34.0, prom=29.5, nrel=2, seed=17, lmode="prev",
   nm={"Ein Frankfurt":"Eintracht Frankfurt","FC Koln":"K\u00f6ln","M'gladbach":"Gladbach","Hamburg":"Hamburger SV"},
   codes={"Augsburg":"AUG","Bayern Munich":"BAY","Dortmund":"BVB","Eintracht Frankfurt":"SGE","Elversberg":"ELV","K\u00f6ln":"KOE","Freiburg":"FRE","Hamburger SV":"HSV","Hoffenheim":"HOF","Leverkusen":"LEV","Gladbach":"BMG","Mainz":"MAI","Paderborn":"PAD","RB Leipzig":"RBL","Schalke 04":"S04","Stuttgart":"VFB","Union Berlin":"UNI","Werder Bremen":"BRE"},
   hist0=["2025/26 full season, no prior","0.997","0.953"], histTitle="Checks on the Bundesliga",
   histNote="The settings were tuned on Premier League data. The goal level comes from last season\u2019s average and the 34-game season is allowed for. The market scored better in both checks. The relegation chance counts the bottom two only, not the play-off place."),
}
P = dict(w=0.6, c=0.16, k=8, hf=1.16, db=0.16)   # frozen model settings

AGENTS = ["Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Mozilla/5.0 FootIQ"]

def fetch_text(url, tries=3):
    last = "unknown error"
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTS[i % len(AGENTS)]})
            with urllib.request.urlopen(req, timeout=60) as r:
                return r.read().decode("utf-8-sig", errors="replace")
        except urllib.error.HTTPError as e:
            last = "HTTP %s" % e.code
            if e.code == 404:
                break
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        time.sleep(3)
    raise RuntimeError(last)

def parse(text):
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        if not r.get("HomeTeam") or not r.get("FTHG"):
            continue
        dt = None
        for f in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                dt = datetime.datetime.strptime(r["Date"], f); break
            except Exception:
                pass
        if dt is None:
            continue
        r["_d"] = dt; out.append(r)
    out.sort(key=lambda r: r["_d"]); return out

def points(rows):
    pts = defaultdict(int)
    for r in rows:
        hg, ag = int(r["FTHG"]), int(r["FTAG"])
        pts[r["HomeTeam"]] += 3 if hg > ag else 1 if hg == ag else 0
        pts[r["AwayTeam"]] += 3 if ag > hg else 1 if hg == ag else 0
    return dict(pts)

def pois(l, n=10):
    p = [math.exp(-l)]
    for i in range(1, n): p.append(p[-1] * l / i)
    return p

def hda(lh, la):
    a, b = pois(lh), pois(la); h = d = x = 0.0
    for i in range(10):
        for j in range(10):
            v = a[i] * b[j]
            if i > j: h += v
            elif i == j: d += v
            else: x += v
    t = h + d + x; return h / t, d / t, x / t

def eff(r, side, w):
    g = float(r["FTHG" if side == "H" else "FTAG"])
    s = float(r["HS" if side == "H" else "AS"]); sot = float(r["HST" if side == "H" else "AST"])
    return w * g + (1 - w) * (0.30 * sot + 0.04 * max(s - sot, 0))

def mk3(h, d, a):
    t = 1 / h + 1 / d + 1 / a; return [1 / h / t, 1 / d / t, 1 / a / t]

def build(key, cur, prev, fixtures):
    C = LEAGUES[key]; nm = lambda t: C["nm"].get(t, t)
    prior = points(prev); ng = C["ng"]; promoted_pts = C["prom"]
    L = (sum(int(r["FTHG"]) + int(r["FTAG"]) for r in prev) / (2 * len(prev))) if C["lmode"] == "prev" else 1.35
    mean = sum(prior.values()) / len(prior)
    z = lambda t: ((prior.get(t, promoted_pts) / ng) - (mean / ng)) / 0.40
    st = defaultdict(lambda: [0.0, 0.0, 0.0]); sh = defaultdict(lambda: [0, 0, 0, 0]); tab = defaultdict(lambda: [0] * 7)
    def rate(t):
        return ((st[t][0] + P["k"] * L * (1 + P["c"] * z(t))) / (st[t][2] + P["k"]),
                (st[t][1] + P["k"] * L * (1 - P["c"] * z(t))) / (st[t][2] + P["k"]))
    def predict(h, a):
        ah, dh = rate(h); aa, da = rate(a)
        lh = (ah * da / L) * P["hf"]; la = (aa * dh / L) / P["hf"]
        p = list(hda(lh, la)); p[1] *= 1 + P["db"]; s = sum(p)
        return [x / s for x in p], lh, la
    mr = []; mll = kll = ma = ka = 0
    for r in cur:
        h, a = r["HomeTeam"], r["AwayTeam"]; p, _, _ = predict(h, a)
        hg, ag_ = int(r["FTHG"]), int(r["FTAG"]); o = "H" if hg > ag_ else "D" if hg == ag_ else "A"; i = {"H": 0, "D": 1, "A": 2}[o]
        m = mk3(float(r["AvgH"]), float(r["AvgD"]), float(r["AvgA"]))
        mr.append([round(p[0] * 100, 1), round(p[1] * 100, 1), round(p[2] * 100, 1), round(m[0] * 100, 1), round(m[1] * 100, 1), round(m[2] * 100, 1), o])
        mll += -math.log(p[i]); kll += -math.log(m[i])
        ma += (max(range(3), key=lambda j: p[j]) == i); ka += (max(range(3), key=lambda j: m[j]) == i)
        eh, ea = eff(r, "H", P["w"]), eff(r, "A", P["w"])
        for t, fo, ag in ((h, eh, ea), (a, ea, eh)):
            s = st[t]; s[0] += fo; s[1] += ag; s[2] += 1
        for t, s_, sot, c in ((h, "HS", "HST", "HC"), (a, "AS", "AST", "AC")):
            x = sh[t]; x[0] += int(r[s_]); x[1] += int(r[sot]); x[2] += int(r[c]); x[3] += 1
        for t, gf, ga in ((h, hg, ag_), (a, ag_, hg)):
            x = tab[t]; x[4] += gf; x[5] += ga; x[6] += 3 if gf > ga else 1 if gf == ga else 0
    n = len(cur)
    rec = dict(n=n, ml=round(mll / n, 3), kl=round(kll / n, 3), ma=round(100 * ma / n, 1), ka=round(100 * ka / n, 1))
    teams = sorted(st)
    ts = {nm(t): [round(sh[t][0] / sh[t][3], 1), round(sh[t][1] / sh[t][3], 1), round(sh[t][2] / sh[t][3], 1),
                  round(rate(t)[0] / L * 100), round(L / rate(t)[1] * 100)] for t in teams}
    played = {(r["HomeTeam"], r["AwayTeam"]) for r in cur}
    up = []
    for x in fixtures:
        if x.get("Div") != C["f"]: continue
        h, a = x["HomeTeam"], x["AwayTeam"]
        if h not in st or a not in st or (h, a) in played: continue
        d = datetime.datetime.strptime(x["Date"], "%d/%m/%Y").strftime("%Y-%m-%d")
        p, lh, la = predict(h, a)
        row = [d, x["Time"], nm(h), nm(a), round(p[0] * 100, 1), round(p[1] * 100, 1), round(p[2] * 100, 1), round(lh, 2), round(la, 2)]
        try:
            m = mk3(float(x["AvgH"]), float(x["AvgD"]), float(x["AvgA"]))
            row += [round(m[0] * 100, 1), round(m[1] * 100, 1), round(m[2] * 100, 1)]
        except Exception:
            pass
        up.append(row)
    up.sort(key=lambda u: (u[0], u[1]))
    probs = {(h, a): predict(h, a)[0] for h in teams for a in teams if h != a and (h, a) not in played}
    random.seed(C["seed"]); N = 4000; cnt = {t: [0, 0, 0, 0] for t in teams}
    for _ in range(N):
        pts = {t: tab[t][6] for t in teams}
        for (h, a), p in probs.items():
            u = random.random()
            if u < p[0]: pts[h] += 3
            elif u < p[0] + p[1]: pts[h] += 1; pts[a] += 1
            else: pts[a] += 3
        o = sorted(teams, key=lambda t: (pts[t], tab[t][4] - tab[t][5], random.random()), reverse=True)
        cnt[o[0]][0] += 1
        for t in o[:4]: cnt[t][1] += 1
        for t in o[-C["nrel"]:]: cnt[t][2] += 1
        for t in teams: cnt[t][3] += pts[t]
    sim = {nm(t): [round(100 * c[0] / N, 1), round(100 * c[1] / N, 1), round(100 * c[2] / N, 1), int(c[3] / N)] for t, c in cnt.items()}
    res = [[r["_d"].strftime("%Y-%m-%d"), nm(r["HomeTeam"]), nm(r["AwayTeam"]), int(r["FTHG"]), int(r["FTAG"])] for r in cur]
    gps = [sum(1 for r in cur if t in (r["HomeTeam"], r["AwayTeam"])) for t in teams]
    codes = dict(C["codes"])
    for t in sim:
        codes.setdefault(t, t.replace(" ", "")[:3].upper())
    hist = C.get("hist") or [C["hist0"], ["This season so far, with prior", "%.3f" % rec["ml"], "%.3f" % rec["kl"]]]
    promoted = sorted(nm(t) for t in teams if t not in prior)
    return dict(name=C["name"], mw=("Next round \u00b7 times GMT" if up else "Next round not listed yet"), gp=(str(min(gps)) if min(gps) == max(gps) else "%d\u2013%d" % (min(gps), max(gps))),
                nrel=C["nrel"], promoted=promoted, hist=hist, histTitle=C["histTitle"], histNote=C["histNote"],
                mr=mr, ts=ts, res=res, up=up, sim=sim, rec=rec, codes=codes)

def season_codes(today):
    start = today.year if today.month >= 7 else today.year - 1
    return [(start, "%02d%02d" % (start % 100, (start + 1) % 100)), (start - 1, "%02d%02d" % ((start - 1) % 100, start % 100))]

def main(get=fetch_text, today=None, out_path="data.json"):
    today = today or datetime.datetime.utcnow()
    log = []
    def say(m):
        print(m); log.append(m)
    try:
        with open(out_path, encoding="utf-8") as f:
            old = json.load(f).get("leagues", {})
    except Exception:
        old = {}
    try:
        fixtures = list(csv.DictReader(io.StringIO(get(BASE + "fixtures.csv"))))
        say("fixtures.csv: %d rows" % len(fixtures))
    except Exception as e:
        say("fixtures.csv not available: %s" % e); fixtures = []
    (s0, c0), (s1, c1) = season_codes(today)
    label = "%d/%02d" % (s0, (s0 + 1) % 100)
    result = {}
    for key, C in LEAGUES.items():
        cur = None
        try:
            cur = parse(get("%smmz4281/%s/%s.csv" % (BASE, c0, C["f"])))
            prev = parse(get("%smmz4281/%s/%s.csv" % (BASE, c1, C["f"])))
        except Exception as e:
            say("%s: download failed (%s)" % (C["name"], e)); cur = None
        if not cur or len(cur) < 10:
            if cur is not None:
                say("%s: only %d matches in the %s file, too early to model" % (C["name"], len(cur), label))
            if key in old:
                result[key] = old[key]; say("%s: kept the previous data" % C["name"])
            else:
                say("%s: skipped" % C["name"])
            continue
        result[key] = build(key, cur, prev, fixtures)
        result[key]["season"] = label
        say("%s: %d matches, %d upcoming, season %s" % (C["name"], len(cur), len(result[key]["up"]), label))
    if not result:
        raise SystemExit("No league could be built, keeping the old data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"asof": datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "log": log, "leagues": result}, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote", out_path)

if __name__ == "__main__":
    main()
