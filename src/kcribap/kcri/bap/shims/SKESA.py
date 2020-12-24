#!/usr/bin/env python3
#
# kcri.bap.shims.SKESA - service shim to the SKESA backend
#

import os, logging
from cge.flow.workflow.executor import Execution
from cge.flow.jobcontrol.job import JobSpec, Job
from kcri.bap.data import SeqPlatform, SeqPairing
from kcri.bap.shims.base import BAPServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "SKESA", BACKEND_VERSIONS['skesa']

# SKESA resource parameters: cpu, memory, disk, run time reqs
#MAX_CPU = -1 # all
#MAX_MEM = 12 # all
MAX_SPC = 1
MAX_TIM = 10 * 60

# Output file ex work dir
CONTIGS_OUT = 'contigs.fna'

# The Service class
class SKESAShim:
    '''Service shim that executes the SKESA backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        execution = SKESAExecution(SERVICE, VERSION, ident, blackboard, scheduler)

         # Get the execution parameters from the blackboard
        MAX_CPU = scheduler.max_cpu
        MAX_MEM = int(scheduler.max_mem)
        try:
            if not execution.is_seq_platform(SeqPlatform.ILLUMINA):
                raise UserException("SKESA requires Illumina reads (seq_platform parameter)")

            params = [
                '--cores', MAX_CPU,
                '--memory', MAX_MEM,
                '--reads', ','.join(execution.get_fastq_paths()),
                '--contigs_out', CONTIGS_OUT
            ]
            if execution.is_seq_pairing(SeqPairing.PAIRED) and len(execution.get_fastq_paths()) == 1:
                params.append('--use_paired_end')

            job_spec = JobSpec('skesa', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
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
class SKESAExecution(BAPServiceExecution):
    '''A single execution of the service, returned by execute().'''

    _job = None

    def start(self, job_spec):
        if self.state == Execution.State.STARTED:
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

