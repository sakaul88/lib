import logging
import logmatic
import os
import unittest
from mock import Mock
from mock import patch

import baseutils


class TestUtils(unittest.TestCase):
    def test_logger(self):
        logger = logging.getLogger()
        baseutils.configure_logger(logger, file_path='/tmp/logfile')
        self.assertTrue(isinstance(logger.handlers[0], logging.handlers.RotatingFileHandler))
        self.assertTrue(isinstance(logger.handlers[0].formatter, logmatic.JsonFormatter))
        logger.handlers = []
        formatter = logging.Formatter('[%(asctime)-15s] [unittests] %(levelname)s %(message)s')
        baseutils.configure_logger(logger, stream=True, formatter=formatter)
        self.assertTrue(isinstance(logger.handlers[0], logging.StreamHandler))
        self.assertEqual(formatter, logger.handlers[0].formatter)
        formatter2 = logging.Formatter('[%(asctime)-15s] [unittests2] %(levelname)s %(message)s')
        baseutils.replace_logger_formatter(logger, formatter2)
        self.assertEqual(formatter2, logger.handlers[0].formatter)

    def test_exe_cmd(self):
        self.assertEqual(baseutils.exe_cmd('echo -n value'), (0, 'value'))
        self.assertEqual((0, 'value'), baseutils.exe_cmd('echo -n "value"'))
        custom_value = 'value1'
        custom_env = os.environ.copy()
        custom_env['custom_value'] = custom_value
        self.assertEqual((0, custom_value), baseutils.exe_cmd('echo -n "${custom_value}"', env=custom_env))

    @patch('smtplib.SMTP')
    def test_send_mail(self, mock_smtp):
        mock_smtp_instance = mock_smtp.return_value
        baseutils.send_mail('unittest@travis.ibm.com', ['user1@ie.ibm.com'], 'Unit Test Email Subject', 'Unit Test Email Body',
                            cc=['user2@ie.ibm.com'], bcc=['user3@ie.ibm.com'], smtpServer='localhost')
        self.assertEqual(1, mock_smtp_instance.sendmail.call_count)
        self.assertEqual(('unittest@travis.ibm.com', ['user1@ie.ibm.com', 'user2@ie.ibm.com', 'user3@ie.ibm.com']), mock_smtp_instance.sendmail.call_args_list[0][0][0:2])
        self.assertEqual(1, mock_smtp_instance.quit.call_count)

    def test_shell_escape(self):
        self.assertEqual(baseutils.shell_escape('a\'b'), '\'a\'"\'"\'b\'')

    def test_timeout(self):
        timeout = baseutils.timeout()
        self.assertRaises(Exception, timeout.handle_timeout)

    @patch('baseutils.baseutils.create_ssh_client')
    def test_parallel_ssh(self, mock_create_ssh_client):
        mock_client = mock_create_ssh_client.return_value
        std_out = Mock()
        std_out.readlines.return_value = ['my', 'content']
        mock_client.exec_command.return_value = ('in', std_out, 'err')
        result = baseutils.parallel_ssh([{'ip': '127.0.0.1', 'username': 'centos', 'sshKey': 'abc'}], 'cmd')
        self.assertEqual(result[0]['output'], 'mycontent')


if __name__ == '__main__':
    unittest.main()
