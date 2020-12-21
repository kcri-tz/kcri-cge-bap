#!/usr/bin/env python3
'''
################################################################################
##########                    CGE Service Wrapper                    ###########
################################################################################
'''
import sys, os, json
from cgecore import (check_file_type, debug, get_arguments, proglist, Program,
                     open_, adv_dict)

def main():
   ''' MAIN '''
   # PARSE ARGUMENTS
   # Add service specific arguments using the following format:
   #  (OPTION, VARIABLE,  DEFAULT,  HELP)
   args = get_arguments([
      ('-f', 'raw_reads', None, 'The input file (fastq file required)'),
      ('-f2', 'raw_reads2', None, 'The paired end file (fastq file only)'),
      ('-o', 'kma_output_prefix', None, 'Output prefix. Default is based on the input file'),
      ('--db', 'db', None, 'path to the kma database or a fasta file'),
      ('-k', 'kmer_size', None, 'path to the kma database or a fasta file'),
      ('--flags', 'flags', 'mdb1',
       'set KMA flags: allowed letters: 1 S b c d e m n r s t'),
      ])
   
   # VALIDATE REQUIRED ARGUMENTS
   if args.db is None:
      debug.graceful_exit("Input Error: No database directory was provided!\n")
   elif not os.path.exists(args.db):
      debug.graceful_exit("Input Error: The specified database directory does "
                          "not exist!\n")
   
   if args.raw_reads is None:
      debug.graceful_exit("Input Error: No input was provided!\n")
   elif not os.path.exists(args.raw_reads):
      debug.graceful_exit("Input Error: Input file does not exist!\n")
   elif check_file_type(args.raw_reads) != 'fastq':
      debug.graceful_exit(('Input Error: Invalid raw reads format (%s)!\nOnly the '
                           'fastq format is recognised as a proper raw read format.'
                           '\n')%(check_file_type(args.raw_reads)))
   else:
       args.raw_reads = os.path.abspath(args.raw_reads)
   
   if args.raw_reads2 is not None:
      if not os.path.exists(args.raw_reads2):
         debug.graceful_exit("Input Error: Input file 2 does not exist!\n")
      elif check_file_type(args.raw_reads2) != 'fastq':
         debug.graceful_exit(('Input Error: Invalid raw reads 2 format (%s)!\nOnly the '
                              'fastq format is recognised as a proper raw read format.'
                              '\n')%(check_file_type(args.raw_reads2)))
      else:
         args.raw_reads2 = os.path.abspath(args.raw_reads2)
   
   if args.kma_output_prefix is None:
      args.kma_output_prefix = os.path.basename(raw_reads).split('.')[0]
   
   flags = {'1':'-1t1',
            'S':'-shm',
            'b':'-boot',
            'c':'-deCon',
            'd':'-dense',
            'e':'-ex_mode',
            'm':'-mem_mode',
            'n':'-NW',
            'r':'-ref_fsa',
            's':'-Sparse',
            't':'-matrix'
            }
   if os.path.exists(args.db) and check_file_type(args.db) == 'fasta':
      # Database must be indexed first
      kma_db = args.db.rsplit('.',1)[0]
      progname = 'kma_index'
      prog = Program(path='kma_index',
         name=progname, wait=True,
         args=['-i', args.db,
               '-o', kma_db
               ]
         )
      try: prog.append_args([flags[f] for f in args.flags])
      except Exception as e:
         debug.graceful_exit(("Input Error: invalid flag found in flags (%s)!\n"
                              "%s\nHere is the list of accepted flags: %s\n")%(
                              args.flags, e, flags))
      
      if args.kmer_size is not None:
         prog.append_args(['-k', args.kmer_size])
      prog.execute()
      proglist.add2list(prog)
   else:
      kma_db = args.db
   
   # Execute Program
   progname = 'kma'
   prog = Program(path='kma',
      name=progname, wait=True,
      args=['-o', args.kma_output_prefix,
            '-t_db', kma_db
            ]
      )
   try: prog.append_args([flags[f] for f in args.flags])
   except Exception as e:
      debug.graceful_exit(("Input Error: invalid flag found in flags (%s)!\n"
                           "%s\nHere is the list of accepted flags: %s\n")%(
                           args.flags, e, flags))
   if args.kmer_size is not None:
      prog.append_args(['-k', args.kmer_size])
   prog.append_args(['-i', args.raw_reads])
   if args.raw_reads2:
      prog.append_args([args.raw_reads2])
   prog.execute()
   proglist.add2list(prog)
   
   sys.stdout.write(("Check the 5-6 result files for the results! The files are:"
                     "\n{name}.res\n{name}.aln\n{name}.frag.gz\n"
                     "{name}.frag_raw.b\n{name}.fsa\n"
                     "{name}.spa (Sparse option only)\n").format(
      {'name': args.kma_output_prefix}))
   
   # THE SUCCESS OF THE PROGRAMS ARE VALIDATED
   # results = {
   #    'type': 'Unknown'
   # }
   # status = prog.get_status()
   # if status == 'Done' and os.path.exists('AlleleMatrix.mat-st.txt'): #AlleleMatrix.mat.txt
   #    # Extract service results
   #    with open('AlleleMatrix.mat-st.txt', 'r') as f:
   #       # OUTPUT EXAMPLE tab
   #       # Sample	Predicted Serotype	ST	ST mismatches	ST sero prediction	SeqSero prediction	O-type	H1-type	H2-type	MLST serotype details	Flagged
   #       # 17030523_S9_L001_R1_001.fastq.gz	infantis	32	0	infantis	infantis	O-7	r	1,5	rough_o:r:1,5 (3, 0.33) | enteritidis (15, 1.64) | infantis (893, 97.70) | virchow (3, 0.33)	*
   #       for l in f:
   #          if not l.strip(): continue
   #          if l.startswith('Sample'): continue
   #          results['type'] = l.split('\t')[1]
   #          break
   #    
   #    sys.stdout.write('%s\n'%json.dumps(results))
   # else:   
   #    sys.stderr.write('OBS: No results were found!\n')
   
   # LOG THE TIMERS
   proglist.print_timers()

if __name__ == '__main__':
   main()
