# Day Trader Panel

A Streamlit app for planning day trades in two markets:

- **🥇 Gold — Asia session**: opening-range breakout on gold futures, on Gold Coast time (AEST). Live session chart, exit plan, a 10,000-replay time machine, and position sizing for CFDs, micro (MGC) and full (GC) futures.
- **🇺🇸 US stocks (NYSE)**: scanner, news, entry timer, exit plan, time machine, sizing and risk check, built on the [day-trader-skill](https://github.com/Jakeschincariol/day-trader-skill) scripts (MIT).

It never sends orders. Data is free and delayed (Yahoo Finance, SEC EDGAR, Nasdaq Trader, House Clerk). Simulations are not predictions.

## Run it online

Deploy on [Streamlit Community Cloud](https://share.streamlit.io): **Create app** → this repository → branch `main` → main file `app.py`.

Each visitor gets their own settings and plans, tied to their link (`?u=...`). Bookmark your link to keep yours.

## Run it on your computer

```
./Start-Mac.command        # Mac
Start-Windows.bat          # Windows
```

Needs Python 3.8+. Opens at http://localhost:8501.
