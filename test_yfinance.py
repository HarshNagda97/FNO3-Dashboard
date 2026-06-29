import yfinance as yf

test_tickers = ['360ONE', 'ABCAPITAL', 'ADANIENSOL', 'WIPRO', 'YESBANK', 'ZYDUSLIFE']
for t in test_tickers:
    sym = t + '.NS'
    data = yf.download(sym, period='5d', progress=False)
    print(sym, '-> OK, rows:', len(data)) if not data.empty else print(sym, '-> EMPTY/FAILED')