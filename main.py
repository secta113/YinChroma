import flet as ft
import logging
import sys
import glob
import configparser
from pathlib import Path
from typing import Dict, Optional

# モジュールインポート
try:
    from soundhandler import SoundHandler
    from pitchdetector import PitchDetector
except ImportError:
    pass

# --- パス設定 (変更なし) ---
def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    else:
        return Path(__file__).resolve().parent

BASE_DIR = get_base_dir()
SOUND_DIR = BASE_DIR / "sound"
LOG_DIR = BASE_DIR / "log"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE_PATH = LOG_DIR / "app.log"
CONFIG_FILE_PATH = BASE_DIR / "config.ini"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE_PATH, encoding='utf-8')
    ]
)

class GuitarTunerFletApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "🎸 ギターチューニングソフト"
        self.page.window_width = 450
        self.page.window_height = 700  # スイッチ追加分少し高さを広げました
        self.page.window_resizable = False
        self.page.padding = 20
        self.page.theme_mode = ft.ThemeMode.DARK 
        #終了判定中フラグ        
        self.is_closing = False

        self.sounds: Dict[str, Path] = {}
        self.last_selected_sound_path: Optional[Path] = None
        
        self.result_text: Optional[ft.Text] = None
        self.volume_bar: Optional[ft.ProgressBar] = None
        self.toggle_button: Optional[ft.ElevatedButton] = None
        self.mode_switch: Optional[ft.Switch] = None  # (★追加) モード切替スイッチ
        
        self.amplitude_threshold = self._load_or_create_config()
        
        try:
            self.sound_handler = SoundHandler()
            self.pitch_detector = PitchDetector(
                self._update_ui_callback,
                threshold=self.amplitude_threshold
            )
            self._load_sounds()
        except Exception as e:
            logging.error(f"初期化エラー: {e}")
            self.page.add(ft.Text(f"起動エラー: {e}", color="red"))
            return

        self._build_ui()
        
        try:
            self.pitch_detector.start_stream()
        except Exception as e:
            logging.error(f"マイク開始失敗: {e}")

    def _load_or_create_config(self) -> float:
        # (変更なし)
        config = configparser.ConfigParser()
        default_threshold = 20.5
        if not CONFIG_FILE_PATH.exists():
            config['Tuner'] = {'AmplitudeThreshold': str(default_threshold)}
            try:
                with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
                    config.write(f)
            except Exception:
                pass
            return default_threshold
        try:
            config.read(CONFIG_FILE_PATH, encoding='utf-8')
            return config.getfloat('Tuner', 'AmplitudeThreshold', fallback=default_threshold)
        except Exception:
            return default_threshold

    def _load_sounds(self):
        # (変更なし)
        if not SOUND_DIR.exists():
            SOUND_DIR.mkdir(exist_ok=True)
        wav_files = sorted(glob.glob(str(SOUND_DIR / "*.wav")))
        for file_path_str in wav_files:
            p = Path(file_path_str)
            self.sounds[p.stem] = p

    def _build_ui(self):
        # 判定結果テキスト
        self.result_text = ft.Text(
            value="---",
            size=40,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            color=ft.Colors.CYAN_200
        )

        # 音量メーター
        self.volume_bar = ft.ProgressBar(
            width=300,
            value=0,
            color=ft.Colors.GREEN_400,
            bgcolor=ft.Colors.GREY_800,
        )

        top_container = ft.Container(
            content=ft.Column([
                ft.Text("現在のピッチ", size=14, color=ft.Colors.GREY_400),
                self.result_text,
                ft.Divider(height=10, color="transparent"),
                ft.Text("入力レベル", size=12),
                self.volume_bar,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=20,
            bgcolor=ft.Colors.GREY_900,
            border_radius=15,
            alignment=ft.alignment.center
        )

        # (★追加) ヘッドセットモードスイッチ
        self.mode_switch = ft.Switch(
            label="ヘッドセットモード (再生中も判定)",
            value=False, # デフォルトはOFF (スピーカーモード)
            active_color=ft.Colors.TEAL_400,
            tooltip="ONにすると、お手本再生中もマイク入力を受け付けます。\nイヤホン使用時に推奨。"
        )

        # 再生ボタン
        self.toggle_button = ft.ElevatedButton(
            text="ループ再生",
            icon=ft.Icons.PLAY_CIRCLE_FILLED,
            on_click=self.toggle_play_click,
            width=200,
            height=50,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=10),
                bgcolor=ft.Colors.BLUE_700,
                color=ft.Colors.WHITE,
            )
        )

        # 弦ボタンエリア
        buttons = []
        for name, path in self.sounds.items():
            btn = ft.ElevatedButton(
                text=name,
                data=path,
                on_click=self.play_sound_click,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=8),
                    padding=10
                )
            )
            buttons.append(btn)

        grid = ft.GridView(
            expand=1,
            runs_count=2,
            max_extent=160,
            child_aspect_ratio=2.5,
            spacing=10,
            run_spacing=10,
            controls=buttons
        )
        
        if not buttons:
            grid = ft.Container(
                content=ft.Text("soundフォルダにWAVファイルがありません\n(sound/*.wav を配置してください)", 
                                color="red", text_align="center"),
                alignment=ft.alignment.center
            )

        self.page.add(
            top_container,
            ft.Divider(height=10, thickness=1),
            ft.Text("お手本再生 (WAV)", size=16, weight=ft.FontWeight.BOLD),
            # スイッチを配置
            ft.Container(self.mode_switch, alignment=ft.alignment.center),
            ft.Container(self.toggle_button, alignment=ft.alignment.center, padding=5),
            ft.Container(grid, expand=True, padding=10)
        )

    def _update_ui_callback(self, result_text: str, volume: float):
        """
        PitchDetectorからのコールバック
        """
        #終了処理中は更新しない
        if self.is_closing:
            return
        
        # スイッチがOFF(スピーカーモード) かつ 音声再生中 なら更新しない
        if not self.mode_switch.value and self.sound_handler.is_playing:
            return

        # メーターの動きを調整
        sensitivity = 10.0 
        display_vol = min(volume * sensitivity, 1.0)
        
        self.volume_bar.value = display_vol

        if result_text != "---" and result_text != "一致なし":
            self.result_text.value = result_text
            self.result_text.color = ft.Colors.CYAN_200
            if "OK" in result_text:
                self.result_text.color = ft.Colors.GREEN_300
        
        try:
            self.page.update()
        except Exception:
            # 万が一ここでエラーが出てもログに出さない（終了時によくあるため）
            pass

    def play_sound_click(self, e):
        sound_path = e.control.data
        
        # マイク判定が無効になるモードの場合のみ、テキストを「再生中...」にする
        if not self.mode_switch.value:
            self.result_text.value = "再生中..."
            self.result_text.color = ft.Colors.ORANGE_300
            self.volume_bar.value = 0
            
        self.page.update()

        success = self.sound_handler.play_sound(sound_path, loop=True)
        if success:
            self.last_selected_sound_path = sound_path
        
        self._update_toggle_button_state()

    def toggle_play_click(self, e):
        if self.sound_handler.is_playing:
            self.sound_handler.stop_sound()
        else:
            if self.last_selected_sound_path:
                self.sound_handler.play_sound(self.last_selected_sound_path, loop=True)
            else:
                self.page.open(ft.SnackBar(ft.Text("再生する弦を選んでください")))
        
        self._update_toggle_button_state()

    def _update_toggle_button_state(self):
        if self.sound_handler.is_playing:
            self.toggle_button.text = "停止"
            self.toggle_button.icon = ft.Icons.STOP_CIRCLE
            self.toggle_button.style.bgcolor = ft.Colors.RED_700
        else:
            self.toggle_button.text = "ループ再生"
            self.toggle_button.icon = ft.Icons.PLAY_CIRCLE_FILLED
            self.toggle_button.style.bgcolor = ft.Colors.BLUE_700
        self.page.update()

    def on_close(self, e):
        
        self.is_closing = True
        logging.info("終了処理...")
        if hasattr(self, 'pitch_detector'):
            self.pitch_detector.stop_stream()
        if hasattr(self, 'sound_handler'):
            self.sound_handler.quit()
        self.page.window_destroy()

def main(page: ft.Page):
    app = GuitarTunerFletApp(page)
    page.on_window_event = lambda e: app.on_close(e) if e.data == "close" else None

if __name__ == "__main__":
    ft.app(target=main)