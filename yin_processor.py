# v4.3
import numpy as np
from typing import Tuple

class YinProcessor:
    """
    YINアルゴリズムによるピッチ検出を行うクラス。
    
    v4.3: 計算量最適化 (High Performance Update)
          - ボトルネックだった差分二乗和関数 (Difference Function) の計算を
            Pythonループから FFT (高速フーリエ変換) と 累積和 (Cumulative Sum) を用いた
            ベクトル演算に置き換え。計算オーダーを O(N^2) から O(N log N) へ短縮。
    v4.2: 低周波誤検知（Subharmonic Error）を防ぐためのバックトラック処理を追加。
    """
    def __init__(self, sample_rate: float, min_freq: float, max_freq: float, threshold: float = 0.20):
        self.sample_rate = sample_rate
        self.min_freq = min_freq
        self.max_freq = max_freq
        self.threshold = threshold
        
        # 探索範囲の計算
        self.min_period = int(self.sample_rate / self.max_freq)
        self.max_period = int(self.sample_rate / self.min_freq)
        
        # FFT用のサイズなどの事前計算は、入力サイズが可変のため process 内で動的に行うか、
        # ある程度余裕を持ったサイズで行う。ここでは動的かつキャッシュを活用する方針。
        self.tau_range = np.arange(self.max_period, dtype=np.float32)

    def process(self, signal: np.ndarray) -> Tuple[float, float]:
        """
        信号から基本周波数と信頼度(confidence)を計算して返す。
        freq=0.0 は検出不能を意味する。
        """
        signal_len = len(signal)
        half_chunk = signal_len // 2
        
        # 必要なデータ長チェック
        if signal_len < self.max_period + half_chunk:
            return 0.0, 1.0

        # --- Step 1: Difference Function (FFT Accelerated) ---
        # 定義: d(tau) = sum_{j=0}^{W-1} (x[j] - x[j+tau])^2
        # 展開: d(tau) = sum(x[j]^2) + sum(x[j+tau]^2) - 2 * sum(x[j] * x[j+tau])
        #       d(tau) = Term1       + Term2           - Term3
        
        # テンプレート枠 (x) と サーチ枠全体 (signal)
        x = signal[:half_chunk]
        
        # [Term 1] sum(x[j]^2) -> 定数 (tauに依存しない)
        term1 = np.sum(x ** 2)

        # [Term 2] sum(x[j+tau]^2) -> 移動二乗和 (Cumulative Sumで高速化)
        # signal全体の二乗
        sq_signal = signal ** 2
        # 累積和を計算 (先頭に0を追加してインデックス操作を容易に)
        cum_sq = np.concatenate(([0.0], np.cumsum(sq_signal)))
        
        # tau=0 から tau=max_period-1 までの移動和を一括計算
        # sum(x[j+tau]^2) = cum_sq[half_chunk + tau] - cum_sq[tau]
        # ただし、配列スライスを使ってベクトル化する
        # 必要な範囲: tau = 0 ... max_period (exclusive)
        start_indices = np.arange(self.max_period)
        end_indices = start_indices + half_chunk
        
        # 安全策: インデックスが範囲外にならないようクリップ（前段の長さチェックで保証されているはずだが念のため）
        valid_len = min(len(cum_sq), end_indices[-1] + 1)
        term2 = cum_sq[end_indices] - cum_sq[start_indices]

        # [Term 3] 2 * sum(x[j] * x[j+tau]) -> 相互相関 (Cross-Correlation)
        # FFTを使って畳み込みで計算する。
        # Correlation(x, signal) <=> Convolution(reverse(x), signal)
        
        n_fft = 1
        min_fft_len = signal_len + half_chunk
        while n_fft < min_fft_len:
            n_fft *= 2
            
        # FFT計算 (実数FFTを使用)
        # xを反転させて畳み込みを行うことで相関を計算
        x_reversed = x[::-1]
        
        X = np.fft.rfft(x_reversed, n=n_fft)
        S = np.fft.rfft(signal, n=n_fft)
        
        # 畳み込み (周波数領域での乗算)
        conv_spectrum = X * S
        conv_result = np.fft.irfft(conv_spectrum, n=n_fft)
        
        # 必要なラグ部分を取り出す
        # 畳み込みの結果、xの末尾とsignalの先頭が重なる位置がインデックス half_chunk - 1
        # 欲しいのは tau=0 (完全重なり) からの相関値
        term3 = conv_result[half_chunk - 1 : half_chunk - 1 + self.max_period] * 2

        # 差分関数の合成
        diff_buffer = term1 + term2 - term3
        
        # 浮動小数点の誤差でわずかに負になることがあるのでクリップ
        diff_buffer = np.maximum(diff_buffer, 0.0)

        # --- Step 2: CMNDF (Cumulative Mean Normalized Difference Function) ---
        # 累積和を使うことで、ここもループなしで高速化可能だが、
        # YINの定義上、tauごとの割り算が必要。numpyのベクトル演算で処理。
        
        cumulative_diff = np.cumsum(diff_buffer)
        cumulative_diff[0] = 1.0 # ゼロ除算回避用ダミー
        
        # buffer[0] は常に0 (tau=0で差分なし) なので、結果は0/0になる。
        # YINの定義では tau=0 のとき 1 とする。
        with np.errstate(divide='ignore', invalid='ignore'):
            cmndf_buffer = (diff_buffer * np.arange(self.max_period)) / cumulative_diff
        
        cmndf_buffer[0] = 1.0

        # --- Step 3: Absolute Threshold (First Pass) ---
        # 以降はデータ数が max_period (数百点) 程度なので、従来ロジックでも十分に高速
        
        # min_period 以降で閾値を下回る箇所を探す
        search_range = cmndf_buffer[self.min_period : self.max_period]
        candidates = np.where(search_range < self.threshold)[0]
        
        best_tau = 0
        
        if len(candidates) > 0:
            first_occurrence = candidates[0] + self.min_period
            tau = first_occurrence
            # 局所最小値を探す
            while tau + 1 < self.max_period and cmndf_buffer[tau + 1] < cmndf_buffer[tau]:
                tau += 1
            best_tau = tau
        else:
            # 閾値未満がない場合、全体からベストを探す（Global Min）
            if len(search_range) > 0:
                best_tau = np.argmin(search_range) + self.min_period
                if cmndf_buffer[best_tau] >= 1.0:
                     return 0.0, 1.0
            else:
                return 0.0, 1.0

        # --- Step 3.5: Harmonic Check (Backtracking) ---
        # v4.2のロジックを維持 (1弦誤検知対策)
        current_freq = self.sample_rate / best_tau
        
        if current_freq < 250.0:
            current_val = cmndf_buffer[best_tau]
            
            for harmonic in range(2, 5):
                check_tau = int(best_tau / harmonic)
                if check_tau < self.min_period:
                    break
                
                start = max(self.min_period, check_tau - 2)
                end = min(self.max_period, check_tau + 3)
                if start >= end: continue
                
                local_slice = cmndf_buffer[start:end]
                local_min_idx = np.argmin(local_slice)
                found_tau = start + local_min_idx
                found_val = cmndf_buffer[found_tau]

                if found_val < 0.35 and found_val < current_val * 2.5:
                    best_tau = found_tau
                    current_val = found_val
                    break

        # --- Step 4: Parabolic Interpolation ---
        current_period = float(best_tau)
        if 0 < best_tau < self.max_period - 1:
            y1 = cmndf_buffer[best_tau - 1]
            y2 = cmndf_buffer[best_tau]
            y3 = cmndf_buffer[best_tau + 1]
            denom = y1 - (2 * y2) + y3
            if abs(denom) > 1e-6:
                current_period += 0.5 * (y1 - y3) / denom

        freq = self.sample_rate / current_period
        confidence = cmndf_buffer[best_tau]

        return freq, confidence