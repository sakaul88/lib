import logging
import logmatic
import signal
import smtplib
import subprocess
from email.MIMEMultipart import MIMEMultipart
from email.MIMEText import MIMEText

logger = logging.getLogger(__name__)


def configure_logger(custom_logger, file_path=None, stream=False, formatter=None, json_formatter=False, level=logging.INFO):
    """
    Configure a logger in a standard way for python applications.
    Args:
        custom_logger: The logger to be configured
        file_path: The path to a log file to use. If not provided, file logging will not be enabled
        stream: Set True if logs should be streamed to standard out. (Default: False)
        formatter: A custom formatter to use. If not provided, standard formatter will be created. See arg json_formatter for details (Optional)
        json_formatter: If a formatter is not provided, this identifies if the formatter that will be created should be a json formatter (logmatics) or a standard formatter
    """
    if file_path:
        handler = logging.handlers.RotatingFileHandler(file_path, backupCount=10, maxBytes=10240000)
        _add_logger_handler(custom_logger, handler, formatter)
    if stream:
        handler = logging.StreamHandler()
        _add_logger_handler(custom_logger, handler, formatter, json_formatter=json_formatter)
    custom_logger.setLevel(level)


def _add_logger_handler(custom_logger, handler, formatter=None, json_formatter=False):
    """
    Add a handler to a logger. If a formatter is not provided, a default logmatic one will be created.
    Args:
        custom_logger: The logger to add the handler to
        handler: The handler to add
        formatter: The formatter for formatting the log. See arg json_formatter for details (Optional)
        json_formatter: If a formatter is not provided, this identifies if the formatter that will be created should be a json formatter (logmatics) or a standard formatter
    """
    if not formatter:
        if json_formatter:
            formatter = logmatic.JsonFormatter()
        else:
            formatter = logging.Formatter('[%(asctime)-15s] [%(module)s] [%(funcName)s] %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    custom_logger.addHandler(handler)


def replace_logger_formatter(custom_logger, formatter):
    """
    Replaces the formatter used by a logger's handlers.
    Args:
        formatter: The formatter for formatting the log
    """
    for handler in custom_logger.handlers:
        handler.setFormatter(formatter)


def exe_cmd(cmd, working_dir=None, obfuscate=None, env=None, log_level=logging.INFO, raise_exception=True):
    """
    Helper function for easily executing a command.
        cmd: The command to execute
        working_dir: The directory to execution the command from (Optional)
        obfuscate: A value to obfuscate in the logging (Optional)
        log_level: The default logging level. Default: INFO. Setting to None will disable logging in this function
        raise_exception: Whether to raise an exception if the command return a non-zero return code (Default: True)
    """
    obfus_cmd = cmd.replace(obfuscate, '***') if obfuscate else cmd
    logger.info('Executing: %s' % (obfus_cmd))
    p = subprocess.Popen(cmd, shell=True, bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=working_dir, universal_newlines=True, env=env)
    output = ''
    for line in iter(p.stdout.readline, ''):
        output += line
        if line.strip():
            logger.log(log_level, line.rstrip())
    p.stdout.close()
    rc = p.wait()
    if rc:
        if raise_exception:
            raise Exception('Error executing command: %s. RC: %s' % (obfus_cmd, rc,))
        else:
            logger.error('Error executing command: %s.    RC: %s' % (obfus_cmd, rc))
    logger.info('Command successful. Returning output')
    return (rc, output)


def send_mail(mail_from, mail_to, subject, body, cc=None, bcc=None, smtpServer='localhost'):
    """
    Helper function to send a mail.
    Args:
        mail_from: The emails to be listed as the sending user. Value is a string
        mail_to: A list of email addresses to send the email to. Value is a list of strings
        subject: The subject of the email
        body: The content of the email
        cc: A list of email addresses to cc on the email. Value is a list of strings. (Optional)
        bcc: A list of email addresses to bcc on the email. Value is a list of strings. (Optional)
        smtp_server: The SMTP server to use to send the mail. (Optional, default: localhost)
    Example: send_mail('scdevops@us.ibm.com', ['johnsmith@us.ibm.com', 'mikethompson@us.ibm.com'], 'Deployment Failure', '<content>', ['smitha@us.ibm.com', 'smithb@us.ibm.com'])
    """
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = mail_from
    msg['To'] = ','.join(mail_to)
    if cc:
        msg['Cc'] = ','.join(cc)
        mail_to.extend(cc)
    if bcc:
        msg['Bcc'] = ','.join(bcc)
        mail_to.extend(bcc)
    part2 = MIMEText(body, 'html')
    msg.attach(part2)
    server = smtplib.SMTP(smtpServer)
    server.sendmail(msg['From'], mail_to, msg.as_string())
    server.quit()


def shell_escape(value):
    """
    Wraps a value in single quotes and escapes internal single quotes.
    Args:
        The value to escape for safe shell execution
    """
    return "'" + value.replace("'", "'\"'\"'") + "'"


class timeout:
    """
    A timeout class to allow for an exception to be triggered when a passed time period is exceeded.
    This class is intended to be use via the 'with' syntax.
    Example:
        with timeout(seconds=500):
            do_something
    """
    def __init__(self, seconds=1, error_message='A timeout exception has occurred due to exceeding timeout period of SECONDS seconds'):
        self.seconds = seconds
        self.error_message = error_message.replace('SECONDS', str(seconds))

    def handle_timeout(self, signum, frame):
        raise Exception(self.error_message)

    def __enter__(self):
        signal.signal(signal.SIGALRM, self.handle_timeout)
        signal.alarm(self.seconds)

    def __exit__(self, type, value, traceback):
        signal.alarm(0)
