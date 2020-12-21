#!/usr/bin/env python3
#
# kcri.bap.shims.CholeraeFinder - service shim to the CholeraeFinder
#

import os, json, logging, tempfile
from cge.flow.workflow.executor import Execution
from cge.flow.jobcontrol.job import JobSpec, Job
from kcri.bap.shims.base import BAPServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "CholeraeFinder", BACKEND_VERSIONS['choleraefinder']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_SPC = 1
MAX_TIM = 10 * 60


class CholeraeFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        execution = CholeraeFinderExecution(SERVICE, VERSION, ident, blackboard, scheduler)

         # Get the execution parameters from the blackboard
        try:
            species = execution.get_species([])
            if not any(filter(lambda s: s.startswith('Vibrio'), species)):
                raise UserException("service not applicable for species")
            db_path = execution.get_db_path('choleraefinder')
            params = [ '-q',
                '-p', db_path,
                '-t', execution.get_user_input('ch_i'),
                '-l', execution.get_user_input('ch_c'),
                '-ao', execution.get_user_input('ch_o'),
                '-i' ] + execution.get_fastqs_or_contigs_paths()

            job_spec = JobSpec('choleraefinder.py', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
            execution.start(job_spec, 'CholeraeFinder')

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


class CholeraeFinderExecution(BAPServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _tmp_dir = None
    _job = None

    # Start the execution on the scheduler
    def start(self, job_spec, work_dir):
        if self.state == Execution.State.STARTED:
            self.store_job_spec(job_spec.as_dict())
            self._tmp_dir = tempfile.TemporaryDirectory()
            job_spec.args.extend(['--tmp_dir', self._tmp_dir.name])
            self._job = self._scheduler.schedule_job('choleraefinder', job_spec, work_dir)

    # Parse the output produced by the backend service, return list of hits
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        # Clean up the tmp dir used by backend
        self._tmp_dir.cleanup()
        self._tmp_dir = None

        # Load the JSON and obtain the 'results' element.
        out_file = job.file_path('data_CholeraeFinder.json')
        try:
            with open(out_file, 'r') as f: json_in = json.load(f)
            json_in = json_in['choleraefinder']
        except:
            self.fail('failed to open or load JSON from file: %s' % out_file)
            return

        # Results are an extra (capitalised) layer deep.  We strip this and
        # (as we do for other finders) change dicts to arrays as the hit names
        # are problematic JSON keys, and the hits have array semantics anyway.
        # We also copy the 'typing_cholerae' element which summarises findings.

        typing = json_in.get('typing_cholerae', {})
        details = dict()

        for res in json_in.get('results', {}).values():
            for k, v in res.items():
                k1 = k[:-9] if k.endswith('_cholerae') else k
                details[k1] = [] if v == "No hit found" else list(v.values())

        # Store the results on the blackboard
        self.store_results({
            'typing': typing, 
            'details': details })

