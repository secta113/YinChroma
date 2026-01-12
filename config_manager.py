# v1.1
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
設定ファイル（config.ini）の読み書きを管理するモジュール。
"""

import configparser
import logging
from pathlib import Path

class ConfigManager:
    """
    アプリケーションの設定を保持・更新・永続化するクラス。
    """

    def __init__(self, config_file: str = "config.ini"):
        self.config_path = Path(config_file)
        self.config = configparser.ConfigParser()
        self._load_defaults()
        self.load()

    def _load_defaults(self):
        """デフォルト値を設定します。"""
        if "Tuner" not in self.config:
            self.config["Tuner"] = {
                "AmplitudeThreshold": "20.5"
            }

    def load(self):
        """ファイルから設定を読み込みます。"""
        if self.config_path.exists():
            try:
                self.config.read(self.config_path, encoding="utf-8")
                logging.info(f"設定ファイルを読み込みました: {self.config_path}")
            except Exception as e:
                logging.error(f"設定ファイルの読み込みに失敗しました: {e}")
        else:
            logging.info("設定ファイルが見つかりません。デフォルト値を使用します。")
            self.save()

    def get_threshold(self) -> float:
        """振幅閾値を取得します。"""
        try:
            return self.config.getfloat("Tuner", "AmplitudeThreshold", fallback=20.5)
        except ValueError:
            return 20.5

    def set_threshold(self, value: float):
        """振幅閾値を更新し、ファイルに保存します。"""
        if "Tuner" not in self.config:
            self.config["Tuner"] = {}
        self.config["Tuner"]["AmplitudeThreshold"] = f"{value:.1f}"
        self.save()

    def save(self):
        """現在の設定をファイルに書き出します。"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                self.config.write(f)
            logging.debug("設定を保存しました。")
        except Exception as e:
            logging.error(f"設定の保存に失敗しました: {e}")