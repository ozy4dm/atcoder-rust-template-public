"""Demonstration judge. Invalid output deliberately has exit code 0 and Score=0."""
from pathlib import Path
import sys

tokens = list(map(int, Path(sys.argv[1]).read_text().split()))
n, capacity = tokens[:2]
items = list(zip(tokens[2::2], tokens[3::2]))
try:
    selected = list(map(int, Path(sys.argv[2]).read_text().split()))
    if len(selected) != len(set(selected)) or any(not 0 <= i < n for i in selected):
        raise ValueError('invalid item list')
    if sum(items[i][0] for i in selected) > capacity:
        raise ValueError('capacity exceeded')
    print('Score =', sum(items[i][1] for i in selected))
except ValueError as e:
    print('Error:', e)
    print('Score = 0')
