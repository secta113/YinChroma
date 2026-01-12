# v3.0
#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
サウンド再生（Pygame.mixer）を管理するモジュール。
v3.0: 正常系の再生ログを抑制し、エラーログのみを出力するように変更しました。
"""

import pygame.mixer
import logging
from pathlib import Path
from typing import Optional

class SoundHandler:
    def __init__(self):
        try:
            pygame.mixer.init()
            self.current_sound: Optional[pygame.mixer.Sound] = None
            self.is_playing: bool = False
        except pygame.error as e:
            logging.error(f"Mixerの初期化に失敗しました: {e}")
            raise

    def play_sound(self, sound_path: Path, loop: bool = True) -> bool:
        """サウンドを再生します。正常系のログは出力しません。"""
        try:
            pygame.mixer.stop()
            self.current_sound = pygame.mixer.Sound(str(sound_path))
            loop_count = -1 if loop else 0
            self.current_sound.play(loops=loop_count)
            self.is_playing = True
            return True
        except Exception as e:
            # 失敗時のみログを残す
            logging.error(f"サウンド再生失敗 ({sound_path.name}): {e}")
            self.is_playing = False
            return False

    def stop_sound(self):
        pygame.mixer.stop()
        self.is_playing = False

    def quit(self):
        pygame.mixer.quit()