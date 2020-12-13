#!/usr/bin/env python3
#
# WorkflowBlackboard - Defines the blackboard passed between WorkflowServices.
#
#   The blackboard essentially is a dict with some convenience wrappers to ease
#   getting and putting values in the dict using 'paths'.  E.g. to add a value
#   to a list element, use add_to_list('path/to/elem', value).
#
#   The blackboard also maintains a log to which any client can add lines.  It
#   is returned as the blackboard's 'log' element.
#

import sys
from datetime import datetime

def timestamp():
    return datetime.now().isoformat(timespec='seconds')

class Blackboard:

    _data = dict()
    _log_lines = list()
    _verbose = False

    def __init__(self, verbose=False):
        self._verbose = verbose
        self.log("log started")

    def log(self, string, *args):
        msg = string % args
        if self._verbose:
            print('log: %s' % msg, file=sys.stderr, flush=True)
        self._log_lines.append('%s %s' % (timestamp(), msg))

    def as_dict(self, with_log = False):
        '''Return the blackboard as a dict, optionally including the log.'''
        if with_log:
            self._data['log'] = self._log_lines
        else:
            self._data.pop('log', None)
        return self._data

    def get(self, path, default = None):
        '''Return the value at path in the data dict.'''
        parts = path.split('/')
        d = self._data
        for p in parts:
            d = d.get(p)
            if d is None:
                return default
        return d

    def put(self, path, value):
        '''Set the value at path in the blackboard dict.'''
        parts = path.split('/')
        d0 = self._data
        for p in parts[:-1]:
            if not p: continue
            d1 = d0.get(p)
            if d1 is None:
                d0[p] = dict()
                d1 = d0.get(p)
            d0 = d1
        d0[parts[-1]] = value

    def append_to(self, path, value, uniq=False):
        '''Add value to the list at path in the blackboard dict.'''
        parts = path.split('/')
        d0 = self._data
        for p in parts[:-1]:
            if not p: continue
            d1 = d0.get(p)
            if d1 is None:
                d0[p] = dict()
                d1 = d0.get(p)
            d0 = d1
        cur = d0.get(parts[-1], list())
        if isinstance(value, (str,int,float)):
            if not uniq or value not in cur:
                cur.append(value)
        else:
            for i in value:
                if not uniq or i not in cur:
                    cur.append(i)
        d0[parts[-1]] = cur

