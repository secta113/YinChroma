# v3.2
import pyaudio
import numpy as np
import logging
import math
import statistics
from typing import Callable, Optional, Tuple, Dict
from collections import deque

class PitchDetector:
    """
    ピッチ検出ロジックを管理するクラス。
    v3.2: 【最終安定版を目指すアーキテクチャ変更】
    
    1. リングバッファ (Sliding Window): 
       短いCHUNKごとではなく、過去のデータを連結した「長いバッファ」を解析対象とする。
       これにより、低音弦(60Hz周辺)の周期(約16ms)を10周期以上確保し、YINの精度を物理的に高める。
       
    2. ダウンサンプリング (Decimation):
       44.1kHz -> 約7.35kHz に間引いて解析。
       高周波ノイズを物理的に排除し、低音の解像度を相対的に向上させる。
       
    3. ピッチ・ロッキング (Pitch Locking):
       解析の「確信度(Confidence)」が低い場合は、無理に更新せず前回の値を維持する。
    """
    
    RATE = 44100
    
    # UI更新のためのコールバック周期 (短くて良い)
    CHUNK = 2048 
    
    # 解析に使う実質のバッファサイズ (長くする)
    # 44100Hzで16384サンプル = 約0.37秒分の音を常に監視する
    ANALYSIS_BUFFER_SIZE = 16384 
    
    # ダウンサンプリング係数 (6倍間引き -> 解析レート 7350Hz)
    DECIMATION_FACTOR = 6
    
    MIN_FREQ = 25.0 # Low-A/G 対応
    MAX_FREQ = 800.0 # ギターならこれ以上は不要
    
    TOLERANCE_CENTS = 50 
    SMOOTHING_WINDOW = 5

    def __init__(self, 
                 ui_callback: Callable[[str, float, Optional[float]], None],
                 threshold: float = 10.0):
        self.pa: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.ui_callback = ui_callback
        
        self.target_frequencies: Dict[str, float] = {}
        
        # 閾値関連
        self.AMPLITUDE_THRESHOLD_RMS = threshold 
        self.yin_threshold = 0.20 # 周期性の許容誤差
        
        self._is_running = False 

        # 履歴バッファ
        self.cents_history = deque(maxlen=self.SMOOTHING_WINDOW)
        
        # リングバッファ（生データ保持用）
        self.ring_buffer = np.zeros(self.ANALYSIS_BUFFER_SIZE, dtype=np.float32)
        
        # ロッキング機構用
        self.last_valid_cents = 0.0
        self.lock_counter = 0
        
        # YIN用計算定数 (ダウンサンプリング後のレートで計算)
        self.effective_rate = self.RATE / self.DECIMATION_FACTOR
        self.min_period = int(self.effective_rate / self.MAX_FREQ)
        self.max_period = int(self.effective_rate / self.MIN_FREQ)
        
        # 解析用バッファ（間引いた後のサイズで確保）
        decimated_size = self.ANALYSIS_BUFFER_SIZE // self.DECIMATION_FACTOR + 100
        self.diff_buffer = np.zeros(self.max_period, dtype=np.float32)
        self.cmndf_buffer = np.zeros(self.max_period, dtype=np.float32)
        
        logging.info(f"PitchDetector v3.2 Initialized.")
        logging.info(f"Effective Analysis Rate: {self.effective_rate:.1f}Hz")
        logging.info(f"Analysis Window: {self.ANALYSIS_BUFFER_SIZE/self.RATE:.3f} sec")

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
            logging.info("Audio stream started.")
        except Exception as e:
            self._is_running = False 
            logging.error(f"Stream start error: {e}")

    def _normalize_signal(self, data: np.ndarray) -> np.ndarray:
        max_val = np.max(np.abs(data))
        if max_val > 1e-6:
            return data / max_val
        return data

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        """
        ここでの処理:
        1. 入ってきた短い音声(CHUNK)をリングバッファに追加
        2. リングバッファ全体を使って解析（ダウンサンプリング -> YIN）
        """
        if not self._is_running: return (None, pyaudio.paComplete) 
        try:
            # 1. データの取り込み
            new_data = np.frombuffer(in_data, dtype=np.int16).astype(np.float32)
            
            # リングバッファをシフトして新しいデータを末尾に追加 (np.rollより高速なスライス操作)
            self.ring_buffer[:-self.CHUNK] = self.ring_buffer[self.CHUNK:]
            self.ring_buffer[-self.CHUNK:] = new_data
            
            # --- 解析フェーズ ---
            
            # 最新のCHUNK部分の音量で「入力があるか」を判定
            amplitude = np.sqrt(np.mean(new_data**2))
            display_volume = min((amplitude / 1000.0), 1.0) 
            
            threshold_val = max(self.AMPLITUDE_THRESHOLD_RMS, 1.0) * 10.0
            
            final_cents = None
            
            if amplitude < threshold_val:
                # 音が小さい時はリセット
                freq = 0.0
                display_volume = 0.0
                self.cents_history.clear()
                self.last_valid_cents = 0.0
            else:
                # 2. ダウンサンプリング (間引き)
                # リングバッファ全体（0.37秒分）を間引いて取得
                # これにより LPF効果 + 計算量削減 + 低音解像度向上 を同時に達成
                decimated_data = self.ring_buffer[::self.DECIMATION_FACTOR]
                
                # DCカット & 正規化
                decimated_data -= np.mean(decimated_data)
                normalized_data = self._normalize_signal(decimated_data)
                
                # 3. YIN解析 (間引いたデータを使用)
                freq, confidence = self._find_fundamental_frequency_yin(normalized_data)
                
                # 4. ピッチ・ロッキング (信頼度判定)
                if confidence < self.yin_threshold: 
                    # 信頼度が高い(値が小さい)場合のみ採用
                    pass
                else:
                    # 信頼度が低い場合は、前回値を維持する (Hysteresis)
                    if self.last_valid_cents != 0.0:
                        # 周波数を前回のcentsから逆算するのは面倒なので、
                        # ここでは周波数更新をスキップする扱いにする
                        freq = 0.0 
            
            # 結果のマッチング
            if freq > 0:
                result_string, raw_cents = self._match_frequency(freq)
                if raw_cents is not None:
                    self.cents_history.append(raw_cents)
                    final_cents = statistics.median(self.cents_history)
                    self.last_valid_cents = final_cents # ロック用に保存
                else:
                    final_cents = self.last_valid_cents if self.last_valid_cents != 0 else None
            else:
                # 解析失敗または信頼度不足のとき、直前の値を表示し続ける（チラつき防止）
                if self.last_valid_cents != 0 and amplitude > threshold_val:
                     final_cents = self.last_valid_cents
                     result_string = "Holding..." # デバッグ用表示(通常は前の表示維持でも可)
                     # 実際にはUIコールバック側で処理されるため、ここではNoneを返さず値を返す
                     # ただし match_frequency を呼んでないので文字列生成が必要
                     result_string, _ = self._match_frequency(440.0 * (2**(self.last_valid_cents/1200))) # 近似
                else:
                    final_cents = None
                    result_string = "---"

            self.ui_callback(result_string, display_volume, final_cents)
            
        except Exception as e:
            logging.warning(f"Callback Error: {e}")
            import traceback
            traceback.print_exc()
            
        return (in_data, pyaudio.paContinue)

    def _find_fundamental_frequency_yin(self, data: np.ndarray) -> Tuple[float, float]:
        """
        YINアルゴリズム (戻り値に confidence を追加)
        """
        yin_buffer = data
        half_chunk = len(data) // 2
        
        # 安全策: バッファサイズチェック
        if len(data) < self.max_period + half_chunk:
             return 0.0, 1.0

        self.diff_buffer.fill(0.0)
        
        # 1. 差分関数 (Difference Function)
        for tau in range(1, self.max_period):
            diff = yin_buffer[:half_chunk] - yin_buffer[tau : tau + half_chunk]
            self.diff_buffer[tau] = np.sum(diff**2)
            
        # 2. CMNDF
        self.cmndf_buffer[0] = 1.0
        running_sum = 0.0
        for tau in range(1, self.max_period):
            running_sum += self.diff_buffer[tau]
            if running_sum == 0:
                self.cmndf_buffer[tau] = 1.0
            else:
                self.cmndf_buffer[tau] = (self.diff_buffer[tau] * tau) / running_sum
        
        # 3. 絶対閾値探索
        tau = self.min_period
        best_tau = 0
        found = False
        min_val = 1.0 # 最小のCMNDF値 (これが小さいほど信頼度が高い)
        
        while tau < self.max_period:
            val = self.cmndf_buffer[tau]
            if val < min_val: min_val = val
            
            if val < self.yin_threshold:
                while tau + 1 < self.max_period and self.cmndf_buffer[tau+1] < self.cmndf_buffer[tau]:
                    tau += 1
                best_tau = tau
                found = True
                break
            tau += 1
            
        if not found:
            return 0.0, 1.0 # 検出なし, 信頼度最悪

        # 4. 放物線補間
        period = float(best_tau)
        if 0 < best_tau < self.max_period - 1:
            y1 = self.cmndf_buffer[best_tau - 1]
            y2 = self.cmndf_buffer[best_tau]
            y3 = self.cmndf_buffer[best_tau + 1]
            denom = y1 - (2 * y2) + y3
            if abs(denom) > 1e-6:
                period_offset = 0.5 * (y1 - y3) / denom
                period += period_offset
        
        freq = self.effective_rate / period
        confidence = min_val # YINの谷の深さを信頼度とする(0に近いほど完璧な周期)
        
        return freq, confidence

    def _match_frequency(self, freq: float) -> Tuple[str, Optional[float]]:
        if freq == 0.0: return "---", None
        best_match_name, min_diff_cents = None, float('inf')
        
        # 範囲外チェック
        if freq < self.MIN_FREQ or freq > self.MAX_FREQ:
            return "---", None

        for name, base_freq in self.target_frequencies.items():
            try:
                diff_cents = 1200 * math.log2(freq / base_freq)
            except ValueError:
                continue
            if abs(diff_cents) < abs(min_diff_cents):
                min_diff_cents, best_match_name = diff_cents, name
        
        if best_match_name is None: return "---", None

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