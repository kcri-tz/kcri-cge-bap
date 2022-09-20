#!/usr/bin/env python3
#
# kcri.bap.shims.DisinFinder - service shim to the DisinFinder backend
#

import os, json, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version (note: is resfinder)
SERVICE, VERSION = "DisinFinder", BACKEND_VERSIONS['resfinder']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_TIM = 10 * 60


class DisinFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = DisinFinderExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # From here throwing is caught and FAILs the execution
        try:
            db_path = execution.get_db_path('disinfinder')
            params = [
                '--disinfectant',
                '--db_path_disinf', db_path,
                '--db_path_res', execution.get_db_path('resfinder'), # required at all times
                # Set the thresholds from the RF parameters; we have no params specific to DF.
                # We could be fancy and offer separate settings, but then if we migrate to a
                # single Resistance 'all-in-one', we can't pass them to ResFinder separately.
                # It's no big deal; we mention in BAP help that these are for both Res and Disin.
                '-t', execution.get_user_input('rf_i'),
                '-l', execution.get_user_input('rf_c'),
                '--acq_overlap', execution.get_user_input('rf_o'),
                '--threshold_point', execution.get_user_input('rf_i'),
                '--min_cov_point', execution.get_user_input('rf_c'),
                '-j', 'disinfinder.json',
                '-o', '.' ]

            # Append files, backend has different args for fq and fa
            illufqs = execution.get_illufq_paths(list())
            if illufqs:
                for f in illufqs:
                    params.extend(['--inputfastq', f])
            elif execution.get_nanofq_path(""):
                params.extend(['--nanopore', '--inputfastq', execution.get_nanofq_path()])
            else:
                params.extend(['--inputfasta', execution.get_contigs_path()])

            job_spec = JobSpec('resfinder', params, MAX_CPU, MAX_MEM, MAX_TIM)
            execution.store_job_spec(job_spec.as_dict())
            execution.start(job_spec, 'DisinFinder')

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


class DisinFinderExecution(ServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _job = None

    def start(self, job_spec, work_dir):
        if self.state == Task.State.STARTED:
            self._job = self._scheduler.schedule_job('disinfinder', job_spec, work_dir)

    # Parse the output produced by the backend service, return list of hits
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        res_out = dict()

        # ResFinder JSON output since 4.2 has top-level elements
        # 'genes', 'seq_variations', and 'phenotypes'.
        # We include these but change them from objects to lists.  So this:
        #    'genes' : { 'aph(6)-Id;;1;;M28829': { ..., 'key' : 'aph(6)-Id;;1;;M28829', ...
        # becomes:
        #    'genes' : [ { ..., 'key' : 'aph(6)-Id;;1;;M28829', ... }, ...]
        # This is cleaner design (they have list semantics, not object), and
        # avoids issues with keys such as "aac(6')-Ib;;..." that are bound
        # to create issues down the line as they contain JSON delimiters.

        json_out = job.file_path('disinfinder.json')
        try:
            with open(json_out, 'r') as f: json_in = json.load(f)
        except Exception as e:
            logging.exception(e)
            self.fail('failed to open or load JSON from file: %s' % json_out)
            return

        # Append to the result dictionary, converting as documented above.
        for k, v in json_in.items():
            if k in ['genes','seq_variations','phenotypes']:
                res_out[k] = [ o for o in v.values() ]
            else:
                res_out[k] = v

#        # Store the genes, classes and phenotypes in the summary
#        for g in res_out.get('genes', []):
#            self._blackboard.add_amr_gene(g.get('name','unknown'))
#        # Store the classes and phenotypes in the summary
#        for p in filter(lambda d: d.get('resistant', False), res_out.get('phenotypes', [])):
#            self._blackboard.add_amr_classes(p.get('amr_classes',[]))
#            self._blackboard.add_amr_phenotype(p.get('resistance','unknown'))

        # Store the results on the blackboard
        self.store_results(res_out)

