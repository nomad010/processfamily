__author__ = 'matth'

from processfamily import _winprocess_ctypes
import subprocess
import os
import sys
import msvcrt

DEVNULL = -3

#Relevant python docs:
# http://bugs.python.org/issue19764
# http://legacy.python.org/dev/peps/pep-0446/

class WinPopen(subprocess.Popen):


    def __init__(self, args, bufsize=0, executable=None,
                 stdin=None, stdout=None, stderr=None,
                 preexec_fn=None, close_fds=False, shell=False,
                 cwd=None, env=None, universal_newlines=False,
                 startupinfo=None, creationflags=0, pass_handles_over_commandline=False):

        self.pass_handles_over_commandline = pass_handles_over_commandline
        if pass_handles_over_commandline:
            if not isinstance(bufsize, (int, long)):
                raise TypeError("bufsize must be an integer")

            #must be all or nothing for now
            for p in [stdin, stdout, stderr]:
                if p not in [DEVNULL, subprocess.PIPE]:
                    raise ValueError("Only PIPE or DEVNULL is supported if pass_handles_over_commandline is True")

            self.commandline_passed = {}
            for s, p, m in [('stdin', stdin, 'w'), ('stdout', stdout, 'r'), ('stderr', stderr, 'r')]:
                if p == subprocess.PIPE:

                    if m == 'r':
                        mode = 'rU' if universal_newlines else 'rb'
                    else:
                        mode = 'wb'

                    piperead, pipewrite = os.pipe()
                    myfile = os.fdopen(pipewrite if m == 'w' else piperead, mode, bufsize)
                    childhandle = str(int(msvcrt.get_osfhandle(pipewrite if m == 'r' else piperead)))
                    self.commandline_passed[s] = (myfile, childhandle, piperead, pipewrite)
                else:
                    childhandle = str(int(msvcrt.get_osfhandle(open(os.devnull, m))))
                    self.commandline_passed[s] = (None, childhandle)

            args += [str(os.getpid()),
                     self.commandline_passed['stdin'][1],
                     self.commandline_passed['stdout'][1],
                     self.commandline_passed['stderr'][1],
                     ]

            stdin, stdout, stderr = None, None, None

        super(WinPopen, self).__init__(args, bufsize=bufsize, executable=executable,
                 stdin=stdin, stdout=stdout, stderr=stderr,
                 preexec_fn=preexec_fn, close_fds=close_fds, shell=shell,
                 cwd=cwd, env=env, universal_newlines=universal_newlines,
                 startupinfo=startupinfo, creationflags=creationflags)

        if pass_handles_over_commandline:
            self.stdin = self.commandline_passed['stdin'][0]
            self.stdout = self.commandline_passed['stdout'][0]
            self.stderr = self.commandline_passed['stderr'][0]

    def _execute_child(self, *args_tuple):
        if sys.hexversion < 0x02070600: # prior to 2.7.6
            (args, executable, preexec_fn, close_fds,
             cwd, env, universal_newlines, startupinfo,
             creationflags, shell,
             p2cread, p2cwrite,
             c2pread, c2pwrite,
             errread, errwrite) = args_tuple
            to_close = None
        else: # 2.7.6 and later
            (args, executable, preexec_fn, close_fds,
             cwd, env, universal_newlines, startupinfo,
             creationflags, shell, to_close,
             p2cread, p2cwrite,
             c2pread, c2pwrite,
             errread, errwrite) = args_tuple

        # Always or in the create new process group
        creationflags |= _winprocess_ctypes.CREATE_NEW_PROCESS_GROUP

        if _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO:
            attribute_list_data = ()
            startupinfoex           = _winprocess_ctypes.STARTUPINFOEX()
            startupinfo             = startupinfoex.StartupInfo
            startupinfo.cb          = _winprocess_ctypes.sizeof(_winprocess_ctypes.STARTUPINFOEX)
            startupinfo_argument = startupinfoex
        else:
            startupinfo = _winprocess_ctypes.STARTUPINFO()
            startupinfo_argument = startupinfo
        inherit_handles = 0 if close_fds else 1

        if None not in (p2cread, c2pwrite, errwrite):
            if close_fds:
                HandleArray = _winprocess_ctypes.HANDLE * 3
                handles_to_inherit = HandleArray(int(p2cread), int(c2pwrite), int(errwrite))

                attribute_list_data = (
                    (
                        _winprocess_ctypes.PROC_THREAD_ATTRIBUTE_HANDLE_LIST,
                        handles_to_inherit
                    ),
                )
                inherit_handles = 1

            startupinfo.dwFlags |= _winprocess_ctypes.STARTF_USESTDHANDLES
            startupinfo.hStdInput = int(p2cread)
            startupinfo.hStdOutput = int(c2pwrite)
            startupinfo.hStdError = int(errwrite)

        if _winprocess_ctypes.CAN_USE_EXTENDED_STARTUPINFO:
            attribute_list = _winprocess_ctypes.ProcThreadAttributeList(attribute_list_data)
            startupinfoex.lpAttributeList = attribute_list.value
            creationflags |= _winprocess_ctypes.EXTENDED_STARTUPINFO_PRESENT

        if shell:
            raise NotImplementedError()

        def _close_in_parent(fd):
            fd.Close()
            if to_close:
                to_close.remove(fd)

        # set process creation flags
        if env:
            creationflags |= _winprocess_ctypes.CREATE_UNICODE_ENVIRONMENT

        if not isinstance(args, basestring):
            args = subprocess.list2cmdline(args)

        # create the process
        try:
            hp, ht, pid, tid = _winprocess_ctypes.CreateProcess(
                executable, args,
                None, None, # No special security
                inherit_handles, #Inherit handles
                creationflags,
                _winprocess_ctypes.EnvironmentBlock(env) if env else None,
                cwd,
                startupinfo_argument)
        finally:
            # Child is launched. Close the parent's copy of those pipe
            # handles that only the child should have open.  You need
            # to make sure that no handles to the write end of the
            # output pipe are maintained in this process or else the
            # pipe will not close when the child process exits and the
            # ReadFile will hang.
            if p2cread is not None:
                _close_in_parent(p2cread)
            if c2pwrite is not None:
                _close_in_parent(c2pwrite)
            if errwrite is not None:
                _close_in_parent(errwrite)

        self._child_created = True
        self._handle = hp
        self._thread = ht
        self.pid = pid
        self.tid = tid

        ht.Close()
