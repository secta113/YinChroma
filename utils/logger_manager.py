# v3.0
#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

class LoggerManager:
    """
    アプリケーション全体のロギングを管理するクラス。
    保存イベントとエラーに焦点を当て、ログファイルの肥大化を防止します。
    """
    
    @staticmethod
    def setup_logging(log_dir: Path, log_file: str = "app.log"):
        """
        ロギング設定を初期化します。
        - ログローテーション: 1MBごとにローテーション、最大3世代保持。
        - ログレベル: INFO（保存等の重要イベント）と ERROR 以上を重視。
        """
        log_dir.mkdir(exist_ok=True)
        log_path = log_dir / log_file

        # フォーマッタの設定
        formatter = logging.Formatter(
            fmt='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # ファイル出力（ローテーション付き）
        file_handler = RotatingFileHandler(
            log_path, 
            maxBytes=1024 * 1024, # 1MB
            backupCount=3, 
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        # コンソール出力
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)

        # ルートロガーの設定
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # 既存のハンドラをクリアして追加
        if root_logger.hasHandlers():
            root_logger.handlers.clear()
            
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)

        # 外部ライブラリ（pygame等）のログ抑制
        logging.getLogger('pygame').setLevel(logging.WARNING)

        logging.info("--- Logging System Initialized (v3.0) ---")
        logging.info(f"Log file: {log_path}")