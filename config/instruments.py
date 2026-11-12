"""Instrument map and project constants. Single source of truth."""

# --- Crude drivers: MetaTrader 5 (configure your own broker symbols) ---
# Daily bar labelled D spans D 00:00 -> D+1 00:00 broker server time (EET/EEST,
# UTC+2/+3), i.e. it CLOSES at ~03:30 IST on D+1 -- AFTER the NSE cash close on
# day D (15:30 IST). Therefore crude bar D is only tradable on NSE day D+1.
CRUDE = {
    "brent": "UKOIL",   # primary: India's import basket is Brent-linked
    "wti":   "USOIL",   # secondary / spread partner
}

# --- Tradables: NSE cash, via yfinance (split/bonus adjusted) ---
# NOTE: "IOCL" and "IOC" are the same company (Indian Oil Corporation Ltd),
# so the OMC universe is THREE names, not four.
OMC = {
    "IOC":       "IOC.NS",         # Indian Oil Corporation
    "HINDPETRO": "HINDPETRO.NS",   # HPCL
    "BPCL":      "BPCL.NS",
}

# Upstream: opposite crude sign (crude up -> realisations up). Control / hedge leg.
UPSTREAM = {
    "ONGC": "ONGC.NS",
    "OIL":  "OIL.NS",
}

# Macro context
MACRO = {
    "USDINR": "USDINR=X",
    "NIFTY":  "^NSEI",
}

START = "2010-01-01"
END   = "2026-11-08"

# Regime boundaries for Phase 4 / Phase 1 sub-period stability checks.
REGIMES = {
    "pre_dereg":    ("2010-01-01", "2014-10-17"),  # admin pricing, diesel controlled
    "post_dereg":   ("2014-10-18", "2020-02-29"),  # diesel deregulated
    "covid":        ("2020-03-01", "2021-12-31"),  # crude crash + recovery
    "war_discount": ("2022-01-01", "2023-12-31"),  # Russia discount, price freeze
    "recent":       ("2024-01-01", "2026-11-08"),
}
