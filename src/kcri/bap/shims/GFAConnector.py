#!/usr/bin/env python3
#
# kcri.bap.shims.GFAConnector - service shim to the GFAConnector backend
#

import os, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "GFAConnector", BACKEND_VERSIONS['skesa']

# Resource parameters: cpu, memory, disk, run time reqs
#MAX_CPU = -1 # all
#MAX_MEM = 12 # all
MAX_SPC = 0.01
MAX_TIM = 30 * 60

# Output file ex work dir
GFA_OUT = 'contigs.gfa'
CSV_OUT = 'graph.csv'

# The Service class
class GFAConnectorShim:
    '''Service shim that executes the gfa_connector backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = GFAConnectorExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # Max out the CPU and MEM but within reasonability
        MAX_CPU = min(scheduler.max_cpu, 12)
        MAX_MEM = min(int(scheduler.max_mem), 32)

        # Get the execution parameters from the blackboard
        try:
            if len(execution.get_fastq_paths()) != 2:
                raise UserException("GFAConnector backend only handles paired-end reads")

            params = [
                '--cores', MAX_CPU,
                '--reads', ','.join(map(os.path.abspath, execution.get_fastq_paths())),
                '--contigs', os.path.abspath(execution.get_contigs_path()),
                '--gfa', GFA_OUT,
                '--csv', CSV_OUT   # optional
            ]

            job_spec = JobSpec('gfa_connector', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
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
class GFAConnectorExecution(ServiceExecution):
    '''A single execution of the service, returned by execute().'''

    _job = None

    def start(self, job_spec):
        if self.state == Task.State.STARTED:
            self._job = self._scheduler.schedule_job('gfa-connector', job_spec, 'GFAConnector')

    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        gfa_file = job.file_path(GFA_OUT)
        csv_file = job.file_path(CSV_OUT)

        if os.path.isfile(gfa_file):
            self._blackboard.put_graph_path(gfa_file)
            res = dict({'gfa_file': gfa_file})
            if os.path.isfile(csv_file): res['csv_file'] = csv_file
            self.store_results(res)
        else:
            self.fail("gfa_connector job produced no graph, check: %s", job.file_path(""))

