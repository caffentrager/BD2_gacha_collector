# -*- coding: utf-8 -*-
"""
데이터베이스 & 파일 관리
- 무한가챠 구조: 1장 확정 SSR + 나머지 9장
- 통계: 회차별 SSR 수 분포 (1개/2개/3개+) 추적
"""

import sqlite3
import os
from datetime import datetime
import numpy as np
import cv2
from PIL import Image
import imagehash

from config import DB_PATH, CHAR_DIR, DATA_DIR, PHASH_THRESHOLD


def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(CHAR_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS characters (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            char_number INTEGER UNIQUE NOT NULL,
            char_name   TEXT DEFAULT '',
            image_path  TEXT,
            phash       TEXT NOT NULL,
            first_seen  TEXT NOT NULL,
            total_count INTEGER DEFAULT 1,
            is_target   INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at  TEXT NOT NULL,
            ended_at    TEXT,
            total_pulls INTEGER DEFAULT 0,
            ssr_count   INTEGER DEFAULT 0
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS pull_records (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            pull_number     INTEGER NOT NULL,
            char_id         INTEGER,
            card_slot       INTEGER,
            ssr_this_pull   INTEGER DEFAULT 1,
            timestamp       TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id),
            FOREIGN KEY (char_id)    REFERENCES characters(id)
        )
    """)

    # pull_summary: 기존 DB에 없을 수 있으므로 안전하게 생성
    c.execute("""
        CREATE TABLE IF NOT EXISTS pull_summary (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            pull_number     INTEGER NOT NULL,
            ssr_count       INTEGER NOT NULL,
            timestamp       TEXT NOT NULL,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        )
    """)

    # 중복 병합 로그
    c.execute("""
        CREATE TABLE IF NOT EXISTS merge_logs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            keep_char_id    INTEGER NOT NULL,
            drop_char_id    INTEGER NOT NULL,
            keep_number     INTEGER,
            drop_number     INTEGER,
            hash_distance   INTEGER,
            threshold       INTEGER NOT NULL,
            timestamp       TEXT NOT NULL
        )
    """)

    # pull_records에 ssr_this_pull 컬럼 없으면 추가 (마이그레이션)
    try:
        c.execute("ALTER TABLE pull_records ADD COLUMN ssr_this_pull INTEGER DEFAULT 1")
    except sqlite3.OperationalError:
        pass  # 이미 존재

    # pull_records에 card_slot 컬럼 없으면 추가 (마이그레이션)
    try:
        c.execute("ALTER TABLE pull_records ADD COLUMN card_slot INTEGER")
    except sqlite3.OperationalError:
        pass  # 이미 존재

    # characters에 char_name 컬럼 없으면 추가 (마이그레이션)
    try:
        c.execute("ALTER TABLE characters ADD COLUMN char_name TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass  # 이미 존재

    conn.commit()
    conn.close()


# ══════════════════════════════════════════
#  pHash 유틸
# ══════════════════════════════════════════
def _normalize_card_for_hash(card_bgr: np.ndarray) -> Image.Image:
    """
    테두리/배지/반짝임 영향을 줄이기 위해 카드 중심부만 사용해 해시용 이미지를 만든다.
    """
    h, w = card_bgr.shape[:2]
    x1 = int(w * 0.14)
    x2 = int(w * 0.86)
    y1 = int(h * 0.18)
    y2 = int(h * 0.84)

    core = card_bgr[y1:y2, x1:x2]
    if core.size == 0:
        core = card_bgr

    gray = cv2.cvtColor(core, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return Image.fromarray(gray)


def _normalize_card_for_compare(card_bgr: np.ndarray) -> np.ndarray:
    """중복 비교용 정규화 이미지 (grayscale, fixed size)."""
    h, w = card_bgr.shape[:2]
    x1 = int(w * 0.14)
    x2 = int(w * 0.86)
    y1 = int(h * 0.18)
    y2 = int(h * 0.84)

    core = card_bgr[y1:y2, x1:x2]
    if core.size == 0:
        core = card_bgr

    gray = cv2.cvtColor(core, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    return cv2.resize(gray, (96, 160), interpolation=cv2.INTER_AREA)


def _shifted_similarity(a: np.ndarray, b: np.ndarray, max_shift: int = 10) -> float:
    """좌우 미세 오프셋을 허용한 최대 피어슨 유사도 반환."""
    if a is None or b is None or a.shape != b.shape:
        return -1.0

    af = a.astype(np.float32)
    bf = b.astype(np.float32)
    best = -1.0

    for s in range(-max_shift, max_shift + 1):
        if s < 0:
            aa = af[:, :s]
            bb = bf[:, -s:]
        elif s > 0:
            aa = af[:, s:]
            bb = bf[:, :-s]
        else:
            aa = af
            bb = bf

        if aa.size == 0 or bb.size == 0:
            continue

        va = aa - aa.mean()
        vb = bb - bb.mean()
        denom = float(np.sqrt((va * va).sum() * (vb * vb).sum()))
        if denom <= 1e-6:
            continue
        sim = float((va * vb).sum() / denom)
        if sim > best:
            best = sim

    return best


def _is_probable_duplicate(hash_dist: int, sim: float) -> bool:
    """
    보수적 병합 기준:
    - 기본: 해시 거리 <= PHASH_THRESHOLD
    - 보완: 해시 거리 <= PHASH_THRESHOLD+5 AND 유사도 >= 0.93
    """
    if hash_dist <= PHASH_THRESHOLD:
        return True
    return (hash_dist <= PHASH_THRESHOLD + 5) and (sim >= 0.93)


def _compute_phash(card_bgr: np.ndarray) -> imagehash.ImageHash:
    return imagehash.phash(_normalize_card_for_hash(card_bgr))


def _find_matching_char(conn, new_hash, new_cmp: np.ndarray | None = None) -> tuple | None:
    c = conn.cursor()
    c.execute("SELECT id, char_number, phash, image_path FROM characters")
    for row in c.fetchall():
        char_id, char_number, phash_str, image_path = row
        old_hash = None
        try:
            old_hash = imagehash.hex_to_hash(phash_str)
        except Exception:
            pass

        # 항상 최신 전처리 기준으로 재해시해서 비교 (과거 저장 포맷/방식 차이 제거)
        ref_cmp = None
        if image_path and os.path.exists(image_path):
            try:
                ref_img = cv2.imread(image_path)
                if ref_img is not None:
                    ref_hash = _compute_phash(ref_img)
                    ref_cmp = _normalize_card_for_compare(ref_img)
                    if str(ref_hash) != phash_str:
                        c.execute("UPDATE characters SET phash=? WHERE id=?", (str(ref_hash), char_id))
                        conn.commit()
                    old_hash = ref_hash
            except Exception:
                pass

        if old_hash is None:
            continue

        hash_dist = int(abs(new_hash - old_hash))
        sim = _shifted_similarity(new_cmp, ref_cmp) if (new_cmp is not None and ref_cmp is not None) else -1.0
        if _is_probable_duplicate(hash_dist, sim):
            return (char_id, char_number)
    return None


def run_duplicate_check() -> dict:
    """
    저장된 캐릭터를 스캔해 pHash 기준 중복을 병합한다.
    반환: {"checked": int, "merged": int, "details": list}
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("SELECT id, char_number, total_count, is_target, image_path, phash FROM characters")
    raw_rows = c.fetchall()
    if len(raw_rows) < 2:
        conn.close()
        return {"checked": len(raw_rows), "merged": 0, "details": []}

    chars = []
    for row in raw_rows:
        cid, cnum, tcnt, itarget, ipath, phash_str = row
        h = None
        cmp_img = None
        if ipath and os.path.exists(ipath):
            try:
                img = cv2.imread(ipath)
                if img is not None:
                    h = _compute_phash(img)
                    cmp_img = _normalize_card_for_compare(img)
                    if str(h) != phash_str:
                        c.execute("UPDATE characters SET phash=? WHERE id=?", (str(h), cid))
            except Exception:
                h = None

        if h is None:
            try:
                h = imagehash.hex_to_hash(phash_str)
            except Exception:
                h = None

        chars.append({
            "id": cid,
            "char_number": cnum,
            "total_count": int(tcnt or 0),
            "is_target": int(itarget or 0),
            "image_path": ipath,
            "hash": h,
            "cmp": cmp_img,
        })

    chars.sort(key=lambda x: x["char_number"])
    removed_ids = set()
    merged = 0
    details = []

    for i in range(len(chars)):
        keep = chars[i]
        if keep["id"] in removed_ids or keep["hash"] is None:
            continue

        for j in range(i + 1, len(chars)):
            drop = chars[j]
            if drop["id"] in removed_ids or drop["hash"] is None:
                continue

            hash_distance = int(abs(keep["hash"] - drop["hash"]))
            sim = _shifted_similarity(keep.get("cmp"), drop.get("cmp"))
            if not _is_probable_duplicate(hash_distance, sim):
                continue

            # 참조를 보존하면서 drop -> keep으로 병합
            c.execute("UPDATE pull_records SET char_id=? WHERE char_id=?", (keep["id"], drop["id"]))

            keep_total = keep["total_count"] + drop["total_count"]
            keep_target = 1 if (keep["is_target"] or drop["is_target"]) else 0
            keep_img = keep["image_path"] or drop["image_path"]

            c.execute(
                "UPDATE characters SET total_count=?, is_target=?, image_path=? WHERE id=?",
                (keep_total, keep_target, keep_img, keep["id"])
            )
            c.execute("DELETE FROM characters WHERE id=?", (drop["id"],))

            c.execute(
                """INSERT INTO merge_logs
                   (keep_char_id, drop_char_id, keep_number, drop_number, hash_distance, threshold, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    keep["id"],
                    drop["id"],
                    keep["char_number"],
                    drop["char_number"],
                    hash_distance,
                    PHASH_THRESHOLD,
                    datetime.now().isoformat(),
                )
            )

            # 병합된 쪽의 이미지는 고아 파일이므로 정리 시도
            if drop["image_path"] and drop["image_path"] != keep_img and os.path.exists(drop["image_path"]):
                try:
                    os.remove(drop["image_path"])
                except Exception:
                    pass

            keep["total_count"] = keep_total
            keep["is_target"] = keep_target
            keep["image_path"] = keep_img

            removed_ids.add(drop["id"])
            merged += 1
            details.append({
                "keep_number": keep["char_number"],
                "drop_number": drop["char_number"],
                "hash_distance": hash_distance,
                "similarity": round(sim, 4) if sim >= 0 else None,
            })

    conn.commit()
    conn.close()
    return {"checked": len(raw_rows), "merged": merged, "details": details}


# ══════════════════════════════════════════
#  세션
# ══════════════════════════════════════════
def start_session() -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO sessions (started_at) VALUES (?)",
              (datetime.now().isoformat(),))
    sid = c.lastrowid
    conn.commit()
    conn.close()
    return sid


def end_session(session_id: int, total_pulls: int, ssr_count: int):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""UPDATE sessions SET ended_at=?, total_pulls=?, ssr_count=?
                 WHERE id=?""",
              (datetime.now().isoformat(), total_pulls, ssr_count, session_id))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════
#  캐릭터 추가 / 중복 카운트
# ══════════════════════════════════════════
def upsert_character(card_image: np.ndarray) -> tuple:
    """반환: (char_id, char_number, is_new)"""
    new_hash = _compute_phash(card_image)
    new_cmp = _normalize_card_for_compare(card_image)
    now = datetime.now().isoformat()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    match = _find_matching_char(conn, new_hash, new_cmp)
    if match:
        char_id, char_number = match
        c.execute("UPDATE characters SET total_count = total_count + 1 WHERE id=?",
                  (char_id,))
        conn.commit()
        conn.close()
        return char_id, char_number, False

    c.execute("SELECT COALESCE(MAX(char_number), 0) FROM characters")
    next_num = c.fetchone()[0] + 1

    img_path = os.path.join(CHAR_DIR, f"char_{next_num:03d}.png")
    cv2.imwrite(img_path, card_image)

    c.execute("""INSERT INTO characters (char_number, image_path, phash, first_seen, total_count)
                 VALUES (?, ?, ?, ?, 1)""",
              (next_num, img_path, str(new_hash), now))
    char_id = c.lastrowid
    conn.commit()
    conn.close()
    return char_id, next_num, True


def add_pull_record(session_id: int, pull_number: int,
                    char_id: int, ssr_this_pull: int, card_slot: int):
    """개별 캐릭터 기록 + 이 회차의 SSR 수 + 카드 위치(1~10)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO pull_records
                 (session_id, pull_number, char_id, card_slot, ssr_this_pull, timestamp)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (session_id, pull_number, char_id, card_slot, ssr_this_pull,
               datetime.now().isoformat()))
    conn.commit()
    conn.close()


def add_pull_summary(session_id: int, pull_number: int, ssr_count: int):
    """회차 요약 기록 (통계용)"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""INSERT INTO pull_summary
                 (session_id, pull_number, ssr_count, timestamp)
                 VALUES (?, ?, ?, ?)""",
              (session_id, pull_number, ssr_count, datetime.now().isoformat()))
    conn.commit()
    conn.close()


# ══════════════════════════════════════════
#  조회
# ══════════════════════════════════════════
def get_all_characters() -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("""
        SELECT c.id,
               c.char_number,
               c.char_name,
               c.image_path,
               c.first_seen,
               c.total_count,
               c.is_target,
               (
                   SELECT pr.card_slot
                   FROM pull_records pr
                   WHERE pr.char_id = c.id
                   ORDER BY pr.id DESC
                   LIMIT 1
               ) AS last_card_slot,
               (
                   SELECT pr.timestamp
                   FROM pull_records pr
                   WHERE pr.char_id = c.id
                   ORDER BY pr.id DESC
                   LIMIT 1
               ) AS last_seen
        FROM characters c
        ORDER BY c.char_number ASC
    """)
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def get_stats() -> dict:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # 회차/SSR 통계는 pull_summary 기준으로 계산 (회차당 확정 1SSR 전제)
    c.execute("SELECT COALESCE(COUNT(*),0), COALESCE(SUM(ssr_count),0) FROM pull_summary")
    row = c.fetchone()
    total_rounds = int(row[0])
    total_ssr    = int(row[1])

    # 구버전 데이터 호환: pull_summary가 비어있으면 sessions로 fallback
    if total_rounds == 0 and total_ssr == 0:
        c.execute("SELECT COALESCE(SUM(total_pulls),0), COALESCE(SUM(ssr_count),0) FROM sessions")
        row2 = c.fetchone()
        total_rounds = int(row2[0])
        total_ssr = int(row2[1])

    c.execute("SELECT COUNT(*) FROM characters")
    unique_ssr = int(c.fetchone()[0])

    # pull_summary 기반 분포
    try:
        c.execute("SELECT COUNT(*) FROM pull_summary WHERE ssr_count = 1")
        pulls_1ssr = int(c.fetchone()[0])
        c.execute("SELECT COUNT(*) FROM pull_summary WHERE ssr_count = 2")
        pulls_2ssr = int(c.fetchone()[0])
        c.execute("SELECT COUNT(*) FROM pull_summary WHERE ssr_count >= 3")
        pulls_3plus = int(c.fetchone()[0])
    except Exception:
        pulls_1ssr = pulls_2ssr = pulls_3plus = 0

    conn.close()

    guaranteed_ssr = total_rounds  # 무한가챠 룰: 회차당 1개 확정
    extra_ssr   = max(0, total_ssr - guaranteed_ssr)
    extra_pool  = total_rounds * 9
    extra_rate  = (extra_ssr / extra_pool * 100) if extra_pool > 0 else 0.0

    return {
        "total_rounds":  total_rounds,
        "total_ssr":     total_ssr,
        "guaranteed_ssr": guaranteed_ssr,
        "extra_ssr":     extra_ssr,
        "extra_rate":    extra_rate,
        "unique_ssr":    unique_ssr,
        "pulls_1ssr":    pulls_1ssr,
        "pulls_2ssr":    pulls_2ssr,
        "pulls_3plus":   pulls_3plus,
    }


def get_recent_merge_logs(limit: int = 50) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(
        """SELECT keep_char_id, drop_char_id, keep_number, drop_number,
                  hash_distance, threshold, timestamp
           FROM merge_logs
           ORDER BY id DESC
           LIMIT ?""",
        (limit,)
    )
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def set_target(char_id: int, is_target: bool):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE characters SET is_target=? WHERE id=?",
              (1 if is_target else 0, char_id))
    conn.commit()
    conn.close()


def set_character_name(char_id: int, char_name: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE characters SET char_name=? WHERE id=?", (char_name.strip(), char_id))
    conn.commit()
    conn.close()


def get_target_characters() -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM characters WHERE is_target=1")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return rows


def clear_all_targets():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE characters SET is_target=0")
    conn.commit()
    conn.close()
