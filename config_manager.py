# v3.0
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
設定ファイル（config.ini）の読み書きを管理するモジュール。
v3.0: 保存イベントのログ出力を明確化しました。
"""

import configparser
import logging
import json
from pathlib import Path
from typing import Dict, List, Any

class ConfigManager:
    def __init__(self, config_file: str = "config.ini"):
        self.config_path = Path(config_file)
        self.config = configparser.ConfigParser()
        self._load_defaults()
        self.load()

    def _load_defaults(self):
        if "Tuner" not in self.config:
            self.config["Tuner"] = {
                "AmplitudeThreshold": "20.5",
                "CurrentTuning": "Standard",
                "HeadsetMode": "True"
            }
        
        if "Tunings" not in self.config:
            self.config["Tunings"] = {}
            standard = [
                ["1弦 (E4)", 329.63, "1弦.wav"],
                ["2弦 (B3)", 246.94, "2弦.wav"],
                ["3弦 (G3)", 196.00, "3弦.wav"],
                ["4弦 (D3)", 146.83, "4弦.wav"],
                ["5弦 (A2)", 110.00, "5弦.wav"],
                ["6弦 (E2)", 82.41, "6弦.wav"],
                ["7弦 (B1)", 61.74, "7弦.wav"]
            ]
            self.config["Tunings"]["Standard"] = json.dumps(standard, ensure_ascii=False)

    def load(self):
        if self.config_path.exists():
            try:
                self.config.read(self.config_path, encoding="utf-8")
            except Exception as e:
                logging.error(f"設定ファイルの読み込み失敗: {e}")
        else:
            self.save()

    def get_threshold(self) -> float:
        try: return self.config.getfloat("Tuner", "AmplitudeThreshold", fallback=20.5)
        except: return 20.5

    def set_threshold(self, value: float):
        self.config["Tuner"]["AmplitudeThreshold"] = f"{value:.1f}"
        self.save()

    def get_headset_mode(self) -> bool:
        return self.config.getboolean("Tuner", "HeadsetMode", fallback=True)

    def set_headset_mode(self, value: bool):
        self.config["Tuner"]["HeadsetMode"] = str(value)
        self.save()

    def get_current_tuning_name(self) -> str:
        return self.config.get("Tuner", "CurrentTuning", fallback="Standard")

    def set_current_tuning_name(self, name: str):
        self.config["Tuner"]["CurrentTuning"] = name
        self.save()

    def get_tuning_presets(self) -> Dict[str, List[List[Any]]]:
        presets = {}
        if "Tunings" in self.config:
            for name in self.config["Tunings"]:
                try: presets[name] = json.loads(self.config["Tunings"][name])
                except: continue
        return presets

    def save_tuning(self, name: str, data: List[List[Any]]):
        if "Tunings" not in self.config:
            self.config["Tunings"] = {}
        self.config["Tunings"][name] = json.dumps(data, ensure_ascii=False)
        self.save()
        logging.info(f"保存イベント: チューニング '{name}' を更新しました。")

    def save(self):
        """保存処理をログに記録します。"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                self.config.write(f)
            # 頻繁な保存はDEBUG、重要な変更の保存はINFOが望ましいですが、
            # ユーザーの要望により「保存が発生した部分」としてINFO出力します。
            logging.info(f"保存成功: {self.config_path.name}")
        except Exception as e:
            logging.error(f"保存失敗: {self.config_path.name} - {e}")