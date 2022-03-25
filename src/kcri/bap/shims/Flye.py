#!/usr/bin/env python3
#
# kcri.bap.shims.Flye - service shim to the Flye backend
#

import os, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "Flye", BACKEND_VERSIONS['flye']

# Flye resource parameters: cpu, memory, disk, run time reqs
MAX_TIM = 0  # unlimited

# Output file ex work dir
CONTIGS_OUT = 'assembly.fasta'
GFA_OUT = 'assembly_graph.gfa'

# The Service class
class FlyeShim:
    '''Service shim that executes the Flye backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = FlyeExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # Max out the CPU and MEM but within reasonability
        MAX_CPU = min(scheduler.max_cpu, 12)
        MAX_MEM = min(int(scheduler.max_mem), 32)

        readqual = 'hq' if execution.get_user_input('fl_h', False) else 'raw'

        # Get the execution parameters from the blackboard
        try:
            reads = execution.get_nanofq_path()

            params = [
                '--threads', MAX_CPU,
                '--out-dir', '.',
                # Note: use 'nano-raw' for pre-Guppy5 reads, says Flye
                '--nano-%s' % readqual, reads
            ]

            job_spec = JobSpec('flye', params, MAX_CPU, MAX_MEM, MAX_TIM)
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
class FlyeExecution(ServiceExecution):
    '''A single execution of the service, returned by execute().'''

    _job = None

    def start(self, job_spec):
        if self.state == Task.State.STARTED:
            self._job = self._scheduler.schedule_job('flye', job_spec, 'Flye')

    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        contigs_file = job.file_path(CONTIGS_OUT)
        gfa_file = job.file_path(GFA_OUT)

        if os.path.isfile(contigs_file):
            self._blackboard.put_assembled_contigs_path(contigs_file)
            res = dict({ 'contigs_file': contigs_file })
            if os.path.isfile(gfa_file):
                self._blackboard.put_graph_path(gfa_file)
                res['gfa_file'] = gfa_file
            self.store_results(res)
        else:
            self.fail("backend job produced no assembly, check: %s", job.file_path(""))

