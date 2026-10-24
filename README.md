# LINE 毎朝のお知らせ（line-morning-notify）

毎朝 7:00 に、**今日の天気**と**曜日ごとの予定**（ゴミの日・習いごとなど）を、LINE Messaging API で自分の LINE に1通にまとめて届ける Python プログラムです。
（AIエンジニア講座 課題8：連携した API に機能を追加。課題7の [line-push-message](https://github.com/m-tsuna/line-push-message) をもとに作りました）

## 何をするものか

```
🌧️ 弱い雨
最高 18.2℃ ／ 最低 12.5℃
降水確率 70%
☂️ 傘を持っていきましょう

📅 今日の予定
・燃えるゴミ
・ピアノ教室 18:00
```

- 天気は [Open-Meteo](https://open-meteo.com/)（無料・登録不要）から取ります。降水確率が 50% 以上の日は、傘の一言を足します
- 予定は `schedule.txt` に、曜日ごとに書いておきます。プログラムを直さずに書き換えられます
- 天気が取れなかった日も、予定だけは届きます
- 自動実行は GitHub Actions（GitHub のコンピューター）で動かすので、Mac の電源が切れていても届きます

## 事前準備

1. Python 3 と、ライブラリ `requests`・`python-dotenv`（Anaconda なら最初から入っています）
   ```
   pip install requests python-dotenv
   ```
2. LINE 公式アカウントと Messaging API のチャネル（下の「秘密ファイルの用意の仕方」）
3. スマホの LINE で、作った公式アカウントを友だち追加しておく（「Messaging API 設定」タブの QR コードを読む）

## 秘密ファイル（.env）の用意の仕方

1. [LINE Official Account Manager](https://manager.line.biz/) にログインし、LINE 公式アカウントを作る
2. 「設定」→「Messaging API」→「Messaging API を利用する」で、プロバイダーを作って有効にする
3. [LINE Developers コンソール](https://developers.line.biz/console/) でできたチャネルを開く
4. `.env.example` をコピーして `.env` という名前にし、次の2つを `=` の後ろに貼る
   - `LINE_USER_ID`：「チャネル基本設定」タブの一番下にある「あなたのユーザー ID」（`U` で始まる）
   - `LINE_CHANNEL_ACCESS_TOKEN`：「Messaging API 設定」タブの一番下で発行する「チャネルアクセストークン（長期）」

`.env` は鍵なので、GitHub には載せません（`.gitignore` に書いてあります）。漏れたときは、コンソールでトークンを再発行してください。

## 予定のファイル（schedule.txt）の書き方

`schedule.example.txt` をコピーして `schedule.txt` という名前にし、自分の予定に書き換えます。

```
月木: 燃えるゴミ
水: 資源ゴミ（びん・缶・ペットボトル）
火: ジム 19:00
```

- 1行に1つ「曜日: 予定」。曜日は「月火水木金土日」の1文字で、`月木` のように並べると両方の曜日に出ます
- `:` は全角の `：` でもかまいません。`#` で始まる行と空の行は飛ばします
- 書き方が違う行は、警告を出してその行だけ飛ばします
- `schedule.txt` は個人の情報なので、GitHub には載せません

## 使い方

```bash
python main.py            # 天気と予定を LINE に送る
python main.py --dry-run  # 送らずに、送る中身だけ表示する（お試し。送信数を使わない）
```

場所を変えたいときは、`main.py` の先頭の設定（`PLACE_NAME`、`LATITUDE`、`LONGITUDE`）を書き換えます。
緯度・経度は `https://geocoding-api.open-meteo.com/v1/search?name=地名&language=ja` で調べられます。

## 毎朝の自動実行（GitHub Actions）

GitHub Actions は、GitHub のコンピューターで決まった時刻にプログラムを動かす仕組みです。`.github/workflows/morning.yml` に「毎朝 7:00（日本時間）に main.py を動かす」と書いてあります。
自分の GitHub に載せて、鍵と予定を **Secrets**（GitHub の金庫。入れた値は見返せず、ログにも伏せ字で出る）に入れるだけで動きます。

1. このリポジトリを自分の GitHub に載せる（`.env` と `schedule.txt` は載せない）
2. Secrets を入れる。GitHub の画面なら「Settings」→「Secrets and variables」→「Actions」→「New repository secret」。[GitHub CLI](https://cli.github.com/) ならこのフォルダで：
   ```bash
   gh secret set -f .env                    # LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID を入れる
   gh secret set SCHEDULE_TEXT < schedule.txt  # 予定を入れる
   ```
3. 「Actions」タブ →「毎朝のお知らせ」→「Run workflow」で、今すぐ動かして試す（1通送る）。`gh workflow run morning.yml` でも同じ

- 時刻は UTC（世界の標準時。日本より9時間遅い）で書きます。`0 22 * * *` ＝ 日本時間の 7:00。GitHub が混んでいると、数分〜30分ほど遅れて始まることがあります
- 予定を変えたら、`schedule.txt` を書き換えて、もう一度 `gh secret set SCHEDULE_TEXT < schedule.txt` を実行します
- 失敗したときは GitHub からメールが届きます。結果は「Actions」タブの実行記録で見られます
- 公開リポジトリで 60 日間コミットが無いと、定期実行が止まります（GitHub からメールが来るので、「Actions」タブで有効にし直します）
- 毎日1通で月に約31通です。無料プランの月 200 通に収まります

## Mac で動かす場合（launchd）

Mac の電源を切らない人は、Mac の launchd でも動かせます（GitHub Actions と両方使うと2通届くので、どちらか一方にします）。

launchd は Mac に最初から入っている「目覚まし時計係」です。`launchd/line-morning.plist.example` に「毎朝 7:30 に main.py を動かす」と書いてあるので、自分の環境に合わせてコピーし、登録します。このフォルダで次を実行してください。

```bash
# 1. ログを入れるフォルダを作る
mkdir -p logs

# 2. 見本の __PYTHON__ と __PROJECT_DIR__ を自分の環境に置き換えて、launchd の置き場所にコピーする
sed -e "s#__PYTHON__#$(which python)#" -e "s#__PROJECT_DIR__#$(pwd)#g" \
  launchd/line-morning.plist.example > ~/Library/LaunchAgents/local.line-morning.plist

# 3. 登録する（これで毎朝 7:30 に動く）
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.line-morning.plist
```

| やりたいこと | コマンド |
|---|---|
| 朝を待たずに今すぐ動かして試す（1通送る） | `launchctl kickstart gui/$(id -u)/local.line-morning` |
| 登録されているか見る | `launchctl print gui/$(id -u)/local.line-morning` |
| 結果を見る | `cat logs/morning.log logs/error.log` |
| 自動実行をやめる | `launchctl bootout gui/$(id -u)/local.line-morning` |

- 7:30 に Mac がスリープしていた場合は、起きたときに動きます。電源が切れていた日は動きません
- 時刻を変えたいときは、plist の `Hour`・`Minute` を書き換え、一度やめてから登録し直します

## うまくいかないとき

| 表示 | 対処 |
|---|---|
| 〜が設定されていません | `.env` を作り、トークンとユーザー ID を書く |
| ユーザー ID の形が正しくありません | 「チャネル基本設定」の「あなたのユーザー ID」をコピーし直す（LINE ID とは別物） |
| チャネルアクセストークンが正しくありません | 「Messaging API 設定」のトークンと同じか確かめる。再発行したら貼り直す |
| 送れる数の上限を超えました | 今月の 200 通を使い切ったか、送りすぎ。来月まで、または少し待つ |
| LINE につながりませんでした | インターネット接続を確かめる |
| 注意: schedule.txt が無いので… | `schedule.example.txt` をコピーして `schedule.txt` を作る |
| 注意: schedule.txt の ◯ 行目を飛ばしました | その行を「曜日: 予定」の形に直す |
| 朝に通知が来ない | GitHub Actions：「Actions」タブの実行記録を見る（遅れて始まることもある）／launchd：`logs/error.log` を見る |

## ファイル

| ファイル | 内容 |
|---|---|
| `main.py` | プログラム本体 |
| `requirements.txt` | 使うライブラリの一覧 |
| `.github/workflows/morning.yml` | GitHub Actions の毎朝の設定 |
| `schedule.example.txt` | 予定の書き方の見本 |
| `launchd/line-morning.plist.example` | Mac で動かすときの設定の見本 |
| `.env.example` | `.env` の書き方の見本 |
| `要件定義書.md` | 何をどう作るかを決めた文書（方式を選んだ理由もここに書いています） |
