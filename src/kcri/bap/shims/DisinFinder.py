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
                # No big deal; we point out in BAP help that these are for both Res and Disin.
                '-t', execution.get_user_input('rf_i'),
                '-l', execution.get_user_input('rf_c'),
                '--acq_overlap', execution.get_user_input('rf_o'),
                '-j', 'disinfinder.json',
                '-o', '.' ]

            # Append files, backend has different args for fq and fa
            illufqs = execution.get_illufq_paths(list())
            if illufqs:
                for f in illufqs:
                    params.extend(['--inputfastq', f])
            elif execution.get_contigs_path(""):
                params.extend(['--inputfasta', execution.get_contigs_path()])
            elif execution.get_nanofq_path(""):
                params.extend(['--nanopore', '--inputfastq', execution.get_nanofq_path()])
            else: # the end is neigh
                raise UserException("no input data to analyse")

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

        out_file = job.file_path('disinfinder.json')
        try:
            with open(out_file, 'r') as f: json_in = json.load(f)
        except Exception as e:
            logging.exception(e)
            self.fail('failed to open or load JSON from file: %s' % out_file)
            return

        # ResFinder since 4.2 has standardised JSON with these elements:
        # - seq_regions (loci with AMR-causing genes or mutations)
        # - seq_variations (mutations keying into seq_regions)
        # - phenotypes (antibiotic resistances, keying into above)

        # We include these but change them from objects to lists, so this:
        #   'seq_regions' : { 'XYZ': { ..., 'key' : 'XYZ', ...
        # becomes:
        #   'seq_regions' : [ { ..., 'key' : 'XYZ', ... }, ...]
        # This is cleaner design (they have list semantics, not object), and
        # avoids issues downstream with keys containing JSON delimiters.

        for k, v in json_in.items():
            if k in ['seq_regions','seq_variations','phenotypes']:
                res_out[k] = [ o for o in v.values() ]
            else:
                res_out[k] = v

        # Helpers to retrieve genes names g for regions r causing phenotype p
        r2g = lambda r: json_in.get('seq_regions',{}).get(r,{}).get('name')
        p2gs = lambda p: filter(None, map(r2g, p.get('seq_regions', [])))

        # Store the resistant phenotypes and causative genes for summary
        for p in filter(lambda d: d.get('amr_resistant', False), res_out.get('phenotypes', [])):
            for g in p2gs(p): self._blackboard.add_dis_gene(g)
            self._blackboard.add_dis_resistance(p.get('amr_resistance','?unspecified?'))

        # Store the results on the blackboard
        self.store_results(res_out)

