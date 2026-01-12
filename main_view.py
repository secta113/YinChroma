# v4.0
import flet as ft
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main_controller import MainController

class MainView:
    """
    メイン画面のレイアウトとUIコンポーネントの定義を行うクラス。
    """
    def __init__(self, controller: "MainController"):
        self.c = controller
        
        # --- UIコンポーネントの定義 ---
        self.result_text = ft.Text(
            value="---", 
            size=36, 
            weight="bold", 
            color=ft.Colors.CYAN_200,
            text_align=ft.TextAlign.CENTER
        )
        
        self.meter_width = 320
        self.meter_needle = ft.Container(
            width=4, height=35, bgcolor=ft.Colors.ORANGE_400, border_radius=2, 
            animate_position=ft.Animation(250, ft.AnimationCurve.EASE_OUT_CUBIC)
        )
        
        self.volume_bar = ft.ProgressBar(width=self.meter_width, value=0, color=ft.Colors.GREEN_400)
        self.tuning_dropdown = ft.Dropdown(width=200, on_change=self.c.on_tuning_select)
        self.grid = ft.GridView(expand=1, runs_count=2, max_extent=160, child_aspect_ratio=2.5, spacing=10)
        
        self.mode_switch = ft.Switch(
            label="ヘッドセットモード (再生中も判定)", 
            value=self.c.config_manager.get_headset_mode(), 
            active_color=ft.Colors.TEAL_400, 
            on_change=self.c.on_headset_mode_change
        )
        
        self.toggle_button = ft.ElevatedButton(
            text="ループ再生", 
            icon=ft.Icons.PLAY_CIRCLE_FILLED, 
            on_click=self.c.toggle_play_click, 
            width=200, 
            height=50, 
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
        )

        # 設定セクション用
        current_threshold = self.c.config_manager.get_threshold()
        self.threshold_value_text = ft.Text(f"振幅閾値: {current_threshold:.1f}", size=12)
        self.threshold_slider = ft.Slider(
            min=0, max=100, 
            value=current_threshold, 
            divisions=1000, 
            on_change=self.c.on_threshold_change,
            on_change_end=self.c.on_threshold_change_end
        )
        self.settings_column = ft.Column(
            [ft.Divider(height=20, color=ft.Colors.GREY_700), self.threshold_value_text, self.threshold_slider], 
            visible=False, 
            horizontal_alignment="center"
        )

    def build(self):
        """全体のレイアウトを構築して返します。"""
        
        def create_scale_line(left_pos, color=ft.Colors.GREY_800, height=15):
            return ft.Container(width=1, height=height, bgcolor=color, left=left_pos, bottom=0)

        def create_scale_label(text, left_pos):
            return ft.Container(content=ft.Text(text, size=10, color=ft.Colors.GREY_500), left=left_pos - 10, top=2)

        center = self.meter_width / 2
        ok_zone_width = (self.meter_width / 100) * 10
        
        meter_bg = ft.Container(
            content=ft.Stack([
                ft.Container(width=self.meter_width, height=50, bgcolor=ft.Colors.BLACK, border_radius=5),
                ft.Container(width=ok_zone_width, height=30, bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.GREEN_400), left=center - (ok_zone_width / 2), bottom=0, border_radius=2),
                create_scale_label("-50", 10),
                create_scale_label("0", center),
                create_scale_label("+50", self.meter_width - 15),
                create_scale_line(center, ft.Colors.GREY_600, 25),
                create_scale_line(center - (center * 0.5), ft.Colors.GREY_800, 15),
                create_scale_line(center + (center * 0.5), ft.Colors.GREY_800, 15),
                create_scale_line(2, ft.Colors.GREY_800, 15),
                create_scale_line(self.meter_width - 2, ft.Colors.GREY_800, 15),
                self.meter_needle
            ], alignment=ft.alignment.center),
            width=self.meter_width, height=55, border=ft.border.all(1, ft.Colors.GREY_800), border_radius=5
        )
        
        settings_button = ft.IconButton(
            icon=ft.Icons.SETTINGS, 
            icon_color=ft.Colors.GREY_400, 
            on_click=self.toggle_settings_visibility
        )
        
        result_display_area = ft.Container(content=self.result_text, height=110, alignment=ft.alignment.center)

        top_panel = ft.Container(
            content=ft.Column([
                ft.Row([ft.Text("ピッチ解析", size=14, color=ft.Colors.GREY_400), settings_button], alignment="spaceBetween"),
                result_display_area,
                ft.Text("ANALOG TUNER METER", size=9, color=ft.Colors.GREY_600, weight="bold"), 
                meter_bg, 
                self.volume_bar, 
                self.settings_column
            ], horizontal_alignment="center"),
            padding=20, bgcolor=ft.Colors.GREY_900, border_radius=15
        )
        
        return ft.Column([
            top_panel, 
            ft.Divider(height=30), 
            ft.Row([ft.Text("チューニング選択", weight="bold"), self.tuning_dropdown], alignment="center"), 
            ft.Container(self.mode_switch, alignment=ft.alignment.center), 
            ft.Divider(),
            ft.Row([
                ft.Text("お手本音源", weight="bold"), 
                ft.IconButton(ft.Icons.LIBRARY_ADD_ROUNDED, on_click=lambda _: self.c.tuning_editor.show(), tooltip="カスタム登録")
            ], alignment="spaceBetween"),
            self.grid, 
            ft.Container(self.toggle_button, alignment=ft.alignment.center, padding=ft.padding.only(top=10, bottom=20))
        ])

    def toggle_settings_visibility(self, e):
        self.settings_column.visible = not self.settings_column.visible
        self.page.update()

    @property
    def page(self):
        return self.c.page