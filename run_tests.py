"""Run Qt/native-media test modules in separate processes."""
from pathlib import Path
import subprocess
import sys


def main():
    root = Path(__file__).resolve().parent
    failed = []
    for test in sorted((root / "tests").glob("test_*.py")):
        print(f"\n=== {test.name} ===",flush=True)
        try:
            result = subprocess.run([sys.executable,"-m","unittest","discover","-s","tests",
                                     "-p",test.name,"-v"],cwd=root,timeout=180)
            if result.returncode:
                failed.append(test.name)
        except subprocess.TimeoutExpired:
            failed.append(test.name)
            print("검사 시간 제한 초과",flush=True)
    if failed:
        print("실패: " + ", ".join(failed))
        return 1
    print("모든 검사 모듈 정상 종료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
