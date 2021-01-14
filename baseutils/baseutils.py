import json
import logging
import logmatic
import os
import sys
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


def assert_linux():
    """
    Throws an exception if the os is Windows.
    Call thid from any functions that do not work in Windows.
    """
    if os.name == 'nt':
        raise Exception('This function currently does not support Windows')


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
        handler = logging.handlers.RotatingFileHandler(file_path, backupCount=10, maxBytes=52428800)
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
    version = ''
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

    if os.name == 'nt' and sys.version_info[0] == 3:
        # the encoding is needed for windows & python3
        p = subprocess.Popen(cmd, shell=True, bufsize=0, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, encoding='utf-8',
                             stdin=subprocess.PIPE if stdin else None, cwd=working_dir, universal_newlines=True, env=env)
    else:
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
    if os.name == 'nt':
        return '"' + value.replace('"', '\\"') + '"'
    else:
        return "'" + value.replace("'", "'\"'\"'") + "'"


def send_slack(token, channel, message):
    """
    Single function to send message to Slack using Slack app and web API.
    Args:
        token: The access token for Slack app
        channel: The channel to send the message to
        message: The content of the message
    """
    url = 'https://slack.com/api/chat.postMessage'
    headers = {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Authorization': 'Bearer {}'.format(token)
    }
    data = {
        'channel': channel,
        'text': message,
    }
    try:
        response = requests.post(url=url, headers=headers, data=json.dumps(data))
        if not response.ok:
            logger.error('Failed to post to Slack channel {channel}: {err}'.format(channel=channel, err=response.text))
    except Exception as err:
        logger.error('Error posting to Slack channel: {}'.format(err))


def send_p2paas_slack(token, msg_title, msg_id='Unknown', msg_severity=None, cluster=None, job=None, msg_details=None):  # noqa: C901
    """
    Helper function that should be used when submitting messages to p2paas-awx-alerts that will ensure consistent messages.
    Args:
        token: The token to use for auth
        msg_title: The title (ie first line) of the message
        msg_id (optional but strongly recommended): An id that uniquely identifies the scenario/caller.
            This allows people to easily track the message back to the code that created it.
            This should follow a format of prefix_####, ex: PAIO_0001
        msg_severity (optional but strongly recommended): 1, 2 or 3
        cluster (optional): the cluster the message applies to. If the message applies to multiple clusters then the cluster names should be included with the details.
        job name: pulled from environ.get('tower_job_template_name')
        job id: pulled from os.environ['tower_job_id']
        job: no longer used, replaced by tower_job_id
        msg_details (optional but strongly recommended): The main message content.
    """
    # todo:
    # add token/title check?
    # add optional playbook field?
    # add random icons? :)
    lines = []
    lines.append('*{msg_id}: {msg_title}*'.format(msg_id=msg_id, msg_title=msg_title))
    if msg_severity is not None:
        # todo: add icon / colour?
        sev = msg_severity
        if (msg_severity == 1):
            sev = '*High*'
            # add @here?
        elif (msg_severity == 2):
            sev = 'Medium'
        elif (msg_severity == 3):
            sev = 'Low'
        else:
            sev = 'Unknown'
        lines.append('Severity: {}'.format(sev))
    if cluster is not None:
        lines.append('Cluster: {}'.format(cluster))
    job_name = os.environ.get('tower_job_template_name', 'Unknown')
    lines.append('AWX Template: {}'.format(job_name))
    job_id = os.environ.get('tower_job_id', 'Unknown')
    lines.append('AWX Job: {}'.format(job_id))

    if msg_details is not None:
        lines.append('```{}```'.format(msg_details))

    message = '\n'.join(lines)
    logger.debug('Sending {} lines to slack'.format(len(lines)))
    send_slack(token, 'p2paas-awx-alerts', message)


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
