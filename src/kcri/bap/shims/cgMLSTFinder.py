#!/usr/bin/env python3
#
# kcri.bap.shims.cgMLSTFinder - service shim to the cgMLSTFinder backend
#

import os, json, tempfile, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "cgMLSTFinder", BACKEND_VERSIONS['cgmlstfinder']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_TIM = 10 * 60


class cgMLSTFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        # Check whether running is applicable, else throw to SKIP execution
        scheme_lst = list(filter(None, blackboard.get_user_input('cq_s','').split(',')))
        species_lst = blackboard.get_species(list())
        if not (scheme_lst or species_lst):
            raise UserException("no species is known and no cgMLST scheme specified")

        execution = cgMLSTExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # From here run the execution, and FAIL it on exception
        try:
            db_dir = execution.get_db_path('cgmlstfinder')
            db_cfg = os.path.join(db_dir, 'config')

            # Note we do only one fq, regardless of how many we have
            # We error out if only Nanopore reads available (which we can't handle yet)
            inputs = execution.get_illufq_or_contigs_paths()
            fname = inputs[0]

            schemes = self.determine_schemes(db_cfg, scheme_lst, species_lst)
            execution.start(schemes, fname, db_dir)
 
        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


    def determine_schemes(self, db_cfg, scheme_lst, species_lst):
        '''Reads the database config to find out which schemes to run for the
           given scheme and species lists.  Returns a list of (scheme,loci)
           tuples or raises a user interpretable error.'''

        schemes = list()
        spc_db = dict()

        if not os.path.exists(db_cfg):
            raise UserException("no database config file: %s" % db_cfg)

        with open(db_cfg, 'r') as f:
            for l in f:
                l = l.strip()
                if not l or l.startswith('#'): continue
                r = l.split('\t')
                if not len(r) == 3: continue
                spc_db[r[1].strip()] = r[0].strip()

        for db in scheme_lst:
            if not db in spc_db.values():
                raise UserException("unknown scheme: %s; valid schemes are: %s" %
                        (db, ', '.join(spc_db.values())))
            elif not db in schemes:
                schemes.append(db)

        for s in species_lst:
            if s.startswith('Shigella'): s = 'Escherichia coli'   # argh: should be fixed in config
            db = spc_db.get(s.split(' ')[0], spc_db.get(s))
            if db and not db in schemes:
                schemes.append(db)

        if not schemes:
            raise UserException("no applicable cgMLST scheme")

        return schemes


class cgMLSTExecution(ServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _jobs = list()

    def start(self, schemes, fname, db_dir):
        # Schedule a backend job for every scheme if all is good
        if self.state == Task.State.STARTED:
            for scheme in schemes:
                self.run_scheme(scheme, fname, db_dir)

    def run_scheme(self, scheme, fname, db_dir):
        '''Spawn cgMLST for one scheme.'''

        # Create a command line for the job
        tmpdir = tempfile.TemporaryDirectory()
        params = [
                '-db', db_dir,
                '-t', tmpdir.name,
#                '-o', '.',
                '-s', scheme,
                fname ]

        # Spawn the job and hold a record in the jobs table
        job_spec = JobSpec('cgMLST.py', params, MAX_CPU, MAX_MEM, MAX_TIM)
        job = self._scheduler.schedule_job('cgmlst_%s' % scheme, job_spec, os.path.join(SERVICE,scheme))
        self._jobs.append((job, scheme, tmpdir))
 

    def report(self):
        '''Implements WorkflowService.Task.report(), update blackboard
           if we are done and return our current state.'''

        # If our outward state is STARTED check the jobs
        if self.state == Task.State.STARTED:

            # We may be running no jobs at all if no scheme applied
            if len(self._jobs) == 0:

                self.add_warning("no cgMLST scheme was found for the species")
                self.store_results(list())
                self.done()

            # Else we report only once all our jobs are done
            elif all(j[0].state in [ Job.State.COMPLETED, Job.State.FAILED ] for j in self._jobs):

                typings = list()

                for job, scheme, tmpdir in self._jobs:
                    if job.state == Job.State.COMPLETED:
                        typings.append(self.collect_output(job, scheme))
                    elif job.state == Job.State.FAILED:
                        self.add_error('%s: %s' % (job.name, job.error))
                    tmpdir.cleanup()

                # Store result 
                self.store_results(typings)

                # Report fail if none of the runs succeeded
                if any(j[0].state == Job.State.COMPLETED for j in self._jobs):
                    self.done()
                else:
                    self.fail('no successful cgMLSTFinder job')

        return self.state


    def collect_output(self, job, scheme):

        typing = dict({'scheme': scheme })

        try:
            with open(job.file_path('data.json'), 'r') as f:

                j = json.load(f)
                d = j.get('cgMLSTFinder').get('results')

                if d: # There should be at most one, as we have 1 FA or 1 fastq 
                    hit = list(d.values())[0]
                    typing.update(hit)
                    self._blackboard.add_cgmlst(scheme, hit.get('cgST', 'NA'), hit.get('perc_allele_matches', 'NA'))

        except Exception as e:
            typing['error'] = "cgMLSTFinder ran successfully but output could not be parsed: %s" % str(e)

        return typing
 

if __name__ == '__main__':
    main()

