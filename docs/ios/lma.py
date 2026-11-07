#!/usr/bin/env python3
"""Local Media Archiver for iPhone - a-Shell 内で動く保存スクリプト。

使い方 (a-Shell / iOS ショートカットから):
    python3 ~/Documents/bin/lma.py <URL>            動画を ~/Documents/LMA/ に mp4 で保存
    python3 ~/Documents/bin/lma.py --audio <URL>    音声のみを mp3 で保存
    python3 ~/Documents/bin/lma.py --selfcheck      yt-dlp と保存先の確認 (終了コード 0 なら OK)

出力契約:
    進捗を標準出力に流し、最後の 1 行に保存ファイルのフルパスを出す。
    失敗時は最後の 1 行が "ERROR: <日本語の理由>" で終了コード 1。
    ショートカットはこの最後の行だけを読む。

依存: yt-dlp (python3 -m pip install yt-dlp)。ffmpeg / ffprobe は a-Shell 内蔵のものを使う。
"""
import datetime
import glob
import os
import re
import sys

OUT_DIR = os.path.join(os.path.expanduser("~"), "Documents", "LMA")
MAX_URL_LENGTH = 2048
TITLE_MAX_CHARS = 80

# 写真アプリで再生できる H.264 + AAC の mp4 を最優先に選ぶ
_H264 = "[vcodec~='^(avc1|h264)']"
_AAC = "[acodec~='^(mp4a|aac)']"
VIDEO_FORMAT = "/".join([
    f"bv*{_H264}[ext=mp4]+ba{_AAC}[ext=m4a]",   # H.264 + AAC の mp4
    f"b{_H264}{_AAC}[ext=mp4]",
    f"bv*{_H264}+ba{_AAC}",                     # H.264 + AAC の他コンテナ (mp4 に詰め替える)
    f"b{_H264}{_AAC}",
    "b[ext=mp4]",
    "bv*+ba/b",
])
AUDIO_FORMAT = "ba/b"
FORMAT_SORT = ["vcodec:h264", "acodec:aac", "res", "br"]


def out(line: str) -> None:
    print(line, flush=True)


def fail(message: str):
    out(f"ERROR: {message}")
    sys.exit(1)


def validate_url(url: str) -> str:
    url = (url or "").strip()
    if len(url) > MAX_URL_LENGTH:
        fail("URLが長すぎます。")
    if any(ch in url for ch in "\r\n\x00"):
        fail("URLに不正な文字が含まれています。")
    if not (url.startswith("http://") or url.startswith("https://")):
        fail("http(s)で始まるURLを指定してください。")
    return url


def ensure_out_dir() -> None:
    try:
        os.makedirs(OUT_DIR, exist_ok=True)
    except OSError:
        fail("保存先フォルダを作成できませんでした。")


class _QuietLogger:
    """yt-dlp のログを標準出力に混ぜない。エラーは最後の 1 行だけ覚えておく。"""

    def __init__(self) -> None:
        self.last_error = ""

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        pass

    def error(self, msg: str) -> None:
        self.last_error = str(msg).strip().splitlines()[-1] if str(msg).strip() else ""


def _mb(num) -> str:
    try:
        return f"{float(num) / (1024 * 1024):.1f} MB"
    except (TypeError, ValueError):
        return "-- MB"


class _Progress:
    def __init__(self) -> None:
        self.last_percent = -1.0

    def hook(self, d: dict) -> None:
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            percent = (done / total * 100.0) if total else 0.0
            if percent - self.last_percent >= 1.0 or percent >= 100.0:
                self.last_percent = percent
                out(f"取得中 {percent:.1f}% {_mb(done)} / {_mb(total)}")
        elif status == "finished":
            self.last_percent = -1.0
            out("取得完了、変換しています...")


def _cleanup_leftovers(stamp: str, keep: str) -> None:
    """同じタイムスタンプの .part / .ytdl / 中間フラグメントを削除する。"""
    patterns = [
        f"{stamp}-*.part",
        f"{stamp}-*.ytdl",
        f"{stamp}-*.part-Frag*",
        f"{stamp}-*-Frag*",
        f"{stamp}-*.temp.*",
    ]
    for pattern in patterns:
        for path in glob.glob(os.path.join(OUT_DIR, pattern)):
            if os.path.abspath(path) == os.path.abspath(keep):
                continue
            try:
                os.remove(path)
            except OSError:
                pass


def _final_path(info: dict, ydl, stamp: str, ext: str) -> str:
    """後処理後の最終ファイルパスを決める (requested_downloads → prepare_filename → glob の順)。"""
    for item in info.get("requested_downloads") or []:
        path = item.get("filepath")
        if path and os.path.isfile(path):
            return path
    try:
        path = ydl.prepare_filename(info)
        base = os.path.splitext(path)[0]
        for cand in (base + "." + ext, path):
            if os.path.isfile(cand):
                return cand
    except Exception:
        pass
    matches = sorted(glob.glob(os.path.join(OUT_DIR, f"{stamp}-*.{ext}")))
    if matches:
        return matches[-1]
    fail("保存ファイルが見つかりませんでした。")


def _short_reason(text: str) -> str:
    """yt-dlp のエラー文から、通知に出せる短い理由だけを取り出す。"""
    line = (text or "").strip().splitlines()[-1] if (text or "").strip() else ""
    line = line.replace("ERROR:", "").strip()
    for marker in ("; please report", ". please report", " (caused by"):
        idx = line.lower().find(marker.lower())
        if idx > 0:
            line = line[:idx]
    line = re.sub(r"^\[[^\]]+\]\s*[^:]{0,80}:\s*", "", line)  # "[generic] none: " のような接頭辞
    line = line.strip()
    return (line[:120] + "…") if len(line) > 120 else (line or "不明なエラー")


def download(url: str, audio_only: bool) -> str:
    try:
        import yt_dlp
    except ImportError:
        fail("抽出エンジン (yt-dlp) が入っていません。設定コマンドをもう一度実行してください。")

    ensure_out_dir()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    outtmpl = os.path.join(OUT_DIR, f"{stamp}-%(title).{TITLE_MAX_CHARS}s.%(ext)s")
    logger = _QuietLogger()
    progress = _Progress()

    opts = {
        "outtmpl": outtmpl,
        "paths": {"home": OUT_DIR, "temp": OUT_DIR},
        "windowsfilenames": True,
        "noplaylist": True,
        "concurrent_fragment_downloads": 4,
        "retries": 5,
        "fragment_retries": 10,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "logger": logger,
        "progress_hooks": [progress.hook],
        "format_sort": FORMAT_SORT,
        "overwrites": True,
    }
    if audio_only:
        ext = "mp3"
        opts["format"] = AUDIO_FORMAT
        opts["postprocessors"] = [
            {"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"},
        ]
    else:
        ext = "mp4"
        opts["format"] = VIDEO_FORMAT
        opts["merge_output_format"] = "mp4"
        opts["postprocessors"] = [
            {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"},
        ]

    out("解析しています...")
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                fail("取得できませんでした（メディア情報がありません）")
            final = _final_path(info, ydl, stamp, ext)
    except yt_dlp.utils.DownloadError as e:
        fail(f"取得できませんでした（{_short_reason(logger.last_error or str(e))}）")
    except SystemExit:
        raise
    except KeyboardInterrupt:
        fail("中断しました")
    except Exception as e:  # スタックトレースは出さず型名だけ
        fail(f"予期しないエラー（{type(e).__name__}）")

    _cleanup_leftovers(stamp, keep=final)
    return final


def selfcheck() -> None:
    try:
        import yt_dlp
    except ImportError:
        fail("抽出エンジン (yt-dlp) が入っていません。")
    ensure_out_dir()
    out(f"yt-dlp {getattr(yt_dlp.version, '__version__', '?')}")
    out(f"保存先 {OUT_DIR}")
    out("OK")
    sys.exit(0)


def main(argv: list) -> None:
    args = list(argv[1:])
    if args == ["--selfcheck"]:
        selfcheck()
    audio_only = False
    if args and args[0] == "--audio":
        audio_only = True
        args = args[1:]
    if len(args) != 1:
        fail("使い方: python3 lma.py [--audio] <URL>")
    url = validate_url(args[0])
    final = download(url, audio_only)
    out(final)
    sys.exit(0)


if __name__ == "__main__":
    main(sys.argv)
