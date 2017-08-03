#!/usr/bin/env python3

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

import subprocess
import sys
import logging


def configure_logger(use_color=True):
    class ColoredFormatter(logging.Formatter):
        """Adds coloring to a log message if using a TTY"""

        def __init__(self, use_color, *args, **kwargs):
            self.use_color = use_color
            super(ColoredFormatter, self).__init__(*args, **kwargs)

        def format(self, record):
            return get_colored(
                super(ColoredFormatter, self).format(record),
                use_color=self.use_color
            )

    format = "[%(levelname)-5s] %(message)s"
    logging.basicConfig(level=logging.DEBUG, format=format)

    formatter = ColoredFormatter(use_color=use_color, fmt=format)
    for handler in logging.getLogger().handlers:
        handler.setFormatter(formatter)


def readable_check_call(args, action="", **kwargs):
    """
    Runs check_call and prints out the command that's being run

    Params:
        action - A description used in logging saying what was being
                 attempted with this call
    """
    try:
        logging.info("{bold}Running %s{clear}", " ".join(args))
        subprocess.check_call(args, **kwargs)
    except subprocess.CalledProcessError:
        logging.error(
            "{red}Got non-zero exit from '%s' while %s{clear}", " ".join(args),
            action
        )
        raise
    finally:
        sys.stderr.flush()
        sys.stdout.flush()


def readable_check_output(args, action="", **kwargs):
    """
    Runs check_call and prints out the command that's being run

    Params:
        action - A description used in logging saying what was being
                 attempted with this call
    """
    try:
        logging.info("{bold}Running %s{clear}", " ".join(args))
        return subprocess.check_output(args, **kwargs).decode('utf-8')
    except subprocess.CalledProcessError:
        logging.error(
            "{red}Got non-zero exit from '%s' while %s{clear}", " ".join(args),
            action
        )
        raise
    finally:
        sys.stderr.flush()
        sys.stdout.flush()


def get_colored(format_string, file=sys.stdout, use_color=True):
    """
    Returns a string that adds formatting based on stdout

    args and kwargs are interpolated, and various colors are added if stdout
    is a tty
    """
    is_tty = file.isatty()
    use_color = use_color and is_tty

    return format_string\
        .replace('{clear}', '\033[0m' if use_color else '')\
        .replace('{bold}', '\033[1m' if use_color else '')\
        .replace('{dim}', '\033[2m' if use_color else '')\
        .replace('{standout}', '\033[3m' if use_color else '')\
        .replace('{underline}', '\033[4m' if use_color else '')\
        .replace('{blink}', '\033[5m' if use_color else '')\
        .replace('{rev}', '\033[7m' if use_color else '')\
        .replace('{invis}', '\033[8m' if use_color else '')\
        .replace('{black_fg}', '\033[30m' if use_color else '')\
        .replace('{red_fg}', '\033[31m' if use_color else '')\
        .replace('{green_fg}', '\033[32m' if use_color else '')\
        .replace('{yellow_fg}', '\033[33m' if use_color else '')\
        .replace('{blue_fg}', '\033[34m' if use_color else '')\
        .replace('{magenta_fg}', '\033[35m' if use_color else '')\
        .replace('{cyan_fg}', '\033[36m' if use_color else '')\
        .replace('{white_fg}', '\033[37m' if use_color else '')\
        .replace('{reset_fg}', '\033[39m' if use_color else '')\
        .replace('{black}', '\033[40m' if use_color else '')\
        .replace('{red}', '\033[41m' if use_color else '')\
        .replace('{green}', '\033[42m\033[30m' if use_color else '')\
        .replace('{yellow}', '\033[43m\033[30m' if use_color else '')\
        .replace('{blue}', '\033[44m' if use_color else '')\
        .replace('{magenta}', '\033[45m' if use_color else '')\
        .replace('{cyan}', '\033[46m' if use_color else '')\
        .replace('{white}', '\033[47m' if use_color else '')\
        .replace('{reset_bg}', '\033[49m' if use_color else '')
