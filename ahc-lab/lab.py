"""Local AHC experiment runner. Standard library only; commands never use a shell."""
from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import statistics
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

HERE = Path(__file__).resolve().parent


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def fingerprint(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def save_json(path, data):
    path = Path(path)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    # On Windows a reader or sync/indexing process can briefly hold the destination.
    for attempt in range(12):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 11:
                raise
            time.sleep(.01 * (attempt + 1))


def load_config(path):
    path = Path(path).resolve()
    c = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(c, dict):
        raise ValueError('設定ファイルにはJSONオブジェクトを指定してください')
    c['_path'] = str(path)
    root = (path.parent / c.get('root', '.')).resolve()
    c['_root'] = str(root)
    for key in ('source', 'inputs', 'runs'):
        if not isinstance(c.get(key), str) or not c[key]:
            raise ValueError(f'{key} にパスを指定してください')
        c[key] = str((root / c[key]).resolve())
    if not isinstance(c.get('ready', True), bool):
        raise ValueError('ready は true または false にしてください')
    # Before the statement is public, input mode and scoring direction are unknown.
    # Allow the dashboard to open, but never execute an unconfigured contest.
    if c.get('ready', True) is False:
        return c
    if c.get('direction') not in ('max', 'min'):
        raise ValueError('direction は max または min を指定してください')
    if c.get('mode', 'offline') not in ('offline', 'interactive'):
        raise ValueError('mode は offline または interactive')
    required = ['solver_command'] + (['judge_command'] if c.get('mode', 'offline') == 'offline' else ['tester_command'])
    for key in required + (['build_command'] if c.get('build_command') else []):
        if not isinstance(c.get(key), list) or not c[key] or not all(isinstance(x, str) for x in c[key]):
            raise ValueError(f'{key} はコマンド引数の配列にしてください')
    if not any('{solver}' in x for x in c['solver_command']):
        raise ValueError('solver_command に {solver} を含めてください（実行版を保存するため）')
    for key in ('judge_command', 'tester_command', 'feature_command'):
        if c.get(key) and (not isinstance(c[key], list) or not all(isinstance(x, str) for x in c[key])):
            raise ValueError(f'{key} は配列にしてください')
    if isinstance(c.get('workers', 1), bool) or not isinstance(c.get('workers', 1), int) or not 1 <= c.get('workers', 1) <= 16:
        raise ValueError('workers は 1〜16')
    for key in ('timeout_seconds', 'judge_timeout_seconds', 'build_timeout_seconds'):
        value = float(c.get(key, 10 if key != 'build_timeout_seconds' else 120))
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f'{key} は正の有限値')
    pattern = re.compile(c.get('score_pattern', r'^Score\s*=\s*([-+\d.eE]+)\s*$'))
    if pattern.groups < 1:
        raise ValueError('score_pattern の第1キャプチャに得点を指定してください')
    if c.get('score_stream', 'stdout') not in ('stdout', 'stderr'):
        raise ValueError('score_stream は stdout または stderr')
    for key in ('judge_ignore_patterns', 'judge_error_patterns'):
        if key in c and (not isinstance(c[key], list) or not all(isinstance(s, str) for s in c[key])):
            raise ValueError(f'{key} は正規表現の配列にしてください')
        for regex in c.get(key, []):
            re.compile(regex)
    if c.get('mode') == 'interactive':
        count = c['tester_command'].count('{solver_args}')
        if count > 1 or (count == 0 and not any('{solver}' in s for s in c['tester_command'])):
            raise ValueError('tester_command に {solver_args} を1つ、または {solver} を指定してください')
    fs = c.get('features', [])
    if not isinstance(fs, list) or not all(isinstance(f, dict) for f in fs):
        raise ValueError('features は項目の配列にしてください')
    names = set()
    for f in fs:
        if not f.get('name') or any(isinstance(f.get(k, 0), bool) or not isinstance(f.get(k, 0), int) or f.get(k, 0) < 0 for k in ('line', 'token')):
            raise ValueError('特徴量には name と0以上の line/token が必要です')
        if not isinstance(f['name'], str) or f['name'] in names:
            raise ValueError('特徴量のnameは重複しない文字列にしてください')
        names.add(f['name'])
        bins = f.get('bins', [])
        if not isinstance(bins, list) or any(isinstance(b, bool) or not isinstance(b, (int, float)) or not math.isfinite(b) for b in bins) or bins != sorted(set(bins)):
            raise ValueError('bins は昇順・重複なしの有限数にしてください')
        if f.get('labels') and (not isinstance(f['labels'], list) or not all(isinstance(s, str) for s in f['labels']) or len(f['labels']) != len(bins) + 1):
            raise ValueError('labels は bins より1つ多くしてください')
    return c


def command(template, variables):
    # Literal replacement avoids interpreting JSON/program braces or invoking shell syntax.
    result = []
    for arg in template:
        for key, value in variables.items():
            arg = arg.replace('{' + key + '}', str(value))
        result.append(arg)
    return result


def select_cases(c, count):
    files = sorted(p for p in Path(c['inputs']).glob(c.get('input_glob', '*.txt')) if p.is_file())
    # Keep 10 as a fixed subset of 100; both cover the input pool rather than first seeds only.
    pool_size = min(100, len(files))
    if pool_size:
        pool = [files[i * len(files) // pool_size] for i in range(pool_size)]
    else:
        pool = []
    if not 1 <= count <= len(pool):
        raise ValueError(f'{count}件を実行できません。利用可能な入力は{len(pool)}件です（最大100件）。')
    return [pool[i * len(pool) // count] for i in range(count)]


def features(c, path, extracted=None):
    values, warnings = {}, []
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    for f in c.get('features', []):
        try:
            raw = float(extracted[f['key']] if 'key' in f else lines[f.get('line', 0)].split()[f.get('token', 0)])
            if not math.isfinite(raw):
                raise ValueError('非有限値')
            bins = f.get('bins', [])
            i = sum(raw >= b for b in bins)
            labels = f.get('labels') or ([f'< {bins[0]}'] + [f'{a} 〜 < {b}' for a, b in zip(bins, bins[1:])] + [f'≥ {bins[-1]}'] if bins else ['全体'])
            values[f['name']] = {'value': raw, 'group': labels[i], 'index': i}
        except (ValueError, IndexError, KeyError, TypeError) as e:
            values[f['name']] = {'value': None, 'group': '取得不可', 'index': 999}
            warnings.append(f"{f['name']}: {e}")
    return values, warnings


class WindowsJob:
    """Own a suspended process and its descendants before allowing it to execute.

    Microsoft Job Objects / THREADENTRY32 / ResumeThread documentation:
    https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
    """
    def __init__(self):
        import ctypes as ct
        from ctypes import wintypes as wt
        self.ct = ct
        self.api = ct.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': ([ct.c_void_p, wt.LPCWSTR], wt.HANDLE),
            'SetInformationJobObject': ([wt.HANDLE, ct.c_int, ct.c_void_p, wt.DWORD], wt.BOOL),
            'AssignProcessToJobObject': ([wt.HANDLE, wt.HANDLE], wt.BOOL),
            'OpenProcess': ([wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
            'CloseHandle': ([wt.HANDLE], wt.BOOL),
            'CreateToolhelp32Snapshot': ([wt.DWORD, wt.DWORD], wt.HANDLE),
            'Thread32First': ([wt.HANDLE, ct.c_void_p], wt.BOOL),
            'Thread32Next': ([wt.HANDLE, ct.c_void_p], wt.BOOL),
            'OpenThread': ([wt.DWORD, wt.BOOL, wt.DWORD], wt.HANDLE),
            'ResumeThread': ([wt.HANDLE], wt.DWORD),
        }
        for name, (args, restype) in signatures.items():
            f = getattr(self.api, name)
            f.argtypes, f.restype = args, restype
        class Basic(ct.Structure):
            _fields_ = [('ProcessTime', ct.c_longlong), ('JobTime', ct.c_longlong),
                        ('Flags', wt.DWORD), ('MinWS', ct.c_size_t), ('MaxWS', ct.c_size_t),
                        ('Active', wt.DWORD), ('Affinity', ct.c_size_t), ('Priority', wt.DWORD), ('Scheduling', wt.DWORD)]
        class Limits(ct.Structure):
            _fields_ = [('Basic', Basic), ('IO', ct.c_ulonglong * 6), ('ProcessMemory', ct.c_size_t),
                        ('JobMemory', ct.c_size_t), ('PeakProcess', ct.c_size_t), ('PeakJob', ct.c_size_t)]
        class ThreadEntry(ct.Structure):
            _fields_ = [('size', wt.DWORD), ('usage', wt.DWORD), ('thread', wt.DWORD),
                        ('owner', wt.DWORD), ('base', wt.LONG), ('delta', wt.LONG), ('flags', wt.DWORD)]
        self.ThreadEntry = ThreadEntry
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ct.WinError(ct.get_last_error())
        limits = Limits()
        limits.Basic.Flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ct.byref(limits), ct.sizeof(limits)):
            error = ct.WinError(ct.get_last_error())
            self.close()
            raise error

    def attach_and_resume(self, pid):
        ct, api = self.ct, self.api
        process = api.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ct.WinError(ct.get_last_error())
        try:
            if not api.AssignProcessToJobObject(self.handle, process):
                raise ct.WinError(ct.get_last_error())
        finally:
            api.CloseHandle(process)
        snap = api.CreateToolhelp32Snapshot(0x00000004, 0)  # TH32CS_SNAPTHREAD
        if snap == ct.c_void_p(-1).value:
            raise ct.WinError(ct.get_last_error())
        try:
            entry = self.ThreadEntry()
            entry.size = ct.sizeof(entry)
            found = api.Thread32First(snap, ct.byref(entry))
            while found:
                if entry.owner == pid:
                    thread = api.OpenThread(0x0002, False, entry.thread)  # THREAD_SUSPEND_RESUME
                    if not thread:
                        raise ct.WinError(ct.get_last_error())
                    try:
                        if api.ResumeThread(thread) == 0xffffffff:
                            raise ct.WinError(ct.get_last_error())
                        return
                    finally:
                        api.CloseHandle(thread)
                found = api.Thread32Next(snap, ct.byref(entry))
            raise OSError('起動したプロセスのスレッドが見つかりません')
        finally:
            api.CloseHandle(snap)

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None


def kill_tree(p, job=None):
    if os.name == 'nt':
        if job:
            job.close()
    else:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        p.kill()
    except ProcessLookupError:
        pass
    p.wait()


def run_process(args, cwd, stdin, stdout, stderr, timeout, cancel):
    start = time.perf_counter()
    kwargs = {'creationflags': subprocess.CREATE_NO_WINDOW | 0x00000004} if os.name == 'nt' else {'start_new_session': True}
    job = None
    p = None
    try:
        if os.name == 'nt':
            job = WindowsJob()
        with (open(stdin, 'rb') if stdin else open(os.devnull, 'rb')) as fin, open(stdout, 'wb') as fout, open(stderr, 'wb') as ferr:
            p = subprocess.Popen(args, cwd=cwd, stdin=fin, stdout=fout, stderr=ferr, shell=False, **kwargs)
            if job:
                job.attach_and_resume(p.pid)
            while p.poll() is None:
                if cancel.is_set() or time.perf_counter() - start > timeout:
                    status = 'cancelled' if cancel.is_set() else 'timeout'
                    kill_tree(p, job)
                    return {'status': status, 'seconds': time.perf_counter() - start, 'exit_code': p.returncode}
                time.sleep(.015)
            return {'status': 'ok' if p.returncode == 0 else 'process_error', 'seconds': time.perf_counter() - start, 'exit_code': p.returncode}
    except OSError as e:
        if p:
            kill_tree(p, job)
        Path(stderr).write_text(str(e), encoding='utf-8')
        return {'status': 'launch_error', 'seconds': time.perf_counter() - start, 'exit_code': None}
    finally:
        if job:
            job.close()
        elif p and os.name != 'nt':
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def parse_score(c, stdout, stderr):
    texts = {'stdout': Path(stdout).read_text(encoding='utf-8', errors='replace'),
             'stderr': Path(stderr).read_text(encoding='utf-8', errors='replace')}
    stream = c.get('score_stream', 'stdout' if c.get('mode', 'offline') == 'offline' else 'stderr')
    if stream not in texts:
        raise ValueError('score_stream は stdout または stderr')
    pattern = re.compile(c.get('score_pattern', r'^Score\s*=\s*([-+\d.eE]+)\s*$'))
    ignore = [re.compile(s) for s in c.get('judge_ignore_patterns', [])]
    errors = [re.compile(s, re.I) for s in c.get('judge_error_patterns', [r'\berror\b', r'\binvalid\b', r'\bpanicked\b', r'\bfailed\b'])]
    selected = texts[stream]
    # For tester mode stdout is the interaction transcript, not judge diagnostics.
    diagnostics = selected + ('\n' + texts['stderr'] if stream == 'stdout' else '')
    if any(p.search(diagnostics) for p in errors):
        return None, 'judge_error', '採点ログにエラーがあります'
    scores = []
    for line in selected.splitlines():
        if not line.strip():
            continue
        m = pattern.fullmatch(line.strip())
        if m:
            try:
                value = Decimal(m.group(1))
                if not value.is_finite() or abs(value) > 2**53:
                    return None, 'score_out_of_range', '得点は有限で絶対値2^53以下にしてください'
                scores.append(int(value) if value == value.to_integral_value() else float(value))
            except InvalidOperation:
                return None, 'score_missing', '得点を数値として読み取れません'
        elif not any(p.fullmatch(line) for p in ignore):
            return None, 'judge_error', '未認識の採点ログ。正当な診断行は judge_ignore_patterns に指定してください'
    # Offline judge stderr is required to be empty or explicitly allowed too.
    if stream == 'stdout':
        for line in texts['stderr'].splitlines():
            if line.strip() and not any(p.fullmatch(line) for p in ignore):
                return None, 'judge_error', '採点の標準エラーに未認識の行があります'
    if len(scores) != 1 or not math.isfinite(scores[0]):
        return None, 'score_missing', '有限な得点が1件だけ出力される必要があります'
    return scores[0], 'ok', ''


def summarize(rows):
    valid = [r for r in rows if r['status'] == 'ok']
    scores = [r['score'] for r in valid]
    return {'cases': len(rows), 'valid': len(valid), 'failed': len(rows) - len(valid),
            'score_sum': sum(scores) if scores else None,
            'score_mean': statistics.mean(scores) if scores else None,
            'score_median': statistics.median(scores) if scores else None,
            'seconds_mean': statistics.mean(r['seconds'] for r in rows) if rows else None,
            'seconds_max': max((r['seconds'] for r in rows), default=None)}


class Lab:
    def __init__(self, config_path):
        self.config_path = Path(config_path).resolve()
        self.lock = threading.Lock()
        self.cancel = threading.Event()
        self.active = None
        self.thread = None

    def config(self):
        return load_config(self.config_path)

    def submission_dir(self):
        c = self.config()
        return (Path(c['_root']) / c['submissions']).resolve() if c.get('submissions') else Path(c['source']).parent / 'submissions'

    def list_submissions(self):
        records = []
        runs = self.list_runs()
        for path in self.submission_dir().glob('submission-*.json'):
            try:
                record = json.loads(path.read_text(encoding='utf-8'))
                if not re.fullmatch(r'submission-\d{3,}\.[a-zA-Z0-9]+', record['filename']):
                    continue
                source = path.parent / record['filename']
                record['intact'] = source.is_file() and digest(source) == record['sha256']
                record['matching_runs'] = self.matching_runs(record['sha256'], runs)
                records.append(record)
            except (OSError, ValueError, KeyError, TypeError):
                continue
        return sorted(records, key=lambda r: r['number'], reverse=True)

    def matching_runs(self, sha, runs=None):
        return [{'id': r['id'], 'label': r.get('label', ''), 'summary': r.get('summary'),
                 'solver_command': r.get('config', {}).get('solver_command'),
                 'build_command': r.get('config', {}).get('build_command')}
                for r in (self.list_runs() if runs is None else runs)
                if r.get('state') == 'complete' and r.get('source_sha256') == sha]

    def freeze(self, label=''):
        c = self.config()
        source = Path(c['source'])
        if source.suffix.lower() not in ('.rs', '.cpp', '.cc', '.c', '.py', '.java', '.cs', '.go', '.kt'):
            raise ValueError('提出用には実行ファイルではなくソースファイルを指定してください')
        data = source.read_bytes()
        if not data:
            raise ValueError('ソースが空です。main.rs を保存してください')
        sha = hashlib.sha256(data).hexdigest()
        folder = self.submission_dir()
        folder.mkdir(parents=True, exist_ok=True)
        numbers = [int(m.group(1)) for p in folder.iterdir()
                   if (m := re.fullmatch(r'submission-(\d{3,})\.[a-zA-Z0-9]+', p.name))]
        reservations = folder / '.numbers'
        reservations.mkdir(exist_ok=True)
        numbers += [int(p.name) for p in reservations.iterdir() if p.name.isdigit()]
        number = max(numbers, default=0) + 1
        # Reserve the number, not only the extension: two languages cannot share an ID.
        while True:
            path = folder / f'submission-{number:03d}{source.suffix.lower()}'
            try:
                (reservations / f'{number:03d}').mkdir()
                break
            except FileExistsError:
                number += 1
        with path.open('xb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        matching = self.matching_runs(sha)
        record = {'number': number, 'filename': path.name, 'path': str(path),
                  'created_at': datetime.now().astimezone().isoformat(), 'label': str(label)[:100],
                  'sha256': sha, 'bytes': len(data), 'original_source': str(source), 'matching_runs': matching}
        # Publish metadata only after the complete source has been flushed to disk.
        with path.with_suffix('.json').open('x', encoding='utf-8') as meta:
            json.dump(record, meta, ensure_ascii=False, indent=2, allow_nan=False)
        return record

    def list_runs(self):
        c = self.config()
        runs = []
        for f in Path(c['runs']).glob('*/result.json'):
            try:
                r = json.loads(f.read_text(encoding='utf-8'))
                runs.append(r)
            except (OSError, ValueError):
                pass
        return sorted(runs, key=lambda r: r['id'], reverse=True)

    def start(self, count, label, submission=None):
        if not self.lock.acquire(blocking=False):
            raise ValueError('現在のテストが終わるまでお待ちください')
        try:
            c = self.config()
            if c.get('ready', True) is False:
                raise ValueError(c.get('setup_message', '問題公開後に採点設定を行い、ready を true にしてください'))
            if submission is not None:
                saved = next((r for r in self.list_submissions() if r['filename'] == submission), None)
                if not saved or not saved['intact']:
                    raise ValueError('保存版が見つからないか、保存後に内容が変更されています')
                c['source'] = str(self.submission_dir() / saved['filename'])
                c['_submission'] = {'filename': saved['filename'], 'sha256': saved['sha256']}
                label = str(label)[:65] + ' [' + saved['filename'] + ']'
            paths = select_cases(c, count)
            if not Path(c['source']).is_file():
                raise ValueError('source に指定された解答ファイルがありません')
            run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex[:8]
            folder = Path(c['runs']) / run_id
            folder.mkdir(parents=True)
            self.cancel = threading.Event()
            self.active = {'id': run_id, 'label': str(label)[:100], 'state': '準備中', 'done': 0, 'total': count}
            thread = threading.Thread(target=self._run, args=(c, paths, folder), daemon=True)
            self.thread = thread
            thread.start()
            return run_id
        except Exception:
            self.lock.release()
            raise

    def _run(self, c, paths, folder):
        result = {'id': folder.name, 'label': self.active['label'], 'contest': c.get('name', ''),
                  'created_at': datetime.now().astimezone().isoformat(), 'direction': c['direction'],
                  'state': 'running', 'rows': [], 'workers': int(c.get('workers', 1)), 'config': c}
        try:
            source = folder / ('source' + Path(c['source']).suffix)
            shutil.copyfile(c['source'], source)
            result['source_sha256'] = digest(source)
            if c.get('_submission') and result['source_sha256'] != c['_submission']['sha256']:
                raise ValueError('実行準備中に保存版の内容が変更されました')
            binary = folder / ('solver.exe' if os.name == 'nt' else 'solver')
            variables = {'python': sys.executable, 'root': c['_root'], 'source': source, 'binary': binary, 'solver': source}
            build = c.get('build_command')
            if build:
                self.active['state'] = 'ビルド中'
                b = run_process(command(build, variables), c['_root'], None, folder / 'build.stdout.txt',
                                folder / 'build.stderr.txt', float(c.get('build_timeout_seconds', 120)), self.cancel)
                result['build'] = b
                if b['status'] != 'ok' or not binary.is_file():
                    raise ValueError('ビルドが完了しませんでした。build.stderr.txt を確認してください')
                variables['solver'] = binary
            result['solver_sha256'] = digest(variables['solver'])
            # Fingerprint evaluator binaries and interpreter where discoverable.
            tool_hashes = {}
            for key in ('judge_command', 'tester_command', 'solver_command'):
                for i, arg in enumerate(command(c.get(key, []), variables)):
                    if '{' in arg:
                        continue
                    file = Path(shutil.which(arg) or arg) if i == 0 else Path(arg)
                    if not file.is_absolute():
                        file = Path(c['_root']) / file
                    if file.is_file() and file.resolve() not in (source.resolve(), binary.resolve()):
                        tool_hashes[str(file.resolve())] = digest(file)
            result['tool_hashes'] = tool_hashes
            # Solver arguments are the experimental treatment, not evaluator identity.
            semantics = {k: c.get(k) for k in ('name', 'mode', 'direction', 'judge_command', 'tester_command', 'score_stream', 'score_pattern', 'judge_ignore_patterns', 'judge_error_patterns', 'timeout_seconds', 'judge_timeout_seconds', 'workers')}
            semantics['tool_hashes'] = tool_hashes
            result['evaluator_signature'] = fingerprint(semantics)
            prepared = []
            for i, path in enumerate(paths):
                if self.cancel.is_set():
                    break
                case_dir = folder / f'case-{i:04d}'
                case_dir.mkdir()
                input_copy = case_dir / 'input.txt'
                shutil.copyfile(path, input_copy)
                extracted, extract_warnings = None, []
                if c.get('feature_command'):
                    fv = dict(variables, input=input_copy, case_dir=case_dir)
                    fx = run_process(command(c['feature_command'], fv), case_dir, None,
                                     case_dir / 'features.stdout.json', case_dir / 'features.stderr.txt',
                                     float(c.get('judge_timeout_seconds', 10)), self.cancel)
                    try:
                        if fx['status'] != 'ok':
                            raise ValueError(fx['status'])
                        extracted = json.loads((case_dir / 'features.stdout.json').read_text(encoding='utf-8-sig'))
                        if not isinstance(extracted, dict):
                            raise ValueError('JSONオブジェクトが必要です')
                    except (OSError, ValueError) as e:
                        extract_warnings.append('特徴量の抽出: ' + str(e))
                fs, warnings = features(c, input_copy, extracted)
                warnings += extract_warnings
                prepared.append({'id': path.relative_to(c['inputs']).as_posix(), 'input_sha256': digest(input_copy),
                                 'folder': case_dir.name, 'features': fs, 'warnings': warnings})
            result['suite_signature'] = fingerprint([(r['id'], r['input_sha256']) for r in prepared])
            save_json(folder / 'result.json', result)
            self.active['state'] = '実行中'
            with concurrent.futures.ThreadPoolExecutor(max_workers=result['workers']) as pool:
                jobs = [pool.submit(self._case, c, row, folder, variables) for row in prepared]
                for future in concurrent.futures.as_completed(jobs):
                    row = future.result()
                    result['rows'].append(row)
                    result['rows'].sort(key=lambda r: r['id'])
                    result['summary'] = summarize(result['rows'])
                    self.active['done'] = len(result['rows'])
                    save_json(folder / 'result.json', result)
            result['state'] = 'cancelled' if self.cancel.is_set() else 'complete'
        except Exception as e:
            result['state'] = 'cancelled' if self.cancel.is_set() else 'error'
            result['error'] = str(e)
        finally:
            result['summary'] = summarize(result['rows'])
            result['finished_at'] = datetime.now().astimezone().isoformat()
            try:
                save_json(folder / 'result.json', result)
            finally:
                self.active['state'] = {'complete': '完了', 'cancelled': '停止済み', 'error': 'エラー'}.get(result['state'], result['state'])
                self.lock.release()

    def _case(self, c, row, folder, variables):
        row = copy.deepcopy(row)
        case_dir = folder / row['folder']
        v = dict(variables, input=case_dir / 'input.txt', output=case_dir / 'output.txt', case_dir=case_dir)
        row.update(score=None, seconds=0, status='cancelled', message='')
        if self.cancel.is_set():
            return row
        interactive = c.get('mode', 'offline') == 'interactive'
        key = 'tester_command' if interactive else 'solver_command'
        args = command(c[key], v)
        # {solver_args} expands to several arguments for tester cmd arg1 ...
        if interactive and '{solver_args}' in args:
            i = args.index('{solver_args}')
            args[i:i+1] = command(c['solver_command'], v)
        run = run_process(args, case_dir, v['input'], v['output'], case_dir / 'solver.stderr.txt',
                          float(c.get('timeout_seconds', 10)), self.cancel)
        row.update(status=run['status'], seconds=run['seconds'], exit_code=run['exit_code'])
        row['command'] = args
        if run['status'] != 'ok':
            return row
        if not interactive or c.get('judge_command'):
            judge_args = command(c['judge_command'], v)
            judge = run_process(judge_args, case_dir, None, case_dir / 'judge.stdout.txt', case_dir / 'judge.stderr.txt',
                                float(c.get('judge_timeout_seconds', 10)), self.cancel)
            row['judge'] = judge
            if judge['status'] != 'ok':
                row['status'] = 'judge_' + judge['status']
                return row
            score_config = dict(c, mode='offline', score_stream=c.get('score_stream', 'stdout'))
            score, status, msg = parse_score(score_config, case_dir / 'judge.stdout.txt', case_dir / 'judge.stderr.txt')
        else:
            score, status, msg = parse_score(c, v['output'], case_dir / 'solver.stderr.txt')
        row.update(score=score, status=status, message=msg)
        return row


def compare(current, baseline):
    if not current or not baseline or current.get('state') != 'complete' or baseline.get('state') != 'complete':
        return {'compatible': False, 'reason': '完了済みの2つの実行を選んでください'}
    if not current.get('evaluator_signature') or current.get('evaluator_signature') != baseline.get('evaluator_signature'):
        return {'compatible': False, 'reason': '大会・採点設定・ツール・実行条件が異なります'}
    old = {r['id']: r for r in baseline['rows']}
    pairs = []
    wins = ties = losses = 0
    for r in current['rows']:
        b = old.get(r['id'])
        if not b or r['input_sha256'] != b['input_sha256']:
            continue
        item = {'id': r['id'], 'current_status': r['status'], 'baseline_status': b['status'], 'delta': None, 'percent': None}
        if r['status'] == b['status'] == 'ok':
            delta = (r['score'] - b['score']) * (1 if current['direction'] == 'max' else -1)
            item['delta'] = delta
            item['percent'] = 100 * delta / abs(b['score']) if b['score'] != 0 else None
            wins += delta > 0
            losses += delta < 0
            ties += delta == 0
        pairs.append(item)
    valid = [p for p in pairs if p['delta'] is not None]
    return {'compatible': bool(pairs), 'reason': '' if pairs else 'ハッシュの一致する共通入力がありません',
            'common': len(pairs), 'valid_pairs': len(valid), 'wins': wins, 'ties': ties, 'losses': losses,
            'delta_sum': sum(p['delta'] for p in valid) if valid else None,
            'percent_mean': statistics.mean(p['percent'] for p in valid if p['percent'] is not None) if any(p['percent'] is not None for p in valid) else None,
            'same_suite': current.get('suite_signature') == baseline.get('suite_signature'), 'pairs': pairs}


def serve(lab, port, open_browser):
    token = secrets.token_urlsafe(24)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, data, status=200, mime='application/json; charset=utf-8', filename=None):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('X-Frame-Options', 'DENY')
            if filename:
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.end_headers()
            self.wfile.write(body)

        def local(self):
            return self.headers.get('Host') == f'127.0.0.1:{self.server.server_port}'

        def do_GET(self):
            if not self.local():
                return self.send({'error': 'Invalid host'}, 403)
            parsed = urlparse(self.path)
            try:
                if parsed.path == '/api/state':
                    c = lab.config()
                    available = min(100, sum(p.is_file() for p in Path(c['inputs']).glob(c.get('input_glob', '*.txt'))))
                    return self.send({'name': c.get('name'), 'direction': c['direction'], 'workers': c.get('workers', 1),
                                      'source': c['source'], 'features': c.get('features', []), 'token': token,
                                      'available': available, 'ready': c.get('ready', True), 'setup_message': c.get('setup_message', ''),
                                      'active': copy.deepcopy(lab.active), 'runs': lab.list_runs(),
                                      'submissions': lab.list_submissions(), 'submission_dir': str(lab.submission_dir())})
                if parsed.path == '/api/submission':
                    q = parse_qs(parsed.query)
                    name = q.get('file', [''])[0]
                    if not re.fullmatch(r'submission-\d{3,}\.[a-zA-Z0-9]+', name):
                        return self.send({'error': '保存したソースが見つかりません'}, 404)
                    record = next((r for r in lab.list_submissions() if r['filename'] == name), None)
                    if not record:
                        return self.send({'error': '保存したソースが見つかりません'}, 404)
                    if not record['intact']:
                        return self.send({'error': '保存後にファイルが変更されています。保存時の内容と一致しません'}, 409)
                    data = (lab.submission_dir() / name).read_bytes()
                    if hashlib.sha256(data).hexdigest() != record['sha256']:
                        return self.send({'error': 'ファイルの内容が変更されています'}, 409)
                    return self.send(data, mime='text/plain; charset=utf-8',
                                     filename=name if q.get('download') == ['1'] else None)
                if parsed.path == '/api/log':
                    q = parse_qs(parsed.query)
                    run_id, case, name = (q.get(k, [''])[0] for k in ('run', 'case', 'name'))
                    allowed = {'solver.stderr.txt', 'judge.stdout.txt', 'judge.stderr.txt', 'output.txt', 'build.stderr.txt'}
                    if not re.fullmatch(r'\d{8}T\d{6}-[0-9a-f]{8}', run_id) or (case and not re.fullmatch(r'case-\d{4}', case)) or name not in allowed:
                        return self.send({'error': 'ログが見つかりません'}, 404)
                    path = Path(lab.config()['runs']) / run_id / case / name
                    with path.open('rb') as f:
                        data = f.read(200_000)
                    return self.send(data.decode('utf-8', errors='replace').encode(), mime='text/plain; charset=utf-8')
                files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
                if parsed.path in files:
                    name, mime = files[parsed.path]
                    return self.send((HERE / 'web' / name).read_bytes(), mime=mime + '; charset=utf-8')
                return self.send({'error': 'Not found'}, 404)
            except Exception as e:
                return self.send({'error': str(e)}, 400)

        def do_POST(self):
            if not self.local() or self.headers.get('X-Lab-Token') != token:
                return self.send({'error': '操作を許可できません'}, 403)
            try:
                n = int(self.headers.get('Content-Length', '0'))
                if not 0 < n <= 4096:
                    raise ValueError('リクエストが不正です')
                body = json.loads(self.rfile.read(n))
                if self.path == '/api/freeze':
                    return self.send(lab.freeze(body.get('label', '')))
                if self.path == '/api/run':
                    count = int(body['count'])
                    return self.send({'id': lab.start(count, body.get('label', ''), body.get('submission'))})
                if self.path == '/api/stop':
                    lab.cancel.set()
                    return self.send({'ok': True})
                return self.send({'error': 'Not found'}, 404)
            except Exception as e:
                return self.send({'error': str(e)}, 400)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    url = f'http://127.0.0.1:{server.server_port}'
    print(f'AHC Lab: {url}', flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        lab.cancel.set()
    finally:
        lab.cancel.set()
        if lab.thread:
            lab.thread.join(timeout=10)
        server.server_close()


def main():
    p = argparse.ArgumentParser(description='AHCの10/100ケース実行とローカル結果画面')
    p.add_argument('action', choices=['serve', 'run', 'freeze'])
    p.add_argument('--config', default=str(HERE / 'configs' / 'demo.json'))
    p.add_argument('--count', type=int, default=10)
    p.add_argument('--label', default='')
    p.add_argument('--submission', help='保存版のファイル名（runでのみ使用）')
    p.add_argument('--port', type=int, default=8766)
    p.add_argument('--open', action='store_true')
    args = p.parse_args()
    lab = Lab(args.config)
    if args.action == 'serve':
        serve(lab, args.port, args.open)
    elif args.action == 'freeze':
        print(json.dumps(lab.freeze(args.label), ensure_ascii=False))
    else:
        run_id = lab.start(args.count, args.label, args.submission)
        try:
            while lab.lock.locked():
                time.sleep(.1)
        except KeyboardInterrupt:
            lab.cancel.set()
            while lab.lock.locked():
                time.sleep(.1)
        result = next(r for r in lab.list_runs() if r['id'] == run_id)
        print(json.dumps({'id': run_id, 'state': result['state'], 'summary': result['summary'], 'error': result.get('error')}, ensure_ascii=False))
        return 0 if result['state'] == 'complete' and result['summary']['failed'] == 0 else 1
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, KeyError, TypeError, re.error) as e:
        print(f'AHC Lab: {e}', file=sys.stderr)
        sys.exit(1)
