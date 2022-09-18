#!/usr/bin/env python3
#
# kcri.bap.shims.DisinfFinder - service shim to the DisinfFinder backend
#

import os, json, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version (note: is resfinder)
SERVICE, VERSION = "DisinfFinder", BACKEND_VERSIONS['resfinder']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_TIM = 10 * 60


class DisinfFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = DisinfFinderExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # From here throwing is caught and FAILs the execution
        try:
            db_path = execution.get_db_path('disinfinder')
#            db_cfg = self.parse_config(os.path.join(db_path, 'config'))
            params = [
                '--disinfectant',
                '--db_path_disinf', db_path,
                '--db_path_res', execution.get_db_path('resfinder'), # required for AB classes, not found?
#                '--threshold_point', execution.get_user_input('pt_i'),
#                '--min_cov_point', execution.get_user_input('pt_c'),
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
            execution.start(job_spec, 'DisinfFinder')

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


class DisinfFinderExecution(ServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _job = None

    def start(self, job_spec, work_dir):
        if self.state == Task.State.STARTED:
            self._job = self._scheduler.schedule_job('disinffinder', job_spec, work_dir)

    # Parse the output produced by the backend service, return list of hits
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        res_out = dict()

        # ResFinder and PointFinder have provisional standardised output in 
        # 'std_format_under_development.json', which has top-level elements
        # 'genes', 'seq_variations', and 'phenotypes'.
        # We include these but change them from objects to lists.  So this:
        #    'genes' : { 'aph(6)-Id;;1;;M28829': { ..., 'key' : 'aph(6)-Id;;1;;M28829', ...
        # becomes:
        #    'genes' : [ { ..., 'key' : 'aph(6)-Id;;1;;M28829', ... }, ...]
        # This is cleaner design (they have list semantics, not object), and
        # avoids issues with keys such as "aac(6')-Ib;;..." that are bound
        # to create issues down the line as they contain JSON delimiters.

        json_out = job.file_path('std_format_under_development.json')
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

#        # Store the genes, classes and phenetypes in the summary
#        for g in res_out.get('genes', []):
#            self._blackboard.add_amr_gene(g.get('name','unknown'))
#        # Store the classes and phenotypes in the summary
#        for p in filter(lambda d: d.get('resistant', False), res_out.get('phenotypes', [])):
#            self._blackboard.add_amr_classes(p.get('amr_classes',[]))
#            self._blackboard.add_amr_phenotype(p.get('resistance','unknown'))

        # Store the results on the blackboard
        self.store_results(res_out)

