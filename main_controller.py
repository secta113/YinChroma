# v7.0
import logging
import flet as ft
import math
from pathlib import Path
from typing import List, Any, Optional

from pitchhandler.soundhandler import SoundHandler
from pitchhandler.pitchdetector import PitchDetector
from utils.config_manager import ConfigManager
from views.tuning_editor import TuningEditor

class MainController:
    """
    アプリのロジック、イベント処理、状態管理を担当するクラス。
    v6.4: 高精度モード対応。
    v7.0: SettingsView分離に伴い、UIコンポーネントへの参照パスを修正。
          (例: self.view.threshold_slider -> self.view.settings_view.threshold_slider)
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
        
        # Settings Viewへのショートカット
        sv = self.view.settings_view

        # Threshold
        saved_thresh = self.config_manager.get_threshold()
        safe_thresh = max(0.0, saved_thresh)
        slider_pos = 100.0 * (1.0 - math.sqrt(safe_thresh / 100.0))
        slider_pos = max(0.0, min(100.0, slider_pos))
        
        sv.threshold_slider.value = slider_pos
        sv.threshold_value_text.value = f"入力感度: {slider_pos:.0f}%"

        # YIN Threshold
        sv.yin_slider.value = self.config_manager.get_yin_threshold()
        sv.yin_value_text.value = f"検出信頼度(YIN): {sv.yin_slider.value:.2f}"
        
        # HQ Mode
        sv.hq_switch.value = self.config_manager.get_high_quality_mode()
        
        # Headset Mode
        sv.mode_switch.value = self.config_manager.get_headset_mode()

        # Sub-harmonic Ratio
        sub_ratio = self.config_manager.get_subharmonic_confidence_ratio()
        sv.subharmonic_slider.value = sub_ratio
        sv.subharmonic_text.value = f"倍音抑制: {sub_ratio:.2f}"

        # Octave Lookback Ratio
        oct_ratio = self.config_manager.get_octave_lookback_ratio()
        sv.octave_lookback_slider.value = oct_ratio
        sv.octave_lookback_text.value = f"低音補正(オクターブ): {oct_ratio:.2f}"

        # Nearest Note Window
        window_val = self.config_manager.get_nearest_note_window()
        sv.window_slider.value = window_val
        sv.window_text.value = f"許容誤差範囲(Window): {window_val:.0f}"

        # Latency Mode
        sv.latency_dropdown.value = self.config_manager.get_latency_mode()
        
        # Instrument Type
        sv.instrument_group.value = self.config_manager.get_instrument_type()

        # Smoothing
        sv.smoothing_slider.value = float(self.config_manager.get_smoothing())
        sv.smoothing_text.value = f"表示の安定度: {int(sv.smoothing_slider.value)}"

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
        # SettingsView経由で参照
        sv = self.view.settings_view
        sensitivity = e.control.value
        sv.threshold_value_text.value = f"入力感度: {sensitivity:.0f}%"
        
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
        sv = self.view.settings_view
        val = float(e.control.value)
        sv.yin_value_text.value = f"検出信頼度(YIN): {val:.2f}"
        self.pitch_detector.update_settings({"yin_threshold": val})
        self.page.update()

    def on_yin_change_end(self, e):
        self.config_manager.set_yin_threshold(float(e.control.value))

    def on_high_quality_change(self, e):
        val = e.control.value
        self.config_manager.set_high_quality_mode(val)
        self.pitch_detector.update_settings({"high_quality": val})
        self.page.update()

    def on_subharmonic_change(self, e):
        sv = self.view.settings_view
        val = float(e.control.value)
        sv.subharmonic_text.value = f"倍音抑制: {val:.2f}"
        self.pitch_detector.update_settings({"subharmonic_confidence_ratio": val})
        self.page.update()

    def on_subharmonic_change_end(self, e):
        self.config_manager.set_subharmonic_confidence_ratio(float(e.control.value))

    def on_octave_lookback_change(self, e):
        sv = self.view.settings_view
        val = float(e.control.value)
        sv.octave_lookback_text.value = f"低音補正(オクターブ): {val:.2f}"
        self.pitch_detector.update_settings({"octave_lookback_ratio": val})
        self.page.update()

    def on_octave_lookback_change_end(self, e):
        self.config_manager.set_octave_lookback_ratio(float(e.control.value))

    def on_window_change(self, e):
        sv = self.view.settings_view
        val = float(e.control.value)
        sv.window_text.value = f"許容誤差範囲(Window): {val:.0f}"
        self.pitch_detector.update_settings({"nearest_note_window": val})
        self.page.update()

    def on_window_change_end(self, e):
        self.config_manager.set_nearest_note_window(float(e.control.value))

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
        sv = self.view.settings_view
        val = int(e.control.value)
        sv.smoothing_text.value = f"表示の安定度: {val}"
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
        
        # ヘッドセットモードの状態確認もSettingsView経由
        if not self.view.settings_view.mode_switch.value:
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
        """
        PitchDetectorのAnalysisスレッドから呼び出されるコールバック。
        """
        if self.is_closing or not self.view: return
        self._callback_count += 1
        
        if self._callback_count % 5 != 0:
            return

        # SettingsView経由でHeadset Modeのチェック
        if not self.view.settings_view.mode_switch.value and self.sound_handler.is_playing: return
        
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
            
        try:
            self.page.update()
        except Exception:
            pass

    def cleanup(self):
        self.is_closing = True
        self.pitch_detector.stop_stream()
        self.sound_handler.quit()