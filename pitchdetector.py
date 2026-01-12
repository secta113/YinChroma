# v1.4
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
マイク入力とピッチ検出（周波数分析）を管理するモジュール。
v1.4: UIコールバックにセント値を渡す機能を追加しました。
"""

import pyaudio
import numpy as np
import logging
import math
from typing import Callable, Optional, Tuple

class PitchDetector:
    RATE = 44100
    CHUNK = 2048 
    
    # 7弦ギター対応: B1を追加
    GUITAR_FREQUENCIES = {
        "7弦 (B1)": 61.74,
        "6弦 (E2)": 82.41,
        "5弦 (A2)": 110.00,
        "4弦 (D3)": 146.83,
        "3弦 (G3)": 196.00,
        "2弦 (B3)": 246.94,
        "1弦 (E4)": 329.63,
    }
    
    # B1(61.74Hz)を検知できるよう最小周波数を引き下げ
    MIN_FREQ = 55.0
    MAX_FREQ = 350.0
    TOLERANCE_CENTS = 50 
    YIN_THRESHOLD = 0.15

    def __init__(self, 
                 ui_callback: Callable[[str, float, Optional[float]], None], # (★v1.4修正: centsも受け取る定義に変更)
                 threshold: float = 20.5):
        self.pa: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.ui_callback = ui_callback
        
        self.AMPLITUDE_THRESHOLD_RMS = threshold
        self._is_running = False 

        self.min_period = int(self.RATE / self.MAX_FREQ)
        self.max_period = int(self.RATE / self.MIN_FREQ)
        self.yin_buffer_size = self.CHUNK * 2
        self.yin_buffer = np.zeros(self.yin_buffer_size, dtype=np.float32)
        self.diff_buffer = np.zeros(self.max_period, dtype=np.float32)
        self.cmndf_buffer = np.zeros(self.max_period, dtype=np.float32)
        
        logging.info(f"PitchDetector v1.4 (視覚化対応) 初期化。")

    def set_threshold(self, value: float):
        self.AMPLITUDE_THRESHOLD_RMS = value
        logging.debug(f"検出閾値を変更しました: {value}")

    def start_stream(self):
        if self.stream and self.stream.is_active():
            logging.warning("ストリームは既に開始されています。")
            return

        try:
            self.pa = pyaudio.PyAudio()
            self._is_running = True 
            
            self.stream = self.pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.RATE,
                input=True,
                frames_per_buffer=self.yin_buffer_size, 
                stream_callback=self._pyaudio_callback
            )
            self.stream.start_stream()
            logging.info("マイク入力を開始しました。")
        except Exception as e:
            self._is_running = False 
            logging.error(f"ストリーム開始エラー: {e}")
            self.ui_callback("エラー: マイク不可", 0.0, None)

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        if not self._is_running:
            return (None, pyaudio.paComplete) 

        try:
            data = np.frombuffer(in_data, dtype=np.int16)
            if data.size == 0:
                return (in_data, pyaudio.paContinue) 

            amplitude = np.sqrt(np.mean(data.astype(np.float64)**2))
            normalized_volume = min(amplitude / 32768.0, 1.0)

            cents = None
            if amplitude < self.AMPLITUDE_THRESHOLD_RMS:
                freq = 0.0
            else:
                freq = self._find_fundamental_frequency_yin(data)
            
            result_string, cents = self._match_frequency(freq, 1.0)
            self.ui_callback(result_string, normalized_volume, cents)
            
        except Exception as e:
            logging.warning(f"コールバック内エラー: {e}")
            
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
            if running_sum == 0:
                self.cmndf_buffer[tau] = 1.0
            else:
                self.cmndf_buffer[tau] = self.diff_buffer[tau] * tau / running_sum
        tau = self.min_period
        while tau < self.max_period:
            if self.cmndf_buffer[tau] < self.YIN_THRESHOLD:
                while tau + 1 < self.max_period and self.cmndf_buffer[tau + 1] < self.cmndf_buffer[tau]:
                    tau += 1
                period_offset = 0.0
                if tau > 0 and tau < self.max_period - 1:
                    y1 = self.cmndf_buffer[tau - 1]
                    y2 = self.cmndf_buffer[tau]
                    y3 = self.cmndf_buffer[tau + 1]
                    denominator = y1 - (2 * y2) + y3
                    if abs(denominator) > 1e-6:
                        period_offset = 0.5 * (y1 - y3) / denominator
                precise_period = tau + period_offset
                return self.RATE / precise_period
            tau += 1
        return 0.0

    def _match_frequency(self, freq: float, amplitude: float) -> Tuple[str, Optional[float]]:
        """
        周波数を解析し、表示用テキストとセント値を返します。
        """
        if freq == 0.0:
            return "---", None
            
        best_match_name = None
        min_diff_cents = float('inf')
        
        for string_name, base_freq in self.GUITAR_FREQUENCIES.items():
            diff_cents = 1200 * math.log2(freq / base_freq)
            if abs(diff_cents) < abs(min_diff_cents):
                min_diff_cents = diff_cents
                best_match_name = string_name
                
        if abs(min_diff_cents) <= self.TOLERANCE_CENTS:
            if abs(min_diff_cents) < 5:
                res = f"{best_match_name}\n(OK: {min_diff_cents:+.1f} cent)"
            elif min_diff_cents > 0:
                res = f"{best_match_name}\n(高い: {min_diff_cents:+.1f} cent)"
            else:
                res = f"{best_match_name}\n(低い: {min_diff_cents:.1f} cent)"
            return res, min_diff_cents
        else:
            return "一致なし", None

    def stop_stream(self):
        if not self._is_running:
            return 
        self._is_running = False
        try:
            if self.stream:
                self.stream.stop_stream()
                self.stream.close()
                self.stream = None
            if self.pa:
                self.pa.terminate()
                self.pa = None
        except Exception as e:
            logging.error(f"ストリーム停止エラー: {e}")