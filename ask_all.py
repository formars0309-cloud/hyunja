#!/usr/bin/env python3
"""현자(賢者) — 여러 AI CLI에 같은 질문을 동시에 던지고 답을 한 화면에 모은다.

사용:
  현자 "질문"                        # 기본: claude codex grok antigravity (askall 도 같은 명령)
  현자 -a claude,grok "질문"         # 일부만
  현자 -t 600 "질문"                 # 타임아웃(초, 기본 300)
  현자 --no-open "질문"              # 브라우저 안 열고 터미널 출력만
  현자 --commit "질문"               # 작업 폴더가 git 저장소면 답을 곧바로 커밋
  echo "여러 줄 질문" | 현자          # 질문을 stdin으로

작업 폴더: 환경변수 HYUNJA_HOME (기본 ~/.hyunja). 네 CLI는 이 폴더에서 실행되며 폴더의 AGENTS.md(공통 지침)를
읽는다. 처음 실행하면 폴더를 만들고 templates/ 의 지침 파일을 복사한다. 답은 answers/<시각>.md·.html 로 남는다.
환경변수 HYUNJA_COMMIT=1 은 --commit 과 같다. 두 변수는 ~/.config/hyunja/env 파일(KEY=VALUE)에 적어 둬도 된다.
표준 라이브러리만 쓴다.
"""
import argparse
import datetime
import html
import os
import pathlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
DEFAULT_AGENTS = 'claude,codex,grok,antigravity'
DEFAULT_CLAUDE_FALLBACK = 'claude-opus-5'


def load_env_file():
    """~/.config/hyunja/env 의 KEY=VALUE 줄을 환경변수 기본값으로 읽는다. 이미 있는 변수는 건드리지 않는다."""
    f = pathlib.Path.home() / '.config' / 'hyunja' / 'env'
    if not f.exists():
        return
    for line in f.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def workspace():
    """작업 폴더를 정하고, 없으면 만들어 지침 템플릿을 넣는다."""
    load_env_file()
    ws = pathlib.Path(os.environ.get('HYUNJA_HOME') or (pathlib.Path.home() / '.hyunja')).expanduser()
    ws.mkdir(parents=True, exist_ok=True)
    for name in ('AGENTS.md', 'CLAUDE.md', 'GEMINI.md'):
        src, dst = HERE / 'templates' / name, ws / name
        if src.exists() and not dst.exists():
            shutil.copyfile(src, dst)
    return ws


def cmd_for(agent, q, tmpdir):
    # codex는 진행 로그를 stdout에 찍으므로 최종 답만 -o 파일로 받는다
    out = os.path.join(tmpdir, 'codex-last.md')
    table = {
        'claude': ['claude', '-p', q, '--output-format', 'json'],
        'codex': ['codex', 'exec', '--skip-git-repo-check', '-s', 'read-only', '-o', out, q],
        'grok': ['grok', '-p', q],
        'antigravity': ['agy', '--dangerously-skip-permissions', '-p', q],
        'gemini': ['agy', '--dangerously-skip-permissions', '-p', q],  # 옛 이름. 제미나이 CLI는 2026-06-18부터 구글 로그인이 막혀 Antigravity(agy)로 대신한다
    }
    if agent not in table:
        return None, out
    return table[agent], out


def resolve_cmd(cmd):
    exe = shutil.which(cmd[0])
    if not exe:
        return None
    # 윈도우에서 .cmd 배치 파일로 인자를 넘기면 줄바꿈(\n)이 첫 줄에서 잘리는 cmd.exe의 %* 한계가 있다.
    # 따라서 codex.cmd나 grok.cmd처럼 알려진 래퍼는 실제 실행 파일(.exe / node 스크립트)로 직접 푼다.
    if sys.platform == 'win32' and exe.lower().endswith('.cmd'):
        name = os.path.splitext(os.path.basename(cmd[0]))[0].lower()
        if name == 'codex':
            import glob
            codexes = sorted(glob.glob(os.path.expandvars(r'%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe')), reverse=True)
            if codexes:
                return [codexes[0]] + cmd[1:]
        elif name == 'grok':
            node = shutil.which('node')
            js = os.path.join(os.path.dirname(exe), 'node_modules', '@xai-official', 'grok', 'bin', 'grok')
            if node and os.path.exists(js):
                return [node, js] + cmd[1:]
    return [exe] + cmd[1:]

def claude_result(process):
    """구조화된 결과를 우선 읽고, CLI 자체의 사용 한도 안내만 판별한다."""
    stdout, stderr = (process.stdout or '').strip(), (process.stderr or '').strip()
    body = stdout or stderr or '(빈 응답, 종료코드 %s)' % process.returncode
    # 현재 CLI는 한 객체를 출력한다. 진단 줄이 섞인 버전도 마지막 결과를 읽는다.
    for candidate in [stdout] + list(reversed(stdout.splitlines())):
        try:
            result = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(result, dict) and result.get('type') == 'result':
            body = result.get('result') or '\n'.join(map(str, result.get('errors', []))) or body
            # 정상 답변이 한도 안내를 인용해도 재시도하지 않는다.
            if not result.get('is_error', False):
                return str(body), False
            return str(body), is_usage_limit(str(body))
    return body, any(is_usage_limit(value) for value in (stdout, stderr))


def is_usage_limit(message):
    """인증·네트워크·모델 오류는 제외하고 사용량 소진 안내만 허용한다."""
    return bool(re.match(
        r"^you[’']ve (?:reached|hit) your (?:[a-z0-9 ._-]+ )?limit(?:[.!,;: \n]|$)",
        message.strip(), re.IGNORECASE))


def ask_claude(cmd, timeout, cwd):
    """총 대기 한도 안에서 Opus 5로 한 번만 재시도한다."""
    deadline = time.monotonic() + timeout
    notice = ''
    for attempt in range(2):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return notice + '(타임아웃 %d초)' % timeout
        try:
            process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                                     errors='replace', timeout=remaining, cwd=cwd,
                                     stdin=subprocess.DEVNULL)
        except subprocess.TimeoutExpired:
            return notice + '(타임아웃 %d초)' % timeout
        body, limited = claude_result(process)
        if not limited or attempt == 1:
            if attempt and (limited or process.returncode != 0):
                return notice + '(대체 모델 재시도 실패)\n' + body
            return notice + body
        model = os.environ.get('HYUNJA_CLAUDE_FALLBACK_MODEL', DEFAULT_CLAUDE_FALLBACK).strip()
        if not model:
            return body
        notice = '[Claude 자동 재시도: 기본 모델 사용 한도 → %s]\n\n' % model
        print(notice.strip(), file=sys.stderr, flush=True)
        cmd = [*cmd, '--model', model]
    raise AssertionError('재시도 횟수 초과')


def ask(agent, q, timeout, cwd, tmpdir):
    cmd, outfile = cmd_for(agent, q, tmpdir)
    if cmd is None:
        return agent, '(모르는 이름: %s. 가능: %s)' % (agent, DEFAULT_AGENTS), 0.0
    real_cmd = resolve_cmd(cmd)
    if not real_cmd:
        return agent, '(CLI 없음: %s)' % cmd[0], 0.0
    t0 = time.time()
    if agent == 'claude':
        return agent, ask_claude(real_cmd, timeout, cwd), time.time() - t0
    try:
        p = subprocess.run(real_cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                           timeout=timeout, cwd=cwd, stdin=subprocess.DEVNULL)
        text = ''
        if agent == 'codex' and os.path.exists(outfile):
            text = pathlib.Path(outfile).read_text(encoding='utf-8', errors='replace').strip()
        text = text or (p.stdout or '').strip() or (p.stderr or '').strip() or '(빈 응답, 종료코드 %s)' % p.returncode
    except subprocess.TimeoutExpired:
        text = '(타임아웃 %d초)' % timeout
    return agent, text, time.time() - t0


def render_html(q, stamp, results):
    cols = ''.join(
        '<section><h2>%s <small>%.0f초</small></h2><pre>%s</pre></section>' % (agent, sec, html.escape(text))
        for agent, text, sec in results)
    return ('<!doctype html><meta charset="utf-8"><title>현자 %s</title>'
            '<style>body{margin:0;font-family:system-ui,"Apple SD Gothic Neo","Malgun Gothic",sans-serif;'
            'background:#f6f6f4;color:#222}h1{font-size:18px;margin:0;padding:14px 18px;background:#fff;'
            'border-bottom:1px solid #ddd;position:sticky;top:0}main{display:flex;gap:12px;padding:12px;'
            'align-items:flex-start}section{flex:1 1 0;min-width:0;background:#fff;border:1px solid #ddd;'
            'border-radius:8px}h2{font-size:15px;margin:0;padding:10px 14px;border-bottom:1px solid #eee}'
            'small{color:#888;font-weight:normal}pre{white-space:pre-wrap;word-break:break-word;margin:0;'
            'padding:14px;font-family:inherit;font-size:14px;line-height:1.6}</style>'
            '<h1>%s</h1><main>%s</main>') % (stamp, html.escape(q), cols)


def open_in_browser(path):
    try:
        os.startfile(str(path))  # 윈도우 기본 브라우저
    except AttributeError:
        subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])


def main():
    try:
        sys.stdin.reconfigure(encoding='utf-8', errors='replace')
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    ap = argparse.ArgumentParser(description='여러 AI CLI에 동시에 질문')
    ap.add_argument('question', nargs='?', help='질문. 없으면 stdin에서 읽는다')
    ap.add_argument('-f', '--file', help='질문 파일 경로 (파일에서 UTF-8로 직접 읽음)')
    ap.add_argument('-a', '--agents', default=DEFAULT_AGENTS, help='쉼표로 구분 (기본: %s)' % DEFAULT_AGENTS)
    ap.add_argument('-t', '--timeout', type=int, default=300, help='CLI마다 최대 대기 초 (기본 300)')
    ap.add_argument('--no-open', action='store_true', help='결과 HTML을 브라우저로 열지 않는다')
    ap.add_argument('--commit', action='store_true', help='작업 폴더가 git 저장소면 answers/ 를 곧바로 커밋한다')
    args = ap.parse_args()
    if args.file:
        q = pathlib.Path(args.file).read_text(encoding='utf-8-sig', errors='replace').strip()
    else:
        q = (args.question or sys.stdin.read()).strip()
    q = q.encode('utf-8', errors='replace').decode('utf-8')
    if not q:
        ap.error('질문이 비었습니다')
    agents = [a.strip() for a in args.agents.split(',') if a.strip()]

    cwd = workspace()  # 설정 파일도 여기서 읽으므로 커밋 여부는 그 뒤에 정한다
    commit = args.commit or os.environ.get('HYUNJA_COMMIT') == '1'
    outdir = cwd / 'answers'
    tmp = tempfile.mkdtemp(prefix='hyunja-')
    print('질문:', q, file=sys.stderr)
    print('실행 중: %s (최대 %d초, 폴더 %s)' % (', '.join(agents), args.timeout, cwd), file=sys.stderr)
    with ThreadPoolExecutor(len(agents)) as ex:
        results = list(ex.map(lambda a: ask(a, q, args.timeout, str(cwd), tmp), agents))
    shutil.rmtree(tmp, ignore_errors=True)

    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    outdir.mkdir(parents=True, exist_ok=True)
    md = ['# %s' % q, '', '_%s_' % stamp, '']
    for agent, text, sec in results:
        md += ['## %s (%.0f초)' % (agent, sec), '', text, '']
    (outdir / (stamp + '.md')).write_text('\n'.join(md), encoding='utf-8', errors='replace')
    htmlpath = outdir / (stamp + '.html')
    htmlpath.write_text(render_html(q, stamp, results), encoding='utf-8', errors='replace')

    if commit and (cwd / '.git').exists():
        subprocess.run(['git', '-C', str(cwd), 'add', 'answers'], capture_output=True)
        subprocess.run(['git', '-C', str(cwd), 'commit', '-q', '-m', '질문: ' + q[:60]], capture_output=True)

    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    print('\n'.join(md))
    print('저장:', htmlpath, file=sys.stderr)
    if not args.no_open:
        open_in_browser(htmlpath)


if __name__ == '__main__':
    main()
