#!/usr/bin/env python3
#
# kcri.bap.shims.base - base functionality across all service shims
#
#   This module defines ServiceExecution and UnimplementedService.
#

import os
from datetime import datetime
from pico.workflow.executor import Execution
from pico.jobcontrol.job import Job


### class UserException
#
#   Exception to raise so that an error message is reported back to the user,
#   without a stack trace being dumped on standard error.

class UserException(Exception):
    def __init__(self, message, *args):
        super().__init__(message % args)


### class ServiceExecution
#
#   Base class for the executions returned by all BAP Service shims.
#   Implements functionality common across all BAP service executions.

class ServiceExecution(Execution):
    '''Implements a single BAP service execution, subclass for shims to build on.'''

    _blackboard = None
    _scheduler = None

    def __init__(self, svc_name, svc_version, ident, blackboard, scheduler):
        '''Construct execution rwith identity, blackboard and scheduler, registering
        wraps blackboard in BAPBlackboard, passes rest on to super().'''
        super().__init__(ident)
        self._blackboard = blackboard
        self._scheduler = scheduler
        self.put_run_info('service', svc_name)
        self.put_run_info('version', svc_version)
        self._transition(Execution.State.STARTED)

    # Implementable interface of the execution, to be implemented in subclasses

    def report(self):
        '''Default implentation of Execution.report, should work for most executions.
           Checks the job and calls collect_output() to put job output on blackboard.'''

        # If our outward state is STARTED check the job
        if self.state == Execution.State.STARTED:
            if self._job.state == Job.State.COMPLETED:
                self.collect_output(self._job)
                if self.state != Execution.State.FAILED:
                    self.done()
            elif self._job.state == Job.State.FAILED:
                self.fail(self._job.error)

        return self.state

    # Low level update routines for subclasses

    def get_run_info(self, path):
        return self._blackboard.get('services/%s/run_info/%s' % (self._ident, path))

    def put_run_info(self, path, value):
        '''Update the run_info for this execution to have value at path.'''
        self._blackboard.put('services/%s/run_info/%s' % (self._ident, path), value)

    def add_warning(self, warning):
        '''Add warning to the list of warnings of the execution.'''
        self._blackboard.append_to('services/%s/%s' % (self._ident, 'warnings'), warning)

    def add_warnings(self, warnings):
        '''Add list of warnings if not empty to the list of warnings of the execution.'''
        self.add_warning(list(filter(None, warnings)))  # append_to deals with lists

    def add_error(self, errmsg):
        '''Add errmsg to the list of errors of the service.'''
        self._blackboard.append_to('services/%s/%s' % (self._ident, 'errors'), errmsg)

    def store_job_spec(self, jobspec):
        '''Store the service parameters on the blackboard.'''
        self.put_run_info('job', jobspec)

    def store_results(self, result):
        '''Store the service results on the blackboard.'''
        self._blackboard.put('services/%s/results' % self._ident, result)

    # Override Execution._transition() to add timestamps and status on blackboard.

    def _transition(self, new_state, error = None):
        '''Extends the superclass _transition to update the blackboard with status,
           errors, and timestamp fields.'''

        # Rely on superclass to set self.state and self.error
        super()._transition(new_state, error)

        # Set the run_info timestamps
        now_time = datetime.now()
        if new_state == Execution.State.STARTED:
            self.put_run_info('time/start', now_time.isoformat(timespec='seconds'))
        else:
            start_time = datetime.fromisoformat(self.get_run_info('time/start'))
            self.put_run_info('time/duration', (now_time - start_time).total_seconds())
            self.put_run_info('time/end', now_time.isoformat(timespec='seconds'))

        # Set the run_info status field and error list
        self.put_run_info('status', new_state.value)
        if new_state == Execution.State.FAILED:
            self.add_error(self.error)

        return new_state

    # Getters for the shared fields among services;
    # all of these raise an exception unless default is given

    def is_verbose(self):
        '''Return True if the run was requested to be verbose.'''
        return self.get_user_input('verbose', False)

    def get_db_path(self, db_name, default=None):
        '''Return the path to db_name under db_root, fail if not a dir.'''
        db_path = os.path.join(self._blackboard.get_db_root(), db_name)
        if not os.path.isdir(db_path):
            raise UserException("database path not found: %s", db_path)
        return db_path

    def get_user_input(self, param, default=None):
        '''Return the user-provided value for param, fail if no default provided.'''
        ret = self._blackboard.get_user_input(param, default)
        if ret is None:
            raise UserException("required user input is missing: %s" % param)
        return ret

    def get_fastq_paths(self, default=None):
        '''Return the list of fastq paths, or fail if no default provided.'''
        ret = self._blackboard.get_fastq_paths(default)
        if ret is None:
            raise UserException("no fastq files were provided")
        return ret

    def get_user_contigs_path(self, default=None):
        '''Return the path to the user provided contigs, or fail if no default.'''
        ret = self._blackboard.get_user_contigs_path(default)
        if ret is None:
            raise UserException("no contigs file was provided")
        return ret

    def get_assembled_contigs_path(self, default=None):
        '''Return the path to the assembled contigs, or else default or else fail.'''
        ret = self._blackboard.get_assembled_contigs_path(default)
        if ret is None:
            raise UserException("no contigs file was produced by an assembler")
        return ret

    def get_contigs_path(self, default=None):
        '''Return the path to the assembled contigs, or else user contigs, else default or fail.'''
        ret = self._blackboard.get_assembled_contigs_path(self._blackboard.get_user_contigs_path(default))
        if ret is None:
            raise UserException("no contigs file was provided or produced")
        return ret

    def get_fastqs_or_contigs_paths(self, default=None):
        '''Return the fastqs or else the contigs in a list, or else default or fail.'''
        ret = self._blackboard.get_fastq_paths(self._blackboard.get_user_contigs_path(default))
        if ret is None:
            raise UserException("no fastq or contigs files were provided")
        return ret if isinstance(ret,list) else [ret]

    def get_species(self, default=None):
        '''Return the list of specified and detected species, or else default or else fail if None.'''
        ret = self._blackboard.get_species(default)
        if ret is None:
            raise UserException("no species was specified or determined")
        return ret

    def get_closest_reference(self, default=None):
        '''Return dict with fields accession and name for the established closest reference.'''
        ret = self._blackboard.get_closest_reference(default)
        if ret is None:
            raise UserException("no closest reference was determined")
        return ret

    def get_reference_path(self, default=None):
        '''Return path to FASTA with the user provided reference or else the established one, or else default.'''
        ret = self._blackboard.get_user_reference_path(self._blackboard.get_closest_reference_path(default))
        if ret is None:
            raise UserException("no reference genome was specified or found")
        return ret

    def get_reference_length(self, default=None):
        '''Return length of FASTA with the user provided reference or else the established one, or else default.'''
        ret = self._blackboard.get_user_reference_length(self._blackboard.get_closest_reference_length(default))
        if ret is None:
            raise UserException("no reference length available: no reference was specified or found")
        return ret

    def get_plasmids(self, default=None):
        '''Return the list of specified and detected plasmids, or else default or else fail if None.'''
        ret = self._blackboard.get_plasmids(default)
        if ret is None:
            raise UserException("no plasmids were specified or determined")
        return ret


### class UnimplementedService
#
#   Shim for services in the SERVICES map that don't have a shim yet.
#   The UnimplementedService returns a ServiceExecution that fails.

class UnimplementedService():
    '''Base unimplemented class, starts but then fails on first report.'''

    def execute(self, ident, blackboard, scheduler):
        return UnimplementedService.Execution( \
                'unimplemented', '1.0.0', ident, blackboard, scheduler)

    class Execution(ServiceExecution):
        def report(self):
            return self.fail("service %s is not implemented", self.ident)


