#!/usr/bin/env python3
#
# kcri.bap.shims.ResFinder - service shim to the ResFinder backend
#

import os, json, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "ResFinder", BACKEND_VERSIONS['resfinder']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_TIM = 10 * 60


class ResFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = ResFinderExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

         # Get the execution parameters from the blackboard
        try:
            db_path = execution.get_db_path('resfinder')
            params = [
                '--acquired',
                '--db_path_res', db_path,
                '-t', execution.get_user_input('rf_i'),
                '-l', execution.get_user_input('rf_c'),
                '--acq_overlap', execution.get_user_input('rf_o'),
                '-j', 'resfinder.json',
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
            else: # expect the unexpected
                raise UserException("no input data to analyse")

            job_spec = JobSpec('resfinder', params, MAX_CPU, MAX_MEM, MAX_TIM)
            execution.store_job_spec(job_spec.as_dict())
            execution.start(job_spec, 'ResFinder')

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


    def parse_config(self, cfg_file):
        '''Parse the config file into a dict of key->name, or raise on error.'''
        ret = dict()

        if not os.path.exists(cfg_file):
            raise UserException('database config file missing: %s', cfg_file)

        with open(cfg_file) as f:
            for l in f:
                l = l.strip()
                if not l or l.startswith('#'): continue
                r = l.split('\t')
                if len(r) != 3: raise UserException('invalid database config line: %s', l)
                ret[r[0].strip] = r[1].strip()

        return ret


class ResFinderExecution(ServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _job = None

    def start(self, job_spec, work_dir):
        if self.state == Task.State.STARTED:
            self._job = self._scheduler.schedule_job('resfinder', job_spec, work_dir)

    # Parse the output produced by the backend service, return list of hits
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        res_out = dict()

        out_file = job.file_path('resfinder.json')
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

        # Helpers to retrieve gene names g for regions r causing phenotype p
        r2g = lambda r: json_in.get('seq_regions',{}).get(r,{}).get('name')
        p2gs = lambda p: filter(None, map(r2g, p.get('seq_regions', [])))

        # Store the resistant phenotypes and causative regions for the summary output
        # Note that a lot more information is present, including PMIDs and notes
        for p in filter(lambda d: d.get('amr_resistant', False), res_out.get('phenotypes', [])):
            for g in p2gs(p): self._blackboard.add_amr_gene(g)
            for c in p.get('amr_classes',[]): self._blackboard.add_amr_class(c)
            self._blackboard.add_amr_antibiotic(p.get('amr_resistance','?unspecified?'))

        # Store on the blackboard
        self.store_results(res_out)

