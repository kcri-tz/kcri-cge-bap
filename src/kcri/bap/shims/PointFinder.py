#!/usr/bin/env python3
#
# kcri.bap.shims.PointFinder - service shim to the PointFinder backend
#

import os, json, csv, logging
from pico.workflow.executor import Execution
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version (note: is resfinder)
SERVICE, VERSION = "PointFinder", BACKEND_VERSIONS['resfinder']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_SPC = 1
MAX_TIM = 10 * 60


class PointFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        # If this throws, we SKIP the execution (rather than fail)
        species = blackboard.get_species()
        if not species:
            raise UserException("no species is known")

        execution = PointFinderExecution(SERVICE, VERSION, ident, blackboard, scheduler)

        # From here throwing is caught and FAILs the execution
        try:
            if len(species) > 1:
                execution.add_warning('only first species is analysed, ignoring %d species' % len(species) - 1)

            db_path = execution.get_db_path('pointfinder')
            db_cfg = self.parse_config(os.path.join(db_path, 'config'))
            params = [
                '--point',
                '-db_point', db_path,
                '-db_res', execution.get_db_path('resfinder'), # required for AB classes, not found?
                '-t_p', execution.get_user_input('pt_i'),
                '-l_p', execution.get_user_input('pt_c'),
                '-s', species[0],
                '-o', '.' ]

            # Append files, backend has different args for fq and fa
            fq_files = execution.get_fastq_paths(list())
            for f in fq_files:
                params.extend(['-ifq', f])
            if not fq_files:
                params.extend(['-ifa', execution.get_contigs_path()])

            # Parse list of user specified genes and check with DB
            for g in filter(None, execution.get_user_input('pt_g',"").split(',')):
                if g not in db_cfg:
                    raise UserException("gene '%s' not in database, known are: %s", g, ', '.join(db_cfg.keys()))
                params.extend(['-g', g])

            if execution.get_user_input('pt_a'):
                params.append('--unknown_mut')

            job_spec = JobSpec('run_resfinder.py', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
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
        if self.state == Execution.State.STARTED:
            self._job = self._scheduler.schedule_job('pointfinder', job_spec, work_dir)

    # Parse the output produced by the backend service, return list of hits
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        res_out = dict()

        # The provisional JSON we parse further down does not yet link sequence variations
        # to phenotypes, so for now we parse PointFinder_results.txt:
        #    Mutation        Nucleotide change       Amino acid change       Resistance      PMID
        #    gyrA p.S83L     TCG -> TTG      S -> L  Nalidixic acid,Ciprofloxacin    8891148
        #    gyrA p.D87N     GAC -> AAC      D -> N  Nalidixic acid,Nalidixic acid,Ciprofloxacin     12654733
        #    parC p.S80I     AGC -> ATC      S -> I  Nalidixic acid,Ciprofloxacin    8851598
        #    parE p.S458T    TCG -> ACG      S -> T  Nalidixic acid,Ciprofloxacin    14506034

        tab_out = job.file_path('PointFinder_results.txt')
        try:
            res_out['findings'] = list()
            with open(tab_out, newline='') as f:
                reader = csv.DictReader(f, delimiter='\t')
                for row in reader:
                    # Append the mutation to the findings list
                    res_out['findings'].append(dict({
                        'mutation': row['Mutation'],
                        'nt_change': row['Nucleotide change'],
                        'aa_change': row['Amino acid change'],
                        'resistance': sorted(list(set(row.get('Resistance','').split(',')))),
                        'pmid': row.get('PMID')}))
                    # Append the mutation to the summary info on the blackboard
                    self._blackboard.add_amr_mutation(row['Mutation'])
        except Exception as e:
            logging.exception(e)
            self.fail('failed to open or read file: %s' % tab_out)
            return

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

        # Store the classes and phenotypes in the summary
        for p in filter(lambda d: d.get('resistant', False), res_out.get('phenotypes', [])):
            self._blackboard.add_amr_classes(p.get('classes',[]))
            self._blackboard.add_amr_phenotype(p.get('resistance',p.get('key','unknown')))
        # We don't store the seq_variations until we know their phenotype (instead do above)
        #for m in res_out.get('seq_variations', []):
        #    self._blackboard.add_amr_mutation('%s:%s' % (m.get('genes',['?'])[0], m.get('seq_var','?')))

        # Store the results on the blackboard
        self.store_results(res_out)

