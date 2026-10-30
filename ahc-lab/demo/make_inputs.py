"""Create 100 small, deterministic demonstration inputs. Never replace existing inputs."""
from pathlib import Path
import random


def main():
    root = Path(__file__).resolve().parent / 'inputs'
    root.mkdir(exist_ok=True)
    for i in range(100):
        path = root / f'{i:04d}.txt'
        if path.exists():
            continue
        rng = random.Random(i)
        n = 20 + i % 5 * 20
        capacity = 40 + (i // 5) % 5 * 40
        items = [(rng.randint(1, 35), rng.randint(1, 200)) for _ in range(n)]
        path.write_text(f'{n} {capacity}\n' + ''.join(f'{w} {v}\n' for w,v in items), encoding='utf-8')
    print('Demo: 100 inputs ready (not AHC contest data).')


if __name__ == '__main__':
    main()
