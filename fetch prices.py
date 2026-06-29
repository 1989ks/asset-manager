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

# ===== 米国株ティッカー =====
US_STOCKS = [
    "CRWD", "AAPL", "PYPL", "TSLA", "XOM", "MMM", "MO", "MSFT",
    "SQ", "JPM", "DHR", "OKTA", "COST", "WMT", "NVDA", "UNH",
    "CVX", "TGT", "DIS", "PEP", "KO",
    "BFLY", "QS", "JOBY", "SBSW", "ALT", "RXRX", "MP", "CHPT",
]


def fetch_url(url, timeout=15):
    """URLからデータを取得"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (compatible; PriceBot/1.0)',
            'Accept': 'application/json,text/plain,*/*',
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f"  エラー: {url[:60]}... → {e}")
        return None


def fetch_usd_jpy():
    """USD/JPYレートを取得"""
    text = fetch_url("https://api.frankfurter.app/latest?from=USD&to=JPY")
    if text:
        d = json.loads(text)
        rate = d.get("rates", {}).get("JPY")
        if rate:
            print(f"  USD/JPY = {rate}")
            return rate
    # バックアップ
    text2 = fetch_url("https://open.er-api.com/v6/latest/USD")
    if text2:
        d2 = json.loads(text2)
        rate2 = d2.get("rates", {}).get("JPY")
        if rate2:
            print(f"  USD/JPY = {rate2} (backup)")
            return rate2
    print("  USD/JPY取得失敗、155を使用")
    return 155.0


def fetch_trust_price(ticker, isin):
    """
    投資信託の基準価額を取得（円/万口）
    投資信託協会API → Yahoo Finance の順で試みる
    """
    # ① 投資信託協会API（サーバーサイドなのでCORS不要）
    url = f"https://toushin-lib.fwg.ne.jp/FdsWeb/FDST030000?isinCd={isin}"
    text = fetch_url(url)
    if text:
        try:
            d = json.loads(text)
            # レスポンス形式に応じてパース
            if isinstance(d, list) and len(d) > 0:
                price = float(d[0].get("basicPrice") or d[0].get("price") or 0)
                if price > 0:
                    print(f"  {ticker}: {price}円/万口 (投信協会)")
                    return price
            elif isinstance(d, dict):
                price = float(d.get("basicPrice") or d.get("price") or 0)
                if price > 0:
                    print(f"  {ticker}: {price}円/万口 (投信協会)")
                    return price
        except Exception:
            pass

    # ② Yahoo Finance v7/quote（サーバーサイドなのでCORS不要）
    url2 = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}&lang=ja&region=JP"
    text2 = fetch_url(url2)
    if text2:
        try:
            d2 = json.loads(text2)
            result = d2.get("quoteResponse", {}).get("result", [])
            if result:
                price2 = float(result[0].get("regularMarketPrice") or 0)
                prev2  = float(result[0].get("regularMarketPreviousClose") or price2)
                if price2 > 0:
                    print(f"  {ticker}: {price2}円/万口 (Yahoo Finance)")
                    return price2, prev2
        except Exception:
            pass

    # ③ Yahoo Finance v8/chart
    url3 = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
    text3 = fetch_url(url3)
    if text3:
        try:
            d3 = json.loads(text3)
            meta = d3.get("chart", {}).get("result", [{}])[0].get("meta", {})
            price3 = float(meta.get("regularMarketPrice") or 0)
            prev3  = float(meta.get("chartPreviousClose") or price3)
            if price3 > 0:
                print(f"  {ticker}: {price3}円/万口 (Yahoo Finance v8)")
                return price3, prev3
        except Exception:
            pass

    print(f"  {ticker}: 取得失敗")
    return None


def fetch_stock_price(ticker, usd_jpy):
    """米国株の価格を取得してJPY換算"""
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
    text = fetch_url(url)
    if text:
        try:
            d = json.loads(text)
            result = d.get("quoteResponse", {}).get("result", [])
            if result:
                price = float(result[0].get("regularMarketPrice") or 0)
                prev  = float(result[0].get("regularMarketPreviousClose") or price)
                currency = result[0].get("currency", "USD")
                if price > 0:
                    if currency == "USD":
                        price *= usd_jpy
                        prev  *= usd_jpy
                    print(f"  {ticker}: {price:.2f}円")
                    return {"price": round(price, 2), "prevClose": round(prev, 2)}
        except Exception:
            pass

    # バックアップ: v8
    url2 = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
    text2 = fetch_url(url2)
    if text2:
        try:
            d2 = json.loads(text2)
            meta = d2.get("chart", {}).get("result", [{}])[0].get("meta", {})
            price2 = float(meta.get("regularMarketPrice") or 0)
            prev2  = float(meta.get("chartPreviousClose") or price2)
            currency2 = meta.get("currency", "USD")
            if price2 > 0:
                if currency2 == "USD":
                    price2 *= usd_jpy
                    prev2  *= usd_jpy
                print(f"  {ticker}: {price2:.2f}円 (v8)")
                return {"price": round(price2, 2), "prevClose": round(prev2, 2)}
        except Exception:
            pass

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

    # USD/JPY
    print("【USD/JPY】")
    prices["usdJpy"] = fetch_usd_jpy()
    time.sleep(1)

    # 投資信託
    print("\n【投資信託 基準価額】")
    for ticker, info in TRUST_FUNDS.items():
        result = fetch_trust_price(ticker, info["isin"])
        if result:
            if isinstance(result, tuple):
                price, prev = result
            else:
                price, prev = result, result
            prices["trusts"][ticker] = {
                "price":     round(price, 2),
                "prevClose": round(prev, 2),
                "name":      info["name"]
            }
        time.sleep(0.5)

    # 米国株
    print("\n【米国株】")
    for ticker in US_STOCKS:
        result = fetch_stock_price(ticker, prices["usdJpy"])
        if result:
            prices["stocks"][ticker] = result
        time.sleep(0.3)

    # 保存
    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完了: trusts={len(prices['trusts'])}件, stocks={len(prices['stocks'])}件 ===")
    print("prices.json を更新しました")


if __name__ == "__main__":
    main()
