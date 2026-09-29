"""Offline naming/ownership negatives and actual runner wiring, no launch."""
import inspect
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import logger_file
import run


class LoggerFileTest(unittest.TestCase):
    def test_restart_preserves_profile_rate_buffer_but_no_timestamp(self):
        cli=Mock()
        with patch.object(logger_file.time,'sleep') as sleep:
            logger_file.restart(cli)
        self.assertEqual(cli.call_args_list[0].args,('logger','stop'))
        self.assertEqual(cli.call_args_list[1].args,('logger','start','-b','256','-r','1000','-f'))
        sleep.assert_called_once_with(1.1)

    def test_stop_failure_cannot_start_another_writer(self):
        cli=Mock(side_effect=RuntimeError('stop failed'))
        with self.assertRaises(RuntimeError):logger_file.restart(cli)
        self.assertEqual(cli.call_count,1)

    def test_unique_new_session_preserves_old_path_bytes(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);old=root/'2026-09-29/03_52_10.ulg';old.parent.mkdir();old.write_bytes(b'old')
            before={old};new=root/'sess001/log001.ulg';new.parent.mkdir();new.write_bytes(b'new')
            self.assertEqual(logger_file.owned_log(root,before),new)
            self.assertEqual(old.read_bytes(),b'old')

    def test_missing_or_rewritten_same_path_not_new(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            with self.assertRaises(RuntimeError):logger_file.owned_log(root,set())
            old=root/'old.ulg';old.write_bytes(b'old');before={old};old.write_bytes(b'overwritten')
            with self.assertRaises(RuntimeError):logger_file.owned_log(root,before)

    def test_multiple_new_writers_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for i in (1,2):
                f=root/f'sess00{i}/log001.ulg';f.parent.mkdir();f.write_bytes(b'new')
            with self.assertRaises(RuntimeError):logger_file.owned_log(root,set())

    def test_timestamp_name_and_symlink_escape_rejected(self):
        for kind in ('timestamp','file_link','directory_link'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as t:
                root=Path(t)/'log';root.mkdir();other=Path(t)/'outside';other.mkdir();f=other/'log001.ulg';f.write_bytes(b'other')
                if kind=='directory_link':(root/'sess001').symlink_to(other,target_is_directory=True)
                else:
                    parent=root/('2026-09-29' if kind=='timestamp' else 'sess001');parent.mkdir()
                    if kind=='timestamp':(parent/'03_52_10.ulg').write_bytes(b'old naming')
                    else:(parent/'log001.ulg').symlink_to(f)
                with self.assertRaises(RuntimeError):logger_file.owned_log(root,set())

    def test_real_runner_uses_restart_and_unique_session_before_live_checks(self):
        self.assertIs(run.restart_logger,logger_file.restart)
        self.assertIs(run.owned_log,logger_file.owned_log)
        self.assertIn('restart_logger(cli)',inspect.getsource(run.Checks.__call__))
        self.assertIn("owned_log(self.log_root,self.logs_before)",inspect.getsource(run.Checks.start_heading))
        self.assertIn('PositionLiveLog',inspect.getsource(run.Checks.start_heading))


if __name__=='__main__':unittest.main(verbosity=2)
