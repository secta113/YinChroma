# v5.5
import numpy as np
import math
import logging
from typing import Optional, Tuple, Dict, Any

try:
    from yin_processor import YinProcessor
    from note_stabilizer import NoteStabilizer
except ImportError:
    logging.error("Required modules (yin_processor.py, note_stabilizer.py) not found.")
    raise

class PitchAnalyzer:
    """
    ピッチ解析のオーケストレーター (v5.5: 高精度モード対応版)。
    
    変更点:
    - 設定 `high_quality` が True の場合、High Band のデシメーションを 1 (44.1kHz Full) に設定。
      これにより計算負荷は倍増するが、補間誤差を最小限に抑え、高音域の追従性を最大化する。
    """
    RATE = 44100

    def __init__(self, config: Dict[str, Any]):
        self.settings = config
        
        self.stabilizer: NoteStabilizer = NoteStabilizer(self.settings)
        self.target_frequencies: Dict[str, float] = {}

        # --- Dual Processors State ---
        self.proc_low: Optional[YinProcessor] = None
        self.buf_low = np.array([], dtype=np.float32)
        self.ptr_low = 0
        self.rem_low = np.array([], dtype=np.float32)
        self.dec_low = 8 # Default
        
        self.proc_high: Optional[YinProcessor] = None
        self.buf_high = np.array([], dtype=np.float32)
        self.ptr_high = 0
        self.rem_high = np.array([], dtype=np.float32)
        self.dec_high = 2 # Default

        self.apply_settings(full_reset=True)

    def set_tuning_frequencies(self, frequencies: Dict[str, float]):
        self.target_frequencies = frequencies

    def update_settings(self, new_config: Dict[str, Any]) -> bool:
        # high_quality の切り替えもストリーム再起動（バッファ再構築）が必要
        restart_required_keys = ["latency_mode", "instrument_type", "high_quality"]
        needs_restart = any(key in new_config for key in restart_required_keys)

        self.settings.update(new_config)
        self.stabilizer.update_config(self.settings)

        if needs_restart:
            self.apply_settings(full_reset=True)
        else:
            self.apply_settings(full_reset=False)
            
        return needs_restart

    def apply_settings(self, full_reset: bool = False):
        if not full_reset: return

        instr = self.settings.get("instrument_type", "guitar").lower()
        
        # High Quality Mode 設定の取得
        # config.ini から文字列で来る場合と、プログラムからboolで来る場合を考慮
        hq_val = self.settings.get("high_quality", False)
        is_high_quality = (str(hq_val).lower() == "true") if isinstance(hq_val, (str, bool)) else False

        # 楽器タイプに応じて帯域設定を微調整
        if instr == "bass":
            # Bass: Low重視
            self.dec_low = 10   # 4.4kHz
            # Bassの高音域はそれほど高くないので、HQモードでも x2 程度で十分かもしれないが
            # 一貫性のために x1 を許容する設計にしておく
            self.dec_high = 2 if is_high_quality else 4
            
            low_range = (20.0, 300.0)
            high_range = (100.0, 600.0)
        else:
            # Guitar: 標準的なハイブリッド構成
            self.dec_low = 8    # 5.5kHz
            
            # High Quality Mode: 間引きなし (44.1kHz)
            # Standard Mode: 間引き x2 (22.05kHz)
            self.dec_high = 1 if is_high_quality else 2
            
            low_range = (30.0, 400.0)
            high_range = (200.0, 1200.0)

        # バッファサイズ計算
        mode = self.settings.get("latency_mode", "normal").lower()
        base_samples = {"fast": 8192, "stable": 32768}.get(mode, 16384)

        # Low Band Setup
        size_low = int(base_samples / self.dec_low)
        self.buf_low = np.zeros(size_low * 2, dtype=np.float32)
        self.ptr_low = 0
        self.proc_low = YinProcessor(
            sample_rate=self.RATE / self.dec_low,
            min_freq=low_range[0], max_freq=low_range[1],
            threshold=float(self.settings.get("yin_threshold", 0.20))
        )

        # High Band Setup
        size_high = int(base_samples / self.dec_high)
        self.buf_high = np.zeros(size_high * 2, dtype=np.float32)
        self.ptr_high = 0
        self.proc_high = YinProcessor(
            sample_rate=self.RATE / self.dec_high,
            min_freq=high_range[0], max_freq=high_range[1],
            threshold=float(self.settings.get("yin_threshold", 0.20))
        )
        
        self.rem_low = np.array([], dtype=np.float32)
        self.rem_high = np.array([], dtype=np.float32)
        self.stabilizer.reset()

        # デバッグログ (本来はloggingを使うべきだが簡易的に)
        # print(f"[PitchAnalyzer] Settings Applied. Instrument: {instr}, HQ: {is_high_quality}, Rate(H): {self.RATE/self.dec_high}Hz")

    def reset_state(self):
        self.stabilizer.reset()
        if len(self.buf_low) > 0: self.buf_low.fill(0)
        if len(self.buf_high) > 0: self.buf_high.fill(0)
        self.ptr_low = 0
        self.ptr_high = 0
        self.rem_low = np.array([], dtype=np.float32)
        self.rem_high = np.array([], dtype=np.float32)

    def process(self, raw_input_bytes: bytes) -> Tuple[str, float, Optional[float]]:
        # 1. データ変換 & 振幅計算
        raw_ints = np.frombuffer(raw_input_bytes, dtype=np.int16)
        new_data = raw_ints.astype(np.float32)
        
        rms_amplitude = np.sqrt(np.mean(new_data**2))
        display_volume = min((rms_amplitude / 1000.0), 1.0)

        # 2. 並列処理実行 (Low & High)
        
        # --- Low Band ---
        data_L, self.rem_low, self.ptr_low = self._update_buffer(
            new_data, self.rem_low, self.buf_low, self.ptr_low, self.dec_low
        )
        freq_L, conf_L = self._analyze(data_L, self.proc_low)

        # --- High Band ---
        data_H, self.rem_high, self.ptr_high = self._update_buffer(
            new_data, self.rem_high, self.buf_high, self.ptr_high, self.dec_high
        )
        freq_H, conf_H = self._analyze(data_H, self.proc_high)

        # 3. 結果の統合 (Merge Logic)
        threshold = float(self.settings.get("yin_threshold", 0.20))
        valid_L = (conf_L < threshold) and (freq_L > 0)
        valid_H = (conf_H < threshold) and (freq_H > 0)
        
        raw_freq = 0.0
        confidence = 1.0

        if valid_L and valid_H:
            # High Qualityモードの場合、高域の信頼度がさらに高まるはずなので
            # クロスオーバー周波数を少しアグレッシブに設定しても良いが、
            # 安全のため既存ロジックを維持
            if freq_H > 350.0: 
                raw_freq = freq_H
                confidence = conf_H
            elif freq_L < 150.0:
                raw_freq = freq_L
                confidence = conf_L
            else:
                if conf_H <= conf_L:
                    raw_freq = freq_H
                    confidence = conf_H
                else:
                    raw_freq = freq_L
                    confidence = conf_L
                    
        elif valid_H:
            raw_freq = freq_H
            confidence = conf_H
        elif valid_L:
            raw_freq = freq_L
            confidence = conf_L

        # 4. 安定化処理
        threshold_rms = float(self.settings.get("threshold", 10.0))
        stable_freq, is_valid = self.stabilizer.process(
            raw_freq, confidence, rms_amplitude, threshold_rms
        )

        # 5. 音名マッチング
        final_cents = None
        result_string = "---"

        if is_valid and stable_freq > 0:
            match_result, diff_cents = self._match_frequency(stable_freq)
            if match_result != "---":
                final_cents = self.stabilizer.smooth_cents(diff_cents)
                result_string = match_result
        else:
            if self.stabilizer.last_valid_cents != 0 and rms_amplitude > (threshold_rms * 10):
                 final_cents = self.stabilizer.last_valid_cents
                 base_440 = 440.0 * (2**(final_cents/1200))
                 res, _ = self._match_frequency(base_440)
                 if res != "---":
                     result_string = res

        return result_string, display_volume, final_cents

    def _update_buffer(self, new_data, remainder, buffer, ptr, dec_factor):
        """共通のバッファ更新ロジック (間引き + ダブルバッファリング)"""
        if len(remainder) > 0:
            combined = np.concatenate((remainder, new_data))
        else:
            combined = new_data
            
        num_blocks = len(combined) // dec_factor
        
        if num_blocks > 0:
            process_len = num_blocks * dec_factor
            to_process = combined[:process_len]
            new_rem = combined[process_len:]
            
            # 間引き (平均)
            # dec_factor=1 の場合、meanをとる意味はないが reshape(-1, 1) で動作はする
            reshaped = to_process.reshape(-1, dec_factor)
            decimated = np.mean(reshaped, axis=1)
            
            # ダブルバッファ書き込み
            n = len(decimated)
            N = len(buffer) // 2
            
            if n > N:
                decimated = decimated[-N:]
                n = N
            
            remain_space = N - ptr
            if n <= remain_space:
                buffer[ptr : ptr + n] = decimated
                buffer[ptr + N : ptr + N + n] = decimated
                new_ptr = (ptr + n) % N
            else:
                chunk1 = decimated[:remain_space]
                buffer[ptr : N] = chunk1
                buffer[ptr + N : 2*N] = chunk1
                
                chunk2 = decimated[remain_space:]
                len2 = len(chunk2)
                buffer[0 : len2] = chunk2
                buffer[N : N + len2] = chunk2
                new_ptr = len2
                
            out_data = buffer[new_ptr : new_ptr + N]
            return out_data, new_rem, new_ptr
        else:
            N = len(buffer) // 2
            out_data = buffer[ptr : ptr + N]
            return out_data, combined, ptr

    def _analyze(self, data, processor):
        if processor is None: return 0.0, 1.0
        mean_val = np.mean(data)
        normalized = self._normalize_signal(data - mean_val)
        return processor.process(normalized)

    def _normalize_signal(self, data: np.ndarray) -> np.ndarray:
        max_val = np.max(np.abs(data))
        if max_val > 1e-6: return data / max_val
        return data

    def _match_frequency(self, freq: float) -> Tuple[str, float]:
        if freq == 0.0: return "---", 0.0
        
        best_match_name = None
        min_diff_cents = float('inf')
        
        for name, base_freq in self.target_frequencies.items():
            try:
                diff_cents = 1200 * math.log2(freq / base_freq)
            except ValueError:
                continue
            if abs(diff_cents) < abs(min_diff_cents):
                min_diff_cents = diff_cents
                best_match_name = name
        
        if best_match_name is None: return "---", 0.0

        limit = float(self.settings.get("nearest_note_window", 300.0))
        if abs(min_diff_cents) > limit:
             return "---", 0.0

        if abs(min_diff_cents) <= 50:
            label = "OK" if abs(min_diff_cents) < 5 else ("高い" if min_diff_cents > 0 else "低い")
            return f"{best_match_name}\n({label}: {min_diff_cents:+.1f})", min_diff_cents
        
        direction = "高すぎる" if min_diff_cents > 0 else "低すぎる"
        return f"{best_match_name}?\n({direction})", min_diff_cents