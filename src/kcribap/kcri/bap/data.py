#!/usr/bin/env python3
#
# cgecore.bap.data
#
#   Defines the structure of the data produced by the BAP and its services, by
#   implementing class BAPBlackboard which adds a semantic layer over the generic
#   Blackboard.  This layer implements getters and putters that all services can
#   rely on (rather than just grabbing 'untyped' data from a bag).
#

import os, enum
from datetime import datetime
from cgetools.workflow.blackboard import Blackboard


### Enums
#
#   Define enums for supported sequencing platform, read pairing.

class SeqPlatform(enum.Enum):
    ILLUMINA = 'Illumina'
    NANOPORE = 'Nanopore'
    PACBIO = 'PacBio'

class SeqPairing(enum.Enum):
    PAIRED = 'paired'
    UNPAIRED = 'unpaired'
    MATE_PAIRED = 'mate-paired'

### BAPBlackboard class
#
#   Wraps the generic Blackboard with an API that adds getters and putters for data
#   that is well-defined and needs to be exchanged between service implementations.

class BAPBlackboard(Blackboard):
    '''Adds to the generic Blackboard getters and putters specific to the shared
       data definitions in the current BAP.'''

    def __init__(self, verbose=False):
        super().__init__(verbose)

    # BAP-level methods

    def start_bap_run(self, service, version, user_inputs):
        self.put('bap/run_info/service', service)
        self.put('bap/run_info/version', version)
        self.put('bap/run_info/time/start', datetime.now().isoformat(timespec='seconds'))
        self.put('bap/user_inputs', user_inputs)

    def end_bap_run(self, state):
        start_time = datetime.fromisoformat(self.get('bap/run_info/time/start'))
        end_time = datetime.now()
        self.put('bap/run_info/time/end', end_time.isoformat(timespec='seconds'))
        self.put('bap/run_info/time/duration', (end_time - start_time).total_seconds())
        self.put('bap/run_info/status', state)

    def put_user_input(self, param, value):
        return self.put('bap/user_inputs/%s' % param, value)

    def get_user_input(self, param, default=None):
        return self.get('bap/user_inputs/%s' % param, default)

    def add_warning(self, warning):
        '''Stores a warning on the 'bap' top level (note: use service warning instead).'''
        self.append_to('bap/warnings', warning)

    # Standard methods for BAP common data

    def put_db_root(self, path):
        '''Stores the root of the BAP services databases.'''
        self.put_user_input('db_root', path)

    def get_db_root(self):
        '''Retrieve the user_input/db_root, this must be set.'''
        db_root = self.get_user_input('db_root')
        if not db_root:
            raise Exception("database root path is not set")
        elif not os.path.isdir(db_root):
            raise Exception("db root path is not a directory: %s" % db_root)
        return os.path.abspath(db_root)

    # Sample ID

    def put_sample_id(self, id):
        '''Store id as the sample id in the summary.'''
        self.put('bap/summary/sample_id', id)

    def get_sample_id(self):
        return self.get('bap/summary/sample_id', 'unknown')

    # Sequencing specs

    def put_seq_platform(self, platform):
        '''Stores the sequencing platform as its own (pseudo) user input.'''
        assert isinstance(platform, SeqPlatform)
        self.put_user_input('seq_platform', platform.value)

    def get_seq_platform(self, default=None):
        '''Returns the stored platform as SeqPlatform enum value.'''
        s = self.get_user_input('seq_platform')
        return SeqPlatform(s) if s else default

    def put_seq_pairing(self, pairing):
        '''Stores the sequencing pairing as its own (pseudo) user input.'''
        assert isinstance(pairing, SeqPairing)
        self.put_user_input('seq_pairing', pairing.value)

    def get_seq_pairing(self, default=None):
        '''Returns the stored pairing as SeqPairing enum value.'''
        s = self.get_user_input('seq_pairing')
        return SeqPairing(s) if s else default

    # Contigs and reads

    def put_fastq_paths(self, paths):
        '''Stores the fastqs path as its own (pseudo) user input.'''
        self.put_user_input('fastqs', paths)

    def get_fastq_paths(self, default=None):
        return self.get_user_input('fastqs', default)

    def put_user_contigs_path(self, path):
        '''Stores the contigs path as its own (pseudo) user input.'''
        self.put_user_input('contigs', path)

    def get_user_contigs_path(self, default=None):
        return self.get_user_input('contigs', default)

    def put_assembled_contigs_path(self, path):
        '''Stores the path to the computed contigs.'''
        self.put('bap/summary/contigs', path)

    def get_assembled_contigs_path(self, default=None):
        return self.get('bap/summary/contigs', default)

    # Species

    def put_user_species(self, lst):
        '''Stores list of species specified by user.'''
        self.put_user_input('species', lst)

    def get_user_species(self, default=None):
        return self.get_user_input('species', default)

    def add_detected_species(self, lst):
        self.append_to('bap/summary/species', lst, True)

    def get_detected_species(self, default=None):
        return self.get('bap/summary/species', default)

    # MLST

    def add_mlst(self, st, loci, alleles):
        str = "%s[%s]" % (st, ','.join(map(lambda l: '%s:%s' % l, zip(loci, alleles))))
        self.append_to('bap/summary/mlst', str, True)

    def get_mlsts(self):
        return sorted(self.get('bap/summary/mlst', []))

    # Plasmids

    def put_user_plasmids(self, lst):
        '''Stores list of plasmids specified by user.'''
        self.put_user_input('plasmids', lst)

    def get_user_plasmids(self, default=None):
        return sorted(self.get_user_input('plasmids', default))

    def add_detected_plasmid(self, plasmid):
        self.append_to('bap/summary/plasmids', plasmid, True)

    def get_detected_plasmids(self, default=None):
        return sorted(self.get('bap/summary/plasmids', default))

    def add_pmlst(self, profile, st):
        str = "%s%s" % (profile, st)
        self.append_to('bap/summary/pmlsts', str)

    def get_pmlsts(self):
        return sorted(self.get('bap/summary/pmlsts', []))

    # Virulence

    def add_detected_virulence_gene(self, gene):
        self.append_to('bap/summary/virulence_genes', gene, True)

    def get_virulence_genes(self):
        return sorted(self.get('bap/summary/virulence_genes', []))

    # Resistance

    def add_amr_gene(self, gene):
        self.append_to('bap/summary/amr_genes', gene, True)

    def get_amr_genes(self):
        return sorted(self.get('bap/summary/amr_genes', []))

    def add_amr_classes(self, classes):
        self.append_to('bap/summary/amr_classes', classes, True)

    def get_amr_classes(self):
        return sorted(self.get('bap/summary/amr_classes', []))

    def add_amr_phenotype(self, pheno):
        self.append_to('bap/summary/amr_phenotypes', pheno, True)

    def get_amr_phenotypes(self):
        return sorted(self.get('bap/summary/amr_phenotypes', []))

    def add_amr_mutation(self, mut):
        self.append_to('bap/summary/amr_mutations', mut, True)

    def get_amr_mutations(self):
        return sorted(self.get('bap/summary/amr_mutations', []))

    # cgMLST

    def add_cgmlst(self, scheme, st, pct):
        str = '%s:%s(%s%%)' % (scheme, st, pct)
        self.append_to('bap/summary/cgmlst', str, True)

    def get_cgmlsts(self):
        return sorted(self.get('bap/summary/cgmlst', []))

