import yfinance as yf
print("Testing GC=F")
try:
    print(yf.Ticker("GC=F").history(period="1d"))
except Exception as e:
    print(e)
print("Testing XAUUSD=X")
try:
    print(yf.Ticker("XAUUSD=X").history(period="1d"))
except Exception as e:
    print(e)
print("Testing GOLD")
try:
    print(yf.Ticker("GOLD").history(period="1d"))
except Exception as e:
    print(e)
