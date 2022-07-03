#!/usr/bin/env python3
#
# kcri.bap.shims.MLSTFinder - service shim to the CGE MLST backend
#

import os, tempfile, json, logging
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "MLSTFinder", BACKEND_VERSIONS['mlst']

# MLST backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1     # @TODO@ measure: time --verbose
MAX_MEM = 1
MAX_TIM = 12 * 60

class MLSTFinderShim:
    '''Service shim that executes CGE MLST backend.
       We call it MLSTFinder to avoid confusion with the term MLST.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        # Check whether running is applicable, else throw to SKIP execution
        genus_lst = list(filter(None, blackboard.get_user_input('ml_g', '').split(',')))
        scheme_lst = list(filter(None, blackboard.get_user_input('ml_s', '').split(',')))
        species_lst = blackboard.get_species(list())
        if not (genus_lst or scheme_lst or species_lst):
            raise UserException("species must be known or a scheme or genus must be specified")

        execution = MLSTFinderExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # From here run the execution, and FAIL it on exception
        try:
            db_dir = execution.get_db_path('mlst')
            db_cfg = os.path.join(db_dir, 'config')
            files = execution.get_illufq_or_contigs_paths()

            # Determine schemes to run from lists of genus, schemes, species
            schemes = self.determine_schemes(db_cfg, genus_lst, scheme_lst, species_lst)

            execution.start(schemes, files, db_dir)

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution

    def determine_schemes(self, db_cfg, genus_lst, scheme_lst, species_lst):
        '''Reads the database config to find out which schemes to run for the
           given genus, scheme, and species list.  Returns a list of (scheme,loci)
           tuples or throws a descriptive exception on failure.'''

        scheme_loci = dict()
        genus_schemes = dict()
        species_schemes = dict()

        if not os.path.exists(db_cfg):
            raise UserException("no database config file: %s" % db_cfg)

        with open(db_cfg, 'r') as f:
            for l in f:

                l = l.strip()
                if not l or l.startswith('#'): continue
                r = l.split('\t')
                if not len(r) == 3: continue
                s = r[0].strip()
                if s in scheme_loci:
                    raise UserException("duplicate scheme (%s) in database config: %s", s, db_cfg)

                scheme_loci[s] = r[2].strip().split(',')

                g = r[1].split(' ')[0].strip()
                ss = genus_schemes.get(g, set())
                ss.add(s)
                genus_schemes[g] = ss

        # Create list of schemes to test
        schemes = list()
        for s in scheme_lst:
            if s not in scheme_loci:
                raise UserException("unknown MLST scheme '%s', available are: %s", s,','.join(scheme_loci.keys()))
            elif s not in schemes:
                schemes.append(s)

        # Add the schemes for the genuses
        warnings = list()
        genus = set(map(lambda x: x.split(' ')[0], genus_lst + species_lst))
        for g in genus:
            if g == 'Shigella': g = 'Escherichia'   # Hack ...
            ss = genus_schemes.get(g)
            if not ss:
                warnings.append("no scheme found for genus: %s" % g)
            else:
                schemes.extend(filter(lambda s: s not in schemes, ss))

        # Return the zipped list
        return [ (s, scheme_loci[s]) for s in sorted(schemes) ]


class MLSTFinderExecution(ServiceExecution):
    '''A single execution of the MLSTFinder service, returned by MLSTFinder.execute().'''

    _jobs = list()

    def start(self, schemes, files, db_dir):
        # Schedule a backend job for every scheme if all is good
        if self.state == Task.State.STARTED:
            for scheme,loci in schemes:
                self.run_scheme(scheme, loci, files, db_dir)

    def run_scheme(self, scheme, loci, files, db_dir):
        '''Spawn CGE MLST for one scheme and corresponding loci list.'''

        # Create a command line for the job
        tmpdir = tempfile.TemporaryDirectory()
        params = [
                '-p', db_dir,
                '-s', scheme,
                '-t', tmpdir.name,
                '-q',
                '-i' ] + files

        # Spawn the job and hold a record in the jobs table
        job_spec = JobSpec('mlst.py', params, MAX_CPU, MAX_MEM, MAX_TIM)
        job = self._scheduler.schedule_job('mlst_%s' % scheme, job_spec, os.path.join(SERVICE,scheme))
        self._jobs.append((job, scheme, loci, tmpdir))


    def report(self):
        '''Implements WorkflowService.Task.report(), update blackboard
           if we are done and return our current state.'''

        # If our outward state is STARTED check the jobs
        if self.state == Task.State.STARTED:

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
                    self.fail('no successful MLSTFinder job')

        return self.state


    def collect_output(self, job, scheme, scheme_loci):
        '''Collect the output of the MLST job for scheme as a scheme object,
           including the lists of alleles and hits to the extent they were hit.'''

        typing = dict({
            'scheme': scheme
            })

        try:
            with open(job.file_path('data.json'), 'r') as f:

                j = json.load(f)
                scheme_name = j.get('mlst',{}).get('user_input',{}).get('organism')

                # Prepend conventional 'ST' to sequence type if valid
                r = j.get('mlst').get('results', dict())
                st = r.get('sequence_type')
                if st.isnumeric(): st = 'ST%d' % int(st)

                # Reorder the loci to expected order in list of loci, hits, allele-hits
                p = r.get('allele_profile', {})
                hits = list()
                loci = list()
                alleles = list()
                for locus in scheme_loci:
                    l = p.get(locus)
                    allele = l.get('allele')
                    if allele:
                        hits.append(l)
                        loci.append(locus)
                        alleles.append(allele)

                # Report the fraction of loci found and incomplete if not all were found
                typing.update({
                    'mlst_scheme': scheme_name,
                    'loci_found': "%d/%d" % (len(hits), len(scheme_loci)),
                    'incomplete': len(hits) != len(scheme_loci),
                    'sequence_type': st
                })

                # Store other data and summary only if typing was complete (all loci hit)
                if len(hits) == len(scheme_loci):

                    nearest = list(map(lambda i: "ST%s" % i, filter(None, r.get('nearest_sts', "").split(','))))

                    typing.update({
                        'alleles': alleles,
                        'loci': loci,
                        'hits': hits,
                        'nearest_sts': nearest,
                        'notes': list(filter(None, r.get('notes', "").split('\n')))
                    })

                    # Add to the summary on the blackboard
                    self._blackboard.add_mlst(scheme_name, st, loci, alleles, nearest)

        except Exception as e:
            typing['error'] = "MLSTFinder ran successfully but output could not be parsed: %s" % str(e)

        return typing

