"""Collect only small, hashed evidence into the paper package."""
from pathlib import Path

if __name__ == "__main__":
    print(Path(__file__).resolve().parents[1] / "reports")
