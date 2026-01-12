#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
サウンド再生（Pygame.mixer）を管理するモジュール。

音声の初期化、再生、停止、リソース解放をカプセル化します。
"""

import pygame.mixer
import logging
from pathlib import Path
from typing import Optional

class SoundHandler:
    """
    サウンド再生に関連するロジックを管理するクラス。

    Attributes:
        current_sound (Optional[pygame.mixer.Sound]): 現在ロードされている
                                                      サウンドオブジェクト。
        is_playing (bool): 現在サウンドが再生中かどうかを示すフラグ。
    """

    def __init__(self):
        """
        SoundHandlerを初期化し、Pygame.mixerをセットアップします。
        
        Raises:
            pygame.error: ミキサーの初期化に失敗した場合。
        """
        logging.info("Pygame mixerを初期化しています...")
        try:
            pygame.mixer.init()
            self.current_sound: Optional[pygame.mixer.Sound] = None
            self.is_playing: bool = False
            logging.info("Mixerの初期化が完了しました。")
        except pygame.error as e:
            logging.error(f"Mixerの初期化に失敗しました: {e}")
            raise  # エラーを呼び出し元に伝播させる

    def play_sound(self, sound_path: Path, loop: bool = True) -> bool:
        """
        指定されたサウンドファイルを再生します。

        再生中に呼び出された場合、現在の再生を停止してから新しい音を再生します。

        Args:
            sound_path (Path): 再生するWAVファイルのパス。
            loop (bool): ループ再生するかどうか。デフォルトはTrue。

        Returns:
            bool: 再生に成功した場合はTrue、失敗した場合はFalse。
        """
        try:
            logging.info(f"{sound_path.name} の再生を開始します (ループ: {loop})")

            # (要件 Q1:A) 現在再生中の音があれば停止する
            # ※ self.stop_sound() ではなく mixer.stop() を直接呼ぶ
            #   (stop_soundはis_playingフラグも更新するため)
            pygame.mixer.stop()
            logging.debug("既存のサウンドストリームを停止しました。")

            # サウンドをロード
            self.current_sound = pygame.mixer.Sound(str(sound_path))

            # ループ回数を設定 (-1 は無限ループ)
            loop_count = -1 if loop else 0

            # 再生
            self.current_sound.play(loops=loop_count)

            # 状態を更新
            self.is_playing = True
            return True

        except pygame.error as e:
            logging.error(f"サウンド再生エラー ({sound_path.name}): {e}")
            self.is_playing = False
            return False
        except Exception as e:
            logging.error(f"予期せぬエラー (play_sound): {e}")
            self.is_playing = False
            return False

    def stop_sound(self):
        """
        現在再生中のサウンドをすべて停止します。
        """
        logging.info("サウンド再生を停止します。")
        pygame.mixer.stop()
        self.is_playing = False

    def quit(self):
        """
        Pygame.mixerのリソースを解放します。
        """
        logging.debug("Pygame mixerのリソースを解放しています...")
        if pygame.mixer.get_init():
            pygame.mixer.quit()