# -*- coding: utf-8 -*-
"""
GUI 앱 - 번호 기반 캐릭터 그리드
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import queue, os
import re
import numpy as np
import cv2
from PIL import Image, ImageTk, ImageDraw

import config as C
from data_manager import (
    init_db, get_all_characters, get_stats,
    set_target, clear_all_targets, get_target_characters,
    run_duplicate_check, set_character_name
)
from macro_engine import MacroEngine

# ── 테마 ──
BG        = "#1a1a2e"
BG2       = "#16213e"
ACCENT    = "#0f3460"
GOLD      = "#e2b04a"
CYAN      = "#00b4d8"
RED       = "#e63946"
GREEN     = "#06d6a0"
TEXT      = "#e0e0e0"
TEXT2     = "#a0a0a0"
TARGET_BG = "#2a1a00"
TARGET_BD = "#e2b04a"

CARD_W    = 160
CARD_H    = 360   # 기본 카드 배율
MAX_GRID_COLS = 10

SETTINGS_SCHEMA = [
    ("SKIP_BTN_BRIGHT_PIXEL_MIN", "스킵 밝은픽셀 임계", int),
    ("SSR_MIN_HI_SAT_PIXELS", "SSR 고채도 최소픽셀", int),
    ("SSR_MIN_HUE_VARIANCE", "SSR 색상분산 최소", float),
    ("SSR_SAT_THRESHOLD", "SSR 채도 임계", int),
    ("PHASH_THRESHOLD", "pHash 임계", int),
    ("CARD_CENTER_EXTRA", "중앙 추가 간격", int),
    ("DELAY_AFTER_REROLL", "다시뽑기 후 대기(초)", float),
    ("DELAY_AFTER_POPUP", "팝업 확인 후 대기(초)", float),
    ("DELAY_AFTER_SKIP", "스킵 후 대기(초)", float),
    ("DELAY_STATE_CHECK", "상태 체크 간격(초)", float),
    ("MAX_PULLS_LIMIT", "반복 횟수 제한(0=무제한)", int),
    ("RUN_DUPLICATE_CHECK_EACH_PULL", "회차마다 중복검사", bool),
    ("DISCORD_NOTIFY_ENABLED", "디스코드 알림 사용", bool),
    ("DISCORD_NOTIFY_ON_START", "디코 알림: 시작", bool),
    ("DISCORD_NOTIFY_ON_STOP", "디코 알림: 종료", bool),
    ("DISCORD_NOTIFY_ON_TARGET", "디코 알림: 목표달성", bool),
    ("DISCORD_NOTIFY_ON_DEDUPE", "디코 알림: 중복병합", bool),
    ("DISCORD_NOTIFY_ON_ERROR", "디코 알림: 오류", bool),
    ("DISCORD_WEBHOOK_URL", "디스코드 웹훅 URL", str),
    ("DISCORD_TEMPLATE_START", "디코 템플릿: 시작", str),
    ("DISCORD_TEMPLATE_STOP", "디코 템플릿: 종료", str),
    ("DISCORD_TEMPLATE_TARGET", "디코 템플릿: 목표달성", str),
    ("DISCORD_TEMPLATE_DEDUPE", "디코 템플릿: 중복병합", str),
    ("DISCORD_TEMPLATE_ERROR", "디코 템플릿: 오류", str),
]


class GachaApp:
    def __init__(self, root: tk.Tk):
        self.root  = root
        self.root.title("브라운더스트2 가챠 수집기")
        self.root.configure(bg=BG)
        self.root.minsize(920, 680)

        self.event_queue  = queue.Queue()
        self.engine       = MacroEngine(self.event_queue)
        self.char_widgets: dict[int, dict] = {}   # char_id → widgets
        self.is_running   = False
        self.card_w       = CARD_W
        self.card_h       = CARD_H
        self.grid_cols    = 5
        self.search_var   = tk.StringVar(value="")
        self.sort_var     = tk.StringVar(value="번호순")
        self.status_var   = tk.StringVar(value="준비")
        self._card_click_job = None

        init_db()
        self._build_ui()
        self._bind_shortcuts()
        self._load_existing()
        self._poll_queue()

    # ══════════════════════════════════════
    #  UI 구성
    # ══════════════════════════════════════
    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)
        self.root.columnconfigure(1, weight=0)
        self.root.rowconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=0)
        self._build_left()
        self._build_right()
        self._build_log()

    # ── 좌측: 그리드/목록 탭 ──
    def _build_left(self):
        left = tk.Frame(self.root, bg=BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(10,5), pady=10)
        left.rowconfigure(2, weight=1)
        left.columnconfigure(0, weight=1)

        # 탭 바
        tab_bar = tk.Frame(left, bg=BG2)
        tab_bar.grid(row=0, column=0, sticky="ew")

        self.tab_var = tk.StringVar(value="grid")
        for lbl, val in [("🃏 그리드", "grid"), ("📋 목록", "list")]:
            tk.Radiobutton(
                tab_bar, text=lbl, variable=self.tab_var, value=val,
                command=self._switch_tab,
                bg=BG2, fg=TEXT, selectcolor=ACCENT,
                activebackground=BG2, activeforeground=CYAN,
                font=("맑은 고딕", 10, "bold"), bd=0,
                indicatoron=False, relief="flat", padx=14, pady=5
            ).pack(side="left")

        self.count_lbl = tk.Label(
            tab_bar, text="수집: 0종", bg=BG2, fg=GOLD,
            font=("맑은 고딕", 10, "bold")
        )
        self.count_lbl.pack(side="right", padx=10)

        # 검색/정렬/줌
        tools_bar = tk.Frame(left, bg=BG2)
        tools_bar.grid(row=1, column=0, sticky="ew", pady=(4, 4))
        tools_bar.columnconfigure(1, weight=1)

        tk.Label(tools_bar, text="검색", bg=BG2, fg=TEXT2,
                 font=("맑은 고딕", 9)).grid(row=0, column=0, padx=(8,4), pady=4)
        self.search_entry = tk.Entry(
            tools_bar, textvariable=self.search_var, bg=BG, fg=TEXT,
            insertbackground=TEXT, relief="flat", font=("Consolas", 10)
        )
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(0,6), pady=4)
        self.search_var.trace_add("write", lambda *_: self._reload_characters_from_db())

        self.sort_combo = ttk.Combobox(
            tools_bar,
            values=["번호순", "최근획득순", "등장횟수순", "이름순"],
            textvariable=self.sort_var,
            state="readonly",
            width=11,
        )
        self.sort_combo.grid(row=0, column=2, padx=(0,6), pady=4)
        self.sort_combo.bind("<<ComboboxSelected>>", lambda e: self._reload_characters_from_db())

        self.zoom_lbl = tk.Label(
            tools_bar, text=f"줌 {self.card_w}x{self.card_h}", bg=BG2, fg=CYAN,
            font=("맑은 고딕", 9, "bold")
        )
        self.zoom_lbl.grid(row=0, column=3, padx=(0,8), pady=4)

        # 콘텐츠
        content = tk.Frame(left, bg=BG)
        content.grid(row=2, column=0, sticky="nsew")
        content.rowconfigure(0, weight=1)
        content.columnconfigure(0, weight=1)

        # 그리드 뷰
        self.grid_outer = tk.Frame(content, bg=BG)
        self.grid_outer.grid(row=0, column=0, sticky="nsew")
        self.grid_outer.rowconfigure(0, weight=1)
        self.grid_outer.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(self.grid_outer, bg=BG, highlightthickness=0)
        vsb = ttk.Scrollbar(self.grid_outer, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.grid_frame = tk.Frame(self.canvas, bg=BG)
        self._cwin = self.canvas.create_window((0,0), window=self.grid_frame, anchor="nw")

        self.grid_frame.bind("<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_canvas_mousewheel)

        # 목록 뷰
        self.list_outer = tk.Frame(content, bg=BG)
        self._build_list_view()

        status_bar = tk.Frame(left, bg=BG2)
        status_bar.grid(row=3, column=0, sticky="ew")
        tk.Label(status_bar, textvariable=self.status_var,
             bg=BG2, fg=TEXT2, font=("맑은 고딕", 8)).pack(side="left", padx=8, pady=2)

    def _build_list_view(self):
        cols = ("num", "name", "count", "last_slot", "first_seen", "target")
        self.tree = ttk.Treeview(
            self.list_outer, columns=cols, show="headings", style="G.Treeview"
        )
        self.tree.heading("num",        text="번호")
        self.tree.heading("name",       text="이름")
        self.tree.heading("count",      text="등장 횟수")
        self.tree.heading("last_slot",  text="최근 카드 위치")
        self.tree.heading("first_seen", text="최초 발견")
        self.tree.heading("target",     text="목표")
        self.tree.column("num",        width=80,  anchor="center")
        self.tree.column("name",       width=110)
        self.tree.column("count",      width=80,  anchor="center")
        self.tree.column("last_slot",  width=110, anchor="center")
        self.tree.column("first_seen", width=160)
        self.tree.column("target",     width=50,  anchor="center")

        vsb = ttk.Scrollbar(self.list_outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-Button-1>", self._on_list_dclick)
        self.tree.bind("<Button-3>", self._on_list_rclick)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("G.Treeview",
            background=BG2, foreground=TEXT, fieldbackground=BG2,
            rowheight=26, font=("맑은 고딕", 10))
        style.configure("G.Treeview.Heading",
            background=ACCENT, foreground=GOLD,
            font=("맑은 고딕", 10, "bold"))

    # ── 우측: 컨트롤 ──
    def _build_right(self):
        right = tk.Frame(self.root, bg=BG2, width=210)
        right.grid(row=0, column=1, sticky="nsew", padx=(5,10), pady=10)
        right.grid_propagate(False)
        right.columnconfigure(0, weight=1)

        def section(text):
            tk.Label(right, text=text, bg=BG2, fg=GOLD,
                     font=("맑은 고딕", 11, "bold")).pack(padx=12, pady=(8,2), anchor="w")
            ttk.Separator(right, orient="horizontal").pack(fill="x", padx=8, pady=2)

        # 컨트롤
        section("⚙ 컨트롤")
        self.start_btn = tk.Button(
            right, text="▶ 수집 시작", bg=GREEN, fg="#111",
            font=("맑은 고딕", 11, "bold"), relief="flat", cursor="hand2",
            activebackground="#04a880", command=self._toggle_macro
        )
        self.start_btn.pack(fill="x", padx=12, pady=(4,2))

        self.pause_btn = tk.Button(
            right, text="⏸ 일시정지", bg=ACCENT, fg=TEXT,
            font=("맑은 고딕", 10), relief="flat", cursor="hand2",
            activebackground="#1a5278", command=self._pause_macro, state="disabled"
        )
        self.pause_btn.pack(fill="x", padx=12, pady=2)

        self.dedupe_btn = tk.Button(
            right, text="🔁 중복검사", bg="#1f4e5f", fg=TEXT,
            font=("맑은 고딕", 10), relief="flat", cursor="hand2",
            activebackground="#2a6a80", command=self._run_manual_duplicate_check
        )
        self.dedupe_btn.pack(fill="x", padx=12, pady=2)

        self.settings_btn = tk.Button(
            right, text="🛠 설정", bg="#4a3f2f", fg=TEXT,
            font=("맑은 고딕", 10), relief="flat", cursor="hand2",
            activebackground="#63543d", command=self._open_settings_window
        )
        self.settings_btn.pack(fill="x", padx=12, pady=2)

        # 통계
        section("📊 통계")
        self.stat_lbl = {}
        for key, label in [
            ("total_rounds",   "돌린 횟수"),
            ("total_ssr",      "나온 5성 개수"),
            ("pulls_2ssr",     "5성 2개 나온 횟수"),
            ("pulls_3plus",    "5성 3개+ 나온 횟수"),
            ("guaranteed_ssr", "확정 5성 누적"),
            ("extra_ssr",      "추가 5성 누적"),
            ("extra_rate",     "추가 5성 확률"),
            ("unique_ssr",     "수집 종류"),
        ]:
            row = tk.Frame(right, bg=BG2)
            row.pack(fill="x", padx=12, pady=1)
            tk.Label(row, text=label, bg=BG2, fg=TEXT2,
                     font=("맑은 고딕", 9)).pack(side="left")
            v = tk.Label(row, text="-", bg=BG2, fg=CYAN,
                         font=("맑은 고딕", 10, "bold"))
            v.pack(side="right")
            self.stat_lbl[key] = v

        # 목표
        section("🎯 목표 캐릭터")
        self.target_lb = tk.Listbox(
            right, bg=BG, fg=GOLD, font=("맑은 고딕", 10),
            relief="flat", height=5, selectbackground=ACCENT,
            highlightcolor=GOLD, highlightthickness=1
        )
        self.target_lb.pack(fill="x", padx=12, pady=4)

        self.clear_targets_btn = tk.Button(
            right, text="목표 전체 해제", bg=ACCENT, fg=TEXT,
            font=("맑은 고딕", 9), relief="flat", cursor="hand2",
            command=self._clear_targets
        )
        self.clear_targets_btn.pack(fill="x", padx=12, pady=2)

        section("⌨ 단축키")
        tk.Label(right, text="F9: 중지\nF8: 일시정지\n마우스 좌상단: 긴급종료",
                 bg=BG2, fg=TEXT2, font=("맑은 고딕", 8), justify="left"
                 ).pack(padx=12, anchor="w")

    # ── 하단: 로그 ──
    def _build_log(self):
        bot = tk.Frame(self.root, bg=BG2, height=120)
        bot.grid(row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(0,8))
        bot.grid_propagate(False)
        bot.columnconfigure(0, weight=1)
        bot.rowconfigure(1, weight=1)

        tk.Label(bot, text="📟 로그", bg=BG2, fg=TEXT2,
                 font=("맑은 고딕", 9, "bold")).grid(row=0, column=0, sticky="w", padx=8, pady=2)

        self.log = tk.Text(bot, height=5, bg=BG, fg=TEXT,
                           font=("Consolas", 9), relief="flat",
                           state="disabled", wrap="word")
        vsb = ttk.Scrollbar(bot, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=vsb.set)
        vsb.grid(row=1, column=1, sticky="ns")
        self.log.grid(row=1, column=0, sticky="nsew", padx=(8,0), pady=(0,4))

    # ══════════════════════════════════════
    #  탭 전환
    # ══════════════════════════════════════
    def _switch_tab(self):
        if self.tab_var.get() == "grid":
            self.list_outer.grid_remove()
            self.grid_outer.grid(row=0, column=0, sticky="nsew")
        else:
            self.grid_outer.grid_remove()
            self.list_outer.grid(row=0, column=0, sticky="nsew")
            self._refresh_list()
        self._update_status_bar()

    def _on_canvas_configure(self, event):
        self.canvas.itemconfig(self._cwin, width=event.width)
        self._recalc_grid_cols(event.width)

    def _bind_shortcuts(self):
        self.root.bind_all("<Control-f>", self._shortcut_focus_search)
        self.root.bind_all("<Control-d>", self._shortcut_run_dedupe)
        self.root.bind_all("<Control-comma>", self._shortcut_open_settings)
        self.root.bind_all("<Control-0>", self._shortcut_reset_zoom)

    def _shortcut_focus_search(self, _event=None):
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, "end")
        return "break"

    def _shortcut_run_dedupe(self, _event=None):
        if str(self.dedupe_btn["state"]) != "disabled":
            self._run_manual_duplicate_check()
        return "break"

    def _shortcut_open_settings(self, _event=None):
        if str(self.settings_btn["state"]) != "disabled":
            self._open_settings_window()
        return "break"

    def _shortcut_reset_zoom(self, _event=None):
        self._reset_zoom()
        return "break"

    def _on_canvas_mousewheel(self, event):
        ctrl_pressed = (event.state & 0x4) != 0
        if ctrl_pressed:
            direction = 1 if event.delta > 0 else -1
            self._change_zoom(direction)
            return "break"
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _change_zoom(self, direction: int):
        step_w = 6
        step_h = 12
        new_w = max(60, min(160, self.card_w + (step_w * direction)))
        new_h = max(120, min(360, self.card_h + (step_h * direction)))
        if new_w == self.card_w and new_h == self.card_h:
            return
        self.card_w = new_w
        self.card_h = new_h
        self.zoom_lbl.config(text=f"줌 {self.card_w}x{self.card_h}")
        self._reload_characters_from_db()
        self._log(f"🔎 카드 확대/축소: {self.card_w}x{self.card_h}")

    def _reset_zoom(self):
        self.card_w = CARD_W
        self.card_h = CARD_H
        self.zoom_lbl.config(text=f"줌 {self.card_w}x{self.card_h}")
        self._reload_characters_from_db()
        self._log("🔎 카드 줌 기본값으로 리셋")

    def _recalc_grid_cols(self, canvas_width: int):
        # 카드 프레임 가로폭 + 좌우 간격 대략치
        per_card_w = self.card_w + 16
        cols = max(1, min(MAX_GRID_COLS, canvas_width // per_card_w))
        if cols != self.grid_cols:
            self.grid_cols = cols
            self._reflow_grid()
            self._update_status_bar()

    def _reflow_grid(self):
        for idx, w in enumerate(self.char_widgets.values()):
            row_i = idx // self.grid_cols
            col_i = idx % self.grid_cols
            w["frame"].grid_configure(row=row_i, column=col_i)

    # ══════════════════════════════════════
    #  캐릭터 카드
    # ══════════════════════════════════════
    def _add_or_update_card(self, char: dict, new_img: np.ndarray = None):
        cid       = char["id"]
        num       = char["char_number"]
        name      = (char.get("char_name") or "").strip()
        count     = char["total_count"]
        last_slot = char.get("last_card_slot")
        is_target = bool(char.get("is_target", 0))

        if cid in self.char_widgets:
            w = self.char_widgets[cid]
            w["count_lbl"].config(text=f"×{count}")
            w["name_lbl"].config(text=name if name else "이름 미지정")
            w["slot_lbl"].config(text=f"최근: {last_slot}번 카드" if last_slot else "최근: -")
            bd = TARGET_BD if is_target else BG2
            bg = TARGET_BG if is_target else BG2
            w["frame"].config(highlightbackground=bd, bg=bg)
            return

        total = len(self.char_widgets)
        row_i = total // self.grid_cols
        col_i = total % self.grid_cols

        bd = TARGET_BD if is_target else BG2
        bg = TARGET_BG if is_target else BG2

        frame = tk.Frame(self.grid_frame, bg=bg,
                         highlightbackground=bd, highlightthickness=2,
                         cursor="hand2")
        frame.grid(row=row_i, column=col_i, padx=4, pady=4)

        # 이미지
        img_lbl = tk.Label(frame, bg=bg)
        img_lbl.pack(padx=4, pady=(4,0))
        if new_img is not None:
            self._set_img_from_array(img_lbl, new_img)
        else:
            self._set_img_from_path(img_lbl, char.get("image_path",""), bg)

        # 번호
        num_lbl = tk.Label(frame, text=f"#{num:03d}", bg=bg, fg=GOLD,
                           font=("맑은 고딕", 9, "bold"))
        num_lbl.pack(pady=(2,0))

        name_lbl = tk.Label(frame, text=name if name else "이름 미지정",
                    bg=bg, fg=CYAN, font=("맑은 고딕", 8, "bold"))
        name_lbl.pack()

        # 카운트
        count_lbl = tk.Label(frame, text=f"×{count}", bg=bg, fg=TEXT2,
                             font=("맑은 고딕", 8))
        count_lbl.pack()

        slot_lbl = tk.Label(frame, text=f"최근: {last_slot}번 카드" if last_slot else "최근: -",
                    bg=bg, fg=TEXT2, font=("맑은 고딕", 8))
        slot_lbl.pack()

        # 목표 배지
        badge_lbl = tk.Label(frame, text="🎯" if is_target else " ",
                             bg=bg, fg=GOLD, font=("맑은 고딕", 10))
        badge_lbl.pack(pady=(0,4))

        for w in [frame, img_lbl, num_lbl, name_lbl, count_lbl, slot_lbl, badge_lbl]:
            w.bind("<Button-1>", lambda e, c=cid, n=num: self._schedule_card_toggle(c, n))
            w.bind("<Double-Button-1>", lambda e, c=cid, n=num: self._on_card_double_click(c, n))
            w.bind("<Button-3>", lambda e, c=cid, n=num: self._edit_character_name(c, n))

        self.char_widgets[cid] = {
            "frame":     frame,
            "img_lbl":   img_lbl,
            "num_lbl":   num_lbl,
            "name_lbl":  name_lbl,
            "count_lbl": count_lbl,
            "slot_lbl":  slot_lbl,
            "badge_lbl": badge_lbl,
        }
        self.count_lbl.config(text=f"수집: {len(self.char_widgets)}종")

    def _set_img_from_array(self, label: tk.Label, bgr: np.ndarray):
        try:
            rgb   = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
            photo = ImageTk.PhotoImage(self._fit_card(Image.fromarray(rgb)))
            label.config(image=photo)
            label.image = photo
        except Exception:
            pass

    def _set_img_from_path(self, label: tk.Label, path: str, bg: str):
        try:
            img = Image.open(path) if (path and os.path.exists(path)) else self._placeholder()
            photo = ImageTk.PhotoImage(self._fit_card(img))
            label.config(image=photo)
            label.image = photo
        except Exception:
            pass

    def _fit_card(self, img: Image.Image) -> Image.Image:
        """
        카드 이미지를 CARD_W에 맞게 비율 유지 축소 후
        CARD_H 높이로 중앙 크롭. 찌그러짐 없음.
        """
        orig_w, orig_h = img.size
        # 너비를 CARD_W에 맞추고 높이 비례 계산
        scale  = self.card_w / orig_w
        new_h  = int(orig_h * scale)
        img    = img.resize((self.card_w, new_h), Image.LANCZOS)
        # 높이가 CARD_H보다 크면 중앙 크롭
        if new_h > self.card_h:
            top = (new_h - self.card_h) // 2
            img = img.crop((0, top, self.card_w, top + self.card_h))
        elif new_h < self.card_h:
            # 짧으면 위쪽 정렬 + 여백
            canvas = Image.new("RGB", (self.card_w, self.card_h), (26, 26, 46))
            canvas.paste(img, (0, 0))
            img = canvas
        return img

    def _placeholder(self) -> Image.Image:
        img  = Image.new("RGB", (self.card_w, self.card_h), (30, 30, 60))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0,0,self.card_w-1,self.card_h-1], outline=GOLD, width=2)
        draw.text((self.card_w//2-6, self.card_h//2-10), "?", fill=GOLD)
        return img

    # ══════════════════════════════════════
    #  목록 뷰
    # ══════════════════════════════════════
    def _refresh_list(self):
        for r in self.tree.get_children():
            self.tree.delete(r)
        chars, total = self._get_view_characters()
        for ch in chars:
            last_slot = ch.get("last_card_slot")
            name = (ch.get("char_name") or "").strip() or "-"
            self.tree.insert("", "end", iid=str(ch["id"]), values=(
                f"#{ch['char_number']:03d}",
                name,
                ch["total_count"],
                f"{last_slot}번" if last_slot else "-",
                ch["first_seen"][:10],
                "🎯" if ch["is_target"] else ""
            ))
        self._update_status_bar(len(chars), total)

    def _on_list_dclick(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        cid = int(row_id)
        chars = {ch["id"]: ch for ch in get_all_characters()}
        ch = chars.get(cid)
        if ch:
            self._edit_character_name(cid, ch["char_number"])

    def _on_list_rclick(self, event):
        row_id = self.tree.identify_row(event.y)
        if not row_id:
            return
        self.tree.selection_set(row_id)
        cid = int(row_id)
        chars = {ch["id"]: ch for ch in get_all_characters()}
        ch = chars.get(cid)
        if ch:
            self._edit_character_name(cid, ch["char_number"])

    def _edit_character_name(self, char_id: int, char_number: int):
        if self.is_running:
            self._log("⚠ 실행 중에는 이름 수정이 비활성화됩니다")
            return
        chars = {ch["id"]: ch for ch in get_all_characters()}
        ch = chars.get(char_id)
        if ch is None:
            return
        current = (ch.get("char_name") or "").strip()
        new_name = simpledialog.askstring(
            "이름 설정",
            f"#{char_number:03d} 이름 입력 (빈 값이면 삭제)",
            initialvalue=current,
            parent=self.root,
        )
        if new_name is None:
            return
        set_character_name(char_id, new_name.strip())
        self._reload_characters_from_db()
        if new_name.strip():
            self._log(f"✏ 이름 설정: #{char_number:03d} -> {new_name.strip()}")
        else:
            self._log(f"✏ 이름 삭제: #{char_number:03d}")

    # ══════════════════════════════════════
    #  목표 캐릭터
    # ══════════════════════════════════════
    def _toggle_target(self, char_id: int, char_number: int):
        chars = {ch["id"]: ch for ch in get_all_characters()}
        ch = chars.get(char_id)
        if ch is None:
            return
        new_val = not bool(ch["is_target"])
        set_target(char_id, new_val)

        if char_id in self.char_widgets:
            w  = self.char_widgets[char_id]
            bg = TARGET_BG if new_val else BG2
            bd = TARGET_BD if new_val else BG2
            w["frame"].config(bg=bg, highlightbackground=bd)
            for lbl in [w["img_lbl"], w["num_lbl"], w["name_lbl"], w["count_lbl"], w["slot_lbl"], w["badge_lbl"]]:
                lbl.config(bg=bg)
            w["badge_lbl"].config(text="🎯" if new_val else " ")

        self._refresh_targets()
        self._log(f"{'목표 설정' if new_val else '목표 해제'}: #{char_number:03d}")

    def _refresh_targets(self):
        self.target_lb.delete(0, "end")
        for ch in get_target_characters():
            self.target_lb.insert("end", f"🎯 #{ch['char_number']:03d}")

    def _clear_targets(self):
        clear_all_targets()
        for cid, w in self.char_widgets.items():
            w["frame"].config(bg=BG2, highlightbackground=BG2)
            for lbl in [w["img_lbl"], w["num_lbl"], w["name_lbl"], w["count_lbl"], w["slot_lbl"], w["badge_lbl"]]:
                lbl.config(bg=BG2)
            w["badge_lbl"].config(text=" ")
        self.target_lb.delete(0, "end")
        self._log("목표 전체 해제")

    def _schedule_card_toggle(self, char_id: int, char_number: int):
        if self._card_click_job is not None:
            self.root.after_cancel(self._card_click_job)
        self._card_click_job = self.root.after(
            220,
            lambda cid=char_id, cnum=char_number: self._run_card_toggle(cid, cnum)
        )

    def _run_card_toggle(self, char_id: int, char_number: int):
        self._card_click_job = None
        self._toggle_target(char_id, char_number)

    def _on_card_double_click(self, char_id: int, char_number: int):
        if self._card_click_job is not None:
            self.root.after_cancel(self._card_click_job)
            self._card_click_job = None
        self._edit_character_name(char_id, char_number)

    # ══════════════════════════════════════
    #  매크로 컨트롤
    # ══════════════════════════════════════
    def _toggle_macro(self):
        if not self.is_running:
            self.is_running = True
            self.start_btn.config(text="■ 중지", bg=RED, activebackground="#c0392b")
            self.pause_btn.config(state="normal")
            self._update_control_states()
            self.engine.start()
        else:
            self.engine.stop()
            self.is_running = False
            self.start_btn.config(text="▶ 수집 시작", bg=GREEN, activebackground="#04a880")
            self.pause_btn.config(state="disabled")
            self._update_control_states()

    def _pause_macro(self):
        self.engine.toggle_pause()

    def _run_manual_duplicate_check(self):
        self.dedupe_btn.config(state="disabled")
        self._log("🔍 중복검사 시작...")
        try:
            result = run_duplicate_check()
            self._reload_characters_from_db()

            merged = int(result.get("merged", 0))
            checked = int(result.get("checked", 0))
            self._log(f"🔁 중복검사 완료 | 병합 {merged}건 / 검사 {checked}종")
            messagebox.showinfo("중복검사 완료", f"병합 {merged}건 / 검사 {checked}종")

            for info in result.get("details", [])[:5]:
                sim_txt = ""
                if info.get("similarity") is not None:
                    sim_txt = f", sim={info['similarity']:.3f}"
                self._log(
                    f"  · #{info['drop_number']:03d} -> #{info['keep_number']:03d} "
                    f"(dist={info['hash_distance']}{sim_txt})"
                )
        except Exception as e:
            self._log(f"⚠ 중복검사 오류: {e}")
        finally:
            self.dedupe_btn.config(state="normal")

    def _open_settings_window(self):
        win = tk.Toplevel(self.root)
        win.title("설정")
        win.configure(bg=BG2)
        win.transient(self.root)
        win.grab_set()

        frame = tk.Frame(win, bg=BG2)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        entries = {}
        for key, label, caster in SETTINGS_SCHEMA:
            row = tk.Frame(frame, bg=BG2)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, bg=BG2, fg=TEXT2,
                     font=("맑은 고딕", 9), width=20, anchor="w").pack(side="left")

            if caster is bool:
                v = tk.BooleanVar(value=bool(getattr(C, key)))
                cb = tk.Checkbutton(
                    row, variable=v, bg=BG2, activebackground=BG2,
                    selectcolor=ACCENT, highlightthickness=0
                )
                cb.pack(side="right")
                entries[key] = (caster, v)
            else:
                e = tk.Entry(row, bg=BG, fg=TEXT, insertbackground=TEXT,
                             relief="flat", font=("Consolas", 10), width=14)
                e.insert(0, str(getattr(C, key)))
                e.pack(side="right")
                entries[key] = (caster, e)

        btn_row = tk.Frame(frame, bg=BG2)
        btn_row.pack(fill="x", pady=(8, 0))

        tk.Button(
            btn_row, text="적용 + 저장", bg=GREEN, fg="#111",
            font=("맑은 고딕", 10, "bold"), relief="flat", cursor="hand2",
            command=lambda: self._apply_settings_from_ui(entries, win)
        ).pack(side="left")

        tk.Button(
            btn_row, text="닫기", bg=ACCENT, fg=TEXT,
            font=("맑은 고딕", 10), relief="flat", cursor="hand2",
            command=win.destroy
        ).pack(side="right")

    def _apply_settings_from_ui(self, entries: dict, win: tk.Toplevel):
        updates = {}
        try:
            for key, (caster, widget) in entries.items():
                if caster is bool:
                    val = bool(widget.get())
                else:
                    raw = widget.get().strip()
                    val = caster(raw)
                updates[key] = val
        except Exception as e:
            messagebox.showerror("설정 오류", f"입력값을 확인하세요: {e}")
            return

        # 런타임 반영
        for key, val in updates.items():
            setattr(C, key, val)

        # 파일 저장
        try:
            self._save_config_updates(updates)
        except Exception as e:
            messagebox.showerror("저장 오류", f"config.py 저장 실패: {e}")
            return

        self._log("🛠 설정 적용 완료")
        win.destroy()

    def _save_config_updates(self, updates: dict):
        cfg_path = os.path.join(os.path.dirname(__file__), "config.py")
        with open(cfg_path, "r", encoding="utf-8") as f:
            text = f.read()

        for key, val in updates.items():
            if isinstance(val, bool):
                new_val = "True" if val else "False"
            elif isinstance(val, str):
                new_val = repr(val)
            else:
                new_val = str(val)
            pattern = rf"(?m)^({re.escape(key)}\s*=\s*).*$"
            text, n = re.subn(pattern, lambda m, nv=new_val: f"{m.group(1)}{nv}", text)
            if n == 0:
                text += f"\n{key} = {new_val}\n"

        with open(cfg_path, "w", encoding="utf-8") as f:
            f.write(text)

    # ══════════════════════════════════════
    #  큐 폴링
    # ══════════════════════════════════════
    def _poll_queue(self):
        try:
            while True:
                t, d = self.event_queue.get_nowait()
                if t == "status":
                    self._log(d)
                elif t == "pull_count":
                    self._update_stats()
                elif t == "ssr_found":
                    self._log(
                        f"✨ 5성: #{d['char_number']:03d} | {d.get('card_slot', '-')}번 카드 "
                        f"{'(신규)' if d['is_new'] else '(중복)'}"
                    )
                    self._reload_characters_from_db()
                    self._update_stats()
                elif t == "target_found":
                    self._log(f"🎉 목표 달성! #{d['char_number']:03d}")
                    messagebox.showinfo("🎉 목표 달성!",
                        f"목표 캐릭터 [#{d['char_number']:03d}]를 뽑았습니다!")
                elif t == "dedupe_done":
                    self._reload_characters_from_db()
                    self._log(f"🔁 중복 병합 완료: {d.get('merged', 0)}건")
                elif t == "stopped":
                    self.is_running = False
                    self.start_btn.config(text="▶ 수집 시작", bg=GREEN)
                    self.pause_btn.config(state="disabled")
                    self._update_control_states()
                    self._update_stats()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _update_stats(self):
        s = get_stats()
        self.stat_lbl["total_rounds"].config(text=f"{s['total_rounds']}회")
        self.stat_lbl["total_ssr"].config(text=str(s["total_ssr"]))
        self.stat_lbl["pulls_2ssr"].config(text=f"{s['pulls_2ssr']}회")
        self.stat_lbl["pulls_3plus"].config(text=f"{s['pulls_3plus']}회")
        self.stat_lbl["guaranteed_ssr"].config(text=str(s["guaranteed_ssr"]))
        self.stat_lbl["extra_ssr"].config(text=str(s["extra_ssr"]))
        self.stat_lbl["extra_rate"].config(text=f"{s['extra_rate']:.2f}%")
        self.stat_lbl["unique_ssr"].config(text=str(s["unique_ssr"]))

    # ══════════════════════════════════════
    #  초기 데이터 로드
    # ══════════════════════════════════════
    def _load_existing(self):
        chars, total = self._get_view_characters()
        for ch in chars:
            self._add_or_update_card(ch)
        self.count_lbl.config(text=f"수집: {total}종")
        self._update_status_bar(len(chars), total)
        self._refresh_targets()
        self._update_stats()
        if total:
            self._log(f"기존 데이터 로드: {total}종")
        self._update_control_states()

    def _reload_characters_from_db(self):
        for w in self.char_widgets.values():
            try:
                w["frame"].destroy()
            except Exception:
                pass
        self.char_widgets.clear()

        chars, total = self._get_view_characters()
        for ch in chars:
            self._add_or_update_card(ch)
        self.count_lbl.config(text=f"수집: {total}종")
        self._update_status_bar(len(chars), total)
        self._refresh_targets()
        self._update_stats()
        if self.tab_var.get() == "list":
            self._refresh_list()

    def _get_view_characters(self):
        raw = get_all_characters()
        total = len(raw)

        q = self.search_var.get().strip().lower()
        if q:
            def _match(ch):
                num_txt = f"{int(ch.get('char_number', 0)):03d}"
                name = (ch.get("char_name") or "").lower()
                return (q in num_txt) or (q in name)
            view = [ch for ch in raw if _match(ch)]
        else:
            view = raw

        sort_mode = self.sort_var.get()
        if sort_mode == "최근획득순":
            view.sort(key=lambda ch: ((ch.get("last_seen") or ""), int(ch.get("char_number", 0))), reverse=True)
        elif sort_mode == "등장횟수순":
            view.sort(key=lambda ch: (int(ch.get("total_count", 0)), -int(ch.get("char_number", 0))), reverse=True)
        elif sort_mode == "이름순":
            view.sort(key=lambda ch: (((ch.get("char_name") or "").strip() == ""), (ch.get("char_name") or "").lower(), int(ch.get("char_number", 0))))
        else:
            view.sort(key=lambda ch: int(ch.get("char_number", 0)))

        return view, total

    def _update_status_bar(self, shown: int | None = None, total: int | None = None):
        if shown is None or total is None:
            chars, total = self._get_view_characters()
            shown = len(chars)
        tab_txt = "그리드" if self.tab_var.get() == "grid" else "목록"
        self.status_var.set(
            f"탭: {tab_txt} | 표시: {shown} / 전체: {total} | 줌: {self.card_w}x{self.card_h} | 열: {self.grid_cols}"
        )

    def _update_control_states(self):
        risky_state = "disabled" if self.is_running else "normal"
        self.dedupe_btn.config(state=risky_state)
        self.settings_btn.config(state=risky_state)
        self.clear_targets_btn.config(state=risky_state)

    # ── 로그 ──
    def _log(self, msg: str):
        self.log.config(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.config(state="disabled")
