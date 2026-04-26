# -*- coding: utf-8 -*-
"""
브라운더스트2 가챠 데이터 수집기
엔트리 포인트
"""

import tkinter as tk
import sys
import os

# 실행 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_manager import init_db
from gui_app import GachaApp


def main():
    init_db()
    root = tk.Tk()
    root.title("브라운더스트2 가챠 데이터 수집기")

    # 아이콘 설정 (없어도 무방)
    try:
        root.iconbitmap("icon.ico")
    except Exception:
        pass

    app = GachaApp(root)

    # 창 닫기 처리
    def on_closing():
        if app.is_running:
            app.engine.stop()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
