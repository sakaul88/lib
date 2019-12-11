import logging
import logmatic
import os
import requests
import signal
import smtplib
import subprocess
import tempfile
import time
try:  # python3
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
except ImportError:
    from email.MIMEMultipart import MIMEMultipart
    from email.MIMEText import MIMEText
try:
    import fcntl
except ImportError:
    pass  # fcntl is not available on Windows. The local_lock function will not work there


logger = logging.getLogger(__name__)


def configure_logger(custom_logger, file_path=None, stream=False, formatter=None, json_formatter=False, level=logging.INFO):
    """
    Configure a logger in a standard way for python applications.
    Args:
        custom_logger: The logger to be configured
        file_path: The path to a log file to use. If not provided, file logging will not be enabled (Optional)
        stream: Set True if logs should be streamed to standard out. (Default: False)
        formatter: A custom formatter to use. If not provided, standard formatter will be created. See arg json_formatter for details (Optional)
        json_formatter: If a formatter is not provided, this identifies if the formatter that will be created should be a json formatter (logmatics) or a standard formatter
        level: The log level to configure (Optional, default: logging.INFO)
    """
    if file_path:
        handler = logging.handlers.RotatingFileHandler(file_path, backupCount=10, maxBytes=20971520)
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


def discover_github_latest_patch_release(version_to_match, release_url, pat=None):
    """
    Given a major.minor version, or a major.minor.patch version, the vmajor.minor.latest_available version is discovered for a GitHub release url.
    Args:
        version_to_match: The initial version for which a lookup is being performed, eg. 1.0 or 1.0.1
        release_url: URL to GitHub api for the release
        pat: An optional GitHub personal access token. Authenticated requests have higher rate limits (Optional)
    Returns: The matched vmajor.minor.latest_available version, eg v1.0.2
    """
    releases = requests.get(release_url, headers={'Authorization': 'token {pat}'.format(pat=pat)} if pat else None)
    if not releases.ok:
        raise Exception('Failed to retrieve releases from GitHub: {error}'.format(error=releases.text))
    version_to_match = version_to_match.split('.')
    version_to_match = 'v{major}.{minor}.'.format(major=version_to_match[0], minor=version_to_match[1])
    for release in releases.json():
        if release['tag_name'].startswith(version_to_match):
            version = release['tag_name']
            break
    return version


def exe_cmd(cmd, working_dir=None, obfuscate=None, stdin=None, env=None, log_level=logging.INFO, raise_exception=True):
    """
    Helper function for easily executing a command.
        cmd: The command to execute
        working_dir: The directory to execution the command from (Optional)
        obfuscate: A value to obfuscate in the logging (Optional)
        stdin: A string to pass as standard input to the process (Optional)
        env: Custom environment variables to be used in place of parent envrionment variables (Optional, default: parent process environment variables)
        log_level: The default logging level. Default: INFO. Setting to None will disable logging in this function
        raise_exception: Whether to raise an exception if the command return a non-zero return code (Default: True)
    """
    obfus_cmd = cmd.replace(obfuscate, '***') if obfuscate else cmd
    logger.info('Executing: %s' % (obfus_cmd))
    p = subprocess.Popen(cmd, shell=True, bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.PIPE if stdin else None, cwd=working_dir, universal_newlines=True, env=env)
    if stdin:
        p.stdin.write(stdin)
        p.stdin.close()
    output = ''
    for line in iter(p.stdout.readline, ''):
        output += line
        if line.strip():
            logger.log(log_level, line.rstrip())
    p.stdout.close()
    rc = p.wait()
    if rc:
        if raise_exception:
            raise Exception('Error executing command: {cmd}. RC: {rc}. Output: {output}'.format(
                cmd=obfus_cmd,
                rc=rc,
                output='***' if log_level == logging.NOTSET else output))
        else:
            logger.info('Command returned RC {rc} but received instruction not to raise exception. This may be normal'.format(rc=rc))
    else:
        logger.info('Command successful. Returning output')
    return (rc, output)


class local_lock:
    """
    A lock class to support locking against a local file. This allows some coordination between seperate processes on the same system.
    This class is intended to be use via the 'with' syntax.
    Only a single thread and single process may acquire the lock at one time on a given system.
    Warning: A thread must not attempt to acquire the lock more than once.
    This function does not work on Windows.
    Example:
        with local_lock():
            do_something
    """
    def __init__(self, lock_name='local'):
        """
        Constructor for the lock object.
        Args:
            lock_name: The name of the lock. Contention for locks will only occur between locks with the same name. The value must be safe for use as a filename (Optional)
        """
        self.lock_file_path = os.path.join(tempfile.gettempdir(), 'py.{name}.lockfile'.format(name=lock_name))
        self.lock_file = None

    def __enter__(self):
        self.lock_file = open(self.lock_file_path, 'w')
        fcntl.flock(self.lock_file, fcntl.LOCK_EX)

    def __exit__(self, type, value, traceback):
        fcntl.flock(self.lock_file, fcntl.LOCK_UN)
        self.lock_file.close()


def retry(func, *args, **kwargs):
    """
    Helper method for retrying a function that fails by throwing an exception.
    If all retries fail, the exception that was raised by the failing function is re-raised.
    Args:
        func: The function to retry
        *args: Any arguments that are passed to the function
        **kwargs: Any keyword arguments that are passed to the function
        interval: The time between retries. This parameter will be removed from kwargs before forwarding to the function (Optional, default: 10 seconds)
        retry: The number of times to retry. This parameter will be removed from kwargs before forwarding to the function (Optional, default: 10)
    Returns: The return value of the passed function
    """
    if 'interval' in kwargs:
        interval = kwargs['interval']
        del kwargs['interval']
    else:
        interval = 10
    if 'retry' in kwargs:
        retry = kwargs['retry']
        del kwargs['retry']
    else:
        retry = 10
    for i in range(1, retry + 1):
        try:
            return func(*args, **kwargs)
        except Exception:
            if i == retry:
                raise
            else:
                logger.warning('Function "{func}" failed. Retrying {retry} more time(s) in {interval} second(s)'.format(func=func.__name__, retry=retry - i, interval=interval))
                time.sleep(interval)


def send_mail(mail_from, mail_to, subject, body, cc=None, bcc=None, smtp_server='localhost'):
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
    server = smtplib.SMTP(smtp_server)
    server.sendmail(msg['From'], mail_to, msg.as_string())
    server.quit()


def shell_escape(value):
    """
    Wraps a value in single quotes and escapes internal single quotes.
    Args:
        The value to escape for safe shell execution
    Returns: The escaped parameter that is safe to pass into a shell command
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
