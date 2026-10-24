"""
LINE 毎朝のお知らせ（課題8：連携した API に機能を追加）

Open-Meteo から今日の天気予報を取り、schedule.txt から今日の曜日の予定を読んで、
LINE Messaging API のプッシュメッセージで、自分の LINE に1通にまとめて送る。
GitHub Actions（GitHub のコンピューターで動かす仕組み）で、毎朝 7:00 に自動で動かす（GitHub が混んでいると遅れることがある）。
（Mac の電源が切れていても届く。Mac の launchd で動かすこともできる）

使い方：
  python main.py            天気と予定を LINE に送る
  python main.py --dry-run  送らずに、送る中身だけ表示する（お試し。送信数を使わない）
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from dotenv import load_dotenv

# ============================================================
# 設定（ここをまとめて書いておく）
# ============================================================

# このプログラム（main.py）が置いてあるフォルダ
BASE_DIR = Path(__file__).resolve().parent

# トークンとユーザー ID を書いておくファイルと、その中の項目名
ENV_FILE = BASE_DIR / ".env"
ENV_EXAMPLE_FILE = BASE_DIR / ".env.example"
TOKEN_NAME = "LINE_CHANNEL_ACCESS_TOKEN"
USER_ID_NAME = "LINE_USER_ID"

# ユーザー ID の形（U のあとに 0〜9・a〜f が 32 文字）
USER_ID_PATTERN = r"U[0-9a-f]{32}"

# 曜日ごとの予定を書いておくファイル（見本は schedule.example.txt）
SCHEDULE_FILE = BASE_DIR / "schedule.txt"
SCHEDULE_EXAMPLE_FILE = BASE_DIR / "schedule.example.txt"

# 予定を、ファイルの代わりに入れておける環境変数の名前
# （GitHub Actions では schedule.txt を載せないので、Secrets に入れた予定をここから読む）
SCHEDULE_ENV_NAME = "SCHEDULE_TEXT"

# 天気を知りたい場所（川崎市幸区北加瀬。Open-Meteo の地名検索で調べた緯度・経度）
PLACE_NAME = "川崎市幸区北加瀬"
LATITUDE = 35.5510
LONGITUDE = 139.6622
TIMEZONE = "Asia/Tokyo"  # 「今日」の日付と、ログの時刻もこの時間帯で数える

# 天気予報の API（Open-Meteo。登録・API キー不要）
WEATHER_API_URL = "https://api.open-meteo.com/v1/forecast"

# プッシュメッセージ（ユーザー ID を指定して送る）の API の URL
PUSH_URL = "https://api.line.me/v2/bot/message/push"

# 無料プラン（コミュニケーションプラン）で1か月に送れる数（エラーの案内に使う）
FREE_PLAN_MONTHLY_LIMIT = 200

# 降水確率がこの値（%）以上なら、傘の一言を足す
UMBRELLA_THRESHOLD = 50

# 相手の返事を待つ秒数（これを過ぎたら「応答が無い」として終わる）
TIMEOUT_SECONDS = 10

# お試し表示にするときの指定
DRY_RUN_OPTION = "--dry-run"

# 曜日の表示（月曜日が 0）
WEEKDAYS = "月火水木金土日"

# 予定のファイルで、曜日を並べるときに間に入れてもよい文字（「月・木」「月、木」など）
WEEKDAY_SEPARATORS = "・、,， 　"

# 天気コード（WMO コード）→（日本語, 絵文字）
WEATHER_CODES = {
    0: ("快晴", "☀️"),
    1: ("晴れ", "🌤️"),
    2: ("晴れ時々くもり", "⛅"),
    3: ("くもり", "☁️"),
    45: ("霧", "🌫️"),
    48: ("霧（霧氷）", "🌫️"),
    51: ("弱い霧雨", "🌦️"),
    53: ("霧雨", "🌦️"),
    55: ("強い霧雨", "🌦️"),
    56: ("凍る霧雨", "🌧️"),
    57: ("強い凍る霧雨", "🌧️"),
    61: ("弱い雨", "🌧️"),
    63: ("雨", "🌧️"),
    65: ("強い雨", "🌧️"),
    66: ("凍る雨", "🌧️"),
    67: ("強い凍る雨", "🌧️"),
    71: ("弱い雪", "🌨️"),
    73: ("雪", "🌨️"),
    75: ("強い雪", "🌨️"),
    77: ("霧雪", "🌨️"),
    80: ("弱いにわか雨", "🌦️"),
    81: ("にわか雨", "🌦️"),
    82: ("激しいにわか雨", "🌧️"),
    85: ("にわか雪", "🌨️"),
    86: ("強いにわか雪", "🌨️"),
    95: ("雷雨", "⛈️"),
    96: ("ひょうを伴う雷雨", "⛈️"),
    99: ("強いひょうを伴う雷雨", "⛈️"),
}


# ============================================================
# F1 設定の読み込み
# ============================================================
def load_settings():
    """
    .env からチャネルアクセストークンとユーザー ID を読み込み、(トークン, ユーザー ID) を返す。
    .env が無い・項目が空・ユーザー ID の形が違う場合は、理由を表示して終了する（F8）。
    """
    # .env の中身を「環境変数」（プログラムが読める設定値）として読み込む
    load_dotenv(ENV_FILE)
    token = os.getenv(TOKEN_NAME, "").strip()
    user_id = os.getenv(USER_ID_NAME, "").strip()

    # 空の項目を集めて、まとめて知らせる
    missing = [name for name, value in ((TOKEN_NAME, token), (USER_ID_NAME, user_id)) if not value]
    if missing:
        show_error_and_exit(
            f"{'、'.join(missing)} が設定されていません。\n"
            f"{ENV_EXAMPLE_FILE.name} をコピーして「{ENV_FILE.name}」という名前にし、\n"
            f"チャネルアクセストークンとユーザー ID を書いてください。\n"
            f"置き場所: {BASE_DIR}"
        )
    if not re.fullmatch(USER_ID_PATTERN, user_id):
        show_error_and_exit(
            f"{USER_ID_NAME} の形が正しくありません（U で始まる 33 文字のはずです）。\n"
            "LINE Developers コンソールでチャネルを開き、「チャネル基本設定」タブの一番下にある\n"
            "「あなたのユーザー ID」をコピーしてください（LINE アプリの「LINE ID」とは別物です）。"
        )
    return token, user_id


# ============================================================
# F2 天気の取得
# ============================================================
def fetch_weather():
    """
    Open-Meteo から今日の天気を取り、次の形の辞書で返す。
    {"code": 天気コード, "max": 最高気温, "min": 最低気温, "rain": 降水確率}
    取れなかった場合は、例外（requests.RequestException / ValueError など）が起きる。
    """
    response = requests.get(
        WEATHER_API_URL,
        params={
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            # 1日分の「天気コード・最高気温・最低気温・降水確率」を頼む
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "timezone": TIMEZONE,
            "forecast_days": 1,
        },
        timeout=TIMEOUT_SECONDS,
    )
    # 200 番台以外（400 や 500 など）なら例外にする
    response.raise_for_status()

    # 返事は「項目ごとに日付の数だけ並んだリスト」なので、1日目（[0]）を取り出す
    daily = response.json()["daily"]
    return {
        "code": daily["weather_code"][0],
        "max": daily["temperature_2m_max"][0],
        "min": daily["temperature_2m_min"][0],
        "rain": daily["precipitation_probability_max"][0],
    }


def try_fetch_weather():
    """
    天気を取り、(天気の辞書, None) を返す。
    取れなかったときは、予定だけでも送れるように終了はせず、(None, 理由) を返す。
    """
    try:
        return fetch_weather(), None
    except requests.HTTPError as error:
        # つながったが、エラー（404 や 500 など）が返ってきた
        reason = f"天気予報のサーバーがエラーを返しました（HTTP {error.response.status_code}）"
    except requests.RequestException as error:
        # 詳細は種類の名前だけにする（中身には長い URL が入っていて読みにくいため）
        reason = f"天気予報のサーバーにつながりませんでした（{type(error).__name__}）"
    except (ValueError, KeyError, IndexError, TypeError) as error:
        reason = f"天気予報の返事の形が想定と違いました（{error!r}）"
    show_warning(reason)
    return None, reason


# ============================================================
# F3 予定の読み込み
# ============================================================
def load_today_schedule(today):
    """
    schedule.txt から、today（今日の日付）の曜日の予定を、書いてある順のリストで返す。
    環境変数 SCHEDULE_TEXT に予定が入っていれば、ファイルの代わりにそちらを読む（GitHub Actions 用）。

    - 1行に1つ「曜日: 予定」（例：「月木: 燃えるゴミ」）。「:」は全角の「：」でもよい
    - # で始まる行と空の行は飛ばす
    - 書き方が違う行は、警告を出して飛ばす（1行の間違いで毎朝の通知が止まらないように）
    - ファイルが無い・読めないときは、警告を出して空のリストを返す（天気だけ送る）
    """
    schedule_text = os.getenv(SCHEDULE_ENV_NAME, "")
    if schedule_text.strip():
        return pick_today_items(schedule_text.splitlines(), SCHEDULE_ENV_NAME, today)

    if not SCHEDULE_FILE.exists():
        show_warning(
            f"{SCHEDULE_FILE.name} が無いので、予定なしで送ります。\n"
            f"予定を入れるには、{SCHEDULE_EXAMPLE_FILE.name} をコピーして「{SCHEDULE_FILE.name}」という名前にし、\n"
            f"自分の予定を書いてください。置き場所: {BASE_DIR}"
        )
        return []
    try:
        lines = SCHEDULE_FILE.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        show_warning(f"{SCHEDULE_FILE.name} を読めなかったので、予定なしで送ります（{type(error).__name__}）")
        return []
    return pick_today_items(lines, SCHEDULE_FILE.name, today)


def pick_today_items(lines, source_name, today):
    """
    予定の行の一覧から、today の曜日の予定だけを取り出して返す。
    source_name は警告に出す名前（schedule.txt または SCHEDULE_TEXT）。
    """
    today_weekday = WEEKDAYS[today.weekday()]
    items = []
    for number, line in enumerate(lines, start=1):
        line = line.strip()
        if line == "" or line.startswith("#"):
            continue
        parsed = parse_schedule_line(line)
        if isinstance(parsed, str):
            # 書き方が違う行（parsed に理由が入っている）
            show_warning(f"{source_name} の {number} 行目を飛ばしました（{parsed}）: {line}")
            continue
        weekdays, item = parsed
        if today_weekday in weekdays:
            items.append(item)
    return items


def parse_schedule_line(line):
    """
    予定の1行「曜日: 予定」を読み、(曜日の文字の集まり, 予定) を返す。
    書き方が違うときは、理由の文字列を返す。
    """
    # 全角の「：」も半角の「:」と同じに扱い、最初の「:」の場所で2つに分ける
    # （予定の中の「：」（例：「19：00」）は、元のまま残す）
    position = line.replace("：", ":").find(":")
    if position == -1:
        return "「曜日: 予定」の「:」がありません"
    day_part = line[:position]
    item = line[position + 1:].strip()

    # 曜日の間に入れてもよい文字（「・」など）を取り除く
    days = "".join(char for char in day_part if char not in WEEKDAY_SEPARATORS)
    if days == "":
        return "曜日が書かれていません"
    wrong = [char for char in days if char not in WEEKDAYS]
    if wrong:
        return f"曜日は「{WEEKDAYS}」の1文字で書いてください（「{''.join(wrong)}」は使えません）"
    if item == "":
        return "予定が書かれていません"
    return set(days), item


# ============================================================
# F4 メッセージを作る
# ============================================================
def describe_weather(code):
    """
    天気コードを（日本語, 絵文字）に直して返す。知らないコードなら「不明」と返す。
    """
    return WEATHER_CODES.get(code, (f"不明（コード {code}）", "❔"))


def format_value(value, unit):
    """
    数値に単位を付けた文字列にする。値が無い（None）ときは「—」にする。
    """
    return "—" if value is None else f"{value}{unit}"


def build_message(today, weather, weather_error, items):
    """
    天気（取れなかったときはその理由）と今日の予定から、LINE に送る1通のテキストを作って返す。
    today は今は使っていない（日付を入れたくなったときのために受け取っておく）。
    """
    # あいさつ・日付・場所は付けず、天気と予定だけのシンプルな形にする（本人の希望）
    lines = []

    if weather is None:
        lines.append(f"⚠️ 天気を取得できませんでした（{weather_error}）")
    else:
        name, emoji = describe_weather(weather["code"])
        rain = weather["rain"]
        lines += [
            f"{emoji} {name}",
            f"最高 {format_value(weather['max'], '℃')} ／ 最低 {format_value(weather['min'], '℃')}",
            f"降水確率 {format_value(rain, '%')}",
        ]
        # 降水確率が高い日だけ、傘の一言を足す（降水確率が取れない日は None になる）
        if rain is not None and rain >= UMBRELLA_THRESHOLD:
            lines.append("☂️ 傘を持っていきましょう")

    lines += ["", "📅 今日の予定"]
    if items:
        lines += [f"・{item}" for item in items]
    else:
        lines.append("今日の予定はありません")

    return "\n".join(lines)


# ============================================================
# F5 LINE に送る
# ============================================================
def push_message(token, user_id, message):
    """
    プッシュメッセージの API で、ユーザー ID の人（自分）にテキストメッセージを送る。

    - トークンは「Authorization: Bearer トークン」というヘッダーで渡す
    - 中身は JSON で送る。to が送り先、messages が送るメッセージの一覧（今回は1件）
    - 成功すると HTTP 200 が返る。失敗は 400・401 などのステータスと、中身の message で理由が返る
    """
    response = requests.post(
        PUSH_URL,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "to": user_id,
            "messages": [{"type": "text", "text": message}],
        },
        timeout=TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        show_error_and_exit(explain_line_error(response))


# ============================================================
# F6 お試し表示
# ============================================================
def show_preview(message):
    """
    LINE に送るはずの中身を、画面に表示する（送らない）。
    """
    print("--- 送る中身（お試し表示。LINE には送りません）---")
    print(message)
    print("-" * 26)


# ============================================================
# F8 エラー表示
# ============================================================
def now_in_japan():
    """
    日本の今の日時を返す。
    GitHub Actions のコンピューターは世界の標準時（日本より9時間遅い）で動いているので、
    時間帯を指定しないと、朝 7:00 が「前の日の 22:00」になり、前の日の曜日の予定が届いてしまう。
    """
    return datetime.now(ZoneInfo(TIMEZONE))


def now_text():
    """
    今の日時（日本）を「2026-10-25 07:30:01」の形の文字列で返す（ログに残すため）。
    """
    return now_in_japan().strftime("%Y-%m-%d %H:%M:%S")


def show_warning(message):
    """
    止めるほどではない問題（予定のファイルの書き間違いなど）を、日時付きで知らせる。
    """
    print(f"[{now_text()}] 注意: {message}", file=sys.stderr)


def show_error_and_exit(message):
    """
    原因が分かる日本語のエラーメッセージを、日時付きで表示して、プログラムを終了する。
    """
    print(f"[{now_text()}] エラー: {message}", file=sys.stderr)
    sys.exit(1)


def explain_line_error(response):
    """
    LINE が返した失敗の返事（HTTP のステータスと、中身の message）を、日本語の説明に直して返す。
    """
    # LINE は失敗の理由を {"message": "...", "details": [...]} の形で返す
    # （JSON でない返事が来ることもあるので、そのときは理由なしとする）
    try:
        body = response.json()
    except ValueError:
        body = {}
    reason = body.get("message", "")
    for detail in body.get("details", []):
        reason += f"（{detail.get('property', '')}: {detail.get('message', '')}）"
    detail_text = f"詳細: HTTP {response.status_code} {reason}".rstrip()

    # トークンが正しくない・再発行されて古くなった
    if response.status_code == 401:
        return (
            "チャネルアクセストークンが正しくありません。\n"
            f"{ENV_FILE.name} の {TOKEN_NAME} が、LINE Developers コンソールの「Messaging API 設定」タブにある\n"
            "チャネルアクセストークン（長期）と同じか確認してください。再発行した場合はトークンが変わります。\n"
            + detail_text
        )
    # 送り先や中身が正しくない
    if response.status_code == 400:
        return (
            "LINE がメッセージを受け付けませんでした。\n"
            f"{ENV_FILE.name} の {USER_ID_NAME} が、このチャネルの「チャネル基本設定」タブにある\n"
            "「あなたのユーザー ID」と同じか確認してください（別のチャネルのユーザー ID では送れません）。\n"
            + detail_text
        )
    # 月の上限を超えた・短い時間に送りすぎた
    if response.status_code == 429:
        return (
            "送れる数の上限を超えました。次のどちらかです。\n"
            f"  ・無料プランで今月送れる {FREE_PLAN_MONTHLY_LIMIT} 通を使い切った（来月まで待つ）\n"
            "  ・短い時間に送りすぎた（少し待ってからやり直す）\n"
            + detail_text
        )
    return "LINE への送信に失敗しました。\n" + detail_text


# ============================================================
# メインの処理（上の関数を順番に呼ぶ）
# ============================================================
def main():
    """
    プログラム全体の流れ：
    設定の読み込み → 天気の取得 → 予定の読み込み → メッセージを作る → LINE に送る
    （お試し表示のときは、送る代わりに中身を表示する）
    """
    dry_run = DRY_RUN_OPTION in sys.argv[1:]

    try:
        # F1 設定の読み込み（お試し表示では送らないので、トークンは要らない）
        token, user_id = (None, None) if dry_run else load_settings()

        # F2 天気の取得（取れなくても、予定だけは送る）
        print(f"{PLACE_NAME}の天気を取得しています...")
        weather, weather_error = try_fetch_weather()

        # F3 予定の読み込み
        today = now_in_japan().date()
        items = load_today_schedule(today)

        # F4 メッセージを作る
        message = build_message(today, weather, weather_error, items)

        # F6 お試し表示
        if dry_run:
            show_preview(message)
            return

        # F5 LINE に送る
        push_message(token, user_id, message)
        if weather_error:
            # 送れたが、天気が取れなかったことをログで分かるように、失敗の終わり方にする
            print(f"天気なしで LINE に送信しました（{now_text()}）")
            sys.exit(1)
        print(f"LINE に送信しました（{now_text()}）")

    except requests.Timeout:
        # 決めた秒数のうちに LINE から返事が無かった（F8）
        show_error_and_exit(
            f"LINE から {TIMEOUT_SECONDS} 秒たっても応答がありませんでした。時間をおいてやり直してください。\n"
            "（届いている場合もあるので、スマホの LINE を確認してください）"
        )
    except requests.RequestException as error:
        # インターネットにつながらない など（F8）
        # エラーの文字列をそのまま出すと送り先の情報まで出ることがあるので、種類の名前だけを出す
        show_error_and_exit(
            "LINE につながりませんでした。インターネット接続を確認してください。\n"
            f"詳細: {type(error).__name__}"
        )
    except KeyboardInterrupt:
        # Ctrl + C で途中でやめた場合
        print("\n中断しました。")
        sys.exit(1)


# このファイルを直接実行したときだけ main() を動かす
if __name__ == "__main__":
    main()
