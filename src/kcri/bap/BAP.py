#!/usr/bin/env python3
#
# BAP.py - main for the KCRI CGE Bacterial Analysis Pipeline
#

import sys, os, argparse, gzip, io, json, re
from pico.workflow.logic import Workflow
from pico.workflow.executor import Executor
from pico.jobcontrol.subproc import SubprocessScheduler
from .data import BAPBlackboard
from .services import SERVICES
from .workflow import DEPENDENCIES
from .workflow import UserTargets, Services, Params
from . import __version__

# Global variables and defaults
SERVICE, VERSION = "KCRI CGE BAP", __version__

# Exit with error message and non-zero code
def err_exit(msg, *args):
    print(('BAP: %s' % msg) % args, file=sys.stderr)
    sys.exit(1)

# Helper to detect whether file is (gzipped) fasta or fastq
def detect_filetype(fname):
    with open(fname, 'rb') as f:
        b = f.peek(2)
        if b[:2] == b'\x1f\x8b':
            b = gzip.GzipFile(fileobj=f).peek(2)[:2]
        c = chr(b[0]) if len(b) > 0 else '\x00'
    return 'fasta' if c == '>' else 'fastq' if c == '@' else 'other'

# Helper to detect whether fastq file has Illumina reads
def is_illumina_reads(fname):
    pat = re.compile(r'^@[^:]+:\d+:[^:]+:\d+:\d+:\d+:\d+ [12]:[YN]:\d+:[^: ]+( .*)?$')
    with open(fname, 'rb') as f:
        b = f.peek(2)
        buf = io.TextIOWrapper(gzip.GzipFile(fileobj=f) if b[:2] == b'\x1f\x8b' else f)
        return re.match(pat, buf.readline())

# Helper to parse string ts which may be UserTarget or Service
def UserTargetOrService(s):
    try: return UserTargets(s)
    except: return Services(s)


def main():
    '''BAP main program.'''

    parser = argparse.ArgumentParser(
        description="""\
The KCRI CGE Bacterial Analysis Pipeline (BAP) performs a configurable
smorgasbord of analyses on the sequencer reads and/or assembled contigs
of a bacterial isolate.

The analyses to be performed are specified using the -t/--targets option.
The DEFAULT target performs species detection, MLST, resistance, virulence,
and plasmid typing (but no cgMLST).  The FULL target runs all available
services.

Use -l/--list-available to see the available targets and services.  Use
-t/--targets to specify a custom set of targets, or combine -t DEFAULT
with -x/--exclude to exclude certain targets or services.

If a requested service depends on the output of another service, then the
dependency will be automatically added.
""",
        epilog="""\
Instead of passing arguments on the command-line, you can put them, one
per line, in a text file and pass this file with @FILENAME.
""",
        fromfile_prefix_chars='@',
        formatter_class=argparse.RawDescriptionHelpFormatter)

    # General arguments
    group = parser.add_argument_group('General parameters')
    group.add_argument('-t', '--targets',  metavar='TARGET[,...]', default='DEFAULT', help="analyses to perform [DEFAULT]")
    group.add_argument('-x', '--exclude',  metavar='TARGET_OR_SERVICE[,...]', help="targets and/or services to exclude from running")
    group.add_argument('-s', '--species',  metavar='NAME[,...]', help="scientific name(s) of the bacterial species, if known")
    group.add_argument('-p', '--plasmids', metavar='NAME[,...]', help="name(s) of plasmids present in the data, if known")
    group.add_argument('-i', '--id',       metavar='ID', help="identifier to use for the isolate in reports")
    group.add_argument('-o', '--out-dir',  metavar='PATH', default='.', help="directory to write output to, will be created (relative to PWD when dockerised)")
    group.add_argument('-n', '--nanopore', action='store_true', help="data are nanopore reads")
    group.add_argument('-l', '--list-available', action='store_true', help="list the available targets and services")
    group.add_argument('-d', '--db-root',  metavar='PATH', default='/databases', help="base path to service databases (leave default when dockerised)")
    group.add_argument('-v', '--verbose',  action='store_true', help="write verbose output to stderr")
    group.add_argument('files', metavar='FILE', nargs='*', default=[], help="input file(s) in optionally gzipped FASTA or fastq format")

    # Resource management arguments
    group = parser.add_argument_group('Scheduler parameters')
    group.add_argument('--max-cpus',      metavar='N',   type=int, default=None, help="number of CPUs to allocate (default: all)")
    group.add_argument('--max-mem',       metavar='GB',  type=int, default=None, help="total memory to allocate (default: all)")
    group.add_argument('--max-time',      metavar='SEC', type=int, default=None, help="maximum overall run time (default: unlimited)")
    group.add_argument('--poll', metavar='SEC', type=int, default=5, help="seconds between backend polls [5]")

    # Service specific arguments
    group = parser.add_argument_group('ContigMetrics parameters')
    group.add_argument('--cm-l', metavar='NT', type=int, default=200, help="Minimum contig length to include in counts [200]")
    group = parser.add_argument_group('KmerFinder parameters')
    group.add_argument('--kf-s', metavar='SEARCH', default='bacteria', help="KmerFinder database to search [bacteria]")
    group = parser.add_argument_group('MLSTFinder parameters')
    group.add_argument('--mf-s', metavar='SCHEME[,...]', help="MLST schemes to apply (default: based on species)")
    group.add_argument('--mf-g', metavar='GENUS[,...]', help="MLST genus to type for (default: genus of the species)")
    group = parser.add_argument_group('KCST parameters')
    group.add_argument('--kc-c', metavar='FRAC', default='0.90', help="KCST minimum coverage")
    group = parser.add_argument_group('ResFinder parameters')
    group.add_argument('--rf-i', metavar='FRAC', default=0.90, help='ResFinder identity threshold')
    group.add_argument('--rf-c', metavar='FRAC', default=0.60, help='ResFinder minimum coverage')
    group.add_argument('--rf-o', metavar='NT', default=30, help='ResFinder maximum overlapping nucleotides')
    group.add_argument('--rf-p', metavar='PHENO[,...]', help='ResFinder phenotypes to search (default: all)')
    group = parser.add_argument_group('PointFinder parameters')
    group.add_argument('--pt-i', metavar='FRAC', default=0.90, help='PointFinder identity threshold')
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

    # Perform the parsing
    args = parser.parse_args()

    # Parse targets and translate to workflow arguments
    targets = []
    try:
        targets = list(map(lambda t: UserTargets(t.strip()), args.targets.split(',') if args.targets else []))
    except ValueError as ve:
        err_exit('invalid target: %s (try --list-available)', ve)

    # Parse excludes and translate to workflow arguments
    excludes = []
    try:
        excludes = list(map(lambda t_or_s: UserTargetOrService(t_or_s.strip()), args.exclude.split(',') if args.exclude else []))
    except ValueError as ve:
        err_exit('invalid exclude: %s (try --list-available)', ve)

    # Parse and validate files into contigs and fastqs list
    contigs = None
    fastqs = list()
    for f in args.files:
        if not os.path.isfile(f):
            err_exit('no such file: %s', f)
        if detect_filetype(f) == 'fasta':
            if contigs:
                err_exit('more than one FASTA file passed: %s', f)
            contigs = os.path.abspath(f)
        elif detect_filetype(f) == 'fastq':
            if len(fastqs) == 2:
                err_exit('more than two fastq files passed: %s', f)
            fastqs.append(os.path.abspath(f))
        else:
            err_exit("file is neither FASTA not fastq: %s" % f)

    # Parse the --list_available
    if args.list_available:
        print('targets:', ','.join(t.value for t in UserTargets))
        print('services:', ','.join(s.value for s in Services))

    # Exit when no contigs and/or fastqs were provided
    if not contigs and not fastqs:
        if not args.list_available:
            err_exit('no input files were provided')
        else:
            sys.exit(0)

    # Check existence of the db_root directory
    if not os.path.isdir(args.db_root):
        err_exit('no such directory for --db-root: %s', args.db_root)
    db_root = os.path.abspath(args.db_root)

    # Now that path handling has been done, and all file references made,
    # we can safely change the base working directory to out-dir.
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
    blackboard.start_run(SERVICE, VERSION, vars(args))
    blackboard.put_db_root(db_root)
    blackboard.put_sample_id(sample_id)

    # Set the workflow params based on user inputs present
    params = list()
    if contigs:
        params.append(Params.CONTIGS)
        blackboard.put_user_contigs_path(contigs)
    if fastqs:
        params.append(Params.READS)
        blackboard.put_fastq_paths(fastqs)
        # Check for paired Illumina reads (SKESA backend dependency)
        if len(fastqs) == 2 and is_illumina_reads(fastqs[0]) and is_illumina_reads(fastqs[1]):
            params.append(Params.ILLUMINA)  # is workflow param: SKESA requires them
        else:
            blackboard.add_warning('fastq files not detected to be paired Illumina reads')
    if args.species:
        params.append(Params.SPECIES)
        blackboard.put_user_species(list(filter(None, map(lambda x: x.strip(), args.species.split(',')))))
    if args.plasmids:
        params.append(Params.PLASMIDS)
        blackboard.put_user_plasmids(list(filter(None, map(lambda x: x.strip(), args.plasmids.split(',')))))
    if args.nanopore:
        params.append(Params.NANOPORE)

    # Pass the actual data via the blackboard
    scheduler = SubprocessScheduler(args.max_cpus, args.max_mem, args.max_time, args.poll, not args.verbose)
    executor = Executor(SERVICES, scheduler)
    workflow = Workflow(DEPENDENCIES, params, targets, excludes)
    executor.execute(workflow, blackboard)
    blackboard.end_run(workflow.status.value)

    # Write the JSON results file
    with open('bap-results.json', 'w') as f_json:
        json.dump(blackboard.as_dict(args.verbose), f_json)

    # Write the TSV summary results file
    with open('bap-summary.tsv', 'w') as f_tsv:
        commasep = lambda l: ','.join(l) if l else ''
        b = blackboard

        # For computing cross-service metrics
        nt_ctgs = int(b.get('services/ContigsMetrics/results/tot_len', 0))
        nt_read = int(b.get('services/ReadsMetrics/results/n_bases', 0))
        pct_q30 = float(b.get('services/ReadsMetrics/results/pct_q30', 0))

        d = dict({
            's_id': b.get_sample_id(),
            'n_reads': b.get('services/ReadsMetrics/results/n_reads', 'NA'),
            'nt_read': nt_read if nt_read else 'NA',
            'pct_q30': pct_q30 if pct_q30 else 'NA',
            'n_ctgs': b.get('services/ContigsMetrics/results/n_seqs', 'NA'),
            'nt_ctgs': nt_ctgs if nt_ctgs else 'NA',
            'n1': b.get('services/ContigsMetrics/results/max_len', 'NA'),
            'n50': b.get('services/ContigsMetrics/results/n50', 'NA'),
            'l50': b.get('services/ContigsMetrics/results/l50', 'NA'),
            'avg_dp': int(0.5 + nt_read / nt_ctgs) if nt_ctgs and nt_read else 'NA',
            'q30_dp': int(0.5 + pct_q30 / 100 * nt_read / nt_ctgs) if nt_ctgs and nt_read and pct_q30 else 'NA',
            'ref_len': b.get_closest_reference_length('NA'),
            'pct_gc': b.get('services/ContigsMetrics/results/pct_gc', b.get('services/ReadsMetrics/results/pct_gc', 'NA')),
            'species': commasep(b.get_detected_species([])),
            'mlst': commasep(b.get_mlsts()),
            'amr_cls': commasep(b.get_amr_classes()),
            'amr_phe': commasep(b.get_amr_phenotypes()),
            'amr_gen': commasep(b.get_amr_genes()),
            'vir_gen': commasep(b.get_virulence_genes()),
            'plasmid': commasep(b.get_detected_plasmids([])),
            'pmlsts': commasep(b.get_pmlsts()),
            'cgst': commasep(b.get_cgmlsts()),
            'amr_mut': commasep(b.get_amr_mutations())
            })
        print('#', '\t'.join(d.keys()), file=f_tsv)
        print('\t'.join(map(lambda v: str(v) if v else '', d.values())), file=f_tsv)

    # Done done
    return 0


if __name__ == '__main__':
   main()
