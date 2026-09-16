#!/usr/bin/env python3
"""楽天APIの 403 の原因を切り分けるための一時的な診断スクリプト。

認証方式 (エンドポイント / accessKey の渡し方 / Referer の値) の組み合わせを
順に試し、どれが 200 を返すかを見る。原因が判明したら削除する。
"""
import http.client
import os
import sys
import time
import urllib.parse

APP_ID = os.environ.get("RAKUTEN_APP_ID", "")
ACCESS_KEY = os.environ.get("RAKUTEN_ACCESS_KEY", "")
APP_URL = "https://github.com/HirotakaKaminishi/vacancy-check"

OPENAPI = "https://openapi.rakuten.co.jp/engine/api/Travel/VacantHotelSearch/20170426"
CLASSIC = "https://app.rakuten.co.jp/services/api/Travel/VacantHotelSearch/20170426"

BASE = {
    "applicationId": APP_ID,
    "format": "json",
    "formatVersion": "2",
    "checkinDate": "2026-09-19",
    "checkoutDate": "2026-09-20",
    "adultNum": "2",
    "latitude": "34.7985",
    "longitude": "135.2478",
    "searchRadius": "1.5",
    "datumType": "1",
    "hits": "1",
}

# (説明, エンドポイント, 追加クエリ, ヘッダ)
CASES = [
    ("openapi + hdr accessKey + Referer(登録URL)",
     OPENAPI, {}, {"accessKey": ACCESS_KEY, "Referer": APP_URL}),
    ("openapi + hdr accessKey + Referer(末尾スラッシュ)",
     OPENAPI, {}, {"accessKey": ACCESS_KEY, "Referer": APP_URL + "/"}),
    ("openapi + hdr accessKey + Referer(ドメインのみ)",
     OPENAPI, {}, {"accessKey": ACCESS_KEY, "Referer": "https://github.com/"}),
    ("openapi + hdr accessKey + Referer + Origin",
     OPENAPI, {}, {"accessKey": ACCESS_KEY, "Referer": APP_URL, "Origin": "https://github.com"}),
    ("openapi + query accessKey + Referer",
     OPENAPI, {"accessKey": ACCESS_KEY}, {"Referer": APP_URL}),
    ("openapi + applicationId のみ (accessKey なし)",
     OPENAPI, {}, {"Referer": APP_URL}),
    ("classic app.rakuten.co.jp + applicationId のみ",
     CLASSIC, {}, {}),
    ("classic + Referer",
     CLASSIC, {}, {"Referer": APP_URL}),
    ("classic + hdr accessKey + Referer",
     CLASSIC, {}, {"accessKey": ACCESS_KEY, "Referer": APP_URL}),
]


def redact(text):
    for secret in (APP_ID, ACCESS_KEY):
        if secret:
            text = text.replace(secret, "***")
    return text


def http_get(url, headers):
    parts = urllib.parse.urlsplit(url)
    conn = http.client.HTTPSConnection(parts.netloc, timeout=15)
    try:
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        conn.putrequest("GET", path, skip_accept_encoding=True)
        for name, value in headers.items():
            conn.putheader(name, value)
        conn.endheaders()
        resp = conn.getresponse()
        return resp.status, resp.read().decode("utf-8", "replace")
    finally:
        conn.close()


def main():
    if not APP_ID:
        sys.exit("RAKUTEN_APP_ID が未設定")
    print(f"APP_ID 形式: {len(APP_ID)}文字 / ハイフン{'あり' if '-' in APP_ID else 'なし'}")
    print(f"ACCESS_KEY 形式: {len(ACCESS_KEY)}文字 / 接頭辞 {ACCESS_KEY[:3]!r}\n")

    for label, endpoint, extra, headers in CASES:
        params = dict(BASE)
        params.update(extra)
        query = urllib.parse.urlencode(params)
        try:
            status, body = http_get(f"{endpoint}?{query}", headers)
        except OSError as e:
            print(f"[接続失敗] {label}: {e}")
            time.sleep(1.2)
            continue
        summary = " ".join(redact(body).split())[:180]
        mark = "★200" if status == 200 else ("404(空室なし=認証OK)" if status == 404 else status)
        print(f"[{mark}] {label}\n        {summary}")
        time.sleep(1.2)


if __name__ == "__main__":
    main()
