# -*- coding: utf-8 -*-
"""
화면 캡처 & 상태 감지 모듈

상태 목록:
  RESULT      - 결과 화면 (다시! 뽑기 버튼 보임)
  ANIMATION   - 뽑기 애니메이션 (스킵 버튼 보임)
  CHAR_DETAIL - 카드 클릭 후 캐릭터 상세 (스킵 버튼 보임)
  POPUP       - 스페셜 무한 뽑기 팝업
  UNKNOWN     - 로딩/전환 중
"""

import cv2
import numpy as np
from PIL import ImageGrab, Image
from pathlib import Path
import os

import config as C


# ══════════════════════════════════════════
#  화면 캡처
# ══════════════════════════════════════════
def capture_full() -> np.ndarray:
    """전체 화면 캡처 → BGR numpy array"""
    shot = ImageGrab.grab()
    return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)


def capture_region(x1: int, y1: int, x2: int, y2: int) -> np.ndarray:
    shot = ImageGrab.grab(bbox=(x1, y1, x2, y2))
    return cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)


def capture_region_pil(x1: int, y1: int, x2: int, y2: int) -> Image.Image:
    return ImageGrab.grab(bbox=(x1, y1, x2, y2))


# ══════════════════════════════════════════
#  상태 감지
# ══════════════════════════════════════════
def _is_color_in_region(region_bgr: np.ndarray,
                         hsv_low: tuple, hsv_high: tuple,
                         min_pixel_ratio: float = 0.05) -> bool:
    """해당 HSV 범위의 색상이 영역에서 min_pixel_ratio 이상 존재하면 True"""
    hsv = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv,
                       np.array(hsv_low, dtype=np.uint8),
                       np.array(hsv_high, dtype=np.uint8))
    ratio = mask.sum() / (mask.size * 255)
    return ratio >= min_pixel_ratio


# 스킵 버튼 템플릿 (1회만 로드)
_skip_template = None

def _get_skip_template() -> np.ndarray | None:
    global _skip_template
    if _skip_template is None:
        tpl_path = os.path.join(C.TEMPLATE_DIR, "skip_btn.png")
        if Path(tpl_path).exists():
            _skip_template = cv2.imread(tpl_path, cv2.IMREAD_COLOR)
    return _skip_template


def _has_skip_button(screen: np.ndarray) -> bool:
    """
    스킵 버튼(⏭) 존재 여부 확인.

    영상 실측 기준 (1920x1080):
      - 스킵버튼 없음(팝업/전환): 밝은픽셀(>180) = 0개
      - 스킵버튼 있음 - 어두운 배경 컷씬: 밝은픽셀 = 688~3529개
      - 스킵버튼 있음 - 밝은 배경: 밝은픽셀 = 17000~18000개
    → 임계값: 밝은픽셀 > 300 이면 스킵버튼 있음

    배경 밝기에 관계없이 버튼 아이콘 자체의 흰 픽셀을 감지.
    """
    x1, y1, x2, y2 = C.SKIP_BTN_REGION
    h, w = screen.shape[:2]

    # 해상도 스케일 보정 (기준: 2560x1440)
    scale_x = w / 2560
    scale_y = h / 1440
    sx1 = int(x1 * scale_x)
    sy1 = int(y1 * scale_y)
    sx2 = int(x2 * scale_x)
    sy2 = int(y2 * scale_y)

    region = screen[sy1:sy2, sx1:sx2]
    if region.size == 0:
        return False

    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)

    # 버튼 아이콘의 흰 픽셀 수로 판단
    bright_pixels = int((gray > 180).sum())
    return bright_pixels > C.SKIP_BTN_BRIGHT_PIXEL_MIN


def _has_reroll_button(screen: np.ndarray) -> bool:
    """'다시! 뽑기' 청록색 버튼 감지"""
    x1, y1, x2, y2 = C.REROLL_BTN_REGION
    region = screen[y1:y2, x1:x2]
    return _is_color_in_region(
        region,
        C.REROLL_BTN_COLOR_HSV_LOW,
        C.REROLL_BTN_COLOR_HSV_HIGH,
        min_pixel_ratio=0.08
    )


def _has_popup(screen: np.ndarray) -> bool:
    """
    '스페셜 무한 뽑기' 팝업 감지.
    팝업 시 화면 전체가 어두워짐(어두운 오버레이).
    """
    # 화면 전체 평균 밝기 < 임계값이면 팝업 오버레이 있다고 판단
    x1, y1, x2, y2 = C.POPUP_REGION
    region = screen[y1:y2, x1:x2]
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    mean_brightness = gray.mean()

    # 팝업이 있으면 어두운 배경 + 밝은 창 존재
    # 분산이 높고 평균이 중간 정도면 팝업 상태
    std = gray.std()
    return (mean_brightness < 160) and (std > 20)


GameState = str  # 타입 힌트용


def _card_center_x(card_idx: int, screen_w: int) -> int:
    """카드 중심 x 좌표를 반환 (6번째 카드부터 중앙 추가 간격 보정)."""
    cx = C.CARD_CENTERS_X[card_idx]
    if card_idx >= C.CARD_CENTER_EXTRA_FROM_INDEX:
        cx += C.CARD_CENTER_EXTRA
    scale_x = screen_w / 2560
    return int(cx * scale_x)

def detect_state(screen: np.ndarray) -> GameState:
    """
    현재 게임 상태를 반환.
    우선순위: RESULT > POPUP > ANIMATION > UNKNOWN
    """
    if _has_reroll_button(screen):
        return "RESULT"
    if _has_popup(screen):
        return "POPUP"
    if _has_skip_button(screen):
        return "ANIMATION"
    return "UNKNOWN"


# ══════════════════════════════════════════
#  5성 카드 감지
# ══════════════════════════════════════════
def detect_ssr_cards(screen: np.ndarray) -> list[int]:
    """
    결과 화면에서 5성(무지개 테두리) 카드의 인덱스 목록 반환 (0~9).
    감지 영역: 카드 상단 무지개 그라데이션 (RAINBOW_Y_TOP ~ RAINBOW_Y_BOTTOM)
    """
    h, w = screen.shape[:2]
    scale_y = h / 1440

    y1 = int(C.RAINBOW_Y_TOP    * scale_y)
    y2 = int(C.RAINBOW_Y_BOTTOM * scale_y)

    ssr_indices = []
    for i in range(len(C.CARD_CENTERS_X)):
        cx = _card_center_x(i, w)
        x1 = max(0, cx - C.CARD_HALF_W)
        x2 = min(w, cx + C.CARD_HALF_W)
        region = screen[y1:y2, x1:x2]
        if region.size == 0:
            continue
        if _is_ssr_card(region):
            ssr_indices.append(i)

    return ssr_indices


def _is_ssr_card(region_bgr: np.ndarray) -> bool:
    """
    카드 상단 무지개 영역으로 5성 판별.
    실측 기준:
      5성:  고채도픽셀 6456~10113, 색상분산 21~45
      비5성: 고채도픽셀 0~1444,   색상분산 0~28
    임계값: 고채도픽셀 > 3000 AND 색상분산 > 18
    """
    hsv = cv2.cvtColor(region_bgr, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    hue = hsv[:, :, 0].astype(float)

    hi_sat_mask = sat > C.SSR_SAT_THRESHOLD
    n_hi = int(hi_sat_mask.sum())

    if n_hi < C.SSR_MIN_HI_SAT_PIXELS:
        return False

    hue_std = float(np.std(hue[hi_sat_mask]))
    return hue_std >= C.SSR_MIN_HUE_VARIANCE


def crop_card(screen: np.ndarray, card_idx: int) -> np.ndarray:
    """결과 화면에서 특정 카드 이미지 크롭 (전체 카드 영역)"""
    h, w   = screen.shape[:2]
    scale_y = h / 1440
    cx = _card_center_x(card_idx, w)
    x1 = max(0, cx - C.CARD_HALF_W)
    x2 = min(w, cx + C.CARD_HALF_W)
    y1 = int(C.CARD_Y_TOP    * scale_y)
    y2 = int(C.CARD_Y_BOTTOM * scale_y)
    return screen[y1:y2, x1:x2].copy()


def get_card_click_pos(card_idx: int) -> tuple[int, int]:
    """카드 클릭 좌표 (중심점)"""
    cx = C.CARD_CENTERS_X[card_idx]
    if card_idx >= C.CARD_CENTER_EXTRA_FROM_INDEX:
        cx += C.CARD_CENTER_EXTRA
    cy = (C.CARD_Y_TOP + C.CARD_Y_BOTTOM) // 2
    return (cx, cy)


# ══════════════════════════════════════════
#  색상 분포 시각화 (디버그용)
# ══════════════════════════════════════════
def save_debug_screenshot(screen: np.ndarray, state: str, ssr_indices: list, filepath: str):
    debug = screen.copy()
    h, w = debug.shape[:2]
    scale_y = h / 1440
    y1 = int(C.CARD_Y_TOP * scale_y)
    y2 = int(C.CARD_Y_BOTTOM * scale_y)
    # 상태 텍스트
    cv2.putText(debug, f"STATE: {state}", (30, 50),
                cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 3)
    # 5성 카드 표시
    for idx in ssr_indices:
        cx = _card_center_x(idx, w)
        cv2.rectangle(debug,
                      (cx - C.CARD_HALF_W, y1),
                      (cx + C.CARD_HALF_W, y2),
                      (0, 255, 255), 4)
        cv2.putText(debug, "5★", (cx - 20, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
    out_path = filepath
    if not os.path.isabs(out_path):
        out_path = os.path.join(C.DEBUG_DIR, out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, debug)
