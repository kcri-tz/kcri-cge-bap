#!/usr/bin/env python3
#
# cgetools.bap.shims.PlasmidFinder - service shim to the PlasmidFinder backend
#

import os, tempfile, json, logging
from cgetools.workflow.executor import Execution
from cgetools.bap.shims.base import BAPServiceExecution, UserException
from cgetools.jobcontrol.job import JobSpec, Job

# Global variables, will be updated by the update-services script
SERVICE, VERSION = "pMLST", "2.0.1-5-g5618"

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_SPC = 1
MAX_TIM = 10 * 60

# Map scheme -> plasmid suffixes
# Copied from old code, match with config and plasmidfinder_db
# TODO fix this hack and add the plasmid -> scheme mappings to config

pmlst_schemes = {
    'incac':    ['A', 'C'],
    'incf':     ['FIA', 'FIB', 'FIC', 'FII'],
    'inchi1':   ['HI1A', 'HI1B'],
    'inchi2':   ['HI2', 'HI2A'],
    'inci1':    ['I1'],
    'incn':     ['N', 'N2', 'N3'],
    'pbssb1-family': [ ]  # No plasmids will pick this
}

# Inverse map: plasmid suffix -> scheme
pmlst_schemes_inv = dict()
for k, l in pmlst_schemes.items(): 
    for i in l: 
        pmlst_schemes_inv[i] = k


class pMLSTShim:
    '''Service shim that executes the backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        execution = pMLSTExecution(SERVICE, VERSION, ident, blackboard, scheduler)

        # Get execution parameters from the blackboard
        try:
            db_dir = execution.get_db_path('pmlst')
            db_cfg = os.path.join(db_dir, 'config')
            files = execution.get_fastqs_or_contigs_paths([])

            # Determine schemes to run pMLST for from user input and PF output
            scheme_lst = list(filter(None, execution.get_user_input('pm_s', '').split(',')))
            plasmid_lst = execution.get_plasmids()
            schemes, warnings = self.determine_schemes(db_cfg, scheme_lst, plasmid_lst)

            execution.add_warnings(warnings)
            execution.start(schemes, files, db_dir)

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


    def determine_schemes(self, db_cfg, scheme_lst, plasmid_lst):
        '''Reads the database config to find out which schemes to run for the
           given scheme and plasmids list.  Returns a list of (scheme,loci)
           tuples or throws a descriptive exception on failure.'''

        scheme_loci = dict()

        if not os.path.exists(db_cfg):
            raise UserException('no database config file: %s', db_cfg)

        if not (scheme_lst or plasmid_lst):
            raise UserException('no plasmids were found and no pMLST shemes were specified')

        # Read the config into a map scheme -> [loci]
        with open(db_cfg, 'r') as f:
            for l in f:
                l = l.strip()
                if not l or l.startswith('#'): continue
                r = l.split('\t')
                if not len(r) == 3: continue
                s = r[0].strip()
                if s in scheme_loci:
                    raise UserException('duplicate scheme (%s) in database config: %s' % s, db_cfg)
                scheme_loci[s] = list(filter(None, r[2].split(',')))

        # Fill list of schemes from user-specified list
        schemes = list()
        for s in scheme_lst:
            if s not in scheme_loci:
                raise UserException("unknown pMLST scheme '%s', available are: %s" % s,','.join(scheme_loci.keys()))
            elif s not in schemes:
                schemes.append(s)

        # Add the schemes for the plasmids found by PlasmidFinder
        warnings = list()
        for plasmid in plasmid_lst:
            p = plasmid.split('(')[0].replace('Inc','')     # Changes IncAAA(BBB) to AAA
            ps = pmlst_schemes_inv.get(p)
            if not ps:
                warnings.append("no scheme found for plasmid: %s" % plasmid)
            elif ps not in scheme_loci:
                raise UserException("pMLST scheme '%s' for plasmid %s is missing from database", ps, plasmid)
            elif ps not in schemes:
                schemes.append(ps)

        # Return the zipped list and the list of warnings
        return [ (s, scheme_loci[s]) for s in sorted(schemes) ], warnings


class pMLSTExecution(BAPServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _jobs = list()  # of (job, scheme, loci, tmpdir) tuple

    def start(self, schemes, files, db_dir):
        # Schedule a backend job for every scheme if all is good
        if self.state == Execution.State.STARTED:
            for scheme,loci in schemes:
                self.run_scheme(scheme, loci, files, db_dir)

    def run_scheme(self, scheme, loci, files, db_dir):
        '''Spawn pMLST for one scheme and corresponding loci list.'''

        # Create a command line for the job
        name = 'pMLST_%s' % scheme
        tmpdir = tempfile.TemporaryDirectory()
        params = [
                '-p', db_dir,
                '-s', scheme,
                '-t', tmpdir.name,
                '-q',
                '-i' ] + files

        # Spawn the job and hold a record in the jobs table
        job_spec = JobSpec('pmlst.py', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
        job = self._scheduler.schedule_job(name, job_spec, name)
        self._jobs.append((job, scheme, loci, tmpdir))


    def report(self):
        '''Implements WorkflowService.Execution.report(), update blackboard
           if we are done and return our current state.'''

        # If our outward state is STARTED check the jobs
        if self.state == Execution.State.STARTED:

            # We report only once all our jobs are done
            if all(j[0].state in [ Job.State.COMPLETED, Job.State.FAILED ] for j in self._jobs):

                typings = list()

                for job, scheme, loci, tmpdir in self._jobs:
                    if job.state == Job.State.COMPLETED:
                        typings.append(self.collect_output(job, scheme, loci))
                    elif job.state == Job.State.FAILED:
                        self.add_error('%s: %s' % (job.name, job.error))
                    tmpdir.cleanup()

                # Store MLST result and add species to global BAP findings
                self.store_results(typings)

                if any(j[0].state == Job.State.COMPLETED for j in self._jobs):
                    self.done()
                else:
                    self.fail('no successful pMLST job')

        return self.state

 
    def collect_output(self, job, scheme, scheme_loci):
        '''Collect the job output for single job as dict.'''

        typing = dict()
        typing['scheme'] = scheme

        try:
            with open(job.file_path('data.json'), 'r') as f:

                json_data = json.load(f)

                r = json_data.get('pmlst', {}).get('user_input', {})
                typing['profile'] = r.get('profile','')

                r = json_data.get('pmlst', {}).get('results', {})
                typing['sequence_type'] = r.get('sequence_type')
                typing['nearest_sts'] = r.get('nearest_sts',[])

                # Reorganise the allele_profile dict to be a list,
                # so that its order is preserved.

                alleles = list()
                hits = r.get('allele_profile')

                for locus in scheme_loci:
                    allele = dict({'locus': locus})
                    hit = hits.get(locus, {})
                    if hit.get('allele'):
                        allele.update(hit)
                    alleles.append(allele)

                typing['alleles'] = alleles
                typing['notes'] = list(filter(None, r.get('notes', "").split('\n')))

                # Append to the blackboard summary
                self._blackboard.add_pmlst(typing['profile'], typing['sequence_type'])

        except Exception as e:
            typing['error'] = "pMLST output could not be parsed: %s" % str(e)

        return typing

