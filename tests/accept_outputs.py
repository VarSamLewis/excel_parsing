#!/usr/bin/env python3
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    while True:
        ans = input("Accept outputs? (Y/N): ").lower().strip()
        if ans == "y":
            shutil.rmtree(ROOT / "artifacts")
            print("Outputs cleared")
            return
        elif ans == "n":
            print("Outputs failed user acceptance")
            sys.exit(1)
        print("Please enter Y or N")


if __name__ == "__main__":
    main()
