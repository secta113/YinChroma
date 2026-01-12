# v4.3
import flet as ft
import sys
import logging
from pathlib import Path
import ctypes

# Windows タスクバーアイコン設定
try:
    myappid = 'secta113.yinchroma.tuner.4.3' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except Exception:
    pass

# モジュールインポート
try:
    from logger_manager import LoggerManager
    from main_controller import MainController
    from main_view import MainView
except ImportError as e:
    print(f"Critical Import Error: {e}")
    raise

def get_base_dir() -> Path:
    """ アプリケーションのベースディレクトリを取得します """
    if getattr(sys, 'frozen', False): return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent

BASE_DIR = get_base_dir()
SOUND_DIR = BASE_DIR / "sound"
LOG_DIR = BASE_DIR / "log"
ASSETS_DIR = BASE_DIR / "assets"

# 1. ロギングの初期化
LoggerManager.setup_logging(LOG_DIR)

def main(page: ft.Page):
    logging.info("--- main() 関数を開始しました ---")
    
    # ウィンドウサイズの設定
    page.window.width = 450
    page.window.height = 800
    page.window.min_width = 400
    page.window.min_height = 700

    # Controllerの初期化
    controller = MainController(page, SOUND_DIR)
    view = MainView(controller)
    controller.set_view(view)

    page.title = "#YinChroma - ギターチューニング"
    
    # メインレイアウトの追加
    page.add(view.build())
    
    # ウィンドウイベントの登録
    page.on_window_event = lambda e: controller.cleanup() if e.data == "close" else None
    
    # プリセットの読み込みと適用
    controller._load_tuning_presets()
    
    try:
        # ピッチ検出ストリームの開始
        controller.pitch_detector.start_stream()
        logging.info("ピッチ検出ストリームを開始しました。")
    except Exception as e:
        logging.error(f"ピッチ検出ストリームの開始に失敗しました: {e}")

if __name__ == "__main__":
    logging.info("=== アプリケーション起動プロセス開始 ===")
    ft.app(target=main, assets_dir=str(ASSETS_DIR))