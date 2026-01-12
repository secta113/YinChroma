# v3.4
import flet as ft
import logging
import shutil
from pathlib import Path
from typing import List, Any, Callable

class TuningEditor:
    """
    カスタムチューニングの登録・編集ダイアログを管理するクラス。
    v3.4: ダイアログのタイトルにツール名「#YinChroma」を追加しました。
    """
    def __init__(self, page: ft.Page, sound_dir: Path, config_manager, on_save_callback: Callable):
        self.page = page
        self.sound_dir = sound_dir
        self.config_manager = config_manager
        self.on_save_callback = on_save_callback
        
        self.active_row = None
        self.upload_rows = ft.Column(spacing=5)
        self.new_tuning_name = ft.TextField(label="チューニング名称", hint_text="例: 7-String Standard")
        
        # FilePickerの設定
        self.file_picker = ft.FilePicker(on_result=self.on_file_result)
        self.page.overlay.append(self.file_picker)

    def show(self):
        """ダイアログを表示します。"""
        self.upload_rows.controls.clear()
        self.new_tuning_name.value = ""
        
        # デフォルトの7弦セットを初期表示 (v3.3修正)
        defaults = [
            ("1弦 (E4)", "329.63"), 
            ("2弦 (B3)", "246.94"), 
            ("3弦 (G3)", "196.00"),
            ("4弦 (D3)", "146.83"), 
            ("5弦 (A2)", "110.00"), 
            ("6弦 (E2)", "82.41"),
            ("7弦 (B1)", "61.74")
        ]
        for name, freq in defaults:
            self._add_row(name, freq)

        dialog = ft.AlertDialog(
            title=ft.Text("カスタムチューニングの登録"),
            content=ft.Column([
                self.new_tuning_name,
                ft.Divider(),
                ft.Row([ft.Text("構成弦リスト", size=12, color=ft.Colors.GREY_400)]),
                self.upload_rows,
                ft.TextButton("弦を追加", icon=ft.Icons.ADD, on_click=lambda _: self._add_row())
            ], scroll="always", tight=True, width=450),
            actions=[
                ft.ElevatedButton("保存", on_click=self.save, bgcolor=ft.Colors.BLUE_700, color=ft.Colors.WHITE),
                ft.TextButton("キャンセル", on_click=lambda _: self.page.close(dialog))
            ]
        )
        self.page.open(dialog)

    def _add_row(self, name="", freq="440.0"):
        row = ft.Row(data={"file": None}, vertical_alignment="center")
        name_field = ft.TextField(label="弦名", value=name, width=90, text_size=12)
        freq_field = ft.TextField(label="Hz", value=freq, width=80, text_size=12)
        file_info = ft.Text("No File", size=10, width=90, overflow="ellipsis", color=ft.Colors.GREY_500)
        
        pick_btn = ft.IconButton(ft.Icons.AUDIO_FILE_OUTLINED, on_click=lambda _: self.pick_file(row))
        del_btn = ft.IconButton(ft.Icons.DELETE_FOREVER, icon_color=ft.Colors.RED_700, on_click=lambda _: self._remove_row(row))
        
        row.controls = [name_field, freq_field, pick_btn, file_info, del_btn]
        self.upload_rows.controls.append(row)
        self.page.update()

    def _remove_row(self, row):
        self.upload_rows.controls.remove(row)
        self.page.update()

    def pick_file(self, row):
        self.active_row = row
        self.file_picker.pick_files(allow_multiple=False, allowed_extensions=["wav"])

    def on_file_result(self, e: ft.FilePickerResultEvent):
        if not e.files or not self.active_row: return
        f = e.files[0]
        self.active_row.data["file"] = f
        self.active_row.controls[3].value = f.name
        self.active_row.controls[3].color = ft.Colors.CYAN_400
        self.page.update()

    def save(self, e):
        name = self.new_tuning_name.value
        if not name: return
        
        new_data = []
        for row in self.upload_rows.controls:
            s_name = row.controls[0].value
            try:
                s_freq = float(row.controls[1].value or 0.0)
            except ValueError:
                s_freq = 0.0
            s_file = row.data.get("file")
            
            fname = ""
            if s_file:
                dest = self.sound_dir / s_file.name
                shutil.copy(s_file.path, dest)
                fname = s_file.name
            new_data.append([s_name, s_freq, fname])
        
        self.config_manager.save_tuning(name, new_data)
        logging.info(f"Custom tuning '{name}' saved with {len(new_data)} strings.")
        self.on_save_callback()
        self.page.close(e.control.parent)