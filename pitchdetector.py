#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
マイク入力とピッチ検出（周波数分析）を管理するモジュール。
(★ 修正版: 音量レベルをUIに通知する機能を追加)
"""

import pyaudio
import numpy as np
import logging
import math
from typing import Callable, Optional

class PitchDetector:
    # ( ... チューニング定数 ... )
    RATE = 44100
    CHUNK = 2048 
    GUITAR_FREQUENCIES = {
        "6弦 (E2)": 82.41,
        "5弦 (A2)": 110.00,
        "4弦 (D3)": 146.83,
        "3弦 (G3)": 196.00,
        "2弦 (B3)": 246.94,
        "1弦 (E4)": 329.63,
    }
    MIN_FREQ = 75.0
    MAX_FREQ = 350.0
    TOLERANCE_CENTS = 50 
    YIN_THRESHOLD = 0.15
    

    # --- クラス実装 ---

    def __init__(self, 
                 ui_callback: Callable[[str, float], None], # (★修正: float(音量)も受け取る定義に変更)
                 threshold: float = 20.5):
        """
        PitchDetectorを初期化します。
        ui_callback: (結果テキスト, 音量0.0-1.0) を受け取る関数
        """
        self.pa: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.ui_callback = ui_callback
        
        # 閾値をインスタンス変数として保存
        self.AMPLITUDE_THRESHOLD_RMS = threshold
        
        self._is_running = False 

        # ( ... YIN関連の初期化 ... )
        self.min_period = int(self.RATE / self.MAX_FREQ)
        self.max_period = int(self.RATE / self.MIN_FREQ)
        self.yin_buffer_size = self.CHUNK * 2
        self.yin_buffer = np.zeros(self.yin_buffer_size, dtype=np.float32)
        self.diff_buffer = np.zeros(self.max_period, dtype=np.float32)
        self.cmndf_buffer = np.zeros(self.max_period, dtype=np.float32)
        
        logging.info("PitchDetector (YIN) が初期化されました。")
        logging.info(f"音量閾値: {self.AMPLITUDE_THRESHOLD_RMS}")


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
            logging.info("マイクストリームを開始しました。")
        except IOError as e:
            self._is_running = False 
            logging.error(f"マイクストリームの開始に失敗しました: {e}")
            self.ui_callback("エラー: マイク不可", 0.0)
        except Exception as e:
            self._is_running = False 
            logging.error(f"予期せぬエラー (start_stream): {e}")
            self.ui_callback(f"エラー: {e}", 0.0)

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        """
        PyAudioからのコールバック
        """
        if not self._is_running:
            return (None, pyaudio.paComplete) 

        try:
            data = np.frombuffer(in_data, dtype=np.int16)

            if data.size == 0:
                return (in_data, pyaudio.paContinue) 

            # RMS (二乗平均平方根) で音量を計算
            amplitude = np.sqrt(np.mean(data.astype(np.float64)**2))

            if np.isnan(amplitude):
                amplitude = 0.0 

            # (★追加) 音量を 0.0 ～ 1.0 に正規化してUIに送る準備
            # int16の最大値は 32768 なのでそれで割る
            normalized_volume = min(amplitude / 32768.0, 1.0)

            if amplitude < self.AMPLITUDE_THRESHOLD_RMS:
                # 閾値以下の場合は周波数検出しないが、音量（ノイズレベル）は送っても良い
                freq = 0.0
            else:
                freq = self._find_fundamental_frequency_yin(data)
            
            result_string = self._match_frequency(freq, 1.0)
            
            # (★修正) コールバックに音量も渡す
            self.ui_callback(result_string, normalized_volume)
            
        except Exception as e:
            logging.warning(f"コールバック処理中にエラー: {e}")
            
        return (in_data, pyaudio.paContinue)

    def _find_fundamental_frequency_yin(self, data: np.ndarray) -> float:
        # ( ... 変更なし ... )
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

    def _match_frequency(self, freq: float, amplitude: float) -> str:
        # ( ... 変更なし ... )
        if freq == 0.0:
            return "---"
        best_match_name = None
        min_diff_cents = float('inf')
        for string_name, base_freq in self.GUITAR_FREQUENCIES.items():
            diff_cents = 1200 * math.log2(freq / base_freq)
            if abs(diff_cents) < abs(min_diff_cents):
                min_diff_cents = diff_cents
                best_match_name = string_name
        if abs(min_diff_cents) <= self.TOLERANCE_CENTS:
            if abs(min_diff_cents) < 5:
                return f"{best_match_name}\n(OK: {min_diff_cents:+.1f} cent)"
            elif min_diff_cents > 0:
                return f"{best_match_name}\n(高い: {min_diff_cents:+.1f} cent)"
            else:
                return f"{best_match_name}\n(低い: {min_diff_cents:.1f} cent)"
        else:
            return "一致なし" 

    def stop_stream(self):
        # ( ... 変更なし ... )
        if not self._is_running:
            return 
        self._is_running = False
        try:
            if self.stream:
                if self.stream.is_active():
                    self.stream.stop_stream()
                self.stream.close()
                self.stream = None
        except Exception:
            pass
        try:
            if self.pa:
                self.pa.terminate()
                self.pa = None
        except Exception:
            pass