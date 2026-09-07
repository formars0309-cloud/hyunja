"""askall.cmd 가 부르는 실행기. 옆의 hyunja.repo 에 적힌 저장소의 ask_all.py 를 실행한다."""
import pathlib
import runpy
import sys

repo = pathlib.Path(__file__).with_name('hyunja.repo').read_text(encoding='utf-8').strip()
script = str(pathlib.Path(repo) / 'ask_all.py')
sys.argv[0] = script
runpy.run_path(script, run_name='__main__')
