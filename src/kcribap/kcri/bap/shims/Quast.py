#!/usr/bin/env python3
#
# kcri.bap.shims.Quast - service shim to the Quast backend
#

import os, csv, logging
from cge.flow.workflow.executor import Execution
from cge.flow.jobcontrol.job import JobSpec, Job
from kcri.bap.data import SeqPlatform, SeqPairing
from kcri.bap.shims.base import BAPServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "Quast", BACKEND_VERSIONS['quast']

# Backend resource parameters: cpu, memory, disk, run time reqs
#MAX_CPU = -1 # all
MAX_MEM = 12
MAX_SPC = 1
MAX_TIM = 20 * 60


class QuastShim:
    '''Service shim that executes the backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        execution = QuastExecution(SERVICE, VERSION, ident, blackboard, scheduler)

         # Get the execution parameters from the blackboard
        MAX_CPU = scheduler.max_cpu
        try:
            # Set up Quast parameters (note there are many more)
            params = [
                '--output-dir', '.',
                '--threads', MAX_CPU,
                '--no-sv',
#                '--fast',
#                '--silent',
#                '--gene-finding',
#                '--circos'
            ]

            # Append the min-contig threshold for analysis
            min_contig = execution.get_user_input('qc_t')
            if min_contig:
                params.extend(['--min-contig', min_contig])

            # Append the reference if we have it
            ref = execution.get_reference_path()
            if ref:
                params.extend(['-r', os.path.abspath(ref)])

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
    'Assembly'                      : 'sample',
    '# contigs'                     : 'num_ctg',
    'Largest contig'                : 'max_ctg',
    'Total length'                  : 'tot_len',
    'Reference length'              : 'ref_len',
    'Reference GC (%)'              : 'ref_pct_gc',
    '# contigs (>= 0 bp)'           : 'ctg_min_0k',
    '# contigs (>= 1000 bp)'        : 'ctg_min_1k',
    '# contigs (>= 5000 bp)'        : 'ctg_min_5k',
    '# contigs (>= 10000 bp)'       : 'ctg_min_10k',
    '# contigs (>= 25000 bp)'       : 'ctg_min_25k',
    '# contigs (>= 50000 bp)'       : 'ctg_min_50k',
    'Total length (>= 0 bp)'        : 'len_min_0k',
    'Total length (>= 1000 bp)'     : 'len_min_1k',
    'Total length (>= 5000 bp)'     : 'len_min_5k',
    'Total length (>= 10000 bp)'    : 'len_min_10k',
    'Total length (>= 25000 bp)'    : 'len_min_25k',
    'Total length (>= 50000 bp)'    : 'len_min_50k',
    'GC (%)'                        : 'pct_gc',
    'N50'                           : 'n50',
    'NG50'                          : 'ng50',
    'N75'                           : 'n75',
    'NG75'                          : 'ng75',
    'L50'                           : 'l50',
    'LG50'                          : 'lg50',
    'L75'                           : 'l75',
    'LG75'                          : 'lg75',
    '# total reads'                 : 'num_reads',
    '# left'                        : 'reads_fwd',
    '# right'                       : 'reads_rev',
    'Mapped (%)'                    : 'pct_map',
    'Reference mapped (%)'          : 'pct_map_ref',
    'Properly paired (%)'           : 'pct_paired`',
    'Reference properly paired (%)' : 'pct_paired_ref',
    'Avg. coverage depth'           : 'cov_dep',
    'Reference avg. coverage depth' : 'cov_dep_ref',
    'Coverage >= 1x (%)'            : 'pct_cov_1x',
    'Reference coverage >= 1x (%)'  : 'pct_cov_1x_ref',
    '# misassemblies'               : 'num_mis_asm',
    '# misassembled contigs'        : 'ctg_mis_asm',
    'Misassembled contigs length'   : 'len_mis_asm',
    '# local misassemblies'         : 'lcl_mis_asm',
    '# scaffold gap ext. mis.'      : 'gap_ext_mis',
    '# scaffold gap loc. mis.'      : 'gap_loc_mis',
    '# unaligned mis. contigs'      : 'ctg_unal_mis',
    '# unaligned contigs'           : 'ctg_unal',
    'Unaligned length'              : 'len_unal',
    'Genome fraction (%)'           : 'pct_cov',
    'Duplication ratio'             : 'dup_rat',
    '# N\'s per 100 kbp'            : 'nbase_p_100k',
    '# mismatches per 100 kbp'      : 'mismt_p_100k',
    '# indels per 100 kbp'          : 'indel_p_100k',
    'Largest alignment'             : 'max_aln',
    'Total aligned length'          : 'tot_aln',
    'NA50'                          : 'na50',
    'NGA50'                         : 'nga50',
    'NA75'                          : 'na75',
    'NGA75'                         : 'nga75',
    'LA50'                          : 'la50',
    'LGA50'                         : 'lga50',
    'LA75'                          : 'la75',
    'LGA75'                         : 'lga75',
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
                'contig_threshold': self.get_user_input('qc_t'),
                'metrics': metrics,
                'html_report': job.file_path('report.html')})
            
        except Exception as e:
            self.fail("failed to parse output file %s: %s" % (tsv, str(e)))

