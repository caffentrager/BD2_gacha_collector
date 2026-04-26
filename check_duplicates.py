# -*- coding: utf-8 -*-
"""
중복 캐릭터 병합 검사 스크립트
사용법:
  python check_duplicates.py
"""

from data_manager import init_db, run_duplicate_check, get_recent_merge_logs


def main():
    init_db()
    result = run_duplicate_check()
    print("중복 검사 완료")
    print(f"- 검사 대상: {result.get('checked', 0)}종")
    print(f"- 병합 건수: {result.get('merged', 0)}건")

    logs = get_recent_merge_logs(limit=5)
    if logs:
      print("\n최근 병합 로그(최신 5건):")
      for row in logs:
        print(
          f"- #{row['drop_number']:03d} -> #{row['keep_number']:03d} "
          f"(dist={row['hash_distance']}, th={row['threshold']}) @ {row['timestamp']}"
        )


if __name__ == "__main__":
    main()
