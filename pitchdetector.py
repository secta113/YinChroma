# v1.6
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
マイク入力とピッチ検出（周波数分析）を管理するモジュール。
v1.6: チューニングセットの動的変更に対応しました。
"""

import pyaudio
import numpy as np
import logging
import math
from typing import Callable, Optional, Tuple, Dict

class PitchDetector:
    RATE = 44100
    CHUNK = 2048 
    
    MIN_FREQ = 50.0 # より低いチューニングに対応するため少し拡張
    MAX_FREQ = 400.0
    TOLERANCE_CENTS = 50 
    YIN_THRESHOLD = 0.15

    def __init__(self, 
                 ui_callback: Callable[[str, float, Optional[float]], None],
                 threshold: float = 20.5):
        self.pa: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.ui_callback = ui_callback
        
        # 現在のターゲット周波数辞書
        self.target_frequencies: Dict[str, float] = {}
        
        self.AMPLITUDE_THRESHOLD_RMS = threshold
        self._is_running = False 

        self.min_period = int(self.RATE / self.MAX_FREQ)
        self.max_period = int(self.RATE / self.MIN_FREQ)
        self.yin_buffer = np.zeros(self.CHUNK * 2, dtype=np.float32)
        self.diff_buffer = np.zeros(self.max_period, dtype=np.float32)
        self.cmndf_buffer = np.zeros(self.max_period, dtype=np.float32)
        
        logging.info("PitchDetector v1.6 初期化完了。")

    def set_threshold(self, value: float):
        self.AMPLITUDE_THRESHOLD_RMS = value

    def set_tuning_frequencies(self, frequencies: Dict[str, float]):
        """検出対象の周波数セットを更新します。"""
        self.target_frequencies = frequencies
        logging.info(f"検出ターゲットを更新しました: {list(frequencies.keys())}")

    def start_stream(self):
        if self.stream and self.stream.is_active(): return
        try:
            self.pa = pyaudio.PyAudio()
            self._is_running = True 
            self.stream = self.pa.open(
                format=pyaudio.paInt16, channels=1, rate=self.RATE,
                input=True, frames_per_buffer=self.CHUNK * 2, 
                stream_callback=self._pyaudio_callback
            )
            self.stream.start_stream()
        except Exception as e:
            self._is_running = False 
            logging.error(f"ストリーム開始エラー: {e}")
            self.ui_callback("エラー: マイク不可", 0.0, None)

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        if not self._is_running: return (None, pyaudio.paComplete) 
        try:
            data = np.frombuffer(in_data, dtype=np.int16)
            amplitude = np.sqrt(np.mean(data.astype(np.float64)**2))
            normalized_volume = min(amplitude / 32768.0, 1.0)

            cents = None
            if amplitude < self.AMPLITUDE_THRESHOLD_RMS:
                freq = 0.0
            else:
                freq = self._find_fundamental_frequency_yin(data)
            
            result_string, cents = self._match_frequency(freq)
            self.ui_callback(result_string, normalized_volume, cents)
        except Exception as e:
            logging.warning(f"コールバックエラー: {e}")
        return (in_data, pyaudio.paContinue)

    def _find_fundamental_frequency_yin(self, data: np.ndarray) -> float:
        self.yin_buffer = data.astype(np.float32)
        self.diff_buffer[0] = 0.0
        for tau in range(1, self.max_period):
            diff = self.yin_buffer[:self.CHUNK] - self.yin_buffer[tau : tau + self.CHUNK]
            self.diff_buffer[tau] = np.sum(diff**2)
        self.cmndf_buffer[0] = 1.0
        running_sum = 0.0
        for tau in range(1, self.max_period):
            running_sum += self.diff_buffer[tau]
            self.cmndf_buffer[tau] = (self.diff_buffer[tau] * tau / running_sum) if running_sum != 0 else 1.0
        
        tau = self.min_period
        while tau < self.max_period:
            if self.cmndf_buffer[tau] < self.YIN_THRESHOLD:
                while tau + 1 < self.max_period and self.cmndf_buffer[tau+1] < self.cmndf_buffer[tau]:
                    tau += 1
                period_offset = 0.0
                if 0 < tau < self.max_period - 1:
                    y1, y2, y3 = self.cmndf_buffer[tau-1:tau+2]
                    denom = y1 - (2 * y2) + y3
                    if abs(denom) > 1e-6: period_offset = 0.5 * (y1 - y3) / denom
                return self.RATE / (tau + period_offset)
            tau += 1
        return 0.0

    def _match_frequency(self, freq: float) -> Tuple[str, Optional[float]]:
        if freq == 0.0: return "---", None
        best_match_name, min_diff_cents = None, float('inf')
        
        for name, base_freq in self.target_frequencies.items():
            diff_cents = 1200 * math.log2(freq / base_freq)
            if abs(diff_cents) < abs(min_diff_cents):
                min_diff_cents, best_match_name = diff_cents, name
                
        if abs(min_diff_cents) <= self.TOLERANCE_CENTS:
            label = "OK" if abs(min_diff_cents) < 5 else ("高い" if min_diff_cents > 0 else "低い")
            return f"{best_match_name}\n({label}: {min_diff_cents:+.1f} cent)", min_diff_cents
        return "一致なし", None

    def stop_stream(self):
        self._is_running = False
        if self.stream: self.stream.close()
        if self.pa: self.pa.terminate()