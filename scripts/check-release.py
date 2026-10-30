"""Check the exact Git publication candidate set, without staging or committing it."""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def main():
    expected = set(json.loads((ROOT / 'release-files.json').read_text(encoding='utf-8')))
    actual = set(git('ls-files', '--cached', '--others', '--exclude-standard', '-z').decode('utf-8').split('\0')) - {''}
    issues = []
    for path in sorted(actual - expected):
        issues.append(f'配布一覧にないファイル: {path}')
    for path in sorted(expected - actual):
        issues.append(f'配布対象が不足: {path}')
    patterns = {
        '個人の絶対パス': re.compile(r'(?:[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]|/[U]sers/[^ /]+|/[h]ome/[^ /]+|\.codex[\\/])'),
        '秘密鍵': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----'),
        'アクセストークン候補': re.compile(r'(?:gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16}|sk-[A-Za-z0-9_-]{24,})'),
    }
    for name in sorted(actual & expected):
        path = ROOT / name
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            issues.append(f'通常のファイルではありません: {name}')
            continue
        try:
            text = path.read_text(encoding='utf-8-sig')
        except UnicodeDecodeError:
            issues.append(f'テキストとして確認できません: {name}')
            continue
        for label, regex in patterns.items():
            if regex.search(text):
                issues.append(f'{label}: {name}')
        if path.name == 'README.md' and re.search(r'ahc\d{3,}', text, re.I):
            issues.append(f'特定の大会番号がREADMEにあります: {name}')
    private = ['contests/example/main.rs', 'contests/notes.txt',
               'ahc-lab/demo/inputs/example.txt', 'ahc-lab/demo/submissions/submission-001.py',
               'ahc-lab/runs/example/result.json', '.test-tmp/example.txt', 'target/example.exe']
    for name in private:
        p = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '--no-index', '-q', name])
        if p.returncode != 0:
            issues.append(f'作業データをGitから除外できていません: {name}')
    print(json.dumps({'files': len(actual), 'issues': issues}, ensure_ascii=False, indent=2))
    return 1 if issues else 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as e:
        print(f'Gitリポジトリ直下で配布一覧を確認してください: {e}', file=sys.stderr)
        sys.exit(1)
