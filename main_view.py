# v7.0
import flet as ft
from typing import TYPE_CHECKING
from settings_view import SettingsView

if TYPE_CHECKING:
    from main_controller import MainController

class MainView:
    """
    メイン画面のレイアウトとUIコンポーネントの定義を行うクラス。
    v7.0: 設定パネルを SettingsView に分離し、コードを軽量化。
    """
    def __init__(self, controller: "MainController"):
        self.c = controller
        
        # 設定ビューの初期化
        self.settings_view = SettingsView(controller)
        
        # --- UI Components Definition (Main Tuner Area) ---
        
        # 1. Main Tuner Components
        self.result_text = ft.Text(
            value="---", 
            size=34, # 文字サイズ
            weight="bold", 
            color=ft.Colors.CYAN_200, 
            text_align=ft.TextAlign.CENTER,
            selectable=True
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
        
        # GridView: 4列設定
        self.grid = ft.GridView(
            expand=True, 
            runs_count=4,           # 4列
            child_aspect_ratio=2.5, # ボタンサイズ縮小
            spacing=8, 
            run_spacing=8
        )
        
        self.toggle_button = ft.ElevatedButton(
            text="ループ再生", icon=ft.Icons.PLAY_CIRCLE_FILLED, 
            on_click=self.c.toggle_play_click, width=200, height=50, 
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
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
                        # 1. 音名テキスト
                        ft.Container(
                            content=self.result_text, 
                            alignment=ft.alignment.center,
                            height=100, 
                            margin=ft.margin.only(bottom=5) 
                        ),
                        
                        # 2. メーター
                        meter_bg,
                        
                        # 3. 余白
                        ft.Container(height=10),
                        
                        # 4. ボリュームバー
                        self.volume_bar,
                    ], horizontal_alignment="center", spacing=0),
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
        # SettingsViewのcontainerを配置
        return ft.Row(
            [
                main_content,
                ft.VerticalDivider(width=1, color=ft.Colors.GREY_800),
                self.settings_view.container
            ],
            expand=True,
            spacing=0
        )

    def toggle_settings_panel(self, e):
        # SettingsViewに委譲
        self.settings_view.toggle_visibility()
        # メイン側でもレイアウト更新が必要な場合があるためupdate
        self.page.update()

    @property
    def page(self): return self.c.page