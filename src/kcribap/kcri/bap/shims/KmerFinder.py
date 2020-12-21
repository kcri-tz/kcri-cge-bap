#!/usr/bin/env python3
#
# kcri.bap.shims.KmerFinder - service shim to the KmerFinder backend
#

import os, logging
from cge.flow.workflow.executor import Execution
from cge.flow.jobcontrol.job import JobSpec, Job
from kcri.bap.shims.base import BAPServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "KmerFinder", BACKEND_VERSIONS['kmerfinder']

# Backend resource parameters: cpu, memory, disk, run time reqs
MAX_CPU = 1
MAX_MEM = 1
MAX_SPC = 1
MAX_TIM = 10 * 60


class KmerFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        execution = KmerFinderExecution(SERVICE, VERSION, ident, blackboard, scheduler)

         # Get the execution parameters from the blackboard
        try:
            kf_search = execution.get_user_input('kf_s')
            db_path, tax_file = find_db(execution.get_db_path('kmerfinder'), kf_search)
            params = [
                '-q',
                '-db', db_path,
                '-o', '.',
                '-i' ] + execution.get_fastqs_or_contigs_paths()
            if tax_file:
                params.extend(['-tax', tax_file])

            job_spec = JobSpec('kmerfinder.py', params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
            execution.store_job_spec(job_spec.as_dict())
            execution.start(job_spec, 'KF_%s' % kf_search)

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


class KmerFinderExecution(BAPServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _job = None

    def start(self, job_spec, work_dir):
        if self.state == Execution.State.STARTED:
            self._job = self._scheduler.schedule_job('kmerfinder', job_spec, work_dir)


    # Parse the output produced by the backend service, return list of hits
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        # Depending on whether there was a tax file
        results_file = job.file_path('results.txt')
        have_tax = os.path.exists(results_file)
        if not have_tax:
            results_file = job.file_path('results.spa')
            if not os.path.isfile(results_file):
                self.fail("service ran but no results.txt or results.spa file in %s", job.file_path(""))
                return False

        # The result list
        hits = list()      # list of detailed hit objects

        with open(results_file, 'r') as f:

            # The spa (no tax) file has these columns, where Template matches one in the database.name file
            # - Template (Accession " " Desc),Num,Score,Expected,Template_length,Query_Coverage,Template_Coverage,Depth,tot_query_Coverage,tot_template_Coverage,tot_depth,q_value,p_value
            # The tax file has these (note Accession here is not one from the spa file, but the new GCF accession (and Assembly is unique)
            # - 0:Assembly/accession,1:Num,Score,Expected,Template_length,Query_Coverage,Template_Coverage,Depth,tot_query_Coverage,tot_template_Coverage,tot_depth,q_value,p_value,Accession,Description,TAXID,Taxonomy,SpeciesTaxId,Species

            # Skip header
            f.readline()
            line = f.readline()

            # Parse all hits
            while line:

                rec = line.split('\t')

                # Bail out completely if line doesn't have the right number of record
                if (have_tax and len(rec) != 19) or (not have_tax and len(rec) != 13):
                    self.fail('invalid line in KmerFinder results: %s' % line)
                    return

                # The accession and description are at 13,14 in tax, and joined at 0 in non-tax
                acc_dsc = [rec[13].strip(), rec[14].strip()] if have_tax else rec[0].strip().split(' ')

                # Construct the hit object from the shared fields
                hit = { 'accession' : acc_dsc[0],
                        'desc' : acc_dsc[1],
                        'num' : int(rec[1]),
                        'score' : int(rec[2]),
                        'expected' : int(rec[3]),
                        'slen' : int(rec[4]),
                        'qcov' : float(rec[5]),
                        'scov' : float(rec[6]),
                        'depth' : float(rec[7]),
                        'tot_qcov' : float(rec[8]),
                        'tot_scov' : float(rec[9]),
                        'tot_depth' : float(rec[10]),
                        'q_value' : float(rec[11]),
                        'p_value' : float(rec[12]) }

                # Add the taxonomy if we have it
                if have_tax:
                    #hit['ass_acc'] = rec[0]
                    hit['strain_taxid'] = int(rec[15])
                    hit['lineage'] = [s.strip() for s in rec[16].split(';')]
                    hit['taxid'] = int(rec[17])
                    hit['species'] = rec[18].strip()

                # Append to the list of hits
                hits.append(hit)

                # Iterate to next line
                line = f.readline()

        # Store result and add species to global BAP findings
        self.store_results(hits)
        if have_tax and len(hits):
            self.add_species(hits[0].get('species'))


# Returns comma-separated list of available databases in db_dir
def list_dbs(db_dir):
    dbs = list()
    cfg = os.path.join(db_dir, "config")
    if os.path.isfile(cfg):
        with open(cfg) as f:
            for l in f:
                l = l.strip()
                if l.startswith('#'): continue
                r = l.split('\t')
                if len(r) == 3:
                    dbs.append(r[0].split('.')[0])
    return ', '.join(dbs)


# Locates database under db_dir, returns (db_path, tax_file)
# or raises an exception with appriopriate error message
def find_db(db_dir, name):

    config = os.path.join(db_dir, 'config')
    if not os.path.isfile(config):
        raise UserException('database config not found: %s', config)

    # Look up the database in the config
    with open(config) as f:
        for l in f:
            # Lines are {name}[.{kmersuffix}]\t{Description}\t{More}
            if not l.startswith(name.lower()): continue
            db_pfx = l.split('\t')[0].strip()
            db = l.split('.')[0] if '.' in db_pfx else db_pfx
            path = os.path.join(db_dir, db_pfx)
            if not os.path.isfile(path + '.seq.b'):
                # Check in subdirectory just in case
                path = os.path.join(db_dir, db, db_pfx)
                if not os.path.isfile(path + '.seq.b'):
                    raise UserException('invalid database, no seq.b file: %s', db_pfx)
            # Locate full path to the tax file (which may be absent)
            tax = os.path.join(os.path.dirname(path), db + ".tax")
            if not os.path.isfile(tax):  # try with pfx and tax
                tax = os.path.join(os.path.dirname(path), db_pfx + ".tax")
                if not os.path.isfile(tax):
                    tax = None
            return (path, tax)

    # If we get here, the database was not in the config
    raise UserException("database '%s' not in config; databases are: %s", name, list_dbs(db_dir))

