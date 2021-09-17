#!/usr/bin/env python3
#
# kcri.bap.shims.SKESA - service shim to the SKESA backend
#

import os, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "SKESA", BACKEND_VERSIONS['skesa']

# SKESA resource parameters: cpu, memory, disk, run time reqs
#MAX_CPU = -1 # all
#MAX_MEM = 12 # all
MAX_TIM = 0  # unlimited

# Output file ex work dir
CONTIGS_OUT = 'contigs.fna'

# The Service class
class SKESAShim:
    '''Service shim that executes the SKESA backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = SKESAExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # Max out the CPU and MEM but within reasonability
        MAX_CPU = min(scheduler.max_cpu, 12)
        MAX_MEM = min(int(scheduler.max_mem), 32)

        # Get the execution parameters from the blackboard
        try:
            if len(execution.get_fastq_paths()) != 2:
                raise UserException("SKESA backend only handles paired-end reads")

            params = [
                '--cores', MAX_CPU,
                '--memory', MAX_MEM,
                '--reads', ','.join(execution.get_fastq_paths()),
                '--contigs_out', CONTIGS_OUT
            ]

            job_spec = JobSpec('skesa', params, MAX_CPU, MAX_MEM, MAX_TIM)
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
class SKESAExecution(ServiceExecution):
    '''A single execution of the service, returned by execute().'''

    _job = None

    def start(self, job_spec):
        if self.state == Task.State.STARTED:
            self._job = self._scheduler.schedule_job('skesa', job_spec, 'SKESA')

    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        contigs_file = job.file_path(CONTIGS_OUT)

        if os.path.isfile(contigs_file):
            self.store_results({ 'contigs_file': contigs_file })
            self._blackboard.put_assembled_contigs_path(contigs_file)
        else:
            self.fail("backend job produced no output, check: %s", job.file_path(""))

