import logging
import logmatic
import os
import unittest
from mock import patch

import baseutils


class TestUtils(unittest.TestCase):
    def test_logger(self):
        logger = logging.getLogger()
        baseutils.configure_logger(logger, file_path='/tmp/logfile', level=logging.INFO)
        self.assertIsInstance(logger.handlers[0], logging.handlers.RotatingFileHandler)
        self.assertIsInstance(logger.handlers[0].formatter, logging.Formatter)
        self.assertEqual(logging.INFO, logger.level)
        logger.handlers = []
        baseutils.configure_logger(logger, stream=True, json_formatter=True, level=logging.ERROR)
        self.assertIsInstance(logger.handlers[0].formatter, logmatic.JsonFormatter)
        self.assertEqual(logging.ERROR, logger.level)
        logger.handlers = []
        formatter = logging.Formatter('[%(asctime)-15s] [unittests] %(levelname)s %(message)s')
        baseutils.configure_logger(logger, stream=True, formatter=formatter)
        self.assertIsInstance(logger.handlers[0], logging.StreamHandler)
        self.assertEqual(formatter, logger.handlers[0].formatter)
        formatter2 = logging.Formatter('[%(asctime)-15s] [unittests2] %(levelname)s %(message)s')
        baseutils.replace_logger_formatter(logger, formatter2)
        self.assertEqual(formatter2, logger.handlers[0].formatter)

    def test_discover_github_latest_patch_version(self):
        release_url = 'https://api.github.com/repos/kubernetes/kubernetes/releases'
        version_not_passing_patch = baseutils.discover_github_latest_patch_release('1.12', release_url)
        version_passing_patch = baseutils.discover_github_latest_patch_release('1.12.1', release_url)
        self.assertEqual(version_not_passing_patch, version_passing_patch)
        self.assertTrue(version_not_passing_patch.startswith('v1.12.'))

    def test_exe_cmd(self):
        self.assertEqual(baseutils.exe_cmd('echo -n value'), (0, 'value'))
        self.assertEqual((0, 'value'), baseutils.exe_cmd('echo -n "value"'))
        custom_value = 'value1'
        custom_env = os.environ.copy()
        custom_env['custom_value'] = custom_value
        self.assertEqual((0, custom_value), baseutils.exe_cmd('echo -n "${custom_value}"', env=custom_env))
        self.assertEqual((0, custom_value), baseutils.exe_cmd('less', stdin=custom_value))
        (rc, output) = baseutils.exe_cmd('fakecmd', raise_exception=False)
        self.assertEqual(127, rc)

    def test_retry(self):
        pid = os.getpid()
        self.assertEquals(pid, baseutils.retry(os.getpid))
        self.assertEquals(pid, baseutils.retry(os.getpid, retry=5, interval=5))
        a = [1, 2]
        self.assertEquals(len(a), baseutils.retry(len, a, interval=5))
        try:
            baseutils.retry(dict, 'value', retry=1, interval=1)
            self.fail('baseutils.retry passed a failed attempt to create a dictionary')
        except Exception as e:
            self.assertIsInstance(e, ValueError)

    @patch('smtplib.SMTP')
    def test_send_mail(self, mock_smtp):
        mock_smtp_instance = mock_smtp.return_value
        baseutils.send_mail('unittest@travis.ibm.com', ['user1@ie.ibm.com'], 'Unit Test Email Subject', 'Unit Test Email Body',
                            cc=['user2@ie.ibm.com'], bcc=['user3@ie.ibm.com'], smtp_server='localhost')
        self.assertEqual(1, mock_smtp_instance.sendmail.call_count)
        self.assertEqual(('unittest@travis.ibm.com', ['user1@ie.ibm.com', 'user2@ie.ibm.com', 'user3@ie.ibm.com']), mock_smtp_instance.sendmail.call_args_list[0][0][0:2])
        self.assertEqual(1, mock_smtp_instance.quit.call_count)

    def test_shell_escape(self):
        self.assertEqual(baseutils.shell_escape('a\'b'), '\'a\'"\'"\'b\'')

    def test_timeout(self):
        timeout = baseutils.timeout()
        self.assertRaises(Exception, timeout.handle_timeout)


if __name__ == '__main__':
    unittest.main()
