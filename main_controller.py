# v5.9
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
    v5.9: 入力感度(Sensitivity)と閾値(Threshold)の関係を修正。
          - スライダー(感度)を上げる(右) -> 閾値を下げる(高感度)
          - スライダーを下げる(左) -> 閾値を上げる(低感度)
          - これによりユーザーの直感と一致させる。
    """
    def __init__(self, page: ft.Page, sound_dir: Path):
        self.page = page
        self.sound_dir = sound_dir
        self.is_closing = False
        
        self.config_manager = ConfigManager()
        self.sound_handler = SoundHandler()
        
        # 設定を読み込んでPitchDetectorを初期化
        config_dict = self.config_manager.get_all_settings_dict()
        
        self.pitch_detector = PitchDetector(
            self._update_ui_callback, 
            config=config_dict
        )
        
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
        self._initialize_ui_values()

    def _initialize_ui_values(self):
        """設定値に基づいてUIコンポーネントの初期状態を設定"""
        if not self.view: return

        # Threshold Slider (Inverted & Non-linear mapping)
        # 保存されているのは「閾値(0-100)」
        # UIで表示したいのは「感度(0-100)」
        # 関係: Threshold = ((100 - Sensitivity) / 100)^2 * 100
        # 逆算: Sensitivity = 100 * (1 - sqrt(Threshold / 100))
        saved_thresh = self.config_manager.get_threshold()
        
        # 安全策: ルート計算の前に負の値を防ぐ
        safe_thresh = max(0.0, saved_thresh)
        
        slider_pos = 100.0 * (1.0 - math.sqrt(safe_thresh / 100.0))
        # 0-100の範囲に収める
        slider_pos = max(0.0, min(100.0, slider_pos))
        
        self.view.threshold_slider.value = slider_pos
        self.view.threshold_value_text.value = f"入力感度: {slider_pos:.0f}%"

        # YIN Threshold
        self.view.yin_slider.value = self.config_manager.get_yin_threshold()
        self.view.yin_value_text.value = f"検出感度: {self.view.yin_slider.value:.2f}"

        # Latency Mode
        self.view.latency_dropdown.value = self.config_manager.get_latency_mode()
        
        # Instrument Type
        self.view.instrument_group.value = self.config_manager.get_instrument_type()

        # Smoothing
        self.view.smoothing_slider.value = float(self.config_manager.get_smoothing())
        self.view.smoothing_text.value = f"針の滑らかさ: {int(self.view.smoothing_slider.value)}"

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

    # --- Setting Handlers ---

    def on_threshold_change(self, e):
        # UI: Sensitivity (0-100%)
        # Logic: Threshold (High Sensitivity -> Low Threshold)
        sensitivity = e.control.value
        self.view.threshold_value_text.value = f"入力感度: {sensitivity:.0f}%"
        
        # 反転マッピング: 感度が高い(100)ほど、閾値は小さく(0)なる
        # 感度が高い領域(右側)での微調整を効かせるため、0付近で細かくなる2乗カーブを使用
        inverted_val = 100.0 - sensitivity
        mapped_threshold = (inverted_val / 100.0) ** 2 * 100.0
        
        self.pitch_detector.update_settings({"threshold": mapped_threshold})
        self.page.update()

    def on_threshold_change_end(self, e):
        sensitivity = e.control.value
        inverted_val = 100.0 - sensitivity
        mapped_threshold = (inverted_val / 100.0) ** 2 * 100.0
        self.config_manager.set_threshold(mapped_threshold)

    def on_yin_change(self, e):
        val = float(e.control.value)
        self.view.yin_value_text.value = f"検出感度: {val:.2f}"
        self.pitch_detector.update_settings({"yin_threshold": val})
        self.page.update()

    def on_yin_change_end(self, e):
        self.config_manager.set_yin_threshold(e.control.value)

    def on_latency_change(self, e):
        val = e.control.value
        self.pitch_detector.update_settings({"latency_mode": val})
        self.config_manager.set_latency_mode(val)
        self.page.update()

    def on_instrument_change(self, e):
        val = e.control.value
        self.pitch_detector.update_settings({"instrument_type": val})
        self.config_manager.set_instrument_type(val)
        self.page.update()

    def on_smoothing_change(self, e):
        val = int(e.control.value)
        self.view.smoothing_text.value = f"針の滑らかさ: {val}"
        self.pitch_detector.update_settings({"smoothing": val})
        self.page.update()

    def on_smoothing_change_end(self, e):
        self.config_manager.set_smoothing(int(e.control.value))

    def on_headset_mode_change(self, e):
        self.config_manager.set_headset_mode(e.control.value)
        self.page.update()

    # --- Sound Handlers ---

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