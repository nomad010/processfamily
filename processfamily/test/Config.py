from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
from future import standard_library
standard_library.install_aliases()
from builtins import *
__author__ = 'matth'

import os
import sys

pythonw_exe = os.path.join(sys.prefix, "pythonw.exe")
svc_name = 'ProcessFamilyTest'
def get_starting_port_nr():
    return int(os.environ.get("PROCESSFAMILY_TESTS_STARTING_PORT_NR", "9080"))