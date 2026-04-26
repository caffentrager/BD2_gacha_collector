# -*- coding: utf-8 -*-
"""
브라운더스트2 가챠 데이터 수집기 - 설정
해상도: 2560 x 1440 기준
"""

# ══════════════════════════════════════════
#  화면 해상도
# ══════════════════════════════════════════
GAME_W = 2560
GAME_H = 1440

# ══════════════════════════════════════════
#  클릭 좌표 (2560x1440 기준)
# ══════════════════════════════════════════
# 스킵 버튼 (⏭) - 우상단 빨간 네모 안 버튼 실측 좌표
SKIP_BTN       = (2361, 79)

# "다시! 뽑기" 버튼 (결과 화면 우하단)
REROLL_BTN     = (1949, 1336)

# 팝업 "확인" 버튼
POPUP_OK_BTN   = (1393, 901)

# ══════════════════════════════════════════
#  화면 상태 감지 영역
# ══════════════════════════════════════════
# "다시! 뽑기" 버튼 색상 감지 영역
REROLL_BTN_REGION = (1880, 1310, 2010, 1365)   # (x1,y1,x2,y2)

# 스킵 버튼 감지 영역 (우상단, 빨간 네모 기준 실측)
SKIP_BTN_REGION   = (2316, 46, 2404, 111)

# 팝업 감지 영역
POPUP_REGION      = (900,  800, 1500, 960)

# 스킵버튼 감지: 영역 내 밝은픽셀(>180) 최소 개수
# 실측: 버튼없음=0개, 어두운배경=688~3529개, 밝은배경=17000~18000개
SKIP_BTN_BRIGHT_PIXEL_MIN = 300

# ══════════════════════════════════════════
#  결과 화면 카드 정보 (10장) ← 누끼+빨간선 실측
# ══════════════════════════════════════════
# 카드 10장의 중심 x 좌표
# dd.png 빨간선 기준 카드1 center=546, 누끼이미지 기준 간격=160px
CARD_CENTERS_X = [546, 706, 866, 1026, 1186, 1346, 1506, 1666, 1826, 1986]

# 중앙 분리 레이아웃 보정값
# 6번째 카드(index 5)부터 중앙 추가 간격을 더해 크롭 오프셋 보정
CARD_CENTER_EXTRA_FROM_INDEX = 5
CARD_CENTER_EXTRA = 28

# 카드 전체 y 범위 (크롭용)
CARD_Y_TOP    = 430
CARD_Y_BOTTOM = 1000

# 카드 가로 절반 폭 (dd.png 빨간선 실측: 카드폭 133px / 2 = 66)
CARD_HALF_W   = 66

# 무지개 감지 전용 y 범위 (카드 상단 그라데이션 영역)
RAINBOW_Y_TOP    = 430
RAINBOW_Y_BOTTOM = 570

# ══════════════════════════════════════════
#  5성 감지 파라미터 ← 실측 기반 튜닝값
# ══════════════════════════════════════════
# 5성 실측: 고채도픽셀 6456~10113, 색상분산 21~45
# 비5성 실측: 고채도픽셀 0~1444,   색상분산 0~28
SSR_MIN_HI_SAT_PIXELS  = 3000
SSR_MIN_HUE_VARIANCE   = 18.0
SSR_SAT_THRESHOLD      = 60

# ══════════════════════════════════════════
#  이미지 중복 감지 (pHash)
# ══════════════════════════════════════════
PHASH_THRESHOLD = 12   # 실측: 중복쌍 최대거리=10, 비중복쌍 최소거리=26 → 12로 여유있게 설정
RUN_DUPLICATE_CHECK_EACH_PULL = False

# ══════════════════════════════════════════
#  타이밍 (초)
# ══════════════════════════════════════════
DELAY_AFTER_REROLL  = 0.8
DELAY_AFTER_POPUP   = 0.4
DELAY_AFTER_SKIP    = 0.6
DELAY_STATE_CHECK   = 0.3
MAX_SKIP_ATTEMPTS   = 10     # 결과 화면 도달 최대 스킵 횟수
MAX_PULLS_LIMIT     = 0

# ══════════════════════════════════════════
#  단축키
# ══════════════════════════════════════════
HOTKEY_STOP  = "f9"
HOTKEY_PAUSE = "f8"

# ══════════════════════════════════════════
#  데이터 경로
# ══════════════════════════════════════════
import os
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DATA_DIR    = os.path.join(BASE_DIR, "data")
CHAR_DIR    = os.path.join(DATA_DIR, "characters")
DB_PATH     = os.path.join(DATA_DIR, "gacha.db")
TEMPLATE_DIR= os.path.join(BASE_DIR, "templates")
DEBUG_DIR   = os.path.join(BASE_DIR, "Debug")


def debug_path(filename: str) -> str:
    """디버그 이미지 저장 절대 경로 반환"""
    return os.path.join(DEBUG_DIR, filename)

# 상태 감지 색상 (BGR)
# "다시! 뽑기" 버튼 색상 (청록/시안)
REROLL_BTN_COLOR_HSV_LOW  = (85,  120, 150)   # H, S, V 하한
REROLL_BTN_COLOR_HSV_HIGH = (105, 255, 255)   # H, S, V 상한

# ══════════════════════════════════════════
#  Discord (선택)
# ══════════════════════════════════════════
DISCORD_NOTIFY_ENABLED = False
DISCORD_NOTIFY_ON_START = True
DISCORD_NOTIFY_ON_STOP = True
DISCORD_NOTIFY_ON_TARGET = True
DISCORD_NOTIFY_ON_DEDUPE = False
DISCORD_NOTIFY_ON_ERROR = True
DISCORD_WEBHOOK_URL = ''

# Discord 메시지 템플릿
DISCORD_TEMPLATE_START = '▶ 가챠 수집 시작'
DISCORD_TEMPLATE_STOP = '■ 가챠 수집 종료\n- 회차: {pull_count}회\n- 5성: {ssr_count}개\n- 소요: {elapsed_mm}분{elapsed_ss}초'
DISCORD_TEMPLATE_TARGET = '🎯 목표 캐릭터 달성: #{char_number:03d}'
DISCORD_TEMPLATE_DEDUPE = '🔁 중복 병합 발생: {merged}건 (검사 {checked}종)'
DISCORD_TEMPLATE_ERROR = '⚠ 가챠 수집 오류: {error}'
