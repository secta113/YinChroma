# v5.1 (Fix Race Condition)
import pyaudio
import logging
import time
import threading
import queue
from typing import Callable, Optional, Dict, Any

try:
    from pitchhandler.pitch_analyzer import PitchAnalyzer
except ImportError:
    logging.error("Required module (pitch_analyzer.py) not found.")
    raise

class PitchDetector:
    """
    v5.1: スレッドセーフ修正版
    
    変更点:
      - 設定更新時(update_settings)の競合状態（Race Condition）を修正。
      - 解析処理と設定変更が衝突しないよう、threading.Lock を導入。
    """
    RATE = 44100
    CHUNK = 2048 

    def __init__(self, 
                 ui_callback: Callable[[str, float, Optional[float]], None],
                 config: Optional[Dict[str, Any]] = None):
        
        self.ui_callback = ui_callback
        self.pa: Optional[pyaudio.PyAudio] = None
        self.stream: Optional[pyaudio.Stream] = None
        self._is_running = False
        
        self.settings = {
            "threshold": 10.0,
            "yin_threshold": 0.20,
            "latency_mode": "normal",
            "smoothing": 5,
            "instrument_type": "guitar",
            "subharmonic_confidence_ratio": 0.9,
            "octave_lookback_ratio": 0.80,
            "nearest_note_window": 300.0,
            "high_quality": False 
        }
        if config:
            self.settings.update(config)

        self.analyzer = PitchAnalyzer(self.settings)
        
        self.audio_queue = queue.Queue(maxsize=10)
        
        self.analysis_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # [Critical Fix] 解析中の設定変更を防ぐためのロック
        self.analysis_lock = threading.Lock()
        
        logging.info("PitchDetector v5.1 Initialized (Thread-Safe).")

    def set_tuning_frequencies(self, frequencies: Dict[str, float]):
        with self.analysis_lock:
            self.analyzer.set_tuning_frequencies(frequencies)

    def update_settings(self, new_config: Dict[str, Any]):
        """
        設定更新。
        スレッド競合を防ぐため、Analyzerの状態変更中はロックを取得する。
        また、ストリーム再起動が必要な設定変更の場合は、安全に停止してから適用する。
        """
        # 再起動が必要なキーが含まれているか事前にチェック（Analyzerのロジックを模倣）
        restart_keys = ["latency_mode", "instrument_type", "high_quality"]
        needs_restart = any(key in new_config for key in restart_keys)

        if needs_restart:
            # 1. 再起動が必要な場合、まずストリームを止める（これで解析スレッドも止まる）
            was_running = self._is_running
            if was_running:
                self.stop_stream()
            
            # 2. 安全に設定を適用
            with self.analysis_lock:
                self.analyzer.update_settings(new_config)
            
            # 3. 再開
            if was_running:
                time.sleep(0.1)
                self.start_stream()
        else:
            # 再起動不要な場合（閾値変更など）は、ロックして即適用
            with self.analysis_lock:
                self.analyzer.update_settings(new_config)

    def start_stream(self):
        if self.stream and self.stream.is_active(): return
        
        try:
            self.pa = pyaudio.PyAudio()
            self._is_running = True 
            self.stop_event.clear()
            
            # 状態リセット
            with self.analysis_lock:
                self.analyzer.reset_state()
            
            with self.audio_queue.mutex:
                self.audio_queue.queue.clear()

            self.analysis_thread = threading.Thread(target=self._analysis_loop, daemon=True)
            self.analysis_thread.start()
            
            self.stream = self.pa.open(
                format=pyaudio.paInt16, channels=1, rate=self.RATE,
                input=True, frames_per_buffer=self.CHUNK, 
                stream_callback=self._pyaudio_callback
            )
            self.stream.start_stream()
            logging.info("Audio stream & Analysis thread started.")
        except Exception as e:
            self._is_running = False 
            logging.error(f"Stream start error: {e}")

    def stop_stream(self):
        self._is_running = False
        self.stop_event.set()
        
        if self.stream:
            try:
                self.stream.stop_stream()
                self.stream.close()
            except: pass
            self.stream = None
        
        if self.pa:
            try: self.pa.terminate()
            except: pass
            self.pa = None
            
        if self.analysis_thread and self.analysis_thread.is_alive():
            self.analysis_thread.join(timeout=0.5)

    def _pyaudio_callback(self, in_data, frame_count, time_info, status):
        if not self._is_running: return (None, pyaudio.paComplete) 
        
        try:
            self.audio_queue.put_nowait(in_data)
        except queue.Full:
            pass
            
        return (in_data, pyaudio.paContinue)

    def _analysis_loop(self):
        """[Consumer] 解析スレッド"""
        while not self.stop_event.is_set():
            try:
                raw_data = self.audio_queue.get(timeout=0.1)
                
                # [Critical Fix] 解析実行中もロックし、設定変更との衝突を防ぐ
                # ただし、ロック期間が長すぎるとUIからの設定変更が詰まる可能性があるが、
                # process処理は数ms〜数十msなので許容範囲。
                with self.analysis_lock:
                    result_string, display_volume, final_cents = self.analyzer.process(raw_data)
                
                if self.ui_callback:
                    self.ui_callback(result_string, display_volume, final_cents)
                    
                self.audio_queue.task_done()
                
            except queue.Empty:
                continue
            except Exception as e:
                logging.warning(f"Analysis Loop Error: {e}")
                # エラーが出てもループは止めない（頑健性）
                pass