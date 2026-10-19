#!/usr/bin/env python3
"""楽天トラベル空室検索API で、指定日・複数エリアの空室を一覧する。

標準ライブラリのみで動作する (huxe-bridge 本体の依存とは独立)。

検索条件は tools/vacancy_query.json で指定する。同じディレクトリのこのファイルを
書き換えて push すると Actions が走り、結果が実行サマリに出る。

環境変数 (query ファイルより優先):
    RAKUTEN_APP_ID        必須。楽天ウェブサービスのアプリID
    RAKUTEN_ACCESS_KEY    必須。同アクセスキー (accessKey ヘッダに載せる)
    RAKUTEN_AFFILIATE_ID  任意。アフィリエイトID
    CHECKIN / CHECKOUT    YYYY-MM-DD
    ADULTS / ROOMS        大人の人数 / 部屋数
    AREAS                 カンマ区切りのエリア名
    DETAIL                1 なら宿ごとに全プランを出す (既定は食事条件別の最安)
    SORT                  value=安い順 / luxury=高い順
    HOTEL_NO              宿番号(カンマ区切り)。指定すると監視モードになる
    REQUIRE_MEAL          監視モードで要求する食事条件 (夕朝 / 夕 / 朝 / なし)
    MAX_HOTELS            エリアごとの表示上限
    RAKUTEN_REFERER       アプリ登録時の Application URL。未指定だと 403

ローカル実行:
    export RAKUTEN_APP_ID=xxxx RAKUTEN_ACCESS_KEY=xxxx
    python3 tools/vacancy_search.py
    ADULTS=2 AREAS=有馬温泉,神戸三宮 python3 tools/vacancy_search.py

GitHub Actions からは .github/workflows/vacancy-check.yml で実行する。
"""
import http.client
import json
import os
import pathlib
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

QUERY_FILE = pathlib.Path(__file__).with_name("vacancy_query.json")


def load_query():
    """検索条件ファイルを読む。無くても環境変数だけで動く。"""
    try:
        with open(QUERY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        print(f"警告: {QUERY_FILE.name} を読めません ({exc})", file=sys.stderr)
        return {}


QUERY = load_query()


def setting(env_name, key, default):
    """環境変数 > query ファイル > 既定値 の優先順で解決する。"""
    value = os.environ.get(env_name)
    if value:
        return str(value)
    value = QUERY.get(key)
    if value not in (None, ""):
        return str(value)
    return default


# openapi ゲートウェイはアプリ登録時の Application URL を Referer / Origin で
# 照合する。ブラウザ経由ではないので自分で付けないと 403 になる。
REFERER = setting("RAKUTEN_REFERER", "referer", "")

CHECKIN = setting("CHECKIN", "checkin", "2026-09-19")
CHECKOUT = setting("CHECKOUT", "checkout", "2026-09-20")
ADULTS = setting("ADULTS", "adults", "3")
ROOMS = setting("ROOMS", "rooms", "1")
SORT = setting("SORT", "sort", "luxury")            # value=安い順 / luxury=高い順
MAX_HOTELS = int(setting("MAX_HOTELS", "max_hotels", "12"))
HOTEL_NO = setting("HOTEL_NO", "hotel_no", "")        # 指定すると宿を名指しで監視する
REQUIRE_MEAL = setting("REQUIRE_MEAL", "require_meal", "")  # 夕朝 / 夕 / 朝 / なし

RATE_LIMIT_SEC = 1.2  # 楽天ウェブサービスの連続アクセス制限対策
_last_call = 0.0


class ApiError(Exception):
    """楽天APIが 404 以外のエラーを返した。原因究明のため本文を保持する。"""


def redact(text):
    """ログに出す前に認証情報を伏せる (ローカル実行時の保険)。"""
    for secret in (APP_ID, ACCESS_KEY, AFFILIATE_ID):
        if secret:
            text = text.replace(secret, "***")
    return text


def env(name, required=True):
    value = os.environ.get(name)
    if required and not value:
        sys.exit(f"エラー: 環境変数 {name} が未設定です")
    return value


APP_ID = env("RAKUTEN_APP_ID")
ACCESS_KEY = env("RAKUTEN_ACCESS_KEY")
AFFILIATE_ID = env("RAKUTEN_AFFILIATE_ID", required=False)


def available_areas():
    """プリセットに query ファイルの custom_areas を重ねたもの。"""
    areas = dict(AREA_PRESETS)
    for name, coords in (QUERY.get("custom_areas") or {}).items():
        try:
            lat, lng, radius = coords
            areas[name] = (float(lat), float(lng), float(radius))
        except (TypeError, ValueError):
            print(f"警告: custom_areas『{name}』は [緯度, 経度, 半径km] で指定してください",
                  file=sys.stderr)
    return areas


def selected_areas():
    """AREAS 環境変数 > query ファイルの areas > 全エリア の順で絞り込む。"""
    areas = available_areas()
    raw = os.environ.get("AREAS", "").strip()
    names = [n.strip() for n in raw.split(",")] if raw else (QUERY.get("areas") or [])

    picked = {}
    for name in names:
        if not name:
            continue
        if name in areas:
            picked[name] = areas[name]
        else:
            print(f"警告: 未知のエリア『{name}』を無視します", file=sys.stderr)
    return picked or areas


def http_get(url, headers):
    """ヘッダ名の大文字小文字を保ったまま GET する。

    urllib は do_open でヘッダ名を .title() するため accessKey が
    Accesskey に変わる。楽天のゲートウェイはこれを認識しない。
    """
    parts = urllib.parse.urlsplit(url)
    conn = http.client.HTTPSConnection(parts.netloc, timeout=15)
    try:
        path = parts.path + (f"?{parts.query}" if parts.query else "")
        conn.putrequest("GET", path, skip_accept_encoding=True)
        for name, value in headers.items():
            conn.putheader(name, value)
        conn.endheaders()
        resp = conn.getresponse()
        return resp.status, resp.reason, resp.read().decode("utf-8", "replace")
    finally:
        conn.close()


def search(lat=None, lng=None, radius=None, page=1, hotel_no=None):
    """1ページ分を取得する。条件に合う空室が無ければ None。

    hotel_no を渡すと緯度経度ではなく宿を名指しで照会する。
    """
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
        "searchPattern": "1",   # 宿泊プラン単位
        "responseType": "middle",
        "sort": "-roomCharge",  # 高い順
        "hits": "30",
        "page": page,
    }
    if hotel_no:
        params["hotelNo"] = hotel_no
    else:
        params.update({"latitude": lat, "longitude": lng,
                       "searchRadius": radius, "datumType": "1"})

    query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    headers = {"accessKey": ACCESS_KEY}
    if REFERER:
        # Referer 単独では 403 REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING になる。
        # Origin との併送で初めてリクエストコンテキストが成立する (実測)。
        origin = urllib.parse.urlsplit(REFERER)
        headers["Referer"] = REFERER
        headers["Origin"] = f"{origin.scheme}://{origin.netloc}"

    try:
        status, reason, body = http_get(f"{ENDPOINT}?{query}", headers)
    except OSError as e:
        raise ApiError(f"接続失敗: {e}") from None
    finally:
        _last_call = time.monotonic()

    if status == 404:           # 条件に合う空室なし
        return None
    if status != 200:
        raise ApiError(f"HTTP {status} {reason}: {redact(body.strip())[:400] or '(本文なし)'}")
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise ApiError(f"JSON として読めない応答: {e}") from None


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


def group_by_hotel(hotels):
    """searchPattern=1 はプラン単位で同じ宿が何度も返るので宿ごとに束ねる。"""
    grouped = {}
    for hotel in hotels:
        basic = next(walk(hotel, "hotelBasicInfo"), {})
        key = basic.get("hotelNo") or basic.get("hotelName")
        entry = grouped.setdefault(key, {"basic": basic, "plans": []})
        for room, charge in plans(hotel):
            total = charge.get("total")
            if isinstance(total, int):
                entry["plans"].append((total, room))
    for entry in grouped.values():
        entry["plans"].sort(key=lambda p: p[0])
    return grouped


MEAL_ORDER = ("夕朝", "夕", "朝", "なし")


def meal_label(room):
    return (("夕" if room.get("withDinnerFlag") else "")
            + ("朝" if room.get("withBreakfastFlag") else "")) or "なし"


def cheapest_by_meal(found):
    """食事条件ごとの最安プランを返す。found は価格昇順であること。"""
    best = {}
    for total, room in found:
        best.setdefault(meal_label(room), (total, room))
    return [(label, best[label]) for label in MEAL_ORDER if label in best]


def describe(total, room):
    plan = (room.get("planName") or "(プラン名なし)")[:38]
    return f"{total:,}円 / {room.get('roomName') or '-'} / {plan}"


def watch():
    """宿を名指しで見張る。条件に合うプランが1件でもあれば True。"""
    print(f"監視: {CHECKIN} → {CHECKOUT} / 大人{ADULTS}名 / {ROOMS}室"
          f" / 条件: 食事{REQUIRE_MEAL or '指定なし'}")
    hit = False

    for number in (n.strip() for n in HOTEL_NO.split(",") if n.strip()):
        try:
            data = search(hotel_no=number)
        except ApiError as e:
            print(f"  [{number}] 照会失敗: {e}")
            continue
        if not data:
            print(f"  [{number}] 空室なし")
            continue

        for entry in group_by_hotel(data.get("hotels", [])).values():
            basic, found = entry["basic"], entry["plans"]
            name = basic.get("hotelName", number)
            matched = [(t, r) for t, r in found
                       if not REQUIRE_MEAL or meal_label(r) == REQUIRE_MEAL]
            if not matched:
                print(f"  [{number}] {name}: 条件に合うプランなし (空きプラン{len(found)}件)")
                continue
            hit = True
            print(f"  ★ {name} — 条件に合うプラン{len(matched)}件")
            for total, room in matched[:5]:
                print(f"      [{meal_label(room)}] {describe(total, room)}")
            if basic.get("planListUrl"):
                print(f"      {basic['planListUrl']}")
    return hit


def main():
    if HOTEL_NO:
        # 空きが出たら終了コード 10。ワークフロー側がこれを見て通知する
        raise SystemExit(10 if watch() else 0)

    detail = os.environ.get("DETAIL") == "1"
    print(f"検索条件: {CHECKIN} → {CHECKOUT} / 大人{ADULTS}名 / {ROOMS}室"
          f"{' / 全プラン表示' if detail else ''}")

    for name, (lat, lng, radius) in selected_areas().items():
        print(f"\n=== {name} ===")
        try:
            hotels = search_all(lat, lng, radius)
        except ApiError as e:
            print(f"  照会失敗: {e}")
            continue

        grouped = group_by_hotel(hotels)
        if not grouped:
            print("  空室なし")
            continue

        if SORT == "value":      # 安い順 (コスパ比較向け)
            ranked = sorted(grouped.values(),
                            key=lambda e: e["plans"][0][0] if e["plans"] else 10 ** 9)
        else:                    # 高い順 (予算制限なし向け)
            ranked = sorted(grouped.values(),
                            key=lambda e: e["plans"][-1][0] if e["plans"] else 0,
                            reverse=True)
        shown = ranked[:MAX_HOTELS]
        more = len(ranked) - len(shown)
        print(f"  空室のある宿: {len(ranked)}軒"
              + (f" (上位{len(shown)}軒を表示、他{more}軒)" if more > 0 else ""))

        for entry in shown:
            basic, found = entry["basic"], entry["plans"]
            print(f"\n  {basic.get('hotelName')}  ★{basic.get('reviewAverage') or '-'}"
                  f"  TEL {basic.get('telephoneNo') or '-'}")
            if not found:
                print("    料金の出ているプランなし")
                continue
            low, high = found[0][0], found[-1][0]
            span = f"{low:,}円" if low == high else f"{low:,}〜{high:,}円"
            print(f"    プラン{len(found)}件 / {span} ({ADULTS}名合計)")
            if detail:
                for total, room in found:
                    print(f"    [{meal_label(room)}] {describe(total, room)}")
            else:
                # 食事条件を揃えないと宿ごとの比較にならないので条件別の最安を出す
                for label, (total, room) in cheapest_by_meal(found):
                    print(f"    [{label}] {describe(total, room)}")
            if basic.get("planListUrl"):
                print(f"    {basic['planListUrl']}")


if __name__ == "__main__":
    main()
