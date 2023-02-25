#!/usr/bin/env python3
#
# kcri.bap.shims.spaType - service shim to spa-type
#

import os, json, logging, tempfile
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException, SkipException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "spaType", BACKEND_VERSIONS['spa-type']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_TIM = 2 * 60


class spaTypeShim:
    '''Service shim that executes the backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        # Check whether running is applicable, else throw to SKIP execution
        species = blackboard.get_species(list())
        if not any(filter(lambda s: s.startswith('Staphylococcus'), species)):
            raise SkipException("service not applicable: not Staphylococcus")

        execution = spaTypeExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # From here run the execution, and FAIL it on exception
        try:
            params = [ os.path.abspath(execution.get_contigs_path()) ]

            job_spec = JobSpec('spa-type', params, MAX_CPU, MAX_MEM, MAX_TIM)
            execution.start(job_spec, 'spaType')

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


class spaTypeExecution(ServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _job = None

    # Start the execution on the scheduler
    def start(self, job_spec, work_dir):
        if self.state == Task.State.STARTED:
            self.store_job_spec(job_spec.as_dict())
            self._job = self._scheduler.schedule_job('spa-type', job_spec, work_dir)

    # Parse the output produced by the backend service, return list of hits
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        # Load the JSON and obtain the 'results' element.
        out_file = job.stdout
        try:
            with open(job.stdout, 'r') as f:
                for line in f:
                    TODO
        except:
            self.fail('failed to open or load JSON from file: %s' % out_file)
            return

        # Store the results on the blackboard
        self.store_results({
            'spa_type': type, 
            'details': details })

