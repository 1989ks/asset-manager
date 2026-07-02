#!/usr/bin/env python3
"""
毎日の価格取得スクリプト
GitHub Actionsから実行され、prices.jsonを更新する

投資信託: 投資信託協会の公式API（ISINコード）
米国株:   Yahoo Finance v8/chart API
"""

import json
import time
import datetime
import urllib.request
import urllib.error
import re

# ===== 投資信託 ISINコード対応表 =====
TRUST_FUNDS = [
    {"ticker": "0331418A.T", "isin": "JP90C000GJB9", "name": "eMAXIS Slim 全世界株式(オルカン)"},
    {"ticker": "03311187.T", "isin": "JP90C000HJF5", "name": "eMAXIS Slim 米国株式(S&P500)"},
    {"ticker": "04311137.T", "isin": "JP90C000GHV0", "name": "iFreeNEXT FANG+インデックス"},
    {"ticker": "9I312179.T", "isin": "JP90C000P8S3", "name": "楽天・SCHD"},
    {"ticker": "2931113C.T", "isin": "JP90C000NJF9", "name": "ニッセイNASDAQ100インデックスファンド"},
    {"ticker": "0331119A.T", "isin": "JP90C000GGH2", "name": "eMAXIS Slim 新興国株式インデックス"},
    {"ticker": "0331117A.T", "isin": "JP90C000GGG4", "name": "eMAXIS Slim 全世界株式(除く日本)"},
    {"ticker": "9I31116A.T", "isin": "JP90C000FGP5", "name": "楽天・全米株式インデックス・ファンド(楽天VTI)"},
]

US_STOCKS = [
    "CRWD", "AAPL", "PAPY", "TSLA", "XOM", "MMM", "MO", "MSFT",
    "SQ", "JPM", "DHR", "OKTA", "COST", "WMT", "NVDA", "UNH",
    "CVX", "TGT", "DIS", "PEP", "KO",
    "BFLY", "QS", "JOBY", "SBSW", "ALT", "RXRX", "MP", "CHPT",
]


def fetch_url(url, timeout=15):
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json, text/html, */*',
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            # UTF-8で試み、失敗したらShift-JIS
            for enc in ['utf-8', 'shift-jis', 'euc-jp']:
                try:
                    return raw.decode(enc)
                except Exception:
                    continue
            return raw.decode('utf-8', errors='replace')
    except urllib.error.HTTPError as e:
        print(f"    HTTPエラー {e.code}: {url[:80]}")
        return None
    except urllib.error.URLError as e:
        print(f"    URLエラー: {e.reason}")
        return None
    except Exception as e:
        print(f"    エラー: {type(e).__name__}: {e}")
        return None


def fetch_usd_jpy():
    for url in [
        "https://api.frankfurter.app/latest?from=USD&to=JPY",
        "https://open.er-api.com/v6/latest/USD",
    ]:
        text = fetch_url(url)
        if text:
            try:
                d = json.loads(text)
                rate = d.get("rates", {}).get("JPY")
                if rate:
                    print(f"  USD/JPY = {rate}")
                    return float(rate)
            except Exception:
                pass
    print("  USD/JPY取得失敗、155を使用")
    return 155.0


def fetch_trust_by_isin(isin, name):
    """
    投資信託協会の公式APIで基準価額を取得
    URL: https://toushin-lib.fwg.ne.jp/FdsWeb/FDST030000?isinCd=ISIN
    レスポンス例: [{"basicPrice":"37637","previousPrice":"37638",...}]
    """
    url = f"https://toushin-lib.fwg.ne.jp/FdsWeb/FDST030000?isinCd={isin}"
    print(f"    投信協会API: {url}")
    text = fetch_url(url)
    if not text:
        return None, None

    print(f"    レスポンス(先頭200): {text[:200]}")

    try:
        d = json.loads(text)
        # リスト形式
        if isinstance(d, list) and len(d) > 0:
            item = d[0]
            # basicPrice, standardPrice, price など複数のキーを試みる
            for key in ["basicPrice", "standardPrice", "price", "nav"]:
                val = item.get(key)
                if val is not None:
                    try:
                        price = float(str(val).replace(",", ""))
                        if price > 0:
                            # 前日価格
                            prev = None
                            for pkey in ["previousPrice", "prevPrice", "previousNav"]:
                                pval = item.get(pkey)
                                if pval is not None:
                                    try:
                                        prev = float(str(pval).replace(",", ""))
                                        break
                                    except Exception:
                                        pass
                            print(f"    OK 投信協会 key={key}: {price}円/万口")
                            return price, prev or price
                    except Exception:
                        pass
        # 辞書形式
        elif isinstance(d, dict):
            for key in ["basicPrice", "standardPrice", "price", "nav"]:
                val = d.get(key)
                if val is not None:
                    try:
                        price = float(str(val).replace(",", ""))
                        if price > 0:
                            print(f"    OK 投信協会 key={key}: {price}円/万口")
                            return price, price
                    except Exception:
                        pass

        print(f"    投信協会: 価格キーが見つからない。キー一覧: {list(d[0].keys()) if isinstance(d, list) and d else list(d.keys()) if isinstance(d, dict) else 'unknown'}")
    except json.JSONDecodeError:
        # JSON以外（HTMLなど）の場合、数値をスクレイピング
        print(f"    JSONでない、テキストから数値抽出を試みる")
        # 基準価額: 数字パターンを探す（例：37,637）
        matches = re.findall(r'基準価額[^\d]*?([\d,]+)', text)
        if matches:
            try:
                price = float(matches[0].replace(",", ""))
                if price > 0:
                    print(f"    OK スクレイピング: {price}円/万口")
                    return price, price
            except Exception:
                pass
        print(f"    スクレイピング失敗")
    except Exception as e:
        print(f"    パースエラー: {e}")

    return None, None


def fetch_trust_by_morningstar(isin, name):
    """
    Morningstar経由で基準価額取得（バックアップ）
    """
    url = f"https://www.morningstar.co.jp/FundData/SnapShot.do?isinCode={isin}"
    print(f"    Morningstar: {url}")
    text = fetch_url(url)
    if not text:
        return None, None

    # HTMLから基準価額を抽出
    patterns = [
        r'基準価額[^\d]*([\d,]+)円',
        r'"nav"\s*:\s*([\d.]+)',
        r'<td[^>]*>([\d,]+)</td>.*?基準価額',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text)
        if matches:
            try:
                price = float(matches[0].replace(",", ""))
                if 100 < price < 1000000:
                    print(f"    OK Morningstar: {price}円/万口")
                    return price, price
            except Exception:
                pass
    print(f"    Morningstar: 価格抽出失敗")
    return None, None


def fetch_trust_price(fund):
    ticker = fund["ticker"]
    isin   = fund["isin"]
    name   = fund["name"]
    print(f"  [{ticker}] {name[:30]}")

    # ① 投資信託協会 公式API
    price, prev = fetch_trust_by_isin(isin, name)
    if price:
        return price, prev

    time.sleep(0.5)

    # ② Morningstar
    price, prev = fetch_trust_by_morningstar(isin, name)
    if price:
        return price, prev

    print(f"    NG 全API失敗")
    return None, None


def fetch_stock_price(ticker, usd_jpy):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=2d"
    text = fetch_url(url)
    if text:
        try:
            d = json.loads(text)
            result = d.get("chart", {}).get("result")
            if result:
                meta = result[0].get("meta", {})
                price = meta.get("regularMarketPrice")
                prev  = meta.get("chartPreviousClose") or price
                currency = meta.get("currency", "USD")
                if price and price > 0:
                    price = float(price)
                    prev  = float(prev)
                    if currency == "USD":
                        price *= usd_jpy
                        prev  *= usd_jpy
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
        "usdJpy":    155.0,
        "trusts":    {},
        "stocks":    {},
    }

    print("【USD/JPY】")
    prices["usdJpy"] = fetch_usd_jpy()
    time.sleep(1)

    print("\n【投資信託 基準価額】")
    for fund in TRUST_FUNDS:
        price, prev = fetch_trust_price(fund)
        if price:
            prices["trusts"][fund["ticker"]] = {
                "price":     round(price, 2),
                "prevClose": round(prev, 2),
                "name":      fund["name"],
            }
        time.sleep(1)

    print(f"\n投信取得結果: {len(prices['trusts'])}/{len(TRUST_FUNDS)}件成功")

    print("\n【米国株】")
    for ticker in US_STOCKS:
        result = fetch_stock_price(ticker, prices["usdJpy"])
        if result:
            prices["stocks"][ticker] = result
        time.sleep(0.3)

    with open("prices.json", "w", encoding="utf-8") as f:
        json.dump(prices, f, ensure_ascii=False, indent=2)

    print(f"\n=== 完了: trusts={len(prices['trusts'])}件, stocks={len(prices['stocks'])}件 ===")
    print("prices.json を更新しました")


if __name__ == "__main__":
    main()
