#!/usr/bin/env python3
#
# kcri.bap.shims.PointFinder - service shim to the PointFinder backend
#

import os, json, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version (note: is resfinder)
SERVICE, VERSION = "PointFinder", BACKEND_VERSIONS['resfinder']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_TIM = 10 * 60


class PointFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        # If this throws, we SKIP the execution (rather than fail)
        species = blackboard.get_species()
        if not species:
            raise UserException("no species is known")

        execution = PointFinderExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # From here throwing is caught and FAILs the execution
        try:
            if len(species) > 1:
                execution.add_warning('only first species is analysed, ignoring %d species' % len(species) - 1)

            db_path = execution.get_db_path('pointfinder')
            db_cfg = self.parse_config(os.path.join(db_path, 'config'))
            params = [
                '--point',
                '--db_path_point', db_path,
                '--db_path_res', execution.get_db_path('resfinder'), # required for AB classes, not found?
                '--threshold_point', execution.get_user_input('pt_i'),
                '--min_cov_point', execution.get_user_input('pt_c'),
                '-s', species[0],
                '-j', 'pointfinder.json',
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
            else: # LPT1 is on fire
                raise UserException("no input data to analyse")

            # Parse list of user specified genes and check with DB
            for g in filter(None, execution.get_user_input('pt_g',"").split(',')):
                if g not in db_cfg:
                    raise UserException("gene '%s' not in database, known are: %s", g, ', '.join(db_cfg.keys()))
                params.extend(['-g', g])

            if execution.get_user_input('pt_a'):
                params.append('--unknown_mut')

            if execution.get_user_input('pt_d'):
                params.append('--ignore_indels')

            if execution.get_user_input('pt_s'):
                params.append('--ignore_stop_codons')

            job_spec = JobSpec('resfinder', params, MAX_CPU, MAX_MEM, MAX_TIM)
            execution.store_job_spec(job_spec.as_dict())
            execution.start(job_spec, 'PointFinder')

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


class PointFinderExecution(ServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _job = None

    def start(self, job_spec, work_dir):
        if self.state == Task.State.STARTED:
            self._job = self._scheduler.schedule_job('pointfinder', job_spec, work_dir)

    # Parse the output produced by the backend service, return list of hits
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        res_out = dict()

        out_file = job.file_path('pointfinder.json')
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

        # Collect resistant phenotypes and causative mutations for the summary output
        # Note that a lot more information is present, including PMID references and notes

        # For collecting the mutations grouped by gene (region)
        ms = dict()

        # We iterate over the resistant phenotypes, adding the classes and antibiotic
        for p in filter(lambda d: d.get('amr_resistant', False), res_out.get('phenotypes', [])):
            for c in p.get('amr_classes',[]): self._blackboard.add_amr_class(c)
            self._blackboard.add_amr_antibiotic(p.get('amr_resistance','?unspecified?'))

            # Each phenotype may have n variations, each variation has a 'seq_var' and may have n named regions
            # We collect the seq_vars per named region (gene), so as to have organised output
            for v in filter(None, map(lambda vid: json_in.get('seq_variations',{}).get(vid,{}), p.get('seq_variations',[]))):
                g = '+'.join(filter(None, map(lambda rid: json_in.get('seq_regions',{}).get(rid,{}).get('name',''), v.get('seq_regions',[]))))
                ms[g] = ms.get(g, set()).union([v.get('seq_var')])

        # Now stringify the mutations an
        for g in ms: self._blackboard.add_amr_mutation('%s(%s)' % (g,','.join(sorted(ms.get(g)))))

        # Store on the blackboard
        self.store_results(res_out)

