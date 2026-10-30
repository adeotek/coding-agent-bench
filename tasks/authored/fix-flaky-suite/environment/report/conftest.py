"""Put the package root on sys.path so the suite runs from a bare checkout."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
