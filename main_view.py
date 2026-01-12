# v5.5
import flet as ft
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from main_controller import MainController

class MainView:
    """
    メイン画面のレイアウトとUIコンポーネントの定義を行うクラス。
    v5.5: メーターを0-110ユニットで設計し、目盛り(10-100)を内側に配置して見切れを防止。
    """
    def __init__(self, controller: "MainController"):
        self.c = controller
        
        # --- UIコンポーネントの定義 ---
        self.result_text = ft.Text(
            value="---", size=36, weight="bold", 
            color=ft.Colors.CYAN_200, text_align=ft.TextAlign.CENTER
        )
        
        # メーターの設計定数
        # 物理幅 385px / 110ユニット = 1ユニット当たり 3.5px
        self.unit_to_px = 3.5
        self.total_units = 110
        self.meter_width_px = self.total_units * self.unit_to_px # 385px
        
        # 針の初期位置（中央 = 55ユニット目）
        self.meter_needle = ft.Container(
            width=4, height=35, bgcolor=ft.Colors.ORANGE_400, border_radius=2, 
            left=(55 * self.unit_to_px) - 2,
            bottom=0,
            animate_position=ft.Animation(200, ft.AnimationCurve.EASE_OUT_CUBIC)
        )
        
        # 音量バーもメーターの物理幅に合わせる
        self.volume_bar = ft.ProgressBar(
            width=self.meter_width_px, 
            value=0, 
            color=ft.Colors.GREEN_400
        )
        
        self.tuning_dropdown = ft.Dropdown(width=200, on_change=self.c.on_tuning_select)
        self.grid = ft.GridView(
            expand=True, runs_count=3, child_aspect_ratio=2.2, spacing=8, run_spacing=8
        )
        
        self.mode_switch = ft.Switch(
            label="ヘッドセットモード (再生中も判定)", 
            value=self.c.config_manager.get_headset_mode(), 
            active_color=ft.Colors.TEAL_400, 
            on_change=self.c.on_headset_mode_change
        )
        
        self.toggle_button = ft.ElevatedButton(
            text="ループ再生", icon=ft.Icons.PLAY_CIRCLE_FILLED, 
            on_click=self.c.toggle_play_click, width=200, height=50, 
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=10), bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE)
        )

        # 設定パネル
        current_threshold = self.c.config_manager.get_threshold()
        slider_max = 100.0
        safe_threshold = min(current_threshold, slider_max)
        
        self.threshold_value_text = ft.Text(f"入力音量しきい値: {safe_threshold:.1f}%", size=12)
        self.threshold_slider = ft.Slider(
            min=0, max=slider_max, value=safe_threshold, divisions=100, label="{value}%",
            on_change=self.c.on_threshold_change, on_change_end=self.c.on_threshold_change_end
        )

        current_yin = self.c.config_manager.get_yin_threshold()
        self.yin_value_text = ft.Text(f"ピッチ検出感度: {current_yin:.2f}", size=12)
        self.yin_slider = ft.Slider(
            min=0.05, max=0.40, value=current_yin, divisions=35, 
            on_change=self.c.on_yin_change, on_change_end=self.c.on_yin_change_end
        )

        self.settings_column = ft.Column(
            [
                ft.Divider(height=20, color=ft.Colors.GREY_700), 
                self.threshold_value_text, self.threshold_slider,
                ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                self.yin_value_text, self.yin_slider,
                ft.Text("(反応が悪い時は感度を右へ上げてください)", size=10, color=ft.Colors.GREY_500)
            ], 
            visible=False, horizontal_alignment="center"
        )

    def build(self):
        # 目盛り（Ticks）の生成
        # -50cent(10unit) 〜 +50cent(100unit) の範囲で描画
        ticks = []
        for i in range(-50, 51, 10): 
            # ユニット位置: 10 + (i + 50) * 0.9
            unit_pos = 10 + ((i + 50) * 0.9)
            pixel_pos = unit_pos * self.unit_to_px
            is_main = (i % 50 == 0) or (i == 0)
            
            # 目盛り線
            ticks.append(
                ft.Container(
                    width=2 if is_main else 1,
                    height=12 if is_main else 6,
                    bgcolor=ft.Colors.GREY_700,
                    left=pixel_pos - (1 if is_main else 0.5),
                    top=5
                )
            )
            # 数値ラベル (-50, 0, 50)
            if is_main:
                ticks.append(
                    ft.Text(
                        str(i), size=9, color=ft.Colors.GREY_600,
                        left=pixel_pos - 15, top=18, width=30, text_align="center"
                    )
                )

        # OK ゾーン (中心 55ユニットから左右 4.5ユニット分 = 計10cent)
        ok_zone_width_px = 9 * self.unit_to_px
        ok_zone_left = (55 - 4.5) * self.unit_to_px

        meter_bg = ft.Container(
            content=ft.Stack([
                # 黒い背景バー（全体 110ユニット分）
                ft.Container(
                    width=self.meter_width_px, height=50, 
                    bgcolor=ft.Colors.BLACK, border_radius=5
                ),
                # OK ゾーン
                ft.Container(
                    width=ok_zone_width_px, height=30, 
                    bgcolor=ft.Colors.with_opacity(0.15, ft.Colors.GREEN_400), 
                    left=ok_zone_left, 
                    bottom=0, border_radius=2
                ),
                *ticks,
                self.meter_needle
            ], width=self.meter_width_px, height=50),
            width=self.meter_width_px,
            height=60, 
            border=ft.border.all(1, ft.Colors.GREY_800), 
            border_radius=5
        )
        
        top_panel = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Text("ピッチ解析", size=14, color=ft.Colors.GREY_400),
                    ft.IconButton(ft.Icons.SETTINGS, on_click=self.toggle_settings_visibility)
                ], alignment="spaceBetween"),
                ft.Container(content=self.result_text, height=110, alignment=ft.alignment.center),
                meter_bg, 
                self.volume_bar,
                self.settings_column
            ], horizontal_alignment="center"),
            padding=20, bgcolor=ft.Colors.GREY_900, border_radius=15
        )
        
        return ft.Column([
            top_panel, 
            ft.Divider(height=20), 
            ft.Row([ft.Text("チューニング", weight="bold"), self.tuning_dropdown], alignment="center"), 
            ft.Container(self.mode_switch, alignment=ft.alignment.center),
            ft.Divider(),
            ft.Row([ft.Text("お手本音源", weight="bold"), 
                    ft.IconButton(ft.Icons.LIBRARY_ADD_ROUNDED, on_click=lambda _: self.c.tuning_editor.show())], alignment="spaceBetween"),
            self.grid, 
            ft.Container(self.toggle_button, alignment=ft.alignment.center, padding=10)
        ], expand=True)

    def toggle_settings_visibility(self, e):
        self.settings_column.visible = not self.settings_column.visible
        self.page.update()

    @property
    def page(self): return self.c.page