"""ds-analytics: dream-studio analytics pipeline."""
from __future__ import annotations
import argparse
import sys

def main() -> None:
    ap = argparse.ArgumentParser(description="ds-analytics — harvest, analyze, render")
    ap.parse_args()
    print("DSAE: no data yet")

if __name__ == "__main__":
    main()
