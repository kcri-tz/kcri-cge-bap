#!/usr/bin/env python3
#
# kcri.bap.shims.Quast - service shim to the Quast backend
#

import os, csv, logging
from cge.flow.workflow.executor import Execution
from cge.flow.jobcontrol.job import JobSpec, Job
from kcri.bap.data import SeqPlatform, SeqPairing
from kcri.bap.shims.base import BAPServiceExecution, UserException

# Global variables, will be updated by the update-services script
SERVICE, VERSION = "Quast", "5.0.2"

# Backend resource parameters: cpu, memory, disk, run time reqs
#MAX_CPU = -1 # all
MAX_MEM = 12
MAX_SPC = 1
MAX_TIM = 20 * 60

# Need to report this in stats: minimum contig length for Quast metrics
MIN_CONTIG = 500

class QuastShim:
    '''Service shim that executes the backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        execution = QuastExecution(SERVICE, VERSION, ident, blackboard, scheduler)

         # Get the execution parameters from the blackboard
        MAX_CPU = scheduler.max_cpu
        min_ctg = execution.get_user_input('qc_t', MIN_CONTIG)
        try:
            # Set up Quast parameters (note there are many more)
            params = [
                '--min-contig', min_ctg,
                '--output-dir', '.',
                '--threads', MAX_CPU,
                '--fast',
                '--silent',
#                '--gene-finding',
#                '--circos'
            ]

            # Append the reference if we have it
            refs = execution.get_ref_genome_paths([])
            if refs:
                params.extend(['-r', refs[0]])

            # Append reads if we have them
            fastqs = execution.get_fastq_paths(list())
            if fastqs:

                if len(fastqs) == 2:
                    if execution.is_seq_pairing(SeqPairing.PAIRED):
                        params.extend(['--pe1', fastqs[0], '--pe2', fastqs[1]])
                    elif execution.is_seq_pairing(SeqPairing.MATE_PAIRED):
                        params.extend(['--mp1', fastqs[0], '--mp2', fastqs[1]])
                    else:
                        raise Exception("read pairing must be known for Quast with two FASTQ files")
                elif len(fastqs) == 1:
                    if execution.is_seq_pairing(SeqPairing.PAIRED):
                        params.extend(['--pe12', fastqs[0]])
                    elif execution.is_seq_pairing(SeqPairing.MATE_PAIRED):
                        params.extend(['--mp12', fastqs[0]])
                    elif execution.is_seq_pairing(SeqPairing.UNPAIRED):
                        params.extend(['--single', fastqs[0]])
                    else:
                        raise Exception("read pairing must be known for Quast with a single FASTQ files")
                else:
                    raise Exception("Quast cannot make sense of more than 2 reads files")

                # And specify the platform
                if execution.is_seq_platform(SeqPlatform.NANOPORE):
                    params.append('--nanopore')
                elif execution.is_seq_platform(SeqPlatform.PACBIO):
                    params.append('--pacbio')

            params.append(os.path.abspath(execution.get_contigs_path()))

            job_spec = JobSpec('quast.py', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
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


translate = dict({
    'Assembly'                  : 'sample',
    '# contigs'                 : 'n_contigs',
    'Largest contig'            : 'max_ctg_len',
    'Total length'              : 'total_len',
    '# contigs (>= 0 bp)'       : 'ctg_min_0k',
    '# contigs (>= 1000 bp)'    : 'ctg_min_1k',
    '# contigs (>= 5000 bp)'    : 'ctg_min_5k',
    '# contigs (>= 10000 bp)'   : 'ctg_min_10k',
    '# contigs (>= 25000 bp)'   : 'ctg_min_25k',
    '# contigs (>= 50000 bp)'   : 'ctg_min_50k',
    'Total length (>= 0 bp)'    : 'len_min_0k',
    'Total length (>= 1000 bp)' : 'len_min_1k',
    'Total length (>= 5000 bp)' : 'len_min_5k',
    'Total length (>= 10000 bp)': 'len_min_10k',
    'Total length (>= 25000 bp)': 'len_min_25k',
    'Total length (>= 50000 bp)': 'len_min_50k',
    'GC (%)'                    : 'pct_gc',
    'N50'                       : 'n50',
    'N75'                       : 'n75',
    'L50'                       : 'l50',
    'L75'                       : 'l75',
    '# N\'s per 100 kbp'        : 'n_per_100k',
    })

# Single execution of the service
class QuastExecution(BAPServiceExecution):
    '''A single execution of the Quast service'''

    _job = None

    def start(self, job_spec):
        if self.state == Execution.State.STARTED:
            self._job = self._scheduler.schedule_job('quast', job_spec, 'Quast')

    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        tsv = job.file_path('report.tsv')
        try:
            metrics = dict()

            with open(tsv, newline='') as f:
                reader = csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
                for row in reader:
                    metrics[translate.get(row[0], row[0])] = row[1]

            self.store_results({
                'metrics': metrics,
                'html_report': job.file_path('report.html')})
            
        except Exception as e:
            self.fail("failed to parse output file %s: %s" % (tsv, str(e)))

