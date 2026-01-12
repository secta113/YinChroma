# v5.7
import logging
import flet as ft
import math
from pathlib import Path
from typing import List, Any, Optional

from soundhandler import SoundHandler
from pitchdetector import PitchDetector
from config_manager import ConfigManager
from tuning_editor import TuningEditor

class MainController:
    """
    アプリのロジック、イベント処理、状態管理を担当するクラス。
    v5.7: UI表示とスライダー数値を一致させ、非線形マッピングを内部処理に集約。
    """
    def __init__(self, page: ft.Page, sound_dir: Path):
        self.page = page
        self.sound_dir = sound_dir
        self.is_closing = False
        
        self.config_manager = ConfigManager()
        self.sound_handler = SoundHandler()
        
        # 起動時のしきい値を設定から取得
        initial_threshold = self.config_manager.get_threshold()
        
        self.pitch_detector = PitchDetector(
            self._update_ui_callback, 
            threshold=initial_threshold
        )
        self.pitch_detector.set_yin_threshold(self.config_manager.get_yin_threshold())
        
        self.view: Optional["MainView"] = None
        self.tuning_editor = TuningEditor(
            page=self.page, sound_dir=self.sound_dir,
            config_manager=self.config_manager, on_save_callback=self._load_tuning_presets
        )
        
        self.current_tuning_data: List[List[Any]] = []
        self.last_selected_sound_path: Optional[Path] = None
        self._callback_count = 0

    def set_view(self, view: "MainView"):
        self.view = view
        # 内部の実数値(y)からスライダー位置(x)を逆算して初期表示を合わせる
        # x = sqrt(y/100) * 100
        saved_val = self.config_manager.get_threshold()
        slider_pos = math.sqrt(saved_val / 100.0) * 100.0
        
        self.view.threshold_slider.value = slider_pos
        # テキスト表示はスライダーの数値（0-100）に合わせることで乖離を解消
        self.view.threshold_value_text.value = f"入力音量しきい値: {slider_pos:.0f}%"

    def _load_tuning_presets(self):
        presets = self.config_manager.get_tuning_presets()
        self.view.tuning_dropdown.options = [ft.dropdown.Option(name) for name in presets.keys()]
        current_name = self.config_manager.get_current_tuning_name()
        if current_name not in presets:
            current_name = "Standard" if "Standard" in presets else (list(presets.keys())[0] if presets else None)
        if current_name:
            self.view.tuning_dropdown.value = current_name
            self.apply_tuning(current_name)
        self.page.update()

    def apply_tuning(self, name: str):
        presets = self.config_manager.get_tuning_presets()
        if name not in presets: return
        self.current_tuning_data = presets[name]
        self.config_manager.set_current_tuning_name(name)
        
        freq_map = {item[0]: item[1] for item in self.current_tuning_data}
        self.pitch_detector.set_tuning_frequencies(freq_map)
        
        self.view.grid.controls.clear()
        for item in self.current_tuning_data:
            fname = item[2]
            sound_path = self.sound_dir / fname if fname else None
            exists = sound_path and fname and sound_path.exists()
            btn = ft.ElevatedButton(
                content=ft.Text(item[0], size=11, weight="w500"),
                data=sound_path, 
                on_click=self.play_sound_click,
                style=ft.ButtonStyle(
                    shape=ft.RoundedRectangleBorder(radius=6),
                    padding=ft.padding.all(5),
                    color=ft.Colors.WHITE if exists else ft.Colors.GREY_500,
                    bgcolor=None if exists else ft.Colors.BLUE_GREY_900
                ),
                tooltip=f"{item[1]} Hz"
            )
            self.view.grid.controls.append(btn)
        self.view.grid.update()
        self.page.update()

    def on_tuning_select(self, e):
        self.apply_tuning(e.control.value)

    def on_threshold_change(self, e):
        # UI表示はスライダーの生の値（0-100）をそのまま使う
        slider_val = e.control.value
        self.view.threshold_value_text.value = f"入力音量しきい値: {slider_val:.0f}%"
        
        # 内部計算（PitchDetectorへの反映）の時だけ2乗カーブを通す
        mapped_val = (slider_val / 100.0) ** 2 * 100.0
        self.pitch_detector.set_threshold(mapped_val)
        self.page.update()

    def on_threshold_change_end(self, e):
        # 設定ファイルへは、後で逆算できるように計算後の実数値を保存
        mapped_val = (e.control.value / 100.0) ** 2 * 100.0
        self.config_manager.set_threshold(mapped_val)

    def on_yin_change(self, e):
        val = float(e.control.value)
        self.view.yin_value_text.value = f"ピッチ検出感度: {val:.2f}"
        self.pitch_detector.set_yin_threshold(val)
        self.page.update()

    def on_yin_change_end(self, e):
        self.config_manager.set_yin_threshold(e.control.value)

    def on_headset_mode_change(self, e):
        self.config_manager.set_headset_mode(e.control.value)
        self.page.update()

    def play_sound_click(self, e):
        path = e.control.data
        if not path or not path.exists(): return
        if not self.view.mode_switch.value:
            self.view.result_text.value = "再生中..."
            self.view.result_text.color = ft.Colors.ORANGE_300
            self.view.meter_needle.left = (55 * self.view.unit_to_px) - 2
        success = self.sound_handler.play_sound(path, loop=True)
        if success: self.last_selected_sound_path = path
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
            self.view.toggle_button.text = "停止"
            self.view.toggle_button.icon = ft.Icons.STOP_CIRCLE
            self.view.toggle_button.style.bgcolor = ft.Colors.RED_700
        else:
            self.view.toggle_button.text = "ループ再生"
            self.view.toggle_button.icon = ft.Icons.PLAY_CIRCLE_FILLED
            self.view.toggle_button.style.bgcolor = ft.Colors.BLUE_700
        self.page.update()

    def _update_ui_callback(self, result_text: str, volume: float, cents: Optional[float]):
        if self.is_closing or not self.view: return
        self._callback_count += 1
        
        if not self.view.mode_switch.value and self.sound_handler.is_playing: return
        
        self.view.volume_bar.value = volume
        
        if result_text != "---":
            self.view.result_text.value = result_text
            self.view.result_text.color = ft.Colors.GREEN_300 if "OK" in result_text else ft.Colors.CYAN_200
        else:
            self.view.result_text.value = "---"
            self.view.result_text.color = ft.Colors.CYAN_200
        
        if cents is not None:
            clamped_cents = max(min(cents, 50), -50)
            target_unit = 10 + ((clamped_cents + 50) * 0.9)
            pos_px = (target_unit * self.view.unit_to_px) - 2
            
            self.view.meter_needle.left = pos_px
            self.view.meter_needle.bgcolor = ft.Colors.GREEN_400 if abs(cents) < 5 else ft.Colors.ORANGE_400
        else:
            self.view.meter_needle.left = (55 * self.view.unit_to_px) - 2
            self.view.meter_needle.bgcolor = ft.Colors.ORANGE_400
            
        if self._callback_count % 5 == 0:
            self.page.update()

    def cleanup(self):
        self.is_closing = True
        self.pitch_detector.stop_stream()
        self.sound_handler.quit()