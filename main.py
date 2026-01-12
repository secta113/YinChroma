# v4.1
import flet as ft
import sys
import logging
from pathlib import Path

# モジュールインポート
try:
    from logger_manager import LoggerManager
    from main_controller import MainController
    from main_view import MainView
except ImportError as e:
    # 起動時の致命的なインポートエラーを記録
    print(f"Critical Import Error: {e}")
    raise

# --- パス設定 ---
def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False): return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR = get_base_dir()
SOUND_DIR = BASE_DIR / "sound"
LOG_DIR = BASE_DIR / "log"
SOUND_DIR.mkdir(exist_ok=True)

# ログの初期化（logger_managerで設定されたRotatingFileHandler等が適用されます）
LoggerManager.setup_logging(LOG_DIR)

def main(page: ft.Page):
    logging.info("YinChroma アプリケーションを起動しています。")
    
    # Controllerの初期化
    controller = MainController(page, SOUND_DIR)
    
    # Viewの初期化（Controllerを渡す）
    view = MainView(controller)
    
    # ControllerにViewを教える
    controller.set_view(view)
    
    # UIの組み立て
    page.add(view.build())
    
    # 終了イベントの紐付け
    page.on_window_event = lambda e: controller.cleanup() if e.data == "close" else None
    
    # データの初期ロード（View構築後に行う必要がある）
    controller._load_tuning_presets()
    
    # 【v4.1修正】マイクストリームの開始
    # v4.0での機能分割時にこの呼び出しが漏れていたため、判定が開始されない状態でした。
    try:
        controller.pitch_detector.start_stream()
        logging.info("ピッチ検出ストリームを開始しました。")
    except Exception as e:
        logging.error(f"ストリームの開始に失敗しました: {e}")
        page.open(ft.SnackBar(ft.Text("マイクの開始に失敗しました。設定を確認してください。")))

if __name__ == "__main__":
    ft.app(target=main)