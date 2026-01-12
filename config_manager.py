# v1.2
import configparser
import logging
import json
from pathlib import Path
from typing import Dict, List, Any

class ConfigManager:
    """
    config.ini ファイルの読み書きを管理するクラス。
    セクションやキーが欠落していても初期値を返す堅牢な設計。
    """
    SEC_SETTINGS = "SETTINGS"
    SEC_TUNINGS = "TUNING_PRESETS"

    def __init__(self, config_path: str = "config.ini"):
        self.config_path = Path(config_path)
        self.config = configparser.ConfigParser()
        self._load_config()

    def _load_config(self):
        if self.config_path.exists():
            try:
                self.config.read(self.config_path, encoding="utf-8")
            except Exception as e:
                logging.error(f"Config read error: {e}")
        
        if not self.config.has_section(self.SEC_SETTINGS):
            self._create_default_config()

    def _create_default_config(self):
        if not self.config.has_section(self.SEC_SETTINGS):
            self.config.add_section(self.SEC_SETTINGS)
        
        self.config[self.SEC_SETTINGS] = {
            "threshold": "2.0",
            "yin_threshold": "0.15",
            "headset_mode": "False",
            "current_tuning": "Standard"
        }

        if not self.config.has_section(self.SEC_TUNINGS):
            self.config.add_section(self.SEC_TUNINGS)
            self.config[self.SEC_TUNINGS]["Standard"] = json.dumps([
                ["1弦 (E4)", 329.63, ""],
                ["2弦 (B3)", 246.94, ""],
                ["3弦 (G3)", 196.00, ""],
                ["4弦 (D3)", 146.83, ""],
                ["5弦 (A2)", 110.00, ""],
                ["6弦 (E2)", 82.41, ""]
            ])
        self._save_to_disk()

    def _save_to_disk(self):
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                self.config.write(f)
        except Exception as e:
            logging.error(f"Config save error: {e}")

    def _ensure_section(self, section: str):
        if not self.config.has_section(section):
            self.config.add_section(section)

    def get_threshold(self) -> float:
        return self.config.getfloat(self.SEC_SETTINGS, "threshold", fallback=2.0)

    def set_threshold(self, value: float):
        self._ensure_section(self.SEC_SETTINGS)
        self.config[self.SEC_SETTINGS]["threshold"] = str(value)
        self._save_to_disk()

    def get_yin_threshold(self) -> float:
        return self.config.getfloat(self.SEC_SETTINGS, "yin_threshold", fallback=0.15)

    def set_yin_threshold(self, value: float):
        self._ensure_section(self.SEC_SETTINGS)
        self.config[self.SEC_SETTINGS]["yin_threshold"] = f"{value:.2f}"
        self._save_to_disk()

    def get_headset_mode(self) -> bool:
        return self.config.getboolean(self.SEC_SETTINGS, "headset_mode", fallback=False)

    def set_headset_mode(self, value: bool):
        self._ensure_section(self.SEC_SETTINGS)
        self.config[self.SEC_SETTINGS]["headset_mode"] = str(value)
        self._save_to_disk()

    def get_current_tuning_name(self) -> str:
        return self.config.get(self.SEC_SETTINGS, "current_tuning", fallback="Standard")

    def set_current_tuning_name(self, name: str):
        self._ensure_section(self.SEC_SETTINGS)
        self.config[self.SEC_SETTINGS]["current_tuning"] = name
        self._save_to_disk()

    def get_tuning_presets(self) -> Dict[str, List[List[Any]]]:
        presets = {}
        if self.config.has_section(self.SEC_TUNINGS):
            for name, data_str in self.config.items(self.SEC_TUNINGS):
                try:
                    presets[name.capitalize()] = json.loads(data_str)
                except: continue
        return presets

    def save_tuning(self, name: str, data: List[List[Any]]):
        self._ensure_section(self.SEC_TUNINGS)
        self.config[self.SEC_TUNINGS][name] = json.dumps(data)
        self._save_to_disk()