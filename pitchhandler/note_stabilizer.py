# v4.1
import statistics
from typing import Tuple, Dict, Any
from collections import deque

class NoteStabilizer:
    """
    時系列データの状態遷移を管理するクラス。
    アタック検出、ディケイ（減衰）時の周波数ロック、誤検知フィルタリングを行う。
    """
    def __init__(self, config: Dict[str, Any]):
        self.update_config(config)
        self.reset()

    def update_config(self, config: Dict[str, Any]):
        self.yin_threshold = float(config.get("yin_threshold", 0.20))
        self.subharmonic_ratio = float(config.get("subharmonic_confidence_ratio", 0.9))
        self.octave_lookback_ratio = float(config.get("octave_lookback_ratio", 0.8))
        self.nearest_window = float(config.get("nearest_note_window", 300.0))
        
        smoothing = max(1, min(10, int(config.get("smoothing", 5))))
        self.cents_history = deque(maxlen=smoothing)

    def reset(self):
        self.last_stable_freq = 0.0
        self.prev_amplitude = 0.0
        self.frames_since_attack = 0
        self.consecutive_decay_frames = 0
        self.last_valid_cents = 0.0
        self.cents_history.clear()

    def process(self, raw_freq: float, confidence: float, amplitude: float, threshold_rms: float) -> Tuple[float, bool]:
        """
        現在のフレーム情報を受け取り、安定化された周波数を返す。
        戻り値: (stabilized_freq, is_valid_signal)
        """
        # --- アタック/ディケイ判定 ---
        threshold_val = max(threshold_rms, 1.0) * 10.0
        is_attack = False
        
        if amplitude > self.prev_amplitude * 1.2:
            if amplitude > threshold_val:
                is_attack = True
                self.frames_since_attack = 0
                self.consecutive_decay_frames = 0
        elif amplitude < self.prev_amplitude:
            self.consecutive_decay_frames += 1
        
        if not is_attack:
            self.frames_since_attack += 1
        
        self.prev_amplitude = amplitude

        # --- 信号が弱すぎる場合 ---
        if amplitude < threshold_val:
            self.last_stable_freq = 0.0
            self.cents_history.clear()
            self.last_valid_cents = 0.0
            return 0.0, False

        # --- 周波数安定化ロジック (ジャンプガード) ---
        result_freq = 0.0
        
        if raw_freq > 0:
            if self.last_stable_freq > 0:
                ratio = raw_freq / self.last_stable_freq
                is_same_note = 0.94 < ratio < 1.06
                
                if is_attack:
                     if confidence < self.yin_threshold:
                         self.last_stable_freq = raw_freq
                elif self.consecutive_decay_frames > 5:
                    if is_same_note:
                         if confidence < self.yin_threshold:
                             self.last_stable_freq = raw_freq
                    else:
                         raw_freq = self.last_stable_freq
                else:
                    if confidence < self.yin_threshold:
                         if is_same_note or confidence < 0.1:
                             self.last_stable_freq = raw_freq
                         else:
                             raw_freq = self.last_stable_freq
            else:
                if confidence < self.yin_threshold:
                    self.last_stable_freq = raw_freq
            
            result_freq = self.last_stable_freq
            
        return result_freq, (result_freq > 0)

    def smooth_cents(self, cents: float) -> float:
        """セント値の移動平均フィルタ"""
        self.cents_history.append(cents)
        val = statistics.median(self.cents_history)
        self.last_valid_cents = val
        return val