"""Claude 사용 한도 전환과 기존 실행 경로 회귀 검사."""
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import ask_all


def result(text, error=False, code=0):
    return subprocess.CompletedProcess([], code, json.dumps({
        'type': 'result', 'is_error': error, 'result': text}), '')


class ClaudeFallbackTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'HYUNJA_CLAUDE_FALLBACK_MODEL': 'claude-opus-5'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.cmd = ['claude', '-p', '같은 질문', '--output-format', 'json']

    def test_fable_limit_retries_once_with_same_question(self):
        with patch('ask_all.subprocess.run', side_effect=[
            result("You've reached your Fable limit. Switch to another model.", True, 1),
            result('실제 답변'),
        ]) as run:
            text = ask_all.ask_claude(self.cmd, 60, '/tmp')
        self.assertIn('claude-opus-5', text)
        self.assertTrue(text.endswith('실제 답변'))
        self.assertEqual(run.call_count, 2)
        self.assertEqual(run.call_args_list[1].args[0], self.cmd + ['--model', 'claude-opus-5'])
        self.assertEqual(run.call_args.kwargs['cwd'], '/tmp')

    def test_success_quoting_limit_never_retries(self):
        with patch('ask_all.subprocess.run', return_value=result("You've reached your Fable limit.")) as run:
            ask_all.ask_claude(self.cmd, 60, '/tmp')
        self.assertEqual(run.call_count, 1)

    def test_plain_stderr_limit(self):
        with patch('ask_all.subprocess.run', side_effect=[
            subprocess.CompletedProcess([], 1, '', "You've hit your limit · resets tomorrow"),
            result('답변'),
        ]) as run:
            self.assertIn('답변', ask_all.ask_claude(self.cmd, 60, '/tmp'))
        self.assertEqual(run.call_count, 2)

    def test_auth_and_network_errors_do_not_retry(self):
        for message in ['Authentication required', 'Network error', 'Unknown model', 'HTTP 429 overload']:
            with self.subTest(message=message), patch('ask_all.subprocess.run', return_value=result(message, True, 1)) as run:
                self.assertEqual(ask_all.ask_claude(self.cmd, 60, '/tmp'), message)
                self.assertEqual(run.call_count, 1)

    def test_second_limit_stops(self):
        with patch('ask_all.subprocess.run', return_value=result("You've reached your weekly limit.", True, 1)) as run:
            self.assertIn('재시도 실패', ask_all.ask_claude(self.cmd, 60, '/tmp'))
        self.assertEqual(run.call_count, 2)

    def test_custom_model_and_disable(self):
        for model, calls in [('custom-model', 2), ('', 1)]:
            with self.subTest(model=model), patch.dict(os.environ, {'HYUNJA_CLAUDE_FALLBACK_MODEL': model}), patch(
                'ask_all.subprocess.run', side_effect=[result("You've reached your Fable limit.", True), result('답')]
            ) as run:
                ask_all.ask_claude(self.cmd, 60, '/tmp')
                self.assertEqual(run.call_count, calls)
                if model:
                    self.assertEqual(run.call_args.args[0][-1], model)

    def test_shared_timeout_budget(self):
        with patch('ask_all.time.monotonic', side_effect=[100, 101, 109]), patch(
            'ask_all.subprocess.run', side_effect=[result("You've reached your Fable limit.", True), result('답')]
        ) as run:
            ask_all.ask_claude(self.cmd, 10, '/tmp')
        self.assertEqual([c.kwargs['timeout'] for c in run.call_args_list], [9, 1])

    def test_primary_timeout_no_retry(self):
        with patch('ask_all.subprocess.run', side_effect=subprocess.TimeoutExpired(self.cmd, 10)) as run:
            self.assertIn('타임아웃', ask_all.ask_claude(self.cmd, 10, '/tmp'))
        self.assertEqual(run.call_count, 1)

    def test_fallback_timeout_retains_notice(self):
        with patch('ask_all.subprocess.run', side_effect=[
            result("You've reached your Fable limit.", True), subprocess.TimeoutExpired(self.cmd, 10)
        ]):
            text = ask_all.ask_claude(self.cmd, 10, '/tmp')
        self.assertIn('claude-opus-5', text)
        self.assertIn('타임아웃', text)

    def test_diagnostic_line_before_json(self):
        process = result("You've reached your Fable limit.", True, 1)
        process.stdout = 'diagnostic\n' + process.stdout
        self.assertTrue(ask_all.claude_result(process)[1])

    def test_other_agent_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp, patch('ask_all.shutil.which', return_value='/bin/grok'), patch(
            'ask_all.subprocess.run', return_value=subprocess.CompletedProcess([], 1, '', '402 Payment Required')
        ) as run:
            agent, text, _ = ask_all.ask('grok', '질문', 10, tmp, tmp)
        self.assertEqual((agent, text), ('grok', '402 Payment Required'))
        self.assertEqual(run.call_count, 1)

    def test_new_question_uses_default_model_again(self):
        with patch('ask_all.subprocess.run', side_effect=[
            result("You've reached your Fable limit.", True), result('답1'), result('답2')
        ]) as run:
            ask_all.ask_claude(self.cmd, 60, '/tmp')
            self.assertEqual(ask_all.ask_claude(self.cmd, 60, '/tmp'), '답2')
        self.assertNotIn('--model', run.call_args.args[0])


if __name__ == '__main__':
    unittest.main()
