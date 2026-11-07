#!/bin/sh
# Local Media Archiver for iPhone - 初期設定 (a-Shell mini 用)
#
# a-Shell mini に次の 1 行を貼り付けて実行します (2 回目以降は抽出エンジンの更新になります):
#   curl -fsSL https://worksofficedc-droid.github.io/local-media-archiver/ios/setup.sh | sh
#
# a-Shell の sh で動く範囲の構文だけを使う (配列・[[ ]]・local・関数は使わない)。

BASE_URL="https://worksofficedc-droid.github.io/local-media-archiver/ios"
BIN_DIR="$HOME/Documents/bin"
OUT_DIR="$HOME/Documents/LMA"

echo "Local Media Archiver for iPhone - 設定を始めます"

echo "1/5 フォルダを作成しています..."
if ! mkdir -p "$BIN_DIR" "$OUT_DIR"; then
  echo ""
  echo "NG: フォルダを作成できませんでした。"
  echo "    a-Shell を App Store で最新版に更新してから、もう一度このコマンドを貼ってください。"
  exit 1
fi

echo "2/5 抽出エンジン (yt-dlp) を取得・更新しています (少し時間がかかります)..."
if ! python3 -m pip install --upgrade --quiet yt-dlp; then
  echo ""
  echo "NG: 抽出エンジンを取得できませんでした。"
  echo "    通信環境 (Wi-Fi / モバイル回線) を確認して、もう一度このコマンドを貼ってください。"
  exit 1
fi

echo "3/5 保存スクリプトを取得しています..."
if ! curl -fsSL -o "$BIN_DIR/lma.py" "$BASE_URL/lma.py"; then
  echo ""
  echo "NG: 保存スクリプトを取得できませんでした。"
  echo "    通信環境を確認して、もう一度このコマンドを貼ってください。"
  exit 1
fi

echo "4/5 動作確認をしています..."
if ! python3 -c "import yt_dlp"; then
  echo ""
  echo "NG: 抽出エンジンを読み込めませんでした。"
  echo "    a-Shell を App Store で最新版に更新してから、もう一度このコマンドを貼ってください。"
  exit 1
fi
if ! ffmpeg -version >/dev/null 2>&1; then
  echo ""
  echo "NG: 結合エンジン (ffmpeg) が見つかりませんでした。"
  echo "    a-Shell を App Store で最新版に更新してください。"
  exit 1
fi
if ! ffprobe -version >/dev/null 2>&1; then
  echo ""
  echo "NG: 結合エンジン (ffprobe) が見つかりませんでした。"
  echo "    a-Shell を App Store で最新版に更新してください。"
  exit 1
fi

echo "5/5 保存スクリプトを確認しています..."
if ! python3 "$BIN_DIR/lma.py" --selfcheck; then
  echo ""
  echo "NG: 保存スクリプトの確認に失敗しました。"
  echo "    もう一度このコマンドを貼ってください。直らない場合は a-Shell を App Store で最新版に更新してください。"
  exit 1
fi

echo ""
echo "OK: 設定が完了しました。保存先: ファイル > このiPhone内 > a-Shell > LMA"
echo "    次に、ショートカットのリンクを開いて追加してください。"
exit 0
