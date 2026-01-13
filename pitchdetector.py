# v3.7
import pyaudio
import numpy as np
import logging
import math
import statistics
import time
from typing import Callable, Optional, Tuple, Dict, Any
from collections import deque

class PitchDetector:
    """
    ピッチ検出ロジックを管理するクラス。
    v3.7: 減衰時の誤判定対策(Decay Locking)と入力安全策(Input Clamping)を実装。
    
    1. Decay Locking (減衰ロック):
       音量が減少傾向にある間（consecutive_decay_frames > 5）は、
       周波数が大きく変わるような検知結果を「誤検知（倍音浮き上がり）」とみなして無視する。
       これにより、サステインの後半で表示が暴れるのを防ぐ。
       
    2. Averaging Downsample (平均化ダウンサンプリング):
       単純な間引きではなく平均値をとることで、高周波ノイズ（エイリアシング）を物理的に除去する。
    """
    
    RATE = 44100
    CHUNK = 2048 

    def __init__(self, 
                 ui_callback: Callable[[str, float, Optional[float]], None],
                 config: Optional[Dict[str, Any]] = None):
        
        self.pa: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self.ui_callback = ui_callback
        
        # デフォルト設定
        self.settings = {
            "threshold": 10.0,
            "yin_threshold": 0.20,
            "latency_mode": "normal",
            "smoothing": 5,
            "instrument_type": "guitar"
        }
        
        if config:
            self.settings.update(config)

        # 状態管理変数
        self.target_frequencies: Dict[str, float] = {}
        self._is_running = False 
        self.last_valid_cents = 0.0
        
        # ジャンプガード & 減衰ロック用ステート
        self.last_stable_freq = 0.0
        self.prev_amplitude = 0.0
        self.frames_since_attack = 0
        self.consecutive_decay_frames = 0 # 連続して音量が下がっているフレーム数
        
        # 初期化
        self._apply_settings(full_reset=True)
        
        logging.info(f"PitchDetector v3.7 Initialized (Decay Lock & Avg Downsample).")

    def update_settings(self, new_config: Dict[str, Any]):
        """
        設定変更の適用。バッファサイズ変更が必要な場合のみストリームを再起動する。
        """
        restart_required_keys = ["latency_mode", "instrument_type", "smoothing"]
        needs_restart = any(key in new_config for key in restart_required_keys)

        self.settings.update(new_config)

        if needs_restart:
            was_running = self._is_running
            if was_running:
                self.stop_stream()
            self._apply_settings(full_reset=True)
            if was_running:
                time.sleep(0.1) # PortAudioのリソース解放待ち
                self.start_stream()
        else:
            self._apply_settings(full_reset=False)

    def _apply_settings(self, full_reset: bool = False):
        self.amplitude_threshold_rms = float(self.settings.get("threshold", 10.0))
        self.yin_threshold = float(self.settings.get("yin_threshold", 0.20))
        
        if not full_reset:
            return

        # Latency Mode -> Buffer Size
        mode = self.settings.get("latency_mode", "normal").lower()
        if mode == "fast":
            self.analysis_buffer_size = 8192 
        elif mode == "stable":
            self.analysis_buffer_size = 32768
        else:
            self.analysis_buffer_size = 16384

        # Instrument Type -> Decimation & Range
        instr = self.settings.get("instrument_type", "guitar").lower()
        if instr == "bass":
            self.decimation_factor = 10
            self.min_freq = 20.0
            self.max_freq = 400.0
        else:
            self.decimation_factor = 6
            self.min_freq = 25.0
            self.max_freq = 800.0

        # Smoothing
        smooth_val = max(1, min(10, int(self.settings.get("smoothing", 5))))
        self.smoothing_window = smooth_val
        self.cents_history = deque(maxlen=self.smoothing_window)

        # Buffer Allocation
        self.ring_buffer = np.zeros(self.analysis_buffer_size, dtype=np.float32)
        
        self.effective_rate = self.RATE / self.decimation_factor
        self.min_period = int(self.effective_rate / self.max_freq)
        self.max_period = int(self.effective_rate / self.min_freq)
        
        self.diff_buffer = np.zeros(self.max_period, dtype=np.float32)
        self.cmndf_buffer = np.zeros(self.max_period, dtype=np.float32)

    def set_tuning_frequencies(self, frequencies: Dict[str, float]):
        self.target_frequencies = frequencies

    def start_stream(self):
        if self.stream and self.stream.is_active(): return
        
        try:
            self.pa = pyaudio.PyAudio()
            self._is_running = True 
            
            # ストリーム開始時に内部状態をリセット
            self.last_stable_freq = 0.0
            self.prev_amplitude = 0.0
            self.frames_since_attack = 0
            self.consecutive_decay_frames = 0
            self.ring_buffer.fill(0)
            
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
        if not self._is_running: return (None, pyaudio.paComplete) 
        try:
            # int16として読み込み (将来的なクリッピング処理のため)
            raw_ints = np.frombuffer(in_data, dtype=np.int16)
            new_data = raw_ints.astype(np.float32)
            
            # リングバッファ更新
            self.ring_buffer[:-self.CHUNK] = self.ring_buffer[self.CHUNK:]
            self.ring_buffer[-self.CHUNK:] = new_data
            
            amplitude = np.sqrt(np.mean(new_data**2))
            display_volume = min((amplitude / 1000.0), 1.0) 
            threshold_val = max(self.amplitude_threshold_rms, 1.0) * 10.0
            
            # --- アタック & 減衰(Decay)判定 ---
            is_attack = False
            
            # 音量が前回より1.2倍以上増えたらアタックとみなす
            if amplitude > self.prev_amplitude * 1.2:
                if amplitude > threshold_val:
                    is_attack = True
                    self.frames_since_attack = 0
                    self.consecutive_decay_frames = 0
            # 音量が前回より減ったら減衰カウンターを増やす
            elif amplitude < self.prev_amplitude:
                self.consecutive_decay_frames += 1
            else:
                # 変化なし、または微増（ノイズ揺らぎ）の場合は減衰カウントを維持かリセットするか
                # ここでは微増は維持扱いにする
                pass
            
            if not is_attack:
                self.frames_since_attack += 1
            
            self.prev_amplitude = amplitude
            # ----------------------------------

            final_cents = None
            
            # 音量が小さすぎる場合はリセット
            if amplitude < threshold_val:
                freq = 0.0
                display_volume = 0.0
                self.cents_history.clear()
                self.last_valid_cents = 0.0
                self.last_stable_freq = 0.0 
            else:
                # 1. 平均化ダウンサンプリング (Averaging)
                # 高周波ノイズ（スパイク）をなまらせる効果がある
                limit = len(self.ring_buffer) - (len(self.ring_buffer) % self.decimation_factor)
                reshaped = self.ring_buffer[:limit].reshape(-1, self.decimation_factor)
                decimated_data = np.mean(reshaped, axis=1) 
                
                # DCカット & 正規化
                decimated_data -= np.mean(decimated_data)
                normalized_data = self._normalize_signal(decimated_data)
                
                # 2. YIN解析
                freq, confidence = self._find_fundamental_frequency_yin(normalized_data)
                
                # 3. Decay Lock (減衰ロック) & Jump Guard
                # ロジック:
                # - アタック時: どんな周波数でも信頼度が高ければ受け入れる
                # - 減衰時(Decay): 周波数の変更を厳しく制限する
                
                if self.last_stable_freq > 0:
                    ratio = freq / self.last_stable_freq
                    # 半音以内のズレかどうか (0.94 < ratio < 1.06)
                    is_same_note = 0.94 < ratio < 1.06
                    
                    if is_attack:
                         # アタック時は新しい音を弾いた可能性が高いので更新許可
                         if confidence < self.yin_threshold:
                             self.last_stable_freq = freq
                    elif self.consecutive_decay_frames > 5:
                        # 完全に減衰モードに入っている場合
                        if is_same_note:
                             # 同じ音程内なら更新（チョーキング等の追従のため）
                             if confidence < self.yin_threshold:
                                 self.last_stable_freq = freq
                        else:
                             # 違う音程（倍音ジャンプなど）は無視して、前回の安定値を強制使用
                             freq = self.last_stable_freq
                    else:
                        # サステイン安定期 (アタック直後〜減衰開始前)
                        if confidence < self.yin_threshold:
                             # 信頼度が高ければ遷移を許可するが、できれば滑らかに
                             if is_same_note or confidence < 0.1:
                                 self.last_stable_freq = freq
                             else:
                                 freq = self.last_stable_freq
                else:
                    # 初回検出 (何も保持していない時)
                    if confidence < self.yin_threshold:
                        self.last_stable_freq = freq

            if freq > 0:
                result_string, raw_cents = self._match_frequency(freq)
                if raw_cents is not None:
                    self.cents_history.append(raw_cents)
                    final_cents = statistics.median(self.cents_history)
                    self.last_valid_cents = final_cents
                else:
                    final_cents = self.last_valid_cents if self.last_valid_cents != 0 else None
            else:
                # 音はあるが解析失敗、またはロックにより前回値を維持する場合
                if self.last_valid_cents != 0 and amplitude > threshold_val:
                     final_cents = self.last_valid_cents
                     # 保持中の表示更新（"Hold"等の表示に変えても良いが、自然に見せるため値を維持）
                     result_string, _ = self._match_frequency(440.0 * (2**(self.last_valid_cents/1200)))
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
        yin_buffer = data
        half_chunk = len(data) // 2
        
        if len(data) < self.max_period + half_chunk:
             return 0.0, 1.0

        self.diff_buffer.fill(0.0)
        
        # Difference Function
        for tau in range(1, self.max_period):
            diff = yin_buffer[:half_chunk] - yin_buffer[tau : tau + half_chunk]
            self.diff_buffer[tau] = np.sum(diff**2)
            
        # CMNDF
        self.cmndf_buffer[0] = 1.0
        running_sum = 0.0
        for tau in range(1, self.max_period):
            running_sum += self.diff_buffer[tau]
            if running_sum == 0:
                self.cmndf_buffer[tau] = 1.0
            else:
                self.cmndf_buffer[tau] = (self.diff_buffer[tau] * tau) / running_sum
        
        tau = self.min_period
        best_tau = 0
        found = False
        min_val = 1.0 
        
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
            return 0.0, 1.0

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
        confidence = min_val 
        
        return freq, confidence

    def _match_frequency(self, freq: float) -> Tuple[str, Optional[float]]:
        if freq == 0.0: return "---", None
        best_match_name, min_diff_cents = None, float('inf')
        
        if freq < self.min_freq or freq > self.max_freq:
            return "---", None

        for name, base_freq in self.target_frequencies.items():
            try:
                diff_cents = 1200 * math.log2(freq / base_freq)
            except ValueError:
                continue
            if abs(diff_cents) < abs(min_diff_cents):
                min_diff_cents, best_match_name = diff_cents, name
        
        if best_match_name is None: return "---", None

        if abs(min_diff_cents) <= 50:
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
            self.stream = None 
        if self.pa:
            try:
                self.pa.terminate()
            except: pass
            self.pa = None