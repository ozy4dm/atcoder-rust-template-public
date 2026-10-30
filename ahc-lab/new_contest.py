"""Create a local AHC workspace using only the shared, pre-contest template."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re


def create_contest(root: Path, contest: str, port: int | None = None) -> Path:
    root = root.resolve()
    if not re.fullmatch(r'ahc[0-9]{3,}', contest):
        raise ValueError('大会IDは ahc に続く3桁以上の番号で指定してください')
    template = root / 'ahc-human' / 'main.rs'
    if not template.is_file() or not (root / 'ahc-lab' / 'lab.py').is_file():
        raise ValueError('共通の ahc-human/main.rs と ahc-lab/lab.py があるリポジトリを指定してください')
    target = (root / 'contests' / contest).resolve()
    if not target.is_relative_to(root):
        raise ValueError('作業先がリポジトリの外にあります')
    port = 8700 + int(contest[3:]) % 100 if port is None else port
    if not 0 <= port <= 65535:
        raise ValueError('portは0〜65535')
    # Read before creating anything. Existing workspaces are never reset or merged.
    main = template.read_bytes()
    target.mkdir(parents=True, exist_ok=False)
    for name in ('inputs', 'tools', 'runs', 'submissions'):
        (target / name).mkdir()
    (target / 'main.rs').write_bytes(main)
    config = {
        'name': contest.upper(), 'root': '.', 'source': 'main.rs',
        'submissions': 'submissions', 'inputs': 'inputs', 'runs': 'runs',
        'ready': False,
        'setup_message': '公式ツール・入力・入出力方式・採点方向を設定し、readyをtrueにしてください。',
        'direction': None, 'mode': None,
        'build_command': ['rustc', '--edition=2021', '-O', '{source}', '-o', '{binary}'],
        'solver_command': ['{solver}'], 'judge_command': [],
        'timeout_seconds': 10, 'judge_timeout_seconds': 10,
        'build_timeout_seconds': 120, 'workers': 1, 'features': []
    }
    (target / 'lab.json').write_text(json.dumps(config, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    lines = ['@echo off', 'setlocal', r'cd /d "%~dp0..\.."',
             f'python -X utf8 "%~dp0..\\..\\ahc-lab\\lab.py" serve --config "%~dp0lab.json" --port {port} --open %*',
             'if errorlevel 1 goto failed', 'exit /b 0', ':failed',
             'echo AHC Lab could not start. Please check the messages above.', 'pause', 'exit /b 1']
    (target / 'open-lab.cmd').write_bytes(('\r\n'.join(lines)+'\r\n').encode('ascii'))
    (target / 'notes.md').write_text(f'# {contest.upper()} メモ\n\n## 得点・制約\n\n## 解の表現\n\n## 最初の合法解\n\n## 変更と結果\n', encoding='utf-8')
    (target / 'README.md').write_text(f'''# {contest.upper()} の作業場所

`main.rs` を編集・保存し、`open-lab.cmd` から画面を開きます。
共通部品は [library.rs](../../ahc-human/library.rs)、構造の見本は [examples](../../ahc-human/examples/README.md) を参照してください。

## 最初の設定

1. 公式入力を `inputs/`、公式ツールを `tools/` に置く。
2. `lab.json` の `direction`（max/min）、`mode`（offline/interactive）、採点コマンド、制限時間を設定する。10秒は仮値です。
3. 必要なら `features` を設定し、`ready` をtrueにする。
4. 合法解を実装し、最初は下記の1ケース、その後に画面から10件・100件を試す。

```powershell
python ../../ahc-lab/lab.py run --config lab.json --count 1
```

提出用に残す版は「提出用に保存」で `submissions/submission-001.rs` から採番します。
保存版の行の実行ボタンは保存版を、上部のボタンは編集中のmain.rsを対象にします。
入力・ツール・解答・メモ・提出版・結果はこの作業場所にまとまり、既定でGitの公開対象外です。
設定と採点ログ形式の詳細は [AHC Lab](../../ahc-lab/README.md) を参照してください。
''', encoding='utf-8')
    return target


def main():
    parser = argparse.ArgumentParser(description='新しい大会の作業場所を作成（既存は上書きしません）')
    parser.add_argument('contest', help='大会ID（ahcに続く3桁以上の番号）')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument('--port', type=int)
    args = parser.parse_args()
    try:
        path = create_contest(args.root, args.contest.lower(), args.port)
    except FileExistsError:
        parser.exit(1, '既存の作業場所があるため作成しませんでした。\n')
    except (ValueError, OSError) as e:
        parser.exit(1, str(e)+'\n')
    print(f'作成しました: {path}\nmain.rsを編集し、open-lab.cmdで画面を開いてください。')


if __name__ == '__main__':
    main()
