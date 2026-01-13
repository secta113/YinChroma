# v1.3
import configparser
import logging
import json
from pathlib import Path
from typing import Dict, List, Any

class ConfigManager:
    """
    config.ini ファイルの読み書きを管理するクラス。
    v1.3: PitchDetector v3.3対応（レイテンシ、スムージング、楽器タイプ）の設定項目を追加。
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
        
        # v3.3対応のデフォルト値
        self.config[self.SEC_SETTINGS] = {
            "threshold": "2.0",
            "yin_threshold": "0.20",
            "headset_mode": "False",
            "current_tuning": "Standard",
            "latency_mode": "normal",
            "smoothing": "5",
            "instrument_type": "guitar"
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

    # --- Basic Settings ---
    def get_threshold(self) -> float:
        return self.config.getfloat(self.SEC_SETTINGS, "threshold", fallback=2.0)

    def set_threshold(self, value: float):
        self._ensure_section(self.SEC_SETTINGS)
        self.config[self.SEC_SETTINGS]["threshold"] = str(value)
        self._save_to_disk()

    def get_yin_threshold(self) -> float:
        return self.config.getfloat(self.SEC_SETTINGS, "yin_threshold", fallback=0.20)

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

    # --- Advanced Settings (v1.3) ---
    def get_latency_mode(self) -> str:
        return self.config.get(self.SEC_SETTINGS, "latency_mode", fallback="normal")

    def set_latency_mode(self, mode: str):
        self._ensure_section(self.SEC_SETTINGS)
        self.config[self.SEC_SETTINGS]["latency_mode"] = mode
        self._save_to_disk()

    def get_smoothing(self) -> int:
        return self.config.getint(self.SEC_SETTINGS, "smoothing", fallback=5)

    def set_smoothing(self, value: int):
        self._ensure_section(self.SEC_SETTINGS)
        self.config[self.SEC_SETTINGS]["smoothing"] = str(value)
        self._save_to_disk()

    def get_instrument_type(self) -> str:
        return self.config.get(self.SEC_SETTINGS, "instrument_type", fallback="guitar")

    def set_instrument_type(self, value: str):
        self._ensure_section(self.SEC_SETTINGS)
        self.config[self.SEC_SETTINGS]["instrument_type"] = value
        self._save_to_disk()

    # --- Tuning Presets ---
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
    
    def get_all_settings_dict(self) -> Dict[str, Any]:
        """PitchDetectorへ渡すための全設定辞書を作成"""
        return {
            "threshold": self.get_threshold(),
            "yin_threshold": self.get_yin_threshold(),
            "latency_mode": self.get_latency_mode(),
            "smoothing": self.get_smoothing(),
            "instrument_type": self.get_instrument_type()
        }