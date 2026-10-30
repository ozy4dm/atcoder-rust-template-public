"""Demonstration solver, not an AHC solution. Tune --power to compare versions."""
import argparse
import sys

p = argparse.ArgumentParser()
p.add_argument('--power', type=float, default=1)
a = p.parse_args()
tokens = list(map(int, sys.stdin.buffer.read().split()))
n, capacity = tokens[:2]
items = list(zip(tokens[2::2], tokens[3::2]))
order = sorted(range(n), key=lambda i: items[i][1] / items[i][0] ** a.power, reverse=True)
answer = []
for i in order:
    w, v = items[i]
    if w <= capacity:
        answer.append(i)
        capacity -= w
print(*answer)
