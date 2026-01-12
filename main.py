# v1.5
import flet as ft
import logging
import sys
import glob
from pathlib import Path
from typing import Dict, Optional

# モジュールインポート
try:
    from soundhandler import SoundHandler
    from pitchdetector import PitchDetector
    from config_manager import ConfigManager
except ImportError as e:
    logging.error(f"インポートエラー: {e}")

# --- パス設定 ---
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
        self.page.title = "🎸 YinChroma - ギターチューナー (v1.5)"
        self.page.window_width = 450
        self.page.window_height = 850
        self.page.window_resizable = False
        self.page.padding = 20
        self.page.theme_mode = ft.ThemeMode.DARK 
        
        self.is_closing = False
        self.sounds: Dict[str, Path] = {}
        self.last_selected_sound_path: Optional[Path] = None
        
        # 設定管理の初期化
        self.config_manager = ConfigManager()
        
        # UIコンポーネント
        self.result_text: Optional[ft.Text] = None
        self.volume_bar: Optional[ft.ProgressBar] = None
        self.toggle_button: Optional[ft.ElevatedButton] = None
        self.mode_switch: Optional[ft.Switch] = None
        self.threshold_slider: Optional[ft.Slider] = None
        self.threshold_value_text: Optional[ft.Text] = None
        self.settings_column: Optional[ft.Column] = None
        
        # メーター用コンポーネント
        self.meter_needle: Optional[ft.Container] = None
        self.meter_width = 300
        
        try:
            self.sound_handler = SoundHandler()
            self.pitch_detector = PitchDetector(
                self._update_ui_callback,
                threshold=self.config_manager.get_threshold()
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

    def _load_sounds(self):
        if not SOUND_DIR.exists():
            SOUND_DIR.mkdir(exist_ok=True)
        wav_files = sorted(glob.glob(str(SOUND_DIR / "*.wav")))
        for file_path_str in wav_files:
            p = Path(file_path_str)
            self.sounds[p.stem] = p

    def _build_ui(self):
        # 判定結果
        self.result_text = ft.Text(
            value="---",
            size=36,
            weight=ft.FontWeight.BOLD,
            text_align=ft.TextAlign.CENTER,
            color=ft.Colors.CYAN_200
        )

        # 視覚化メーター (v1.5: ft.animation.Animation を ft.Animation に修正)
        self.meter_needle = ft.Container(
            width=4,
            height=30,
            bgcolor=ft.Colors.ORANGE_400,
            border_radius=2,
            left=(self.meter_width / 2) - 2, # 初期位置(中央)
            animate_position=ft.Animation(300, ft.AnimationCurve.EASE_OUT_CUBIC)
        )

        meter_bg = ft.Container(
            content=ft.Stack([
                # 中央の目盛り
                ft.VerticalDivider(width=2, color=ft.Colors.GREY_700, thickness=2),
                # 針
                self.meter_needle,
            ], alignment=ft.alignment.center),
            width=self.meter_width,
            height=40,
            bgcolor=ft.Colors.BLACK,
            border=ft.border.all(1, ft.Colors.GREY_800),
            border_radius=5,
        )

        # 音量メーター
        self.volume_bar = ft.ProgressBar(
            width=self.meter_width,
            value=0,
            color=ft.Colors.GREEN_400,
            bgcolor=ft.Colors.GREY_800,
        )

        # 設定エリア
        current_threshold = self.config_manager.get_threshold()
        self.threshold_value_text = ft.Text(f"振幅閾値: {current_threshold:.1f}", size=12)
        self.threshold_slider = ft.Slider(
            min=0, max=100,
            value=current_threshold,
            divisions=1000,
            label="{value}",
            on_change=self.on_threshold_change
        )

        self.settings_column = ft.Column([
            ft.Divider(height=20, color=ft.Colors.GREY_700),
            self.threshold_value_text,
            self.threshold_slider,
        ], visible=False, horizontal_alignment=ft.CrossAxisAlignment.CENTER)

        settings_button = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            icon_color=ft.Colors.GREY_400,
            on_click=self.toggle_settings
        )

        top_container = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("現在のピッチ", size=14, color=ft.Colors.GREY_400),
                    settings_button
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                self.result_text,
                ft.Text("TUNING METER", size=10, color=ft.Colors.GREY_600),
                meter_bg,
                ft.Divider(height=10, color="transparent"),
                ft.Text("入力レベル", size=12),
                self.volume_bar,
                self.settings_column,
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=20,
            bgcolor=ft.Colors.GREY_900,
            border_radius=15,
            alignment=ft.alignment.center
        )

        self.mode_switch = ft.Switch(
            label="ヘッドセットモード",
            value=False,
            active_color=ft.Colors.TEAL_400
        )

        self.toggle_button = ft.ElevatedButton(
            text="ループ再生",
            icon=ft.Icons.PLAY_CIRCLE_FILLED,
            on_click=self.toggle_play_click,
            width=200, height=50,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
        )

        buttons = []
        for name, path in self.sounds.items():
            btn = ft.ElevatedButton(
                text=name, data=path,
                on_click=self.play_sound_click,
                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), padding=10)
            )
            buttons.append(btn)

        grid = ft.GridView(expand=1, runs_count=2, max_extent=160, child_aspect_ratio=2.5, spacing=10, run_spacing=10, controls=buttons)
        
        self.page.add(
            top_container,
            ft.Divider(height=10, thickness=1),
            ft.Text("お手本再生 (WAV)", size=16, weight=ft.FontWeight.BOLD),
            ft.Container(self.mode_switch, alignment=ft.alignment.center),
            ft.Container(self.toggle_button, alignment=ft.alignment.center, padding=5),
            ft.Container(grid, expand=True, padding=10)
        )

    def toggle_settings(self, e):
        self.settings_column.visible = not self.settings_column.visible
        self.page.update()

    def on_threshold_change(self, e):
        new_val = e.control.value
        self.threshold_value_text.value = f"振幅閾値: {new_val:.1f}"
        self.config_manager.set_threshold(new_val)
        self.pitch_detector.set_threshold(new_val)
        self.page.update()

    def _update_ui_callback(self, result_text: str, volume: float, cents: Optional[float]):
        """
        PitchDetectorからのコールバック
        """
        if self.is_closing: return
        if not self.mode_switch.value and self.sound_handler.is_playing: return

        # 音量表示
        sensitivity = 10.0 
        self.volume_bar.value = min(volume * sensitivity, 1.0)

        # テキスト表示の更新
        if result_text != "---" and result_text != "一致なし":
            self.result_text.value = result_text
            self.result_text.color = ft.Colors.CYAN_200
            if "OK" in result_text:
                self.result_text.color = ft.Colors.GREEN_300
        elif result_text == "---":
            # 入力がない場合は針を中央に戻す
            self.meter_needle.left = (self.meter_width / 2) - 2
            self.meter_needle.bgcolor = ft.Colors.ORANGE_400

        # メーターの針の更新
        if cents is not None:
            # -50 ～ +50 cent を 0 ～ meter_width にマッピング
            clipped_cents = max(min(cents, 50), -50)
            # 中央(150px)からのオフセット計算
            pos_x = (self.meter_width / 2) + (clipped_cents * (self.meter_width / 100)) - 2
            self.meter_needle.left = pos_x
            
            # 色の変更 (±5セント以内なら緑)
            if abs(cents) < 5:
                self.meter_needle.bgcolor = ft.Colors.GREEN_400
            else:
                self.meter_needle.bgcolor = ft.Colors.ORANGE_400
        
        try:
            self.page.update()
        except:
            pass

    def play_sound_click(self, e):
        sound_path = e.control.data
        if not self.mode_switch.value:
            self.result_text.value = "再生中..."
            self.result_text.color = ft.Colors.ORANGE_300
            self.volume_bar.value = 0
            self.meter_needle.left = (self.meter_width / 2) - 2
        self.page.update()
        if self.sound_handler.play_sound(sound_path, loop=True):
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
        logging.info("終了処理中...")
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