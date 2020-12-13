#!/usr/bin/env python3
#
# cgetools.jobcontrol.job - base functionality for backend jobs.
#
#   Defines classes JobSpec and Job.  JobSpec hold the command, arguments, and
#   resource requirements of the job (so the scheduler can decide if/how it can
#   run).  Job is the base class for derived job types and hold State and an
#   error message.

import enum


class JobSpec:
    '''Specification of a job: command, arguments, and resource requirements.'''

    def __init__(self, command, args, cpu=1, mem=1, spc=1, tim=0):
        '''Defines the command and argument list, required cpus, GB memory,
           GB disc space, and maximum wall run time of the job.'''
        self.command = command
        self.args = args
        self.cpu = cpu
        self.mem = mem
        self.spc = spc
        self.tim = tim

    def as_dict(self):
        '''Return self as a dict, so it can be serialised to blackboard.'''
        return dict({
            'command': self.command,
            'args': self.args,
            'resources': {
                'cpu': self.cpu,
                'mem': self.mem,
                'spc': self.spc,
                'tim': self.tim }
            })

class Job:
    '''Base class defining common functionality across all job types.'''

    class State(enum.Enum):
        '''Enum defining the states a job can be in.'''
        QUEUED = 'QUEUED'
        RUNNING = 'RUNNING'
        COMPLETED = 'COMPLETED'
        FAILED = 'FAILED'

    _state = State.QUEUED
    _error = None
    _spec = None

    def __init__(self, spec):
        self._spec = spec

    @property
    def state(self):
        return self._state

    @property
    def error(self):
        return self._error

    @property
    def spec(self):
        return self._spec

    def fail(self, errmsg, *args):
        '''Mark the job as FAILED, storing the error message.'''
        self._error = errmsg % args
        self._state = Job.State.FAILED

