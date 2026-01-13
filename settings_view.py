# v1.0
import flet as ft
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main_controller import MainController

class SettingsView:
    """
    設定パネルのUIコンポーネントとレイアウトを担当するクラス。
    MainViewから分離して管理。
    """
    def __init__(self, controller: "MainController"):
        self.c = controller
        
        # --- UI Components Definition ---
        
        # Threshold
        self.threshold_value_text = ft.Text("入力感度: --%", size=12)
        self.threshold_slider = ft.Slider(
            min=0, max=100.0, divisions=100, label="{value}%",
            on_change=self.c.on_threshold_change, on_change_end=self.c.on_threshold_change_end
        )

        # Headset Mode Switch
        self.mode_switch = ft.Switch(
            label="ヘッドセットモード(再生中も判定)", 
            value=False, # 初期値はControllerから設定される
            active_color=ft.Colors.TEAL_400, 
            on_change=self.c.on_headset_mode_change
        )
        
        # High Quality Mode Switch
        self.hq_switch = ft.Switch(
            label="高精度モード (44kHz解析)",
            value=False,
            active_color=ft.Colors.PURPLE_300,
            on_change=self.c.on_high_quality_change
        )
        self.hq_desc = ft.Text("※ONにすると精度向上(特に高音域)。CPU負荷が増加します。", size=10, color=ft.Colors.GREY_500)

        # Latency Mode
        self.latency_dropdown = ft.Dropdown(
            label="モード (反応速度/安定性)",
            options=[
                ft.dropdown.Option("fast", "High Speed (標準ギター)"),
                ft.dropdown.Option("normal", "Balanced (推奨)"),
                ft.dropdown.Option("stable", "Deep Bass (7弦/ベース)"),
            ],
            on_change=self.c.on_latency_change,
            text_size=12,
            width=200
        )

        # Instrument Type
        self.instrument_group = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="guitar", label="Guitar"),
                ft.Radio(value="bass", label="Bass"),
            ]),
            on_change=self.c.on_instrument_change
        )

        # YIN Sensitivity
        self.yin_value_text = ft.Text("検出信頼度(YIN): --", size=12)
        self.yin_slider = ft.Slider(
            min=0.05, max=0.40, divisions=35, 
            on_change=self.c.on_yin_change, on_change_end=self.c.on_yin_change_end
        )

        # Sub-harmonic Ratio
        self.subharmonic_text = ft.Text("倍音抑制: --", size=12)
        self.subharmonic_slider = ft.Slider(
            min=0.5, max=1.0, divisions=50, label="{value}",
            on_change=self.c.on_subharmonic_change, on_change_end=self.c.on_subharmonic_change_end
        )

        # Octave Lookback Ratio
        self.octave_lookback_text = ft.Text("低音補正(オクターブ): --", size=12)
        self.octave_lookback_slider = ft.Slider(
            min=0.5, max=1.0, divisions=50, label="{value}",
            on_change=self.c.on_octave_lookback_change, on_change_end=self.c.on_octave_lookback_change_end
        )

        # Nearest Note Window
        self.window_text = ft.Text("許容誤差範囲(Window): --", size=12)
        self.window_slider = ft.Slider(
            min=50, max=600, divisions=55, label="{value}",
            on_change=self.c.on_window_change, on_change_end=self.c.on_window_change_end
        )

        # Smoothing
        self.smoothing_text = ft.Text("表示の安定度: --", size=12)
        self.smoothing_slider = ft.Slider(
            min=1, max=10, divisions=9, label="{value}",
            on_change=self.c.on_smoothing_change, on_change_end=self.c.on_smoothing_change_end
        )

        # Main Container (Visible/Hidden controlled by parent)
        self.container = ft.Container(
            width=320, 
            bgcolor=ft.Colors.GREY_900,
            padding=20,
            visible=False, 
            animate_opacity=200,
            border=ft.border.only(left=ft.BorderSide(1, ft.Colors.GREY_800)),
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.TUNE), ft.Text("詳細設定", size=16, weight="bold")], alignment="center"),
                ft.Divider(),
                
                ft.Text("入力設定", size=14, color=ft.Colors.CYAN_100),
                self.threshold_value_text, self.threshold_slider,
                self.mode_switch,
                ft.Divider(),
                
                ft.Text("検出アルゴリズム", size=14, color=ft.Colors.CYAN_100),
                self.hq_switch,
                self.hq_desc,
                ft.Container(height=5),
                self.latency_dropdown,
                ft.Text("楽器タイプ:", size=12),
                self.instrument_group,
                ft.Container(height=10),
                
                ft.Text("ロジック微調整", size=13, weight="bold"),
                self.yin_value_text, self.yin_slider,
                ft.Text("※値を下げると判定が厳しくなり、誤検知を防ぎます", size=10, color=ft.Colors.GREY_500),

                self.subharmonic_text, self.subharmonic_slider,
                ft.Text("※値を下げると高音誤検知(倍音)を抑制", size=10, color=ft.Colors.GREY_500),
                
                self.octave_lookback_text, self.octave_lookback_slider,
                ft.Text("※値を上げると低音誤検知(オクターブ)を抑制", size=10, color=ft.Colors.GREY_500),

                ft.Container(height=5),
                self.window_text, self.window_slider,
                ft.Text("※値を下げると外れた音を無視(---)します", size=10, color=ft.Colors.GREY_500),
                
                ft.Divider(),
                
                ft.Text("表示設定", size=14, color=ft.Colors.CYAN_100),
                self.smoothing_text, self.smoothing_slider,
                
            ], scroll=ft.ScrollMode.AUTO)
        )

    def toggle_visibility(self):
        self.container.visible = not self.container.visible
        self.container.update()