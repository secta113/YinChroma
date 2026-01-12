# v2.3
import pyaudio
import numpy as np
import logging
import math
from typing import Callable, Optional, Tuple, Dict
from collections import deque

class PitchDetector:
    """
    ピッチ検出ロジックを管理するクラス。
    v2.3: デバッグ用のマイク確認ログおよびデバイス一覧表示を削除。
    """
    RATE = 44100
    CHUNK = 4096 
    MIN_FREQ = 50.0 
    MAX_FREQ = 450.0
    TOLERANCE_CENTS = 50 
    SMOOTHING_WINDOW = 5

    def __init__(self, 
                 ui_callback: Callable[[str, float, Optional[float]], None],
                 threshold: float = 10.0):
        self.pa: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.ui_callback = ui_callback
        
        self.target_frequencies: Dict[str, float] = {}
        self.AMPLITUDE_THRESHOLD_RMS = threshold 
        self.yin_threshold = 0.15
        self._is_running = False 

        self.cents_history = deque(maxlen=self.SMOOTHING_WINDOW)
        self.min_period = int(self.RATE / self.MAX_FREQ)
        self.max_period = int(self.RATE / self.MIN_FREQ)
        
        self.window = np.hanning(self.CHUNK)
        self.yin_buffer = np.zeros(self.CHUNK, dtype=np.float32)
        self.diff_buffer = np.zeros(self.max_period, dtype=np.float32)
        self.cmndf_buffer = np.zeros(self.max_period, dtype=np.float32)
        
        logging.info("PitchDetector v2.3 初期化完了。")

    def set_threshold(self, value: float):
        self.AMPLITUDE_THRESHOLD_RMS = value

    def set_yin_threshold(self, value: float):
        self.yin_threshold = value

    def set_tuning_frequencies(self, frequencies: Dict[str, float]):
        self.target_frequencies = frequencies

    def start_stream(self):
        if self.stream and self.stream.is_active(): return
        try:
            self.pa = pyaudio.PyAudio()
            self._is_running = True 
            self.stream = self.pa.open(
                format=pyaudio.paInt16, channels=1, rate=self.RATE,
                input=True, frames_per_buffer=self.CHUNK, 
                stream_callback=self._pyaudio_callback
            )
            self.stream.start_stream()
            logging.info("マイク入力ストリームを開始しました。")
        except Exception as e:
            self._is_running = False 
            logging.error(f"マイク入力開始エラー: {e}")

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        if not self._is_running: return (None, pyaudio.paComplete) 
        try:
            raw_data = np.frombuffer(in_data, dtype=np.int16).astype(np.float64)
            amplitude = np.sqrt(np.mean(raw_data**2))
            
            # 音量ブースト (10倍) 判定
            boosted_volume = min((amplitude / 32768.0) * 10.0, 1.0)

            raw_data -= np.mean(raw_data)
            threshold_ratio = self.AMPLITUDE_THRESHOLD_RMS / 100.0

            cents = None
            if boosted_volume < threshold_ratio:
                freq = 0.0
                display_volume = 0.0
                self.cents_history.clear() 
            else:
                windowed_data = raw_data * self.window
                freq = self._find_fundamental_frequency_yin(windowed_data)
                display_volume = boosted_volume
            
            result_string, raw_cents = self._match_frequency(freq)
            
            if raw_cents is not None:
                self.cents_history.append(raw_cents)
                cents = sum(self.cents_history) / len(self.cents_history)
            else:
                cents = None

            self.ui_callback(result_string, display_volume, cents)
        except Exception as e:
            logging.warning(f"解析コールバックエラー: {e}")
        return (in_data, pyaudio.paContinue)

    def _find_fundamental_frequency_yin(self, data: np.ndarray) -> float:
        self.yin_buffer = data.astype(np.float32)
        half_chunk = self.CHUNK // 2
        self.diff_buffer.fill(0.0)
        for tau in range(1, self.max_period):
            diff = self.yin_buffer[:half_chunk] - self.yin_buffer[tau : tau + half_chunk]
            self.diff_buffer[tau] = np.sum(diff**2)
        self.cmndf_buffer[0] = 1.0
        running_sum = 0.0
        for tau in range(1, self.max_period):
            running_sum += self.diff_buffer[tau]
            self.cmndf_buffer[tau] = (self.diff_buffer[tau] * tau / running_sum) if running_sum != 0 else 1.0
        tau = self.min_period
        while tau < self.max_period:
            if self.cmndf_buffer[tau] < self.yin_threshold:
                while tau + 1 < self.max_period and self.cmndf_buffer[tau+1] < self.cmndf_buffer[tau]:
                    tau += 1
                period_offset = 0.0
                if 0 < tau < self.max_period - 1:
                    y1, y2, y3 = self.cmndf_buffer[tau-1:tau+2]
                    denom = y1 - (2 * y2) + y3
                    if abs(denom) > 1e-6:
                        period_offset = 0.5 * (y1 - y3) / denom
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
            return f"{best_match_name}\n({label}: {min_diff_cents:+.1f})", min_diff_cents
        
        direction = "高すぎる" if min_diff_cents > 0 else "低すぎる"
        return f"{best_match_name}?\n({direction})", min_diff_cents

    def stop_stream(self):
        self._is_running = False
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except: pass
        if self.pa:
            self.pa.terminate()