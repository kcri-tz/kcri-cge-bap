#!/usr/bin/env python3
#
# kcri.bap.shims.ReadsMetrics - service shim to the fastq-stats backend
#

import os, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "ReadsMetrics", BACKEND_VERSIONS['fastq-utils']

# Resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 2
MAX_MEM = 1
MAX_SPC = 1
MAX_TIM = 5 * 60


# The Service class
class ReadsMetricsShim:
    '''Service shim that executes the backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = ReadsMetricsExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # From here we catch exception and execution will FAIL
        try:
            fastqs = execution.get_fastq_paths()
            fn = "'%s'" % os.path.abspath(fastqs[0])
            if len(fastqs) == 2: fn += " '%s'" % os.path.abspath(fastqs[1])
            # Cater for either gzipped or plain input using shell succinctness
            cmd = "(gzip -dc %s 2>/dev/null || cat %s) | fastq-stats" % (fn,fn) 
            params = [
                '-c', cmd, 'fastq-stats'
            ]

            job_spec = JobSpec('sh', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
            execution.store_job_spec(job_spec.as_dict())
            execution.start(job_spec)

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution

# Single execution of the service
class ReadsMetricsExecution(ServiceExecution):
    '''A single execution of the service, returned by execute().'''

    _job = None

    def start(self, job_spec):
        if self.state == Task.State.STARTED:
            self._job = self._scheduler.schedule_job('fastq-stats', job_spec, 'ReadsMetrics')

    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        try:
            with open(job.stdout) as f:
                results = dict((r[0], r[1].strip()) 
                        for r in map(lambda l: l.split('\t'), f) if len(r) == 2)
                self.store_results(results)

        except Exception as e:
            self.fail("failed to process job output (%s): %s", job.stdout, str(e))

