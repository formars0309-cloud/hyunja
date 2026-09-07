"""현자 윈도우 설치기.

%USERPROFILE%\\.local\\bin 에 askall.cmd·hyunja.cmd(ASCII만)와 실행기 askall.py 를 두고,
실행기가 이 저장소의 ask_all.py 를 부른다. 배치 파일에 한글 경로를 직접 쓰면 콘솔 코드페이지가
65001일 때 cmd.exe가 줄을 어긋나게 읽어 깨지므로, 한글 경로는 전부 파이썬이 다룬다.
%USERPROFILE%\\.claude\\skills\\현자 정션도 여기서 만든다.
"""
import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
HOME = pathlib.Path.home()
BIN = HOME / '.local' / 'bin'


def main():
    BIN.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO / 'windows' / 'askall.py', BIN / 'askall.py')
    (BIN / 'hyunja.repo').write_text(str(REPO), encoding='utf-8')
    for name in ('askall.cmd', 'hyunja.cmd'):
        (BIN / name).write_text('@python "%USERPROFILE%\\.local\\bin\\askall.py" %*\r\n', encoding='ascii')
    print('명령 설치:', BIN / 'askall.cmd', BIN / 'hyunja.cmd')
    if str(BIN).lower() not in os.environ.get('PATH', '').lower():
        print('PATH에 %s 가 없습니다. 사용자 환경변수 PATH에 추가하세요.' % BIN)
    for agent in ('.claude', '.codex'):
        base = HOME / agent
        if base.is_dir():
            link = base / 'skills' / '현자'
            link.parent.mkdir(parents=True, exist_ok=True)
            if not link.exists():
                subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(REPO)], check=False)
            print('스킬 등록:', link)
    for cli in ('claude', 'codex', 'grok', 'agy'):
        print(('확인: ' if shutil.which(cli) else '없음: ') + cli)
    print('완료. 사용: askall "질문"')


if __name__ == '__main__':
    sys.exit(main())
