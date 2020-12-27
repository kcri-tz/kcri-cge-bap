#!/usr/bin/env python3
#
# kcri.bap.shims.KCST - service shim to the KCST backend
#

import logging
from pico.workflow.executor import Execution
from pico.jobcontrol.job import JobSpec, Job
from .base import BAPServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "KCST", BACKEND_VERSIONS['kcst']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 12
MAX_SPC = 1
MAX_TIM = 5 * 60

# The Service class
class KCSTShim:
    '''Service shim that executes the KCST backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        execution = KCSTExecution(SERVICE, VERSION, ident, blackboard, scheduler)

         # Get the execution parameters from the blackboard
        try:
            min_cov = execution.get_user_input('kc_c') # is fraction
            params = [
                '-d', execution.get_db_path('mlst'),
                '-m', MAX_MEM,
                '-c', int(round(100.0*float(min_cov))),  # kcst wants pct
                execution.get_contigs_path()
            ]
            if execution.is_verbose():
                params.insert(0, '-v')

            job_spec = JobSpec('kcst', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
            execution.store_job_spec(job_spec.as_dict())
            execution.start(job_spec)

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution

# Single execution of the service
class KCSTExecution(BAPServiceExecution):
    '''A single execution of the KCST service, returned by KCSTShim.execute().'''

    _job = None

    def start(self, job_spec):
        if self.state == Execution.State.STARTED:
            self._job = self._scheduler.schedule_job('kcst', job_spec, 'kcst')


    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        # Collect the MLST typings and species determination
        try:
            typings = list()
            species = list()

            # KCST writes cleanly to stdout
            with open(job.stdout, 'r') as f:

                for l in f:
                    v = l.rstrip().split('\t')

                    # All 5+ field output lines represent a typing
                    if len(v) > 5:

                        # Mangle the species from the schema name
                        sp = ' '.join(v[1].split('#')[0].split(' ')[:2])
                        species.append(sp)

                        # Convert alleles and loci from string to list
                        loci = v[4].split('-')
                        alleles = v[3].split('-')

                        # Collect all MLST typings in a list
                        typings.append({
                            'species': sp,
                            'mlst_scheme': v[1],
                            'sequence_type': v[2],
                            'alleles': alleles,
                            'loci': loci
                            })

                        # Add to the summary on the blackboard
                        self._blackboard.add_mlst(v[2], loci, alleles)
            
            # Store MLST result and add species to global BAP findings
            self.store_results(typings)
            self._blackboard.add_detected_species(value)

        # Mark the job failed if output parsing fails
        except FileNotFoundError:
            self.fail("backend job produced no output, check: %s", job.file_path(""))

