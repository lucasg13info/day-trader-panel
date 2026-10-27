"""Day Trader Panel: a local app for two markets.

  US stocks (NYSE)       runs the day-trader-skill scripts in ./skills
  Gold, Asia session     gold.py, on Gold Coast time (AEST)

Start with:  streamlit run app.py
Nothing here sends orders to a broker. It reads free public data and does the math.
"""

import json
import math
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

import gold as g

APP = Path(__file__).resolve().parent
SKILLS = APP / "skills"
PLACEHOLDER_UA = "Your Name you@example.com"

SCRIPTS = {
    "scan": SKILLS / "trader-scanner" / "scan.py",
    "news": SKILLS / "trader-news" / "news.py",
    "entry": SKILLS / "trader-entry" / "entry.py",
    "exit": SKILLS / "trader-exit" / "exit.py",
    "tm": SKILLS / "trader-timemachine" / "timemachine.py",
    "size": SKILLS / "trader-budget" / "size.py",
    "risk": SKILLS / "trader-risk" / "check.py",
    "alerts": SKILLS / "trader-alerts" / "alerts.py",
    "facts": SKILLS / "trader-analyst" / "facts.py",
    "pelosi": SKILLS / "trader-pelosi" / "ptr.py",
}

GOLD_DEFAULTS = dict(start="10:00", end="17:00", or_minutes=30, no_entries_after="15:30", side="both",
                     symbol="GC=F", balance=5000.0, max_loss=50.0, max_daily_loss=150.0,
                     leverage=20.0, spread=0.30)

# Streamlit reads "$...$" in text as a math formula; prices need a literal dollar sign.
def _dollars(fn):
    def wrapper(body="", *args, **kwargs):
        if isinstance(body, str) and not kwargs.get("unsafe_allow_html"):
            body = body.replace("\\$", "$").replace("$", "\\$")
        return fn(body, *args, **kwargs)
    return wrapper


if not getattr(st, "_dollars_patched", False):   # the script reruns; patch once per process
    for _name in ("markdown", "write", "caption", "info", "success", "warning", "error"):
        setattr(st, _name, _dollars(getattr(st, _name)))
    st._dollars_patched = True

st.set_page_config(page_title="Day Trader Panel", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")


# ------------------------------------------------------------------ who is this?
# On your own computer everything lives in ./trader. Online, each person gets a
# private workspace tied to their link (?u=...), so friends don't overwrite each
# other's settings and plans.

def _is_local():
    try:
        host = (st.context.headers.get("Host") or "").split(":")[0]
    except Exception:
        host = ""
    return host in ("localhost", "127.0.0.1", "::1", "")


if _is_local():
    WORK = APP
    USER_ID = None
else:
    uid = "".join(ch for ch in str(st.query_params.get("u", "")) if ch.isalnum())[:32]
    if not uid:
        import uuid
        uid = uuid.uuid4().hex[:12]
        st.query_params["u"] = uid
    USER_ID = uid
    WORK = APP / "workspaces" / uid
    WORK.mkdir(parents=True, exist_ok=True)

DATA = WORK / "trader"
CONFIG = DATA / "config.json"
GOLD_CFG = DATA / "gold.json"
GOLD_PLAN = DATA / "gold_plan.json"


# ------------------------------------------------------------------ helpers

def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def ensure_files():
    DATA.mkdir(exist_ok=True)
    if not CONFIG.exists():
        CONFIG.write_text((SKILLS / "trader-budget" / "config.example.json").read_text(encoding="utf-8"),
                          encoding="utf-8")
    if not GOLD_CFG.exists():
        save_json(GOLD_CFG, GOLD_DEFAULTS)


def run(name, *args, timeout=600):
    """Run a skill script with this person's workspace as the working directory."""
    cmd = [sys.executable, "-I", str(SCRIPTS[name]), *[str(a) for a in args]]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    try:
        p = subprocess.run(cmd, cwd=WORK, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env)
        out = (p.stdout or "") + (("\n" + p.stderr) if p.stderr.strip() else "")
        return p.returncode, out.strip()
    except subprocess.TimeoutExpired:
        return 1, f"Stopped after {timeout // 60} minutes."


def show(code, out, empty="No result."):
    if code != 0:
        st.error("The script ended with an error. Details below.")
    st.code(out or empty, language=None)


def tickers(text):
    return [t.strip().upper() for t in text.replace(";", ",").replace(" ", ",").split(",") if t.strip()]


PLOT_CFG = {"displayModeBar": False, "scrollZoom": False}


def fan_chart(times, bands, plan, title, yfmt=",.2f"):
    lo, q1, med, q3, hi = (list(x) for x in zip(*bands))
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=times, y=hi, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=times, y=lo, fill="tonexty", fillcolor="rgba(99,110,250,0.15)",
                             line=dict(width=0), name="90% of replays"))
    fig.add_trace(go.Scatter(x=times, y=q3, line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=times, y=q1, fill="tonexty", fillcolor="rgba(99,110,250,0.35)",
                             line=dict(width=0), name="middle half"))
    fig.add_trace(go.Scatter(x=times, y=med, line=dict(color="#636EFA", width=2), name="median"))
    for y, name, color in [(plan["target"], "target", "#00A86B"), (plan["entry"], "entry", "#888"),
                           (plan["stop"], "stop", "#E5484D")]:
        fig.add_hline(y=y, line_dash="dash", line_color=color, annotation_text=f"{name} {y:{yfmt}}",
                      annotation_position="top left", annotation_font_size=11)
    fig.update_layout(height=380, margin=dict(l=4, r=4, t=36, b=4), title=dict(text=title, font_size=13),
                      yaxis_title=None, legend=dict(orientation="h", y=-0.08, yanchor="top", x=0, font_size=11),
                      hovermode="x unified")
    st.plotly_chart(fig, width="stretch", config=PLOT_CFG)


ensure_files()
cfg = load_json(CONFIG) or {}
gcfg = {**GOLD_DEFAULTS, **(load_json(GOLD_CFG) or {})}
sec_ok = cfg.get("sec_user_agent", PLACEHOLDER_UA) not in ("", PLACEHOLDER_UA)


# ------------------------------------------------------------------ top bar (mobile friendly)

st.markdown("""
<style>
.block-container {padding-top: 4rem; padding-bottom: 3rem; max-width: 1200px;}
[data-testid="stMetricValue"] {font-size: 1.6rem;}
@media (max-width: 640px) {
  .block-container {padding-left: 0.75rem; padding-right: 0.75rem; padding-top: 3.75rem;}
  /* two columns per row instead of one tall stack */
  [data-testid="stHorizontalBlock"] {flex-wrap: wrap !important; gap: 0.6rem !important;}
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    flex: 1 1 calc(50% - 0.6rem) !important; min-width: calc(50% - 0.6rem) !important;
    width: calc(50% - 0.6rem) !important;}
  [data-testid="stMetricValue"] {font-size: 1.2rem;}
  [data-testid="stMetricLabel"] p {font-size: 0.78rem;}
  h1 {font-size: 1.45rem !important;} h2 {font-size: 1.2rem !important;} h3 {font-size: 1.05rem !important;}
  button[data-baseweb="tab"] {padding-left: 0.5rem !important; padding-right: 0.5rem !important;}
  button[data-baseweb="tab"] p {font-size: 0.85rem;}
  pre, code {font-size: 0.7rem !important;}
}
</style>
""", unsafe_allow_html=True)

MARKETS = {"gold": "🥇 Gold", "us": "🇺🇸 Stocks"}
top_l, top_r = st.columns([3, 1], vertical_alignment="center")
with top_l:
    picked = st.segmented_control("Market", list(MARKETS), format_func=MARKETS.get,
                                  default=gcfg.get("last_market", "gold"), label_visibility="collapsed")
market_key = picked or gcfg.get("last_market", "gold")
is_gold = market_key == "gold"
if gcfg.get("last_market") != market_key:
    gcfg["last_market"] = market_key
    save_json(GOLD_CFG, gcfg)

with top_r:
    with st.popover("⚙️ Settings", width="stretch"):
        if is_gold:
            st.markdown("**Asia session** (Gold Coast time, AEST)")
            with st.form("gold_cfg", border=False):
                c1, c2 = st.columns(2)
                start = c1.text_input("Starts", gcfg["start"], help="10:00 = Tokyo open.")
                end = c2.text_input("Ends", gcfg["end"], help="Flat by this time. London opens ~17:00-18:00 AEST.")
                c3, c4 = st.columns(2)
                or_minutes = c3.selectbox("Opening range", [15, 30, 60],
                                          index=[15, 30, 60].index(int(gcfg["or_minutes"])),
                                          format_func=lambda m: f"{m} min")
                cutoff = c4.text_input("No entries after", gcfg["no_entries_after"])
                side = st.selectbox("Direction", ["both", "long", "short"],
                                    index=["both", "long", "short"].index(gcfg["side"]),
                                    format_func=lambda s: {"both": "Long and short", "long": "Long only",
                                                           "short": "Short only"}[s])
                symbol = st.selectbox("Price feed", list(g.INSTRUMENTS),
                                      index=list(g.INSTRUMENTS).index(gcfg["symbol"]), format_func=g.INSTRUMENTS.get)
                st.markdown("**Risk**")
                c5, c6 = st.columns(2)
                balance = c5.number_input("Balance (US$)", 100.0, 10_000_000.0, float(gcfg["balance"]), step=500.0)
                max_loss = c6.number_input("Max loss / trade", 1.0, 1_000_000.0, float(gcfg["max_loss"]), step=5.0)
                c7, c8 = st.columns(2)
                max_day = c7.number_input("Max loss / day", 1.0, 1_000_000.0, float(gcfg["max_daily_loss"]), step=10.0)
                leverage = c8.number_input("Leverage cap", 1.0, 100.0, float(gcfg["leverage"]), step=1.0,
                                           help="ASIC caps gold CFDs at 20:1 for retail clients.")
                spread = st.number_input("CFD spread ($/oz)", 0.0, 5.0, float(gcfg["spread"]), step=0.05)
                if st.form_submit_button("Save", type="primary", width="stretch"):
                    try:
                        for t in (start, end, cutoff):
                            g.hm(t)
                        gcfg.update(start=start.strip(), end=end.strip(), or_minutes=int(or_minutes),
                                    no_entries_after=cutoff.strip(), side=side, symbol=symbol, balance=balance,
                                    max_loss=max_loss, max_daily_loss=max_day, leverage=leverage, spread=spread)
                        save_json(GOLD_CFG, gcfg)
                        st.rerun()
                    except ValueError:
                        st.error("Times must look like 10:00.")
        else:
            st.markdown("**Your limits**")
            with st.form("config", border=False):
                c1, c2 = st.columns(2)
                budget = c1.number_input("Budget (US$)", 100.0, 10_000_000.0, float(cfg.get("budget", 5000)), step=100.0)
                max_loss = c2.number_input("Max loss / trade", 1.0, 1_000_000.0,
                                           float(cfg.get("max_loss_per_trade_usd", 50)), step=5.0)
                c3, c4 = st.columns(2)
                max_day = c3.number_input("Max loss / day", 1.0, 1_000_000.0,
                                          float(cfg.get("max_daily_loss_usd", 150)), step=10.0)
                trades_day = c4.number_input("Max trades / day", 1, 50, int(cfg.get("max_trades_per_day", 3)))
                c5, c6 = st.columns(2)
                min_rr = c5.number_input("Min reward:risk", 0.5, 10.0, float(cfg.get("min_reward_risk", 1.0)), step=0.25)
                flat_by = c6.text_input("Flat by (NY time)", cfg.get("flat_by", "15:55"))
                ua_now = cfg.get("sec_user_agent", "")
                ua = st.text_input("Name and email for the SEC", "" if ua_now == PLACEHOLDER_UA else ua_now,
                                   placeholder="Your Name you@email.com",
                                   help="The SEC requires it to read filings and earnings.")
                if st.form_submit_button("Save", type="primary", width="stretch"):
                    cfg.update(budget=budget, max_loss_per_trade_usd=max_loss, max_daily_loss_usd=max_day,
                               max_trades_per_day=int(trades_day), min_reward_risk=min_rr, flat_by=flat_by.strip(),
                               sec_user_agent=ua.strip() or PLACEHOLDER_UA, paper=True)
                    save_json(CONFIG, cfg)
                    st.rerun()
        if USER_ID:
            st.caption("🔖 Your settings are tied to this page's link. Bookmark it to keep them.")

now_local = datetime.now(g.AEST)
if is_gold:
    st.caption(f"🕒 Gold Coast **{now_local:%a %H:%M}** AEST · session {gcfg['start']}–{gcfg['end']} · "
               f"max loss ${gcfg['max_loss']:,.0f}/trade")
else:
    code, out = run("alerts", "clock", timeout=30)
    st.caption(f"🕒 Gold Coast **{now_local:%a %H:%M}** AEST · {(out.splitlines()[0] if out else 'NYSE clock unavailable')}")

if not gcfg.get("welcomed"):
    with st.container(border=True):
        st.markdown("**👋 Welcome! Quick start**")
        st.markdown(
            "1. Tap **⚙️ Settings** and set your balance and max loss per trade.\n"
            "2. **Live**: watch the gold range form from 10:00 AEST and wait for a breakout.\n"
            "3. **Plan** → **Odds** → **Size**: set the stop and target, check the odds, size the trade.\n\n"
            "Data is free and a few minutes delayed. This app never places orders.")
        if st.button("Got it", type="primary"):
            gcfg["welcomed"] = True
            save_json(GOLD_CFG, gcfg)
            st.rerun()


# ================================================================== GOLD

def session_cfg():
    return g.SessionCfg(start=gcfg["start"], end=gcfg["end"], or_minutes=int(gcfg["or_minutes"]),
                        no_entries_after=gcfg["no_entries_after"], side=gcfg["side"])


@st.cache_data(ttl=60, show_spinner=False)
def gold_bars(symbol, minute_key):
    return g.fetch(symbol)


def get_bars():
    try:
        return gold_bars(gcfg["symbol"], int(time.time() // 60))
    except g.GoldError as e:
        st.error(str(e))
        return None


def default_day(bars, scfg):
    """Today if its session has started, else the latest session in the data."""
    today = datetime.now(g.AEST).date()
    s = g.session_bounds(today, scfg)[0]
    if time.time() >= s - 3600 and today.weekday() < 5:
        return today
    days = g.session_days(bars, scfg)
    return days[-1] if days else today


def session_chart(bars, scfg, day, sig, plan=None):
    s, or_end, cutoff, e = g.session_bounds(day, scfg)
    pad = 3600
    idx = [i for i in range(len(bars.t)) if s - pad <= bars.t[i] < e + pad]
    if not idx:
        st.info("No bars for this session yet.")
        return
    x = [bars.local(i) for i in idx]
    fig = go.Figure(go.Candlestick(x=x, open=bars.o[idx], high=bars.h[idx], low=bars.l[idx], close=bars.c[idx],
                                   name=bars.symbol, increasing_line_color="#00A86B", decreasing_line_color="#E5484D"))
    t = lambda ts: datetime.fromtimestamp(ts, g.AEST)
    if not math.isnan(sig.or_high):
        fig.add_shape(type="rect", x0=t(s), x1=t(or_end), y0=sig.or_low, y1=sig.or_high,
                      fillcolor="rgba(250,200,60,0.18)", line_width=0)
        for y, name in [(sig.or_high, "range high"), (sig.or_low, "range low")]:
            fig.add_shape(type="line", x0=t(s), x1=t(e), y0=y, y1=y, line=dict(color="#C9A227", dash="dot", width=1))
            fig.add_annotation(x=t(e), y=y, text=f"{name} {y:,.2f}", showarrow=False, xanchor="right",
                               yanchor="bottom", font_size=11)
    fig.add_vrect(x0=t(cutoff), x1=t(e), fillcolor="rgba(120,120,120,0.08)", line_width=0)
    if sig.status == "triggered":
        fig.add_trace(go.Scatter(x=[t(sig.entry_ts)], y=[sig.entry], mode="markers",
                                 marker=dict(symbol="triangle-up" if sig.side == "long" else "triangle-down",
                                             size=14, color="#636EFA"), name=f"{sig.side} entry"))
    if plan and plan.get("day") == day.isoformat():
        for k, color in [("stop", "#E5484D"), ("target", "#00A86B")]:
            fig.add_hline(y=plan[k], line_dash="dash", line_color=color, annotation_text=f"{k} {plan[k]:,.2f}",
                          annotation_position="top left", annotation_font_size=11)
    fig.update_layout(height=420, margin=dict(l=4, r=4, t=36, b=4), xaxis_rangeslider_visible=False,
                      yaxis_title=None, showlegend=False, dragmode="pan",
                      title=dict(text=f"{bars.symbol} · {day:%a %d %b} · {scfg.start}–{scfg.end} AEST", font_size=13))
    st.plotly_chart(fig, width="stretch", config=PLOT_CFG)


def gold_live(day):
    bars = get_bars()
    if bars is None:
        return
    scfg = session_cfg()
    sig = g.signal(bars, scfg, day)
    st.session_state["gold_sig"] = sig
    color = {"triggered": st.success, "waiting": st.info, "building": st.info,
             "before": st.info, "expired": st.warning}.get(sig.status, st.warning)
    color(sig.message)
    m = st.columns(4)
    m[0].metric("Last", f"{bars.c[-1]:,.2f}", help=f"Last bar {bars.local(len(bars.t) - 1):%H:%M} AEST")
    m[1].metric("Range high", "—" if math.isnan(sig.or_high) else f"{sig.or_high:,.2f}")
    m[2].metric("Range low", "—" if math.isnan(sig.or_low) else f"{sig.or_low:,.2f}")
    m[3].metric("Range size", "—" if math.isnan(sig.or_high) else f"${sig.or_high - sig.or_low:,.2f}")
    session_chart(bars, scfg, day, sig, load_json(GOLD_PLAN))


def gold_ui():
    st.subheader("🥇 Gold — Asia session")
    st.write(f"Opening-range breakout on 5-minute bars. The range is the first {gcfg['or_minutes']} minutes "
             f"from {gcfg['start']} AEST; a bar that closes outside it is the signal. Flat by {gcfg['end']}.")
    tabs = st.tabs(["📈 Live", "🎯 Plan", "🔮 Odds", "💰 Size", "📰 News"])
    scfg = session_cfg()

    # ---- live
    with tabs[0]:
        bars = get_bars()
        if bars is None:
            st.stop()
        days = g.session_days(bars, scfg)
        dflt = default_day(bars, scfg)
        options = sorted(set(days[-15:]) | {dflt}, reverse=True)
        c1, c2 = st.columns([2, 1])
        day = c1.selectbox("Session", options, index=options.index(dflt), format_func=lambda d: f"{d:%a %d %b %Y}")
        auto = c2.toggle("Auto-refresh every 60 s", value=False)
        if auto:
            st.fragment(run_every=60)(gold_live)(day)
        else:
            gold_live(day)
        sig = st.session_state.get("gold_sig")
        if sig and sig.status == "triggered":
            if st.button(f"Use this {sig.side} signal →", type="primary"):
                st.session_state["gold_seed"] = dict(day=day.isoformat(), side=sig.side, entry=sig.entry,
                                                     or_high=sig.or_high, or_low=sig.or_low,
                                                     entry_ts=sig.entry_ts, entry_idx=int(sig.entry_idx))
                st.success("Loaded. Open the 🎯 Plan tab.")
        st.caption("Prices are COMEX gold futures. Your broker's XAU/USD CFD price is usually a few dollars "
                   "different (the futures basis): use the distances, and check levels on your broker's chart.")

    # ---- exit plan
    with tabs[1]:
        st.subheader("Set the stop and target before you enter")
        seed = st.session_state.get("gold_seed") or {}
        sig = st.session_state.get("gold_sig")
        if not seed and sig and not math.isnan(sig.or_high):
            seed = dict(day=sig.day.isoformat(), side=sig.side or "long", entry=sig.entry if sig.status == "triggered"
                        else sig.last, or_high=sig.or_high, or_low=sig.or_low, entry_ts=sig.entry_ts,
                        entry_idx=int(sig.entry_idx))
        if not seed:
            st.info("Open the 📈 Live tab first, or type the numbers below.")
        c1, c2, c3 = st.columns(3)
        side = c1.selectbox("Direction", ["long", "short"], index=0 if seed.get("side", "long") == "long" else 1,
                            format_func=lambda s: "Long (buy)" if s == "long" else "Short (sell)")
        entry = c2.number_input("Entry", 0.0, 100000.0, float(seed.get("entry") or 0.0), step=0.1, format="%.2f")
        target_r = c3.selectbox("Target", [1.0, 1.5, 2.0, 3.0], index=2, format_func=lambda r: f"{r:g}R")
        c4, c5 = st.columns(2)
        or_high = c4.number_input("Range high", 0.0, 100000.0, float(seed.get("or_high") or 0.0), step=0.1, format="%.2f")
        or_low = c5.number_input("Range low", 0.0, 100000.0, float(seed.get("or_low") or 0.0), step=0.1, format="%.2f")
        c6, c7 = st.columns(2)
        stop_rule = c6.selectbox("Stop", ["range-mid", "range-opposite", "atr", "usd"], format_func=lambda s: {
            "range-mid": "Range middle", "range-opposite": "Range other side",
            "atr": "ATR multiple", "usd": "Fixed $ distance"}[s])
        stop_value = c7.number_input("ATR multiple or $ distance", 0.0, 1000.0,
                                     1.5 if stop_rule == "atr" else 5.0, step=0.5,
                                     disabled=stop_rule in ("range-mid", "range-opposite"))
        if st.button("Make plan", type="primary"):
            try:
                atr_v = math.nan
                if stop_rule == "atr":
                    bars = get_bars()
                    i = seed.get("entry_idx", -1)
                    atr_v = g.atr(bars, i if i and i > 0 else len(bars.t) - 1)
                plan = g.make_plan(side, entry, or_high, or_low, stop_rule, stop_value, target_r, atr_v)
                plan.update(day=seed.get("day", datetime.now(g.AEST).date().isoformat()),
                            entry_ts=int(seed.get("entry_ts") or 0), stop_rule=stop_rule, stop_value=stop_value,
                            symbol=gcfg["symbol"], created=datetime.now(g.AEST).isoformat(timespec="minutes"))
                save_json(GOLD_PLAN, plan)
                st.success("Plan saved.")
            except g.GoldError as e:
                st.error(str(e))
        plan = load_json(GOLD_PLAN)
        if plan:
            st.caption(f"Saved plan for {plan['day']} ({plan['symbol']})")
            m = st.columns(5)
            m[0].metric("Side", plan["side"].upper())
            m[1].metric("Entry", f"{plan['entry']:,.2f}")
            m[2].metric("Stop", f"{plan['stop']:,.2f}", f"-${plan['risk']:,.2f}/oz", delta_color="inverse")
            m[3].metric("Target", f"{plan['target']:,.2f}", f"+${plan['target_r'] * plan['risk']:,.2f}/oz")
            m[4].metric("Reward:risk", f"{plan['target_r']:g} : 1")
            st.caption("If price hits the stop you are out; never move it further away. A stop can fill past "
                       f"its price in a fast market. Flat by {gcfg['end']} AEST, win or lose.")

    # ---- time machine
    with tabs[2]:
        st.subheader("Replay the rest of the session thousands of times")
        st.write("Each replay rebuilds the session from gold's own 5-minute bars at the same time of day over "
                 "the last ~60 days, then the same rule is run on every past session.")
        plan = load_json(GOLD_PLAN)
        if not plan:
            st.info("Make a plan in the 🎯 Plan tab first.")
        n = st.select_slider("Replays", [1000, 2000, 5000, 10000], 10000)
        if st.button("Run the time machine", type="primary", disabled=not plan):
            bars = get_bars()
            if bars is not None:
                day = datetime.fromisoformat(plan["day"]).date()
                s, or_end, _, e = g.session_bounds(day, scfg)
                entry_ts = plan.get("entry_ts") or or_end + g.BAR_MIN * 60
                if not s <= entry_ts < e:
                    entry_ts = or_end + g.BAR_MIN * 60
                try:
                    with st.spinner("Replaying..."):
                        mc = g.replay(bars, scfg, plan, day, entry_ts, n=n)
                        hist = g.history(bars, scfg, plan.get("stop_rule", "range-mid"), plan.get("stop_value", 0),
                                         plan["target_r"], before_day=day)
                    m = st.columns(4)
                    m[0].metric("Target first", f"{mc['p_target']:.1%}")
                    m[1].metric("Stop first", f"{mc['p_stop']:.1%}")
                    m[2].metric(f"Neither by {gcfg['end']}", f"{mc['p_neither']:.1%}")
                    m[3].metric("Average R", f"{mc['avg_r']:+.2f}")
                    fan_chart(mc["times"], mc["bands"], plan,
                              f"{plan['side'].upper()} from {g.fmt_ts(entry_ts)} · {n:,} replays")
                    need = 1 / (1 + plan["target_r"])
                    hit = mc["p_target"] + mc["p_stop"]
                    share = mc["p_target"] / hit if hit else 0
                    lean = "toward the target" if share > need + 0.05 else "toward the stop" if share < need - 0.05 else "close to a coin flip"
                    st.info(f"At {plan['target_r']:g}R the target has to come first in {need:.0%} of the replays "
                            f"that hit one side to break even; it did in {share:.0%}. This plan leans **{lean}**.")
                    if hist:
                        wins = sum(t["result"] == "target" for t in hist)
                        stops = sum(t["result"] == "stop" for t in hist)
                        avg = sum(t["R"] for t in hist) / len(hist)
                        st.write(f"**Real history:** the same rule fired on {len(hist)} past sessions: {wins} target, "
                                 f"{stops} stop, {len(hist) - wins - stops} closed at {gcfg['end']}. Average R {avg:+.2f}.")
                        with st.expander("Every past trade"):
                            st.dataframe(hist, width="stretch")
                    st.caption("Built from recent sessions only. It is not a prediction: central-bank news, "
                               "US data and weekend gaps can do things those sessions never did.")
                except g.GoldError as e:
                    st.error(str(e))

    # ---- size
    with tabs[3]:
        st.subheader("How much to trade")
        plan = load_json(GOLD_PLAN)
        if not plan:
            st.info("Make a plan in the 🎯 Plan tab first.")
        else:
            st.caption(f"Balance ${gcfg['balance']:,.0f} · max loss ${gcfg['max_loss']:,.0f} per trade, "
                       f"${gcfg['max_daily_loss']:,.0f} per day · leverage {gcfg['leverage']:g}:1 · "
                       f"spread ${gcfg['spread']:.2f}/oz (change in ⚙️ Settings)")
            cols = st.columns(3)
            for col, (inst, label) in zip(cols, [("cfd", "XAU/USD CFD"), ("mgc", "Micro gold futures (MGC, 10 oz)"),
                                                 ("gc", "Gold futures (GC, 100 oz)")]):
                r = g.size(plan, gcfg["balance"], gcfg["max_loss"], gcfg["leverage"], inst, gcfg["spread"])
                with col:
                    st.markdown(f"**{label}**")
                    if r["units"] == 0:
                        st.error(f"Too big: one {'oz' if inst == 'cfd' else 'contract'} risks "
                                 f"${r['risk_per_oz'] * g.CONTRACTS[inst]:,.2f} at the stop, over your "
                                 f"${gcfg['max_loss']:,.0f} max loss.")
                        continue
                    unit = f"{r['oz']:g} oz = {r['oz'] / 100:.2f} lots" if inst == "cfd" else f"{r['units']} contract(s)"
                    st.metric("Size", unit)
                    st.write(f"Loss at stop: **${r['loss_at_stop']:,.2f}**  \n"
                             f"Gain at target: **${r['gain_at_target']:,.2f}**  \n"
                             f"Position value: ${r['notional']:,.0f}  \n"
                             f"Margin at {gcfg['leverage']:g}:1: ${r['margin']:,.0f} "
                             f"({r['margin'] / gcfg['balance']:.0%} of balance)  \n"
                             f"Limited by: {r['binds']}")
            st.caption("CFD lots assume 1 lot = 100 oz; check your broker's contract size and minimum. "
                       "Futures margin is set by the broker, not by the leverage cap. Nothing has been placed.")

    # ---- news
    with tabs[4]:
        st.subheader("Gold headlines")
        st.write("Yahoo Finance headlines for gold. In the Asia session, watch for China demand, the PBOC, "
                 "the yen and any US data released overnight.")
        hours = st.slider("Last N hours", 1, 72, 24)
        if st.button("Get headlines", type="primary"):
            with st.spinner("Fetching..."):
                show(*run("news", "--tickers", "GC=F", "--no-sec", "--no-moves", "--all", "--hours", hours,
                          "--dry-run"), empty="No headlines.")


# ================================================================== US STOCKS

def us_ui():
    st.subheader("🇺🇸 US stocks (NYSE)")
    tabs = st.tabs(["🔎 Scan", "📰 News", "⏱️ Entry", "🎯 Plan", "🔮 Odds", "💰 Size",
                    "🔔 Alerts", "📊 Earnings", "🏛️ Congress"])

    with tabs[0]:
        st.subheader("Chart scanner")
        st.write("Finds chart setups. A list of setups is not a shopping list.")
        universe = DATA / "universe.txt"
        c1, c2 = st.columns([2, 1])
        with c1:
            mode = st.radio("Scan", ["Pre-market (daily closes)", "Opening-range breakout (during the session)"],
                            horizontal=True)
            syms = st.text_input("Specific tickers (optional)", placeholder="AAPL, TSLA, NVDA — blank = every US stock")
        with c2:
            min_price = st.number_input("Min price (US$)", 0.0, 10000.0, 5.0)
            limit = st.number_input("Only the first N stocks (0 = all)", 0, 20000, 0, step=500,
                                    help="A full scan takes a few minutes.")
        if not universe.exists() and not syms.strip():
            st.info("First time? Download the US stock list before scanning everything.")
        b1, b2 = st.columns(2)
        if b2.button("Download / update stock list", width="stretch"):
            with st.spinner("Downloading from Nasdaq Trader..."):
                show(*run("scan", "universe"))
        if b1.button("Run scanner", type="primary", width="stretch"):
            args = ["daily" if mode.startswith("Pre") else "orb", "--min-price", min_price, "--show", 50]
            if syms.strip():
                args += ["--symbols", ",".join(tickers(syms))]
            if limit:
                args += ["--limit", limit]
            with st.spinner("Scanning charts... (the full list can take a few minutes)"):
                code, out = run("scan", *args, timeout=1800)
            show(code, out)
            wl = load_json(DATA / "watchlist.json")
            if wl and wl.get("hits"):
                st.subheader(f"{len(wl['hits'])} setups found")
                st.dataframe(wl["hits"], width="stretch")

    with tabs[1]:
        st.subheader("News")
        st.write("Yahoo Finance headlines, SEC 8-K filings and how far each stock has moved since yesterday.")
        if not sec_ok:
            st.warning("Add your name and email for the SEC in ⚙️ Settings to see filings. Without it, headlines only.")
        n1, n2 = st.columns([3, 1])
        news_syms = n1.text_input("Tickers", placeholder="AAPL, TSLA — blank = your scanner list and your plan")
        hours = n2.number_input("Last N hours", 1, 168, 24)
        show_all = st.checkbox("Include items I've already seen", value=True)
        if st.button("Get news", type="primary"):
            args = ["--hours", hours]
            if news_syms.strip():
                args += ["--tickers", *tickers(news_syms)]
            if show_all:
                args.append("--all")
            if not sec_ok:
                args.append("--no-sec")
            with st.spinner("Fetching..."):
                show(*run("news", *args), empty="Nothing new.")

    with tabs[2]:
        st.subheader("Time the entry")
        st.write("Watches the setup bar by bar and says whether it's time to get in, or not yet.")
        e1, e2, e3 = st.columns(3)
        e_sym = e1.text_input("Ticker", "TSLA", key="e_sym").strip().upper()
        setup = e2.selectbox("Setup", ["orb", "level"], format_func=lambda s: {
            "orb": "Opening-range breakout", "level": "Close above a price"}[s])
        interval = e3.selectbox("Bars", ["5m", "1m"], format_func=lambda s: {"5m": "5 minutes", "1m": "1 minute"}[s])
        f1, f2 = st.columns(2)
        or_min = f1.number_input("Opening range (minutes)", 5, 60, 15, step=5)
        level = f2.number_input("Level (for 'close above a price')", 0.0, 100000.0, 0.0)
        auto = st.checkbox("Auto-refresh every 60 seconds")

        def entry_check():
            args = ["check", e_sym, "--setup", setup, "--interval", interval, "--or-minutes", or_min, "--write"]
            if setup == "level" and level > 0:
                args += ["--level", level]
            show(*run("entry", *args, timeout=120))

        if auto:
            st.fragment(run_every=60)(entry_check)()
        elif st.button("Check now", type="primary"):
            entry_check()

    with tabs[3]:
        st.subheader("Exit plan")
        st.write("Sets the stop and the target before you enter.")
        entry_saved = load_json(DATA / "entry.json")
        source = st.radio("Based on", ["The last entry check", "A price I type"], horizontal=True)
        x1, x2, x3 = st.columns(3)
        x_sym = x1.text_input("Ticker", (entry_saved or {}).get("symbol", "TSLA"), key="x_sym").strip().upper()
        x_entry = x2.number_input("Entry price", 0.0, 100000.0, 0.0)
        target = x3.selectbox("Target", ["2R", "1.5R", "1R"], help="R is the risk per share. 2R = make twice what you risk.")
        s1, s2 = st.columns(2)
        stop_kind = s1.selectbox("Stop", ["default", "or-low", "pct", "price"], format_func=lambda s: {
            "default": "Middle of the opening range (default)", "or-low": "Low of the opening range",
            "pct": "Percent under the entry", "price": "A price I type"}[s],
            help="With a typed price there is no opening range; the default becomes the percent.")
        stop_val = s2.number_input("Stop value (% or price)", 0.0, 100000.0, 1.0)
        if source.startswith("The last") and not entry_saved:
            st.info("No saved entry check yet. Use the Entry tab or type a price.")
        if st.button("Make plan", type="primary"):
            args = ["plan", "--target", target, "--write"]
            if source.startswith("The last"):
                if x_entry:
                    args += ["--entry", x_entry]
            else:
                args += ["--symbol", x_sym, "--entry", x_entry]
            if stop_kind == "default" and not source.startswith("The last"):
                args += ["--stop", f"pct:{stop_val}"]
            elif stop_kind == "or-low":
                args += ["--stop", "or-low"]
            elif stop_kind == "pct":
                args += ["--stop", f"pct:{stop_val}"]
            elif stop_kind == "price":
                args += ["--stop", f"price:{stop_val}"]
            show(*run("exit", *args))
        plan = load_json(DATA / "plan.json")
        if plan:
            st.caption("Current saved plan (used by the next tabs)")
            p = plan.get("plan", plan)
            m = st.columns(4)
            m[0].metric("Ticker", p.get("symbol", "?"))
            m[1].metric("Entry", f"${p.get('entry', 0):,.2f}")
            m[2].metric("Stop", f"${p.get('stop', 0):,.2f}")
            m[3].metric("Target", f"${p.get('target', 0):,.2f}")

    with tabs[4]:
        st.subheader("Time machine")
        st.write("Replays the rest of the day thousands of times from the stock's own recent bars.")
        has_plan = (DATA / "plan.json").exists()
        if not has_plan:
            st.info("Make a plan in the 🎯 Plan tab first.")
        replays = st.select_slider("Replays", [1000, 2000, 5000, 10000], 10000, key="us_replays")
        if st.button("Run the time machine", type="primary", disabled=not has_plan, key="us_tm"):
            with st.spinner("Replaying..."):
                code, out = run("tm", "run", "--replays", replays, "--write")
            tm = load_json(DATA / "timemachine.json") if code == 0 else None
            if tm:
                mc, hist, p = tm["mc"], tm["history"], tm["plan"]
                m = st.columns(4)
                m[0].metric("Target first", f"{mc['p_target']:.1%}")
                m[1].metric("Stop first", f"{mc['p_stop']:.1%}")
                m[2].metric("Neither by the close", f"{mc['p_neither']:.1%}")
                m[3].metric("Average R", f"{mc['avg_R']:+.2f}")
                fan_chart(mc["band_times"], mc["bands"], p,
                          f"{p['symbol']} from {p['entry_time']} · {mc['replays']:,} replays")
                st.write(f"**Real history:** the same rule fired {hist['triggered']} times in {hist['sessions']} "
                         f"sessions: {hist['target']} target, {hist['stop']} stop, {hist['close']} neither. "
                         f"Average R {hist['avg_R']:+.2f}.")
                if tm.get("verdict"):
                    st.info(tm["verdict"])
            with st.expander("Full report"):
                show(code, out)

    with tabs[5]:
        st.subheader("Position size and risk check")
        st.caption(f"Limits: budget ${cfg.get('budget', 0):,.0f} · max loss per trade "
                   f"${cfg.get('max_loss_per_trade_usd', 0):,.0f} · per day ${cfg.get('max_daily_loss_usd', 0):,.0f} "
                   "(change in ⚙️ Settings)")
        limit_order = st.checkbox("Limit order at the entry price (instead of market)")
        if st.button("Size and check", type="primary", disabled=not (DATA / "plan.json").exists()):
            code, out = run("size", "--write", *(["--limit"] if limit_order else []))
            st.markdown("**Size**")
            show(code, out)
            if code == 0:
                st.markdown("**Risk**")
                show(*run("risk"))
        st.caption("The panel stops here on purpose. To send the order, use the trader-broker skill in Claude, "
                   "which asks for your yes before every order.")

    with tabs[6]:
        st.subheader("Alerts and quotes")
        q1c, q2c = st.columns([3, 1])
        q_syms = q1c.text_input("Quotes for", "AAPL, TSLA, NVDA")
        if q2c.button("Get quotes", width="stretch"):
            show(*run("alerts", "quote", *tickers(q_syms)))
        st.markdown("**New alert**")
        a1, a2, a3 = st.columns(3)
        a_sym = a1.text_input("Ticker", "TSLA", key="a_sym").strip().upper()
        a_kind = a2.selectbox("When", ["above", "below", "pct", "plan"], format_func=lambda s: {
            "above": "Rises above", "below": "Falls below", "pct": "Moves X% from yesterday",
            "plan": "Stop, target and flat-by time from my plan"}[s])
        a_val = a3.number_input("Value", 0.0, 100000.0, 0.0, key="a_val")
        if st.button("Add alert"):
            if a_kind == "plan":
                show(*run("alerts", "add", "--from-plan"))
            else:
                show(*run("alerts", "add", "--symbol", a_sym, f"--{a_kind}", a_val))
        st.markdown("**My alerts**")
        c1, c2 = st.columns(2)
        if c1.button("List", width="stretch"):
            show(*run("alerts", "list"))
        watch = c2.checkbox("Check every 60 seconds")

        def alerts_check():
            code, out = run("alerts", "check", timeout=120)
            if code == 0 and out and not out.startswith("Nothing hit"):
                st.toast("🔔 An alert rang!")
            show(code, out, empty="No alert rang.")

        if watch:
            st.fragment(run_every=60)(alerts_check)()
        elif st.button("Check alerts now"):
            alerts_check()

    with tabs[7]:
        st.subheader("Earnings")
        st.write("Reads the official numbers from the SEC: revenue, margins, net income and EPS, each quarter "
                 "against the same quarter a year earlier.")
        if not sec_ok:
            st.warning("Add your name and email for the SEC in ⚙️ Settings first.")
        f_syms = st.text_input("Companies", "AAPL")
        quarters = st.slider("Quarters", 2, 12, 6)
        if st.button("Read earnings", type="primary", disabled=not sec_ok):
            with st.spinner("Asking the SEC..."):
                show(*run("facts", *tickers(f_syms), "--quarters", quarters))

    with tabs[8]:
        st.subheader("US Congress stock trades")
        st.write("New stock trade disclosures from members of the US House (STOCK Act).")
        g1, g2 = st.columns(2)
        member = g1.text_input("Member (optional)", placeholder="Pelosi")
        since = g2.date_input("Filed since", value=None)
        if st.button("Get filings", type="primary"):
            args = ["new", "--dry-run"]
            if member.strip():
                args += ["--member", member.strip()]
            if since:
                args += ["--since", since.isoformat()]
            with st.spinner("Asking the House Clerk..."):
                show(*run("pelosi", *args), empty="No new filings.")
        st.caption("Reading each filing's line items downloads its PDF and needs the pdftotext program.")


if is_gold:
    gold_ui()
else:
    us_ui()
