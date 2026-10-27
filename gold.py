"""Gold, Asia session: data, session range, entry signal, exit plan,
Monte Carlo replay and position sizing.

Times are Gold Coast / Brisbane time (AEST, UTC+10, no daylight saving).
Prices are COMEX gold futures (Yahoo GC=F) on 5-minute bars, free and delayed.
A spot or CFD XAU/USD quote sits a few dollars away from the futures price
(the futures basis), so levels are a guide: check them on your broker's chart.
"""

import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

AEST = timezone(timedelta(hours=10), "AEST")
BAR_MIN = 5
UA = "Mozilla/5.0 (compatible; day-trader-panel/1.0)"
HOSTS = ("query2", "query1")

INSTRUMENTS = {
    "GC=F": "COMEX gold futures (GC=F)",
    "MGC=F": "COMEX micro gold futures (MGC=F)",
}


class GoldError(Exception):
    pass


# ---------------------------------------------------------------- data

@dataclass
class Bars:
    symbol: str
    t: np.ndarray        # bar start, unix seconds
    o: np.ndarray
    h: np.ndarray
    l: np.ndarray
    c: np.ndarray
    v: np.ndarray
    fetched_at: float = 0.0

    def local(self, i):
        return datetime.fromtimestamp(int(self.t[i]), AEST)


def parse_chart(text, symbol):
    try:
        res = json.loads(text)["chart"]["result"][0]
        ts = res["timestamp"]
        q = res["indicators"]["quote"][0]
    except (ValueError, KeyError, IndexError, TypeError):
        raise GoldError("Yahoo sent no chart data for %s. Try again in a minute." % symbol)
    rows = []
    for i, t in enumerate(ts):
        o, h, l, c = q["open"][i], q["high"][i], q["low"][i], q["close"][i]
        if None in (o, h, l, c):
            continue
        rows.append((t, o, h, l, c, q.get("volume", [0] * len(ts))[i] or 0))
    if len(rows) < 50:
        raise GoldError("Too few bars from Yahoo for %s." % symbol)
    a = np.array(rows, dtype=float)
    return Bars(symbol, a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5], time.time())


def fetch(symbol="GC=F", days=60):
    rng = "%dd" % days
    last = None
    for host in HOSTS:
        url = "https://%s.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=5m&includePrePost=true" % (
            host, urllib.parse.quote(symbol), rng)
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return parse_chart(r.read().decode("utf-8", "replace"), symbol)
        except urllib.error.HTTPError as e:
            last = "HTTP %d" % e.code
            if e.code == 429:
                time.sleep(2)
        except (urllib.error.URLError, OSError) as e:
            last = str(getattr(e, "reason", e))
    raise GoldError("Could not get %s from Yahoo (%s). Check your internet and try again." % (symbol, last))


# ---------------------------------------------------------------- sessions

@dataclass
class SessionCfg:
    start: str = "10:00"        # Tokyo open = 10:00 AEST
    end: str = "17:00"          # just before London
    or_minutes: int = 30
    no_entries_after: str = "15:30"
    side: str = "both"          # long, short, both


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def session_bounds(day, cfg):
    """day: a date in AEST. Returns (start, or_end, cutoff, end) as unix seconds."""
    base = datetime(day.year, day.month, day.day, tzinfo=AEST)
    f = lambda s: int((base + timedelta(minutes=hm(s))).timestamp())
    start = f(cfg.start)
    return start, start + cfg.or_minutes * 60, f(cfg.no_entries_after), f(cfg.end)


def session_days(bars, cfg):
    """AEST dates that have bars inside the session window, oldest first."""
    days = sorted({datetime.fromtimestamp(int(t), AEST).date() for t in bars.t})
    out = []
    for d in days:
        s, _, _, e = session_bounds(d, cfg)
        if np.any((bars.t >= s) & (bars.t < e)):
            out.append(d)
    return out


@dataclass
class Signal:
    day: object
    status: str                     # before, building, waiting, triggered, expired, no_data
    message: str
    or_high: float = math.nan
    or_low: float = math.nan
    side: str = ""
    entry: float = math.nan
    entry_ts: int = 0               # end of the trigger bar
    entry_idx: int = -1             # index of the trigger bar
    last: float = math.nan
    idx: list = field(default_factory=list)   # bar indexes in this session


def signal(bars, cfg, day, now_ts=None):
    """The Asia-session opening-range breakout status for one AEST day."""
    now_ts = now_ts or time.time()
    s, or_end, cutoff, e = session_bounds(day, cfg)
    idx = list(np.nonzero((bars.t >= s) & (bars.t < e) & (bars.t + BAR_MIN * 60 <= now_ts))[0])
    sig = Signal(day, "no_data", "", idx=idx)
    if now_ts < s:
        sig.status, sig.message = "before", "Session not started. The range builds from %s to %s AEST." % (
            cfg.start, fmt_ts(or_end))
        return sig
    rng = [i for i in idx if bars.t[i] < or_end]
    if now_ts < or_end:
        sig.status = "building"
        sig.message = "Building the opening range until %s AEST (%d of %d bars)." % (
            fmt_ts(or_end), len(rng), cfg.or_minutes // BAR_MIN)
        if rng:
            sig.or_high, sig.or_low = float(bars.h[rng].max()), float(bars.l[rng].min())
        return sig
    if len(rng) < max(1, cfg.or_minutes // BAR_MIN - 1):
        sig.message = "Not enough bars in the opening range (market closed or holiday?)."
        return sig
    hi, lo = float(bars.h[rng].max()), float(bars.l[rng].min())
    sig.or_high, sig.or_low = hi, lo
    after = [i for i in idx if bars.t[i] >= or_end]
    if after:
        sig.last = float(bars.c[after[-1]])
    elif rng:
        sig.last = float(bars.c[rng[-1]])
    for i in after:
        end_ts = int(bars.t[i]) + BAR_MIN * 60
        if end_ts > cutoff:
            break
        c = float(bars.c[i])
        if cfg.side in ("long", "both") and c > hi:
            sig.side = "long"
        elif cfg.side in ("short", "both") and c < lo:
            sig.side = "short"
        else:
            continue
        sig.status, sig.entry, sig.entry_ts, sig.entry_idx = "triggered", c, end_ts, i
        sig.message = "TRIGGERED %s at %s AEST: the bar closed at %.2f, %s the range %s %.2f." % (
            sig.side.upper(), fmt_ts(end_ts), c, "above" if sig.side == "long" else "below",
            "high" if sig.side == "long" else "low", hi if sig.side == "long" else lo)
        return sig
    if now_ts >= cutoff:
        sig.status = "expired"
        sig.message = "No breakout before the %s AEST cut-off. No trade today." % cfg.no_entries_after
    else:
        sig.status = "waiting"
        parts = []
        if cfg.side in ("long", "both"):
            parts.append("a close above %.2f (%+.2f)" % (hi, hi - sig.last))
        if cfg.side in ("short", "both"):
            parts.append("a close below %.2f (%+.2f)" % (lo, lo - sig.last))
        sig.message = "Waiting. Last %.2f. Needs %s." % (sig.last, " or ".join(parts))
    return sig


def fmt_ts(ts):
    return datetime.fromtimestamp(int(ts), AEST).strftime("%H:%M")


# ---------------------------------------------------------------- exit plan

def atr(bars, end_idx, n=14):
    lo = max(1, end_idx - n + 1)
    tr = [max(bars.h[i] - bars.l[i], abs(bars.h[i] - bars.c[i - 1]), abs(bars.l[i] - bars.c[i - 1]))
          for i in range(lo, end_idx + 1)]
    return float(np.mean(tr)) if tr else math.nan


def make_plan(side, entry, or_high, or_low, stop_rule="range-mid", stop_value=0.0,
              target_r=2.0, atr_value=math.nan):
    """Returns dict(side, entry, stop, target, risk) or raises GoldError."""
    sgn = 1 if side == "long" else -1
    if stop_rule == "range-mid":
        stop = (or_high + or_low) / 2
    elif stop_rule == "range-opposite":
        stop = or_low if side == "long" else or_high
    elif stop_rule == "atr":
        if not atr_value or math.isnan(atr_value):
            raise GoldError("No ATR available for this entry.")
        stop = entry - sgn * stop_value * atr_value
    elif stop_rule == "usd":
        stop = entry - sgn * stop_value
    else:
        raise GoldError("Unknown stop rule.")
    stop = math.floor(stop * 10) / 10 if side == "long" else math.ceil(stop * 10) / 10
    risk = (entry - stop) * sgn
    if not (risk > 0):
        raise GoldError("The stop (%.2f) is on the wrong side of the entry (%.2f)." % (stop, entry))
    if risk < 0.5:
        raise GoldError("The stop is only $%.2f away: too tight for gold's spread and noise." % risk)
    target = round(entry + sgn * target_r * risk, 2)
    return dict(side=side, entry=round(entry, 2), stop=round(stop, 2), target=target,
                risk=round(risk, 2), target_r=target_r)


# ---------------------------------------------------------------- time machine

def _slot(ts, day, cfg):
    s, _, _, _ = session_bounds(day, cfg)
    return int((ts - s) // (BAR_MIN * 60))


def _pool(bars, cfg, days):
    """slot -> list of (close, high, low) relative to the previous close."""
    pool = {}
    for d in days:
        s, _, _, e = session_bounds(d, cfg)
        idx = np.nonzero((bars.t >= s) & (bars.t < e))[0]
        for i in idx:
            if i == 0:
                continue
            pc = bars.c[i - 1]
            k = int((bars.t[i] - s) // (BAR_MIN * 60))
            pool.setdefault(k, []).append((bars.c[i] / pc - 1, bars.h[i] / pc - 1, bars.l[i] / pc - 1))
    return {k: np.array(v) for k, v in pool.items()}


def replay(bars, cfg, plan, day, entry_ts, n=10000, window=2, seed=7):
    """Monte Carlo of the rest of the session from the entry, drawn from the same
    time of day in the past sessions. Stop is checked before target inside a bar."""
    s, _, _, e = session_bounds(day, cfg)
    past = [d for d in session_days(bars, cfg) if d < day]
    if len(past) < 10:
        raise GoldError("Need at least 10 past sessions of data; got %d." % len(past))
    pool = _pool(bars, cfg, past)
    k0 = int((entry_ts - s) // (BAR_MIN * 60))
    k_end = int((e - s) // (BAR_MIN * 60))
    steps = list(range(k0, k_end))
    if not steps:
        raise GoldError("The entry is at or after the session end.")
    rng = np.random.default_rng(seed)
    sgn = 1 if plan["side"] == "long" else -1
    entry, stop, target, risk = plan["entry"], plan["stop"], plan["target"], plan["risk"]
    price = np.full(n, entry, dtype=float)
    outcome = np.zeros(n, dtype=int)          # 0 open, 1 target, -1 stop
    bands = [np.percentile(price, [5, 25, 50, 75, 95])]
    times = [entry_ts]
    for j, k in enumerate(steps):
        cand = [pool[x] for x in range(k - window, k + window + 1) if x in pool]
        if not cand:
            cand = [np.concatenate(list(pool.values()))]
        src = np.concatenate(cand)
        draw = src[rng.integers(0, len(src), n)]
        hi = price * (1 + draw[:, 1])
        lo = price * (1 + draw[:, 2])
        open_ = outcome == 0
        if sgn == 1:
            hit_stop = open_ & (lo <= stop)
            hit_tgt = open_ & ~hit_stop & (hi >= target)
        else:
            hit_stop = open_ & (hi >= stop)
            hit_tgt = open_ & ~hit_stop & (lo <= target)
        outcome[hit_stop] = -1
        outcome[hit_tgt] = 1
        price = price * (1 + draw[:, 0])
        bands.append(np.percentile(price, [5, 25, 50, 75, 95]))
        times.append(s + (k + 1) * BAR_MIN * 60)
    r_open = sgn * (price - entry) / risk
    r = np.where(outcome == 1, plan["target_r"], np.where(outcome == -1, -1.0, r_open))
    return dict(
        n=n, sessions=len(past), p_target=float(np.mean(outcome == 1)), p_stop=float(np.mean(outcome == -1)),
        p_neither=float(np.mean(outcome == 0)), avg_r=float(r.mean()),
        p_green=float(np.mean(r > 0)),
        bands=np.array(bands), times=[datetime.fromtimestamp(t, AEST) for t in times],
        close_p5=float(np.percentile(price, 5)), close_med=float(np.median(price)),
        close_p95=float(np.percentile(price, 95)),
    )


def history(bars, cfg, stop_rule, stop_value, target_r, before_day=None):
    """Run the same rule on every past session in the data."""
    trades = []
    for d in session_days(bars, cfg):
        if before_day and d >= before_day:
            continue
        s, _, _, e = session_bounds(d, cfg)
        sig = signal(bars, cfg, d, now_ts=e + 1)
        if sig.status != "triggered":
            continue
        try:
            plan = make_plan(sig.side, sig.entry, sig.or_high, sig.or_low, stop_rule, stop_value, target_r,
                             atr(bars, sig.entry_idx))
        except GoldError:
            continue
        sgn = 1 if plan["side"] == "long" else -1
        result, r = "close", None
        rest = [i for i in sig.idx if bars.t[i] > bars.t[sig.entry_idx]]
        for i in rest:
            if (sgn == 1 and bars.l[i] <= plan["stop"]) or (sgn == -1 and bars.h[i] >= plan["stop"]):
                result, r = "stop", -1.0
                break
            if (sgn == 1 and bars.h[i] >= plan["target"]) or (sgn == -1 and bars.l[i] <= plan["target"]):
                result, r = "target", target_r
                break
        if r is None:
            last = bars.c[rest[-1]] if rest else plan["entry"]
            r = sgn * (last - plan["entry"]) / plan["risk"]
        trades.append(dict(date=d.isoformat(), side=plan["side"], entry=plan["entry"], stop=plan["stop"],
                           target=plan["target"], result=result, R=round(float(r), 2)))
    return trades


# ---------------------------------------------------------------- sizing

CONTRACTS = {"cfd": 1.0, "mgc": 10.0, "gc": 100.0}


def size(plan, balance, max_loss, leverage=20.0, instrument="cfd", spread=0.30):
    """Ounces or contracts that fit the max loss and the leverage cap."""
    risk = plan["risk"] + (spread if instrument == "cfd" else 0.0)
    oz_per_unit = CONTRACTS[instrument]
    by_loss = math.floor(max_loss / (risk * oz_per_unit) + 1e-9)
    by_margin = math.floor(balance * leverage / (plan["entry"] * oz_per_unit) + 1e-9)
    units = max(0, min(by_loss, by_margin))
    oz = units * oz_per_unit
    notional = oz * plan["entry"]
    return dict(units=units, oz=oz, by_loss=by_loss, by_margin=by_margin,
                binds="max loss" if by_loss <= by_margin else "leverage / margin",
                notional=notional, margin=notional / leverage if leverage else notional,
                loss_at_stop=oz * risk, gain_at_target=oz * (plan["target"] - plan["entry"]) *
                (1 if plan["side"] == "long" else -1) - (oz * spread if instrument == "cfd" else 0),
                risk_per_oz=risk)
