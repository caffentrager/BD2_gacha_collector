# -*- coding: utf-8 -*-
"""
핵심 매크로 엔진 - 상태 머신 기반 루프
이름 OCR 없음 → 카드 이미지 크롭 → pHash 중복 판별 → DB 저장
"""

import time
import threading
import queue
import json
import urllib.request
from collections import defaultdict
import numpy as np
import pyautogui
import keyboard

import config as C
from screen_utils import (
    capture_full, detect_state, detect_ssr_cards,
    crop_card
)
from data_manager import (
    init_db, start_session, end_session,
    upsert_character, add_pull_record, add_pull_summary,
    get_target_characters, run_duplicate_check
)

pyautogui.FAILSAFE = True
pyautogui.PAUSE    = 0.04


class MacroEngine:
    def __init__(self, event_queue: queue.Queue):
        """
        event_queue 이벤트:
          ("status",       str)        - 상태 문자열
          ("pull_count",   int)        - 총 뽑기 횟수
          ("ssr_found",    dict)       - {char_id, char_number, image, is_new}
          ("target_found", dict)       - 목표 캐릭터 발견
          ("stopped",      None)       - 종료
        """
        self.queue      = event_queue
        self.stop_flag  = threading.Event()
        self.pause_flag = threading.Event()
        self.thread     = None

        self.session_id = None
        self.pull_count = 0
        self.ssr_count  = 0
        self.start_time = None

    # ── 공개 인터페이스 ──
    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_flag.clear()
        self.pause_flag.clear()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_flag.set()

    def toggle_pause(self):
        if self.pause_flag.is_set():
            self.pause_flag.clear()
            self._emit("status", "▶ 재개")
        else:
            self.pause_flag.set()
            self._emit("status", "⏸ 일시정지")

    def is_running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    # ── 내부 유틸 ──
    def _emit(self, t, d=None):
        self.queue.put((t, d))

    def _send_discord(self, message: str):
        """설정된 웹훅으로 Discord 메시지를 전송한다. 실패 시 무시."""
        try:
            if not getattr(C, "DISCORD_NOTIFY_ENABLED", False):
                return
            url = (getattr(C, "DISCORD_WEBHOOK_URL", "") or "").strip()
            if not url:
                return

            payload = json.dumps({"content": message}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=3):
                pass
        except Exception:
            # 알림 실패는 매크로 동작을 방해하지 않는다.
            return

    def _discord_enabled_for(self, event_flag: str) -> bool:
        if not getattr(C, "DISCORD_NOTIFY_ENABLED", False):
            return False
        return bool(getattr(C, event_flag, False))

    def _render_discord_template(self, template_key: str, default_text: str, **context) -> str:
        tpl = str(getattr(C, template_key, default_text) or default_text)
        safe_context = defaultdict(str, context)
        try:
            return tpl.format_map(safe_context)
        except Exception:
            return default_text

    def _click(self, x, y, delay=0.0):
        if self.stop_flag.is_set():
            return
        pyautogui.click(x, y)
        if delay > 0:
            self._wait(delay)

    def _wait(self, secs: float):
        end = time.time() + secs
        while time.time() < end:
            if self.stop_flag.is_set():
                return
            while self.pause_flag.is_set() and not self.stop_flag.is_set():
                time.sleep(0.1)
            time.sleep(0.05)

    # ── 메인 루프 ──
    def _run(self):
        init_db()
        self.session_id = start_session()
        self.start_time = time.time()
        self.pull_count = 0
        self.ssr_count  = 0

        keyboard.add_hotkey(C.HOTKEY_STOP,  self.stop)
        keyboard.add_hotkey(C.HOTKEY_PAUSE, self.toggle_pause)

        self._emit("status", f"▶ 시작 | F9 중지 / F8 일시정지")
        if self._discord_enabled_for("DISCORD_NOTIFY_ON_START"):
            msg = self._render_discord_template(
                "DISCORD_TEMPLATE_START",
                "▶ 가챠 수집 시작",
                pull_count=self.pull_count,
                ssr_count=self.ssr_count,
            )
            self._send_discord(msg)

        for i in range(3, 0, -1):
            self._emit("status", f"  {i}초 후 시작... (게임 창 클릭)")
            self._wait(1)

        try:
            self._main_loop()
        except pyautogui.FailSafeException:
            self._emit("status", "⚠ 페일세이프 발동")
            if self._discord_enabled_for("DISCORD_NOTIFY_ON_ERROR"):
                msg = self._render_discord_template(
                    "DISCORD_TEMPLATE_ERROR",
                    "⚠ 가챠 수집 오류: {error}",
                    error="페일세이프 발동",
                )
                self._send_discord(msg)
        except Exception as e:
            self._emit("status", f"⚠ 오류: {e}")
            if self._discord_enabled_for("DISCORD_NOTIFY_ON_ERROR"):
                msg = self._render_discord_template(
                    "DISCORD_TEMPLATE_ERROR",
                    "⚠ 가챠 수집 오류: {error}",
                    error=str(e),
                )
                self._send_discord(msg)
            import traceback; traceback.print_exc()
        finally:
            keyboard.remove_all_hotkeys()
            end_session(self.session_id, self.pull_count, self.ssr_count)
            elapsed = int(time.time() - self.start_time)
            mm, ss  = divmod(elapsed, 60)
            self._emit("status",
                f"■ 종료 | {self.pull_count}회 뽑기 | 5성 {self.ssr_count}회 | {mm}분{ss}초")
            if self._discord_enabled_for("DISCORD_NOTIFY_ON_STOP"):
                msg = self._render_discord_template(
                    "DISCORD_TEMPLATE_STOP",
                    "■ 가챠 수집 종료\n- 회차: {pull_count}회\n- 5성: {ssr_count}개\n- 소요: {elapsed_mm}분{elapsed_ss}초",
                    pull_count=self.pull_count,
                    ssr_count=self.ssr_count,
                    elapsed_mm=mm,
                    elapsed_ss=ss,
                )
                self._send_discord(msg)
            self._emit("stopped", None)

    def _main_loop(self):
        unknown_streak = 0

        while not self.stop_flag.is_set():
            while self.pause_flag.is_set() and not self.stop_flag.is_set():
                time.sleep(0.1)

            screen = capture_full()
            state  = detect_state(screen)

            elapsed = int(time.time() - self.start_time)
            mm, ss  = divmod(elapsed, 60)
            self._emit("status",
                f"[{mm:02d}:{ss:02d}] {self.pull_count}회 | 5성 {self.ssr_count}회 | {state}")

            if state == "RESULT":
                unknown_streak = 0
                self._handle_result(screen)

            elif state == "POPUP":
                unknown_streak = 0
                self._click(*C.POPUP_OK_BTN, delay=C.DELAY_AFTER_POPUP)

            elif state == "ANIMATION":
                unknown_streak = 0
                self._click(*C.SKIP_BTN, delay=C.DELAY_AFTER_SKIP)

            else:
                # UNKNOWN: 즉시 스킵 시도 (컷씬 중 버튼 미감지 대비)
                unknown_streak += 1
                if unknown_streak >= 3:
                    # 3회 연속 UNKNOWN → 스킵 버튼 한 번 눌러보기
                    self._click(*C.SKIP_BTN, delay=C.DELAY_AFTER_SKIP)
                    unknown_streak = 0
                else:
                    self._wait(C.DELAY_STATE_CHECK)

    def _handle_result(self, screen: np.ndarray):
        self.pull_count += 1
        self._emit("pull_count", self.pull_count)

        ssr_indices = detect_ssr_cards(screen)
        n_ssr = len(ssr_indices)
        self._emit("status", f"  결과 화면 | 5성 {n_ssr}개 (확정1 + 추가{max(0,n_ssr-1)})")

        targets    = {ch["id"] for ch in get_target_characters()}
        target_hit = False

        for idx in ssr_indices:
            if self.stop_flag.is_set():
                return

            card_img = crop_card(screen, idx)
            char_id, char_number, is_new = upsert_character(card_img)
            add_pull_record(self.session_id, self.pull_count, char_id, n_ssr, idx + 1)
            self.ssr_count += 1

            self._emit("ssr_found", {
                "char_id":     char_id,
                "char_number": char_number,
                "card_slot":   idx + 1,
                "image":       card_img,
                "is_new":      is_new,
            })

            if char_id in targets:
                self._emit("target_found", {"char_id": char_id, "char_number": char_number})
                if self._discord_enabled_for("DISCORD_NOTIFY_ON_TARGET"):
                    msg = self._render_discord_template(
                        "DISCORD_TEMPLATE_TARGET",
                        "🎯 목표 캐릭터 달성: #{char_number:03d}",
                        char_number=char_number,
                        pull_count=self.pull_count,
                    )
                    self._send_discord(msg)
                target_hit = True

        # 회차 요약 기록 (5성이 0개인 경우도 포함)
        add_pull_summary(self.session_id, self.pull_count, n_ssr)

        # 회차마다 중복 병합 검사 실행 (옵션)
        if C.RUN_DUPLICATE_CHECK_EACH_PULL:
            dedupe = run_duplicate_check()
            if dedupe.get("merged", 0) > 0:
                self._emit(
                    "status",
                    f"  중복 병합: {dedupe['merged']}건 (검사 {dedupe['checked']}종)"
                )
                for info in dedupe.get("details", [])[:5]:
                    sim_txt = ""
                    if info.get("similarity") is not None:
                        sim_txt = f", sim={info['similarity']:.3f}"
                    self._emit(
                        "status",
                        f"    병합 #{info['drop_number']:03d} -> #{info['keep_number']:03d} "
                        f"(dist={info['hash_distance']}{sim_txt})"
                    )
                if self._discord_enabled_for("DISCORD_NOTIFY_ON_DEDUPE"):
                    msg = self._render_discord_template(
                        "DISCORD_TEMPLATE_DEDUPE",
                        "🔁 중복 병합 발생: {merged}건 (검사 {checked}종)",
                        merged=dedupe["merged"],
                        checked=dedupe["checked"],
                        pull_count=self.pull_count,
                    )
                    self._send_discord(msg)
                self._emit("dedupe_done", dedupe)

        if target_hit:
            self.stop_flag.set()
            return

        if C.MAX_PULLS_LIMIT > 0 and self.pull_count >= C.MAX_PULLS_LIMIT:
            self._emit("status", f"  설정된 반복 횟수 도달: {C.MAX_PULLS_LIMIT}회")
            self.stop_flag.set()
            return

        self._wait(0.3)
        self._click(*C.REROLL_BTN, delay=C.DELAY_AFTER_REROLL)
