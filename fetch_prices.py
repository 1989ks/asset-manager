#!/usr/bin/env python3
"""
毎日の価格取得スクリプト
GitHub Actionsから実行され、prices.jsonを更新する
"""

import json
import time
import datetime
import urllib.request
import urllib.error

# ===== 投資信託 ISINコード対応表 =====
TRUST_FUNDS = {
    "0331418A.T": {
        "name": "eMAXIS Slim 全世界株式(オルカン)",
        "isin": "JP90C000GJB9"
    },
    "03311187.T": {
        "name": "eMAXIS Slim 米国株式(S&P500)",
        "isin": "JP90C000HJF5"
    },
    "04311137.T": {
        "name": "iFreeNEXT FANG+インデックス",
        "isin": "JP90C000GHV0"
    },
    "9I312179.T": {
        "name": "楽天・SCHD",
        "isin": "JP90C000P8S3"
    },
    "2931113C.T": {
        "name": "ニッセイNASDAQ100インデックスファンド",
        "isin": "JP90C000NJF9"
    },
    "0331119A.T": {
        "name": "eMAXIS Slim 新興国株式インデックス",
        "isin": "JP90C000GGH2"
    },
    "0331117A.T": {
        "name": "eMAXIS Slim 全世界株式(除く日本)",
        "isin": "JP90C000GGG4"
    },
    "9I31116A.T": {
        "name": "楽天・全米株式インデックス・ファンド(楽天VTI)",
        "isin": "JP90C000FGP5"
    },
}

US_STOCKS = [
    "CRWD", "AAPL", "PYPL", "TSLA", "XOM", "MMM", "MO", "MSFT",
    "SQ", "JPM", "DHR", "OKTA", "COST", "WMT", "NVDA", "UNH",
    "CVX", "TGT", "DIS", "PEP", "KO",
    "BFLY", "QS", "JOBY", "SBSW", "ALT", "RXRX", "MP", "CHPT",
]


def fetch_url(url, timeout=15):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json,text/plain,*/*',
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        print(f"    HTTPエラー {e.code}: {url[:80]}")
        return None
    except urllib.error.URLError as e:
        print(f"    URLエラー: {e.reason} ({url[:80]})")
        return None
    except Exception as e:
        print(f"    予期しないエラー: {type(e).__name__}: {e} ({url[:80]})")
        return None


def fetch_usd_jpy():
    text = fetch_url("https://api.frankfurter.app/latest?from=USD&to=JPY")
    if text:
        try:
            d = json.loads(text)
            rate = d.get("rates", {}).get("JPY")
            if rate:
                print(f"  USD/JPY = {rate}")
                return rate
        except Exception as e:
            print(f"  パースエラー: {e}")
    text2 = fetch_url("https://open.er-api.com/v6/latest/USD")
    if text2:
        try:
            d2 = json.loads(text2)
            rate2 = d2.get("rates", {}).get("JPY")
            if rate2:
                print(f"  USD/JPY = {rate2} (backup)")
                return rate2
        except Exception:
            pass
    print("  USD/JPY取得失敗、155を使用")
    return 155.0


def fetch_trust_price(ticker, isin, name):
    print(f"  [{ticker}] {name[:30]} を取得中...")

    # ① Yahoo Finance v8/chart
    url1 = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=5d"
    text1 = fetch_url(url1)
    if text1:
        try:
            d1 = json.loads(text1)
            chart_result = d1.get("chart", {}).get("result")
            if chart_result:
                meta = chart_result[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or meta.get("previousClose")
                if price and price > 0:
                    print(f"    OK Yahoo v8: {price}円/万口")
                    return float(price), float(prev or price)
                else:
                    print(f"    Yahoo v8: price データなし")
            else:
                error_info = d1.get("chart", {}).get("error")
                print(f"    Yahoo v8: resultなし (error: {error_info})")
        except Exception as e:
            print(f"    Yahoo v8 パースエラー: {e}")
    else:
        print(f"    Yahoo v8: 接続失敗")

    time.sleep(0.5)

    # ② Yahoo Finance v7/quote
    url2 = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
    text2 = fetch_url(url2)
    if text2:
        try:
            d2 = json.loads(text2)
            result = d2.get("quoteResponse", {}).get("result", [])
            if result:
                price2 = result[0].get("regularMarketPrice")
                prev2 = result[0].get("regularMarketPreviousClose")
                if price2 and price2 > 0:
                    print(f"    OK Yahoo v7: {price2}円/万口")
                    return float(price2), float(prev2 or price2)
            else:
                err = d2.get("quoteResponse", {}).get("error")
                print(f"    Yahoo v7: resultなし (error: {err})")
        except Exception as e:
            print(f"    Yahoo v7 パースエラー: {e}")
    else:
        print(f"    Yahoo v7: 接続失敗")

    time.sleep(0.5)

    # ③ stooq.com
    try:
        stooq_code = ticker.replace('.T', '').lower() + '.jp'
        url3 = f"https://stooq.com/q/l/?s={stooq_code}&f=sd2t2ohlcv&h&e=csv"
        text3 = fetch_url(url3)
        if text3:
            lines = text3.strip().split('\n')
            print(f"    stooq応答: {lines[0][:60] if lines else '空'}")
            if len(lines) >= 2:
                cols = lines[1].split(',')
                if len(cols) >= 5:
                    price3 = cols[4]
                    if price3 and price3 != 'N/D':
                        price3 = float(price3)
                        prev3 = float(cols[3]) if cols[3] != 'N/D' else price3
                        if price3 > 0:
                            print(f"    OK stooq: {price3}円/万口")
                            return price3, prev3
                    else:
                        print(f"    stooq: データなし (N/D)")
    except Exception as e:
        print(f"    stooq エラー: {e}")

    print(f"    NG 全API失敗")
    return None, None


def fetch_stock_price(ticker, usd_jpy):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
    text = fetch_url(url)
    if text:
        try:
            d = json.loads(text)
            chart_result = d.get("chart", {}).get("result")
            if chart_result:
                meta = chart_result[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev = meta.get("chartPreviousClose") or price
                currency = meta.get("currency", "USD")
                if price and price > 0:
                    price = float(price)
                    prev = float(prev)
                    if currency == "USD":
                        price *= usd_jpy
                        prev *= usd_jpy
                    print(f"  {ticker}: {price:.2f}円")
                    return {"price": round(price, 2), "prevClose": round(prev, 2)}
        except Exception as e:
            print(f"  {ticker}: パースエラー {e}")

    print(f"  {ticker}: 取得失敗")
    return None


def main():
    today = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"=== 価格取得開始: {today} ===\n")

    prices = {
        "updatedAt": today,
        "usdJpy": 155.0,
        "trusts": {},
        "stocks": {},
    }

    print("【USD/JPY】")
    prices["usdJpy"] = fetch_usd_jpy()
    time.sleep(1)

    print("\n【投資信託 基準価額】")
    for ticker, info in TRUST_FUNDS.items():
        price, prev = fetch_trust_price(ticker, info["isin"], info["name"])
        if price:
            prices["trusts"][ticker] = {
                "price": round(price, 2),
                "prevClose": round(prev, 2),
                "name": info["name"]
            }
        time.sleep(1)

    print("\n【米国株】")
    for ticker in US_STOCKS:
        result = fetch_stock_price(ticker, prices["usdJpy"])
        if result:
            prices["stocks"][ticker] = result
        time.sleep(0.3)

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完了: trusts={len(prices['trusts'])}件, stocks={len(prices['stocks'])}件 ===")
    if len(prices['trusts']) == 0:
        print("WARNING: 投資信託が1件も取得できませんでした")
    print("prices.json を更新しました")


if __name__ == "__main__":
    main()
