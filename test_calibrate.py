# -*- coding: utf-8 -*-
"""
좌표 보정 & 기능 테스트 스크립트

사용법:
  python test_calibrate.py --state       현재 화면 상태 감지
  python test_calibrate.py --ssr         결과 화면 5성 카드 감지
  python test_calibrate.py --skip-pos    스킵 버튼 위치 확인
  python test_calibrate.py --reroll-pos  다시! 뽑기 버튼 색상 확인
"""

import argparse
import time
import os
import cv2

import config as C
from screen_utils import (
    capture_full, detect_state, detect_ssr_cards,
    crop_card, save_debug_screenshot, _has_skip_button,
    _has_reroll_button, _has_popup
)


def test_state():
    print("3초 후 현재 화면 상태를 감지합니다...")
    time.sleep(3)
    screen = capture_full()
    state  = detect_state(screen)
    ssr    = detect_ssr_cards(screen) if state == "RESULT" else []

    print(f"\n감지된 상태: {state}")
    print(f"  스킵 버튼: {_has_skip_button(screen)}")
    print(f"  다시! 뽑기: {_has_reroll_button(screen)}")
    print(f"  팝업: {_has_popup(screen)}")
    if ssr:
        print(f"  5성 카드 인덱스: {ssr}")

    # 디버그 이미지 저장
    out_path = C.debug_path("debug_state.png")
    save_debug_screenshot(screen, state, ssr, out_path)
    print(f"\n디버그 이미지 저장: {out_path}")


def test_ssr_detection():
    print("3초 후 결과 화면에서 5성 카드를 감지합니다...")
    time.sleep(3)
    screen = capture_full()
    ssr_indices = detect_ssr_cards(screen)

    print(f"\n5성 카드 인덱스 (0~9): {ssr_indices}")
    print(f"  총 {len(ssr_indices)}개 감지")

    os.makedirs(C.DEBUG_DIR, exist_ok=True)
    for idx in ssr_indices:
        card = crop_card(screen, idx)
        out_path = C.debug_path(f"debug_card_{idx}.png")
        cv2.imwrite(out_path, card)
        print(f"  카드 {idx} 저장: {out_path}")

    out_path = C.debug_path("debug_ssr.png")
    save_debug_screenshot(screen, "RESULT", ssr_indices, out_path)
    print(f"디버그 이미지 저장: {out_path}")


def test_skip_pos():
    print(f"스킵 버튼 예상 좌표: {C.SKIP_BTN}")
    print(f"스킵 버튼 감지 영역: {C.SKIP_BTN_REGION}")
    print("\n3초 후 스킵 버튼 영역 캡처...")
    time.sleep(3)
    screen = capture_full()
    has_skip = _has_skip_button(screen)
    print(f"스킵 버튼 감지: {has_skip}")

    x1, y1, x2, y2 = C.SKIP_BTN_REGION
    region = screen[y1:y2, x1:x2]
    out_path = C.debug_path("debug_skip_region.png")
    os.makedirs(C.DEBUG_DIR, exist_ok=True)
    cv2.imwrite(out_path, region)
    print(f"스킵 버튼 영역 저장: {out_path}")


def test_reroll_pos():
    print(f"다시! 뽑기 버튼 예상 좌표: {C.REROLL_BTN}")
    print(f"감지 영역: {C.REROLL_BTN_REGION}")
    print("\n3초 후 결과 화면을 켜놓으세요...")
    time.sleep(3)
    screen = capture_full()
    has_btn = _has_reroll_button(screen)
    print(f"다시! 뽑기 버튼 감지: {has_btn}")

    x1, y1, x2, y2 = C.REROLL_BTN_REGION
    region = screen[y1:y2, x1:x2]
    out_path = C.debug_path("debug_reroll_region.png")
    os.makedirs(C.DEBUG_DIR, exist_ok=True)
    cv2.imwrite(out_path, region)

    # 해당 영역의 HSV 분포
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    print(f"영역 평균 HSV: H={hsv[:,:,0].mean():.0f}, S={hsv[:,:,1].mean():.0f}, V={hsv[:,:,2].mean():.0f}")
    print(f"저장: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="좌표 보정 & 테스트")
    parser.add_argument("--state",      action="store_true", help="상태 감지 테스트")
    parser.add_argument("--ssr",        action="store_true", help="5성 카드 감지 테스트")
    parser.add_argument("--skip-pos",   action="store_true", help="스킵 버튼 위치 테스트")
    parser.add_argument("--reroll-pos", action="store_true", help="다시! 뽑기 버튼 테스트")
    args = parser.parse_args()

    if args.state:      test_state()
    elif args.ssr:      test_ssr_detection()
    elif args.skip_pos: test_skip_pos()
    elif args.reroll_pos: test_reroll_pos()
    else:
        parser.print_help()
        print("\n예시: python test_calibrate.py --state")
