#!/usr/bin/env python3
"""楽天トラベル空室検索API で、指定日・複数エリアの空室を一覧する。

標準ライブラリのみで動作する (huxe-bridge 本体の依存とは独立)。

環境変数:
    RAKUTEN_APP_ID        必須。楽天ウェブサービスのアプリID
    RAKUTEN_ACCESS_KEY    必須。同アクセスキー (accessKey ヘッダに載せる)
    RAKUTEN_AFFILIATE_ID  任意。アフィリエイトID
    CHECKIN / CHECKOUT    YYYY-MM-DD。既定は 2026-09-19 → 2026-09-20
    ADULTS / ROOMS        大人の人数 / 部屋数。既定は 3名 / 1室
    AREAS                 カンマ区切りのエリア名。省略時は AREA_PRESETS 全件

ローカル実行:
    export RAKUTEN_APP_ID=xxxx RAKUTEN_ACCESS_KEY=xxxx
    python3 tools/vacancy_search.py
    ADULTS=2 AREAS=有馬温泉,神戸三宮 python3 tools/vacancy_search.py

GitHub Actions からは .github/workflows/vacancy-check.yml で実行する。
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ENDPOINT = "https://openapi.rakuten.co.jp/engine/api/Travel/VacantHotelSearch/20170426"

# 世界測地系 (緯度, 経度, 検索半径km)。searchRadius の上限は 3.0
AREA_PRESETS = {
    "有馬温泉": (34.7985, 135.2478, 1.5),
    "神戸三宮": (34.6951, 135.1979, 1.5),
    "京都駅周辺": (34.9858, 135.7588, 2.0),
    "伊勢市駅周辺": (34.4880, 136.7094, 2.0),
    "賢島（志摩）": (34.3066, 136.8228, 3.0),
}

CHECKIN = os.environ.get("CHECKIN", "2026-09-19")
CHECKOUT = os.environ.get("CHECKOUT", "2026-09-20")
ADULTS = os.environ.get("ADULTS", "3")
ROOMS = os.environ.get("ROOMS", "1")

RATE_LIMIT_SEC = 1.2  # 楽天ウェブサービスの連続アクセス制限対策
_last_call = 0.0


def env(name, required=True):
    value = os.environ.get(name)
    if required and not value:
        sys.exit(f"エラー: 環境変数 {name} が未設定です")
    return value


APP_ID = env("RAKUTEN_APP_ID")
ACCESS_KEY = env("RAKUTEN_ACCESS_KEY")
AFFILIATE_ID = env("RAKUTEN_AFFILIATE_ID", required=False)


def selected_areas():
    """AREAS 環境変数があればその順で絞り込む。"""
    raw = os.environ.get("AREAS", "").strip()
    if not raw:
        return AREA_PRESETS
    picked = {}
    for name in (part.strip() for part in raw.split(",")):
        if not name:
            continue
        if name in AREA_PRESETS:
            picked[name] = AREA_PRESETS[name]
        else:
            print(f"警告: 未知のエリア『{name}』を無視します", file=sys.stderr)
    return picked or AREA_PRESETS


def search(lat, lng, radius, page=1):
    """1ページ分を取得する。条件に合う空室が無ければ None。"""
    global _last_call
    wait = RATE_LIMIT_SEC - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)

    params = {
        "applicationId": APP_ID,
        "affiliateId": AFFILIATE_ID,
        "format": "json",
        "formatVersion": "2",
        "checkinDate": CHECKIN,
        "checkoutDate": CHECKOUT,
        "adultNum": ADULTS,
        "roomNum": ROOMS,
        "latitude": lat,
        "longitude": lng,
        "searchRadius": radius,
        "datumType": "1",
        "searchPattern": "1",   # 宿泊プラン単位
        "responseType": "middle",
        "sort": "-roomCharge",  # 高い順
        "hits": "30",
        "page": page,
    }
    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    req = urllib.request.Request(f"{ENDPOINT}?{query}", headers={"accessKey": ACCESS_KEY})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 404:       # 条件に合う空室なし
            return None
        raise
    finally:
        _last_call = time.monotonic()


def search_all(lat, lng, radius, max_pages=3):
    """ページングを辿ってホテルを集める。"""
    first = search(lat, lng, radius)
    if not first:
        return []
    hotels = list(first.get("hotels", []))
    last_page = min(first.get("pagingInfo", {}).get("pageCount", 1), max_pages)
    for page in range(2, last_page + 1):
        more = search(lat, lng, radius, page=page)
        if more:
            hotels.extend(more.get("hotels", []))
    return hotels


def walk(obj, key):
    """レスポンスのネスト構造に依存せず、指定キーの値を順に拾う。"""
    if isinstance(obj, dict):
        if key in obj:
            yield obj[key]
        for v in obj.values():
            yield from walk(v, key)
    elif isinstance(obj, list):
        for v in obj:
            yield from walk(v, key)


def plans(hotel):
    """roomInfo のまとまりごとに (部屋情報, 料金) を対にして返す。

    roomBasicInfo と dailyCharge をそれぞれ全件集めてから zip すると、料金の
    欠けたプランが1つあるだけで以降の対応が1つずつズレ、別の部屋の料金を
    表示してしまう。必ず roomInfo 単位で組にする。
    """
    for room_info in walk(hotel, "roomInfo"):
        basic = next(walk(room_info, "roomBasicInfo"), None)
        if basic is None:
            continue
        yield basic, next(walk(room_info, "dailyCharge"), {})


def main():
    print(f"検索条件: {CHECKIN} → {CHECKOUT} / 大人{ADULTS}名 / {ROOMS}室")

    for name, (lat, lng, radius) in selected_areas().items():
        print(f"\n=== {name} ===")
        try:
            hotels = search_all(lat, lng, radius)
        except urllib.error.HTTPError as e:
            print(f"  照会失敗: HTTP {e.code} {e.reason}")
            continue
        except urllib.error.URLError as e:
            print(f"  照会失敗: {e.reason}")
            continue

        if not hotels:
            print("  空室なし")
            continue

        for hotel in hotels:
            basic = next(walk(hotel, "hotelBasicInfo"), {})
            print(f"\n  {basic.get('hotelName')}  ★{basic.get('reviewAverage') or '-'}"
                  f"  TEL {basic.get('telephoneNo') or '-'}")
            for room, charge in plans(hotel):
                meal = ("夕" if room.get("withDinnerFlag") else "") + \
                       ("朝" if room.get("withBreakfastFlag") else "")
                total = charge.get("total")
                price = f"合計{total:,}円" if isinstance(total, int) else "料金未掲載"
                plan = (room.get("planName") or room.get("roomName") or "(プラン名なし)")[:40]
                print(f"    - {room.get('roomName') or '-'} / {plan} / {price} / 食事:{meal or 'なし'}")
                if room.get("reserveUrl"):
                    print(f"      {room['reserveUrl']}")


if __name__ == "__main__":
    main()
