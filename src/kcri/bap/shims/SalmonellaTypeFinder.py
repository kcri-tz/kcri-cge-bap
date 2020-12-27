#!/usr/bin/env python3
'''
################################################################################
##########                    CGE Service Wrapper                    ###########
################################################################################
'''
import sys, os, json
from cgecore import (check_file_type, debug, get_arguments, proglist, Program,
                     open_, adv_dict)

# SET GLOBAL VARIABLES
service, version = "SalmonellaTypeFinder", "1.0"

def main():
   ''' MAIN '''
   # PARSE ARGUMENTS
   # Add service specific arguments using the following format:
   #  (OPTION, VARIABLE,  DEFAULT,  HELP)
   args = get_arguments([
      ('-f', 'raw_reads', None, 'The input file (fastq file required)'),
      ('-f2', 'raw_reads2', None, 'The paired end file (fastq file only)'),
      ('-d', 'db', os.environ.get('CGEPIPELINE_DB', '/databases')+'/salmonellatypefinder/db.json', 'Path to json database'),
      ])
   
   # VALIDATE REQUIRED ARGUMENTS
   if args.db is None:
      debug.graceful_exit("Input Error: No json database was provided!\n")
   elif not os.path.exists(args.db):
      debug.graceful_exit("Input Error: The specified json database does not"
                          " exist!\n")
   
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
   
   # Execute Program
   progname = 'STF'
   prog = Program(path='SalmonellaTypeFinder.py',
      name=progname,
      args=['-d', args.db,
            '-t', os.getcwd(),
            '--output', 'typeFinderResults.txt',
            args.raw_reads
            ]
      )
   prog.execute()
   proglist.add2list(prog)
   prog.wait(interval=25)
   
   # THE SUCCESS OF THE PROGRAMS ARE VALIDATED
   results = {
      'type': 'Unknown'
   }
   status = prog.get_status()
   if status == 'Done' and os.path.exists('typeFinderResults.txt'):
      # Extract service results
      with open('typeFinderResults.txt', 'r') as f:
         # OUTPUT EXAMPLE tab
         # Sample	Predicted Serotype	ST	ST mismatches	ST sero prediction	SeqSero prediction	O-type	H1-type	H2-type	MLST serotype details	Flagged
         # 17030523_S9_L001_R1_001.fastq.gz	infantis	32	0	infantis	infantis	O-7	r	1,5	rough_o:r:1,5 (3, 0.33) | enteritidis (15, 1.64) | infantis (893, 97.70) | virchow (3, 0.33)	*
         for l in f:
            if not l.strip(): continue
            if l.startswith('Sample'): continue
            results['type'] = l.split('\t')[1]
            break
      
      sys.stdout.write('%s\n'%json.dumps(results))
   else:   
      sys.stderr.write('OBS: No results were found!\n')
   
   # LOG THE TIMERS
   proglist.print_timers()

if __name__ == '__main__':
   main()
