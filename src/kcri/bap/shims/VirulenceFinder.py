#!/usr/bin/env python3
#
# kcri.bap.shims.VirulenceFinder - service shim to the VirulenceFinder backend
#
#   Note that VirulenceFinder and PlasmidFinder have most backend logic in common.
#   This is captured in the shared PlasVirBaseExecution class.

import logging
from .base import UserException
from .PlasVirBase import PlasVirBaseExecution
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "VirulenceFinder", BACKEND_VERSIONS['virulencefinder']


class VirulenceFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = VirulenceFinderExecution(SERVICE, VERSION, ident, blackboard, scheduler)

        # Get the execution parameters from the blackboard
        try:
            db_path = execution.get_db_path('virulencefinder')
            min_ident = execution.get_user_input('vf_i')
            min_cov = execution.get_user_input('vf_c')
            search_list = list(filter(None, execution.get_user_input('vf_s', '').split(',')))
            params = [ #'--lineage = --speciesinfo_jsonx',
                '-q',
                '-p', db_path,
                '-t', min_ident,
                '-l', min_cov,
                '-i' ] + execution.get_fastqs_or_contigs_paths()
            if search_list:
                params.extend(['-d', ','.join(search_list)])

            execution.start('virulencefinder', db_path, params, search_list, 'VirulenceFinder')

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


class VirulenceFinderExecution(PlasVirBaseExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    # start() inherited
    # collect_output() inherited

    # We only need to implement the process_hit method to translate (part) of hits
    def process_hit(self, hit):

        vir_gene = hit['virulence_gene']
        self._blackboard.add_detected_virulence_gene(vir_gene)

        return dict({
            'gene': vir_gene,
            'function': hit['protein_function'].strip()
            })

