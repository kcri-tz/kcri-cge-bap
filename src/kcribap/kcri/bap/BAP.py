#!/usr/bin/env python3

import sys, os, argparse, json, re, textwrap
from cgecore import check_file_type
from cge.flow.workflow.logic import Workflow
from cge.flow.workflow.executor import Executor
from cge.flow.jobcontrol.subproc import SubprocessScheduler
from kcri.bap.data import BAPBlackboard, SeqPlatform, SeqPairing
from kcri.bap.services import SERVICES as BAP_SERVICES
from kcri.bap.workflow import DEPENDENCIES as BAP_DEPENDENCIES
from kcri.bap.workflow import UserTargets, Services, Params

# Global variables and defaults
service, version = "KCRI CGE BAP", "3.0.0"

# Exit the BAP with error message and non-zero code
def err_exit(msg, *args):
    print(('BAP: %s' % msg) % args, file=sys.stderr)
    sys.exit(1)

# Helper to parse string ts which may be UserTarget or Service
def UserTargetOrService(s):
    try: return UserTargets(s)
    except: return Services(s)


def main():
    '''BAP main program.'''

    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            The KCRI CGE Bacterial Analysis Pipeline (BAP) performs a configurable
            smorgasbord of analyses on the sequencer reads and/or assembled contigs
            of a bacterial isolate.

            The analyses to be performed are specified using the -t/--targets option.
            The default target performs species detection, MLST, resistance, virulence,
            and plasmid typing (but no assembly, cgMLST, or specialised services).
            The FULL target runs every available service.

            Use -l/--list-targets to see the available targets.  Use -t/--targets to
            specify a custom set of targets, or combine with -x/--exclude to exclude
            certain targets or services.  Use -s/--list-services to see available services.

            If a requested service depends on the output of another service, then the
            dependency will be automatically added.
            """),
        epilog=textwrap.dedent("""\
            Instead of passing arguments on the command-line, you can put them in a
            text file and pass this to the BAP using @FILENAME."""))

    # General arguments
    group = parser.add_argument_group('General parameters')
    group.add_argument('-t', '--targets', metavar='TARGET[,...]', default='DEFAULT', help="analyses to perform [DEFAULT]")
    group.add_argument('-x', '--exclude', metavar='TARGET_OR_SERVICE[,...]', help="targets and/or services to exclude from running")
    group.add_argument('-s', '--species', metavar='NAME[,...]', help="scientific name(s) of the bacterial species, if known")
    group.add_argument('-p', '--plasmids',metavar='NAME[,...]', help="name(s) of plasmids present in the data, if known")
    group.add_argument('-i', '--id',      metavar='ID', help="identifier to use for the isolate in reports")
    group.add_argument('-o', '--out-dir', metavar='PATH', default='.', help="directory to write output to, will be created (must be relative to PWD when dockerised)")
    group.add_argument('--list-targets',  action='store_true', help="list the available targets")
    group.add_argument('--list-services', action='store_true', help="list the available services")
    group.add_argument('-d', '--db-root', metavar='PATH', default='/databases', help="base path to service databases (leave at default when dockerised)")
    group.add_argument('-v', '--verbose', action='store_true', help="write verbose output to stderr")
    group.add_argument('files', metavar='FILE', nargs='*', default=[], help="input file(s) in optionally gzipped FASTA or fastq format")

    # Resource management arguments
    group = parser.add_argument_group('Scheduler parameters')
    group.add_argument('--max-cpus',      metavar='N',   type=int, default=None, help="number of CPUs to allocate (default: all)")
    group.add_argument('--max-mem',       metavar='GB',  type=int, default=None, help="total memory to allocate (default: all)")
    group.add_argument('--max-disc',      metavar='GB',  type=int, default=None, help="total disc space to allocate (default: all)")
    group.add_argument('--max-time',      metavar='SEC', type=int, default=None, help="maximum overall run time (default: unlimited)")
    group.add_argument('--poll', metavar='SEC', type=int, default=5, help="seconds between backend polls [5]")

    # Service specific arguments
    group = parser.add_argument_group('Sequencing specs')
    group.add_argument('--sq-p', metavar='PLATFORM', help='Sequencing platform (%s; default %s)' % (','.join(v.value for v in SeqPlatform), SeqPlatform.ILLUMINA.value))
    group.add_argument('--sq-r', metavar='PAIRING', help='Pairing of reads (%s; default: %s when two fastqs are passed, unpaired when one)' % (', '.join(v.value for v in SeqPairing), SeqPairing.PAIRED.value))
    group = parser.add_argument_group('Assembly parameters')
    group.add_argument('--as-t', metavar='TRIM', default='auto', help="Trim reads (values: yes, no, auto; default: auto)")
    group = parser.add_argument_group('KmerFinder parameters')
    group.add_argument('--kf-s', metavar='SEARCH', default='bacteria', help="KmerFinder database to search [bacteria]")
    group = parser.add_argument_group('MLSTFinder parameters')
    group.add_argument('--mf-s', metavar='SCHEME[,...]', help="MLST schemes to apply (default: based on species)")
    group.add_argument('--mf-g', metavar='GENUS[,...]', help="MLST genus to type for (default: genus of the species)")
    group = parser.add_argument_group('KCST parameters')
    group.add_argument('--kc-c', metavar='FRAC', default='0.90', help="KCST minimum coverage")
    group = parser.add_argument_group('ResFinder parameters')
    group.add_argument('--rf-i', metavar='FRAC', default=0.80, help='ResFinder identity threshold')
    group.add_argument('--rf-c', metavar='FRAC', default=0.60, help='ResFinder minimum coverage')
    group.add_argument('--rf-o', metavar='NT', default=30, help='ResFinder maximum overlapping nucleotides')
    group.add_argument('--rf-p', metavar='PHENO[,...]', help='ResFinder phenotypes to search (default: all)')
    group = parser.add_argument_group('PointFinder parameters')
    group.add_argument('--pt-i', metavar='FRAC', default=0.80, help='PointFinder identity threshold')
    group.add_argument('--pt-c', metavar='FRAC', default=0.60, help='PointFinder minimum coverage')
    group.add_argument('--pt-g', metavar='GENE[,...]', help='PointFinder genes to search (default: all)')
    group.add_argument('--pt-a', action='store_true', help='PointFinder return all mutations including unknown ones')
    group = parser.add_argument_group('VirulenceFinder parameters')
    group.add_argument('--vf-i', metavar='FRAC', default=0.90, help='VirulenceFinder identity threshold')
    group.add_argument('--vf-c', metavar='FRAC', default=0.60, help='VirulenceFinder minimum coverage')
    group.add_argument('--vf-s', metavar='GROUP[,...]', help='VirulenceFinder group(s) to search (default: all)')
    group = parser.add_argument_group('PlasmidFinder parameters')
    group.add_argument('--pf-i', metavar='FRAC', default=0.90, help='PlasmidFinder identity threshold')
    group.add_argument('--pf-c', metavar='FRAC', default=0.60, help='PlasmidFinder minimum coverage')
    group.add_argument('--pf-s', metavar='NAME[,...]', help='PlasmidFinder searches (default: all)')
    group = parser.add_argument_group('pMLST parameters')
    group.add_argument('--pm-s', metavar='SCHEME[,...]', help='pMLST schemes to apply')
    group = parser.add_argument_group('cgMLSTFinder parameters')
    group.add_argument('--cg-s', metavar='SCHEME[,...]', help='cgMLST schemes to apply')
    group = parser.add_argument_group('CholeraeFinder parameters')
    group.add_argument('--ch-i', metavar='FRAC', default=0.90, help='CholeraeFinder identity threshold')
    group.add_argument('--ch-c', metavar='FRAC', default=0.60, help='CholeraeFinder minimum coverage')
    group.add_argument('--ch-o', metavar='NT', default=30, help='CholeraeFinder maximum overlapping nucleotides')
    group = parser.add_argument_group('QC and Metrics parameters')
    group.add_argument('--qc-t', metavar='LEN', default=500, help="Threshold contig length for Quast (500)")

    # Perform the parsing
    args = parser.parse_args()

    # Parse targets and translate to BAP workflow arguments
    targets = []
    try:
        targets = list(map(lambda t: UserTargets(t.strip()), args.targets.split(',') if args.targets else []))
    except ValueError as ve:
        err_exit('invalid target: %s (try --list-targets)', ve)

    # Parse excludes and translate to BAP workflow arguments
    excludes = []
    try:
        excludes = list(map(lambda t_or_s: UserTargetOrService(t_or_s.strip()), args.exclude.split(',') if args.exclude else []))
    except ValueError as ve:
        err_exit('invalid exclude: %s (try --list-targets and --list-services)', ve)

    # Parse and validate files into contigs and fastqs list
    contigs = None
    fastqs = list()
    for f in args.files:
        if not os.path.isfile(f):
            err_exit('no such file: %s', f)
        if check_file_type(f) == 'fasta':
            if contigs:
                err_exit('more than one FASTA file passed: %s', f)
            contigs = os.path.abspath(f)
        elif check_file_type(f) == 'fastq':
            if len(fastqs) == 2:
                err_exit('more than two fastq files passed: %s', f)
            fastqs.append(os.path.abspath(f))
        else:
            err_exit("file is neither FASTA not fastq: %s" % f)

    # Parse the --list options
    if args.list_targets:
        print('targets:', ','.join(t.value for t in UserTargets))
    if args.list_services:
        print('services:', ','.join(s.value for s in Services))

    # Exit when no contigs and/or fastqs were provided
    if not contigs and not fastqs:
        if not args.list_targets and not args.list_services:
            err_exit('no input files were provided')
        else:
            sys.exit(0)

    # Check existence of the db_root directory
    if not os.path.isdir(args.db_root):
        err_exit('no such directory for --db-root: %s', args.db_root)
    db_root = os.path.abspath(args.db_root)

    # Now that all path handling has been done, and all file references
    # been made, we can safely change the base working directory to out-dir.
    try:
        os.makedirs(args.out_dir, exist_ok=True)
        os.chdir(args.out_dir)
    except Exception as e:
        err_exit('error creating or changing to --out-dir %s: %s', args.out_dir, str(e))

    # Generate sample id if not given
    sample_id = args.id
    if not sample_id:
        if contigs and not fastqs:
            _, fname = os.path.split(contigs)
            sample_id, ext = os.path.splitext(fname)
            if ext == '.gz':
                sample_id, _ = os.path.splitext(sample_id)
        elif fastqs:
            # Try if it is Illumina
            pat = re.compile('^(.*)_S[0-9]+_L[0-9]+_R[12]_[0-9]+\.fastq\.gz$')
            _, fname = os.path.split(fastqs[0])
            mat = pat.fullmatch(fname)
            if mat:
                sample_id = mat.group(1)
            else: # no illumina, try to fudge something from common part
                common = os.path.commonprefix(fastqs)
                _, sample_id = os.path.split(common)
                # sample_id now is the common part, chop any _ or _R
                if sample_id[-2:] == "_R" or sample_id[-2:] == "_r":
                    sample_id = sample_id[:-2]
                elif sample_id[-1] == "_":
                    sample_id = sample_id[:-1]
        if not sample_id:
            sample_id = "SAMPLE"

    # Set up the Workflow execution
    blackboard = BAPBlackboard(args.verbose)
    blackboard.start_bap_run(service, version, vars(args))
    blackboard.put_db_root(db_root)
    blackboard.put_sample_id(sample_id)

    # Set platform and pairing defaults when fastqs are present - TODO autodetect?
    seq_platform = None
    seq_pairing = None

    if fastqs:
        if not args.sq_p:
            seq_platform = SeqPlatform.ILLUMINA
            blackboard.add_warning('assuming %s platform reads' % seq_platform.value)
        else:
            try: seq_platform = SeqPlatform(args.sq_p)
            except: err_exit('invalid value for --sq-p (sequencing platform): %s', args.sq_p)

        if not args.sq_r:
            seq_pairing = SeqPairing.PAIRED if len(fastqs) == 2 else SeqPairing.UNPAIRED
            blackboard.add_warning('assuming %s reads' % seq_pairing.value)
        else:
            try: seq_pairing = SeqPairing(args.sq_r)
            except: err_exit('invalid value for --sq-r (read pairing): %s', args.sq_r)

        if not args.as_t in ['yes','no','auto']:
            err_exit('invalid value for --as-t (trim reads): %s', args.as_t)

    # Set the workflow params based on user inputs present
    params = list()
    if contigs:
        params.append(Params.CONTIGS)
        blackboard.put_user_contigs_path(contigs)
    if fastqs:
        params.append(Params.READS)
        blackboard.put_fastq_paths(fastqs)
        blackboard.put_seq_platform(seq_platform)
        blackboard.put_seq_pairing(seq_pairing)
    if seq_platform == SeqPlatform.ILLUMINA:
        params.append(Params.ILLUMINA)   # is workflow param: SKESA requires them
    if args.species:
        params.append(Params.SPECIES)
        blackboard.put_user_species(list(filter(None, map(lambda x: x.strip(), args.species.split(',')))))
    if args.plasmids:
        params.append(Params.PLASMIDS)
        blackboard.put_user_plasmids(list(filter(None, map(lambda x: x.strip(), args.plasmids.split(',')))))

    # Pass the actual data via the blackboard
    workflow = Workflow(BAP_DEPENDENCIES, params, targets, excludes)
    scheduler = SubprocessScheduler(args.max_cpus, args.max_mem, args.max_disc, args.max_time, args.poll, not args.verbose)
    executor = Executor(workflow, BAP_SERVICES, scheduler)
    executor.execute(blackboard)
    blackboard.end_bap_run(workflow.status.value)

    # Write the results to bap-results.json
    with open('bap-results.json', 'w') as f_json:
        json.dump(blackboard.as_dict(args.verbose), f_json)

    # Write the summary table to bap-summary.tsv
    with open('bap-summary.tsv', 'w') as f_tsv:
        commasep = lambda l: '' if not l else ','.join(l)
        b = blackboard
        d = dict({
            'sample_id': b.get_sample_id(),
            'bases_read': '' if b.get_fastq_paths([]) else b.get('services/Quast/results/metrics/total_read'),
            'bases_assembled': b.get('services/Quast/results/metrics/total_len'),
            'n_contigs': b.get('services/Quast/results/metrics/n_contigs'),
            'largest_ctg':  b.get('services/Quast/results/metrics/max_contig_len'),
            'n50':  b.get('services/Quast/results/metrics/n50'),
            'depth': '',
            'species': commasep(b.get_detected_species([])),
            'mlst': commasep(b.get_mlsts()),
            'amr_classes': commasep(b.get_amr_classes()),
            'amr_pheno': commasep(b.get_amr_phenotypes()),
            'amr_genes': commasep(b.get_amr_genes()),
            'virulence_genes': commasep(b.get_virulence_genes()),
            'plasmids': commasep(b.get_detected_plasmids([])),
            'pmlsts': commasep(b.get_pmlsts()),
            'cgst': commasep(b.get_cgmlsts()),
            'amr_mutations': commasep(b.get_amr_mutations())
            })
        print('\t'.join(d.keys()), file=f_tsv)
        print('\t'.join(map(lambda v: v if v else '', d.values())), file=f_tsv)

    # Done done
    return 0


if __name__ == '__main__':
   main()
