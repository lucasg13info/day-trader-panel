DAY TRADER PANEL
================

A local app that opens in your browser. Pick the market at the top:

  Gold - Asia session    opening-range breakout on gold, Gold Coast time (AEST)
  US stocks (NYSE)       runs the day-trader-skill scripts (MIT, Jake Schincariol)

START IT
  Mac:     open Terminal and run
             cd ~/Downloads/day-trader-panel
             ./Start-Mac.command
           (or right-click Start-Mac.command > Open)
  Windows: double-click Start-Windows.bat

  The first run sets itself up (a minute or two), then opens
  http://localhost:8501 in your browser. To quit: Ctrl+C or close the Terminal.
  Needs Python 3.8+ (https://www.python.org/downloads/).

GOLD - ASIA SESSION (all times AEST, Gold Coast)
  10:00         Tokyo opens: the opening range starts (default 30 min)
  ~11:00        Shanghai Gold Exchange opens: China demand moves price
  15:30         no new entries after this (default)
  17:00         flat by: the session ends before London opens (~17:00-18:00)

  Tabs, in order:
    Live           the range, the breakout signal and the chart (auto-refresh option)
    Plan           stop and target before you enter
    Odds           10,000 replays of the rest of the session + every past session
    Size           CFD ounces/lots, micro (MGC) or full (GC) futures contracts
    News           gold headlines

  Change the session times, direction, balance, max loss, leverage
  (ASIC caps gold CFDs at 20:1 for retail) and spread in ⚙️ Settings.

  Prices are COMEX gold futures from Yahoo, free and delayed. A broker's
  XAU/USD CFD price is usually a few dollars away (the futures basis):
  use the distances and check levels on your broker's chart.

US STOCKS
  NYSE opens 9:30 New York = 23:30 AEST until 1 Nov, 00:30 AEST after.
  Scan > News > Entry > Plan > Odds > Size.
  Add your name and email for the SEC in ⚙️ Settings.

IMPORTANT
  - The panel never sends orders.
  - Simulations are not predictions. The decision and the risk are yours.
  - CFDs and futures are leveraged: most retail CFD accounts lose money.
  - Your settings and plans are saved in the "trader" folder.
