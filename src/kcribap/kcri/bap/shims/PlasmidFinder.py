#!/usr/bin/env python3
#
# cgetools.bap.shims.PlasmidFinder - service shim to the PlasmidFinder backend
#
#   Note that VirulenceFinder and PlasmidFinder have most backend logic in common.
#   This is captured in the shared PlasVirBaseExecution class.

import logging
from .PlasVirBase import PlasVirBaseExecution

# Global variables, will be updated by the update-services script
SERVICE, VERSION = "PlasmidFinder", "2.1.1"


class PlasmidFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, ident, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Execution.'''

        execution = PlasmidFinderExecution(SERVICE, VERSION, ident, blackboard, scheduler)

         # Get the execution parameters from the blackboard
        try:
            db_path = execution.get_db_path('plasmidfinder')
            min_ident = execution.get_user_input('pf_i')
            min_cov = execution.get_user_input('pf_c')
            search_list = list(filter(None, execution.get_user_input('pf_s', '').split(',')))
            params = [
                '-q',
                '-p', db_path,
                '-t', min_ident,
                '-l', min_cov,
                '-i' ] + execution.get_fastqs_or_contigs_paths()
            if search_list:
                params.extend(['-d', ','.join(search_list)])

            execution.start('plasmidfinder', db_path, params, search_list, 'PlasmidFinder')

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


class PlasmidFinderExecution(PlasVirBaseExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    # start() inherited
    # collect_output() inherited

    # We only need to implement the process_hit method to translate (part) of hits
    def process_hit(self, hit):

        plasmid = hit['plasmid']
        self.add_plasmid(plasmid)

        return dict({
            'plasmid': plasmid
            })

