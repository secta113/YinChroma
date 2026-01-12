# v3.1
import flet as ft
import logging
import sys
from pathlib import Path
from typing import Dict, Optional, List, Any

# モジュールインポート
try:
    from soundhandler import SoundHandler
    from pitchdetector import PitchDetector
    from config_manager import ConfigManager
    from logger_manager import LoggerManager
    from tuning_editor import TuningEditor
except ImportError as e:
    print(f"Critical Import Error: {e}")

# --- パス設定 ---
def get_base_dir() -> Path:
    if getattr(sys, 'frozen', False): return Path(sys.executable).parent
    return Path(__file__).resolve().parent

BASE_DIR = get_base_dir()
SOUND_DIR = BASE_DIR / "sound"
LOG_DIR = BASE_DIR / "log"
SOUND_DIR.mkdir(exist_ok=True)

LoggerManager.setup_logging(LOG_DIR)

class GuitarTunerFletApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = "🎸 YinChroma - v3.1"
        self.page.window_width = 480
        self.page.window_height = 850
        self.page.theme_mode = ft.ThemeMode.DARK 
        
        self.is_closing = False
        self.config_manager = ConfigManager()
        self.sound_handler = SoundHandler()
        self.pitch_detector = PitchDetector(self._update_ui_callback, threshold=self.config_manager.get_threshold())
        
        self.current_tuning_data: List[List[Any]] = []
        
        # UIパーツ
        self.result_text = ft.Text("---", size=36, weight="bold", color=ft.Colors.CYAN_200)
        self.meter_needle = ft.Container(
            width=4, height=30, bgcolor=ft.Colors.ORANGE_400, border_radius=2, 
            animate_position=ft.Animation(300, ft.AnimationCurve.EASE_OUT_CUBIC)
        )
        self.volume_bar = ft.ProgressBar(width=300, value=0, color=ft.Colors.GREEN_400)
        self.tuning_dropdown = ft.Dropdown(width=200, on_change=self.on_tuning_select)
        self.grid = ft.GridView(expand=1, runs_count=2, max_extent=160, child_aspect_ratio=2.5, spacing=10)
        self.mode_switch = ft.Switch(label="ヘッドセットモード (再生中も判定)", value=self.config_manager.get_headset_mode(), active_color=ft.Colors.TEAL_400, on_change=self.on_headset_mode_change)
        
        # 機能分割: チューニングエディタの初期化 (v3.1)
        self.tuning_editor = TuningEditor(
            page=self.page,
            sound_dir=SOUND_DIR,
            config_manager=self.config_manager,
            on_save_callback=self._load_tuning_presets
        )
        
        self._build_ui()
        self._load_tuning_presets()
        self.pitch_detector.start_stream()

    def _load_tuning_presets(self):
        """保存されているプリセットを読み込み、UIに反映する"""
        presets = self.config_manager.get_tuning_presets()
        self.tuning_dropdown.options = [ft.dropdown.Option(name) for name in presets.keys()]
        current_name = self.config_manager.get_current_tuning_name()
        if current_name not in presets:
            current_name = "Standard" if "Standard" in presets else (list(presets.keys())[0] if presets else None)
        if current_name:
            self.tuning_dropdown.value = current_name
            self.apply_tuning(current_name)
        self.page.update()

    def apply_tuning(self, name: str):
        presets = self.config_manager.get_tuning_presets()
        if name not in presets: return
        self.current_tuning_data = presets[name]
        self.config_manager.set_current_tuning_name(name)
        freq_map = {item[0]: item[1] for item in self.current_tuning_data}
        self.pitch_detector.set_tuning_frequencies(freq_map)
        
        self.grid.controls.clear()
        for item in self.current_tuning_data:
            sound_path = SOUND_DIR / item[2] if item[2] else None
            exists = sound_path and sound_path.exists()
            btn = ft.ElevatedButton(
                text=item[0], data=sound_path, on_click=self.play_sound_click,
                style=ft.ButtonStyle(color=ft.Colors.WHITE if exists else ft.Colors.RED_400, bgcolor=ft.Colors.BLUE_GREY_800 if not exists else None),
                tooltip=f"{item[1]} Hz"
            )
            self.grid.controls.append(btn)
        self.page.update()

    def on_tuning_select(self, e):
        self.apply_tuning(e.control.value)

    def _build_ui(self):
        """メイン画面のレイアウト構築"""
        meter_bg = ft.Container(
            content=ft.Stack([ft.VerticalDivider(width=2, color=ft.Colors.GREY_700), self.meter_needle], alignment=ft.alignment.center),
            width=300, height=40, bgcolor=ft.Colors.BLACK, border_radius=5
        )
        
        # 設定セクション
        current_threshold = self.config_manager.get_threshold()
        self.threshold_value_text = ft.Text(f"振幅閾値: {current_threshold:.1f}", size=12)
        self.threshold_slider = ft.Slider(min=0, max=100, value=current_threshold, divisions=1000, on_change=self.on_threshold_change)
        settings_column = ft.Column([ft.Divider(height=20, color=ft.Colors.GREY_700), self.threshold_value_text, self.threshold_slider], visible=False, horizontal_alignment="center")
        
        def toggle_settings(e):
            settings_column.visible = not settings_column.visible
            self.page.update()

        settings_button = ft.IconButton(icon=ft.Icons.SETTINGS, icon_color=ft.Colors.GREY_400, on_click=toggle_settings)
        
        top_panel = ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("ピッチ解析", size=14, color=ft.Colors.GREY_400), settings_button], alignment="spaceBetween"),
                self.result_text, ft.Text("METER", size=10, color=ft.Colors.GREY_600), meter_bg, self.volume_bar, settings_column
            ], horizontal_alignment="center"),
            padding=20, bgcolor=ft.Colors.GREY_900, border_radius=15
        )
        
        self.toggle_button = ft.ElevatedButton(text="ループ再生", icon=ft.Icons.PLAY_CIRCLE_FILLED, on_click=self.toggle_play_click, width=200, height=50, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE))
        
        self.page.add(
            top_panel, 
            ft.Divider(height=30), 
            ft.Row([ft.Text("チューニング選択", weight="bold"), self.tuning_dropdown], alignment="center"), 
            ft.Container(self.mode_switch, alignment=ft.alignment.center), 
            ft.Divider(),
            ft.Row([
                ft.Text("お手本音源", weight="bold"), 
                # エディタの呼び出し (v3.1)
                ft.IconButton(ft.Icons.LIBRARY_ADD_ROUNDED, on_click=lambda _: self.tuning_editor.show(), tooltip="カスタム登録")
            ], alignment="spaceBetween"),
            self.grid, 
            ft.Container(self.toggle_button, alignment=ft.alignment.center, padding=ft.padding.only(top=10, bottom=20))
        )

    def on_threshold_change(self, e):
        val = e.control.value
        self.threshold_value_text.value = f"振幅閾値: {val:.1f}"
        self.config_manager.set_threshold(val)
        self.pitch_detector.set_threshold(val)
        self.page.update()

    def on_headset_mode_change(self, e):
        self.config_manager.set_headset_mode(e.control.value)
        self.page.update()

    def play_sound_click(self, e):
        path = e.control.data
        if not path or not path.exists(): return
        if not self.mode_switch.value:
            self.result_text.value = "再生中..."
            self.result_text.color = ft.Colors.ORANGE_300
            self.meter_needle.left = 150 - 2
        success = self.sound_handler.play_sound(path, loop=True)
        if success: self.last_selected_sound_path = path
        self._update_toggle_button_state()

    def toggle_play_click(self, e):
        if self.sound_handler.is_playing:
            self.sound_handler.stop_sound()
        else:
            if hasattr(self, 'last_selected_sound_path') and self.last_selected_sound_path:
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

    def _update_ui_callback(self, result_text: str, volume: float, cents: Optional[float]):
        if self.is_closing: return
        if not self.mode_switch.value and self.sound_handler.is_playing: return
        self.volume_bar.value = min(volume * 10.0, 1.0)
        if result_text != "---":
            self.result_text.value = result_text
            self.result_text.color = ft.Colors.GREEN_300 if "OK" in result_text else ft.Colors.CYAN_200
        if cents is not None:
            pos = 150 + (max(min(cents, 50), -50) * 3) - 2
            self.meter_needle.left = pos
            self.meter_needle.bgcolor = ft.Colors.GREEN_400 if abs(cents) < 5 else ft.Colors.ORANGE_400
        else:
            self.meter_needle.left = 150 - 2
            self.meter_needle.bgcolor = ft.Colors.ORANGE_400
        self.page.update()

    def on_close(self, e):
        self.is_closing = True
        logging.info("アプリケーションを正常に終了しています。")
        self.pitch_detector.stop_stream()
        self.sound_handler.quit()
        self.page.window_destroy()

def main(page: ft.Page):
    app = GuitarTunerFletApp(page)
    page.on_window_event = lambda e: app.on_close(e) if e.data == "close" else None

if __name__ == "__main__":
    ft.app(target=main)