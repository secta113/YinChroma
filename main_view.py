# v6.0
import flet as ft
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main_controller import MainController

class MainView:
    """
    メイン画面のレイアウトとUIコンポーネントの定義を行うクラス。
    v6.0: 画面右側に設定サイドパネル（Side Panel）を追加する2カラムレイアウトへ刷新。
    """
    def __init__(self, controller: "MainController"):
        self.c = controller
        
        # --- UI Components Definition ---
        
        # 1. Main Tuner Components
        self.result_text = ft.Text(
            value="---", size=42, weight="bold", 
            color=ft.Colors.CYAN_200, text_align=ft.TextAlign.CENTER
        )
        
        # Meter Constants
        self.unit_to_px = 3.5
        self.total_units = 110
        self.meter_width_px = self.total_units * self.unit_to_px # 385px
        
        # Meter Needle
        self.meter_needle = ft.Container(
            width=4, height=35, bgcolor=ft.Colors.ORANGE_400, border_radius=2, 
            left=(55 * self.unit_to_px) - 2,
            bottom=0,
            animate_position=ft.Animation(200, ft.AnimationCurve.EASE_OUT_CUBIC)
        )
        
        # Volume Bar
        self.volume_bar = ft.ProgressBar(
            width=self.meter_width_px, value=0, color=ft.Colors.GREEN_400
        )
        
        # Tuning Controls
        self.tuning_dropdown = ft.Dropdown(width=200, on_change=self.c.on_tuning_select)
        self.grid = ft.GridView(
            expand=True, runs_count=3, child_aspect_ratio=2.2, spacing=8, run_spacing=8
        )
        
        self.toggle_button = ft.ElevatedButton(
            text="ループ再生", icon=ft.Icons.PLAY_CIRCLE_FILLED, 
            on_click=self.c.toggle_play_click, width=200, height=50, 
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
        )

        self.mode_switch = ft.Switch(
            label="ヘッドセットモード(再生中も判定)", 
            value=self.c.config_manager.get_headset_mode(), 
            active_color=ft.Colors.TEAL_400, 
            on_change=self.c.on_headset_mode_change
        )

        # 2. Settings Panel Components (Right Side)
        
        # Threshold
        self.threshold_value_text = ft.Text("入力感度: --%", size=12)
        self.threshold_slider = ft.Slider(
            min=0, max=100.0, divisions=100, label="{value}%",
            on_change=self.c.on_threshold_change, on_change_end=self.c.on_threshold_change_end
        )

        # YIN Sensitivity
        self.yin_value_text = ft.Text("検出感度: --", size=12)
        self.yin_slider = ft.Slider(
            min=0.05, max=0.40, divisions=35, 
            on_change=self.c.on_yin_change, on_change_end=self.c.on_yin_change_end
        )

        # Latency Mode (Dropdown)
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

        # Instrument Type (Radio)
        self.instrument_group = ft.RadioGroup(
            content=ft.Row([
                ft.Radio(value="guitar", label="Guitar"),
                ft.Radio(value="bass", label="Bass"),
            ]),
            on_change=self.c.on_instrument_change
        )

        # Smoothing
        self.smoothing_text = ft.Text("針の滑らかさ: --", size=12)
        self.smoothing_slider = ft.Slider(
            min=1, max=10, divisions=9, label="{value}",
            on_change=self.c.on_smoothing_change, on_change_end=self.c.on_smoothing_change_end
        )

        # Settings Panel Container
        self.settings_container = ft.Container(
            width=300, # 幅固定
            bgcolor=ft.Colors.GREY_900,
            padding=20,
            visible=False, # 初期状態は隠すか、画面幅に応じて切り替え可能だが、今回はボタンでToggle
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
                self.latency_dropdown,
                ft.Text("楽器タイプ:", size=12),
                self.instrument_group,
                self.yin_value_text, self.yin_slider,
                ft.Divider(),
                
                ft.Text("表示設定", size=14, color=ft.Colors.CYAN_100),
                self.smoothing_text, self.smoothing_slider,
                
            ], scroll=ft.ScrollMode.AUTO)
        )

    def build(self):
        # Meter Build Logic
        ticks = []
        for i in range(-50, 51, 10): 
            unit_pos = 10 + ((i + 50) * 0.9)
            pixel_pos = unit_pos * self.unit_to_px
            is_main = (i % 50 == 0) or (i == 0)
            ticks.append(
                ft.Container(
                    width=2 if is_main else 1, height=12 if is_main else 6,
                    bgcolor=ft.Colors.GREY_700, left=pixel_pos - (1 if is_main else 0.5), top=5
                )
            )
            if is_main:
                ticks.append(
                    ft.Text(str(i), size=9, color=ft.Colors.GREY_600, left=pixel_pos - 15, top=18, width=30, text_align="center")
                )

        ok_zone_width_px = 9 * self.unit_to_px
        ok_zone_left = (55 - 4.5) * self.unit_to_px

        meter_bg = ft.Container(
            content=ft.Stack([
                ft.Container(width=self.meter_width_px, height=50, bgcolor=ft.Colors.BLACK, border_radius=5),
                ft.Container(width=ok_zone_width_px, height=30, bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.GREEN_400), left=ok_zone_left, bottom=0, border_radius=2),
                *ticks,
                self.meter_needle
            ], width=self.meter_width_px, height=50),
            width=self.meter_width_px, height=60, 
            border=ft.border.all(1, ft.Colors.GREY_800), border_radius=5
        )
        
        # Main Left Panel
        main_content = ft.Container(
            expand=True,
            padding=20,
            content=ft.Column([
                # Header
                ft.Row([
                    ft.Text("Python Guitar Tuner", size=20, weight="bold"),
                    ft.IconButton(ft.Icons.SETTINGS, tooltip="設定パネルを開閉", on_click=self.toggle_settings_panel)
                ], alignment="spaceBetween"),
                
                ft.Divider(),
                
                # Tuner Area
                ft.Container(
                    content=ft.Column([
                        ft.Container(content=self.result_text, height=100, alignment=ft.alignment.center),
                        meter_bg,
                        self.volume_bar,
                    ], horizontal_alignment="center"),
                    padding=20, bgcolor=ft.Colors.GREY_800, border_radius=15
                ),
                
                ft.Divider(height=20, color=ft.Colors.TRANSPARENT),

                # Controls Area
                ft.Row([ft.Text("チューニング設定", weight="bold"), self.tuning_dropdown], alignment="center"),
                ft.Divider(),
                ft.Row([ft.Text("お手本音源", weight="bold"), 
                        ft.IconButton(ft.Icons.LIBRARY_ADD_ROUNDED, on_click=lambda _: self.c.tuning_editor.show())], alignment="spaceBetween"),
                self.grid, 
                ft.Container(self.toggle_button, alignment=ft.alignment.center, padding=10)
            ])
        )

        # Root Layout: Row [MainContent, SettingsPanel]
        return ft.Row(
            [
                main_content,
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_800),
                self.settings_container
            ],
            expand=True,
            spacing=0
        )

    def toggle_settings_panel(self, e):
        self.settings_container.visible = not self.settings_container.visible
        self.page.update()

    @property
    def page(self): return self.c.page