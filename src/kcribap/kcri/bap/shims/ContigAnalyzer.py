#!/usr/bin/env python3
'''
################################################################################
##########                    CGE Service Wrapper                    ###########
################################################################################
'''
import sys, os, json
import numpy as np
from cgecore import (check_file_type, debug, get_arguments, seqs_from_file,
                     proglist)

################################################################################
##########                         FUNCTIONS                         ###########
################################################################################

################################################################################
##########                           MAIN                            ###########
################################################################################
# SET GLOBAL VARIABLES
service, version = "ContigAnalyzer", "1.0"

def main():
   ''' MAIN '''
   # PARSE ARGUMENTS
   # Add service specific arguments using the following format:
   #(OPTION,   VARIABLE,  DEFAULT,  HELP)
   #args = getArguments([
   #   ('--uploadpath',  'uploadPath',  None, 'The folder containing uploads'),
   #   ('-t',   'technology',  None, 'The sequencing platform of the input file')])
   #
   # Or by pasting the argument lines from the contigs file
   args = get_arguments([
      ('-f', 'contigs', None, 'The input file (fasta file required)')
      ])
   
   
   # VALIDATE REQUIRED ARGUMENTS
   if args.contigs == None:
      debug.graceful_exit("Error: No Contigs were provided!\n")
   elif not os.path.exists(args.contigs):
      debug.graceful_exit("Error: Contigs file does not exist!\n")
   elif check_file_type(args.contigs) != 'fasta':
      debug.graceful_exit(('Error: Invalid contigs format (%s)!\nOnly the fasta '
                           'format is recognised as a proper contig format.\n'
                           )%(check_file_type(args.contigs)))
   else:
      contigs_path = args.contigs
   
   results = {
      'length':      None,
      'sum':         None,
      'max':         None,
      'median':      None,
      'mean':        None,
      'n50':         None,
      'min':         None,
      'std':         None
   }
   try:
      # Analyse the contigs
      contig_lengths = []
      for seq, name, desc in seqs_from_file(contigs_path):
         contig_lengths.append(len(seq))
      # SUMARISE RESULTS
      contig_lengths = np.asarray(contig_lengths, np.float64)
      contig_lengths.sort()
      results = {
         'length':      contig_lengths.shape[0],
         'sum':         int(contig_lengths.sum()),
         'max':         int(contig_lengths.max()),
         'median':      int(np.median(contig_lengths)),
         'mean':        int(round(contig_lengths.mean())),
         'n50':         int(round((contig_lengths[(contig_lengths.cumsum() <= contig_lengths.sum()/2).sum()]+
                         contig_lengths[::-1][(contig_lengths[::-1].cumsum() <= contig_lengths.sum()/2).sum()]
                         )/2.0)), # https://www.broad.harvard.edu/crd/wiki/index.php/N50
         'min':         int(contig_lengths.min()),
         'std':         int(round(contig_lengths.std()))
      }
   except Exception as e:
      debug.graceful_exit('Error: %s\n'%e)
   else:
      # Print json to stdout
      sys.stdout.write('%s\n'%json.dumps(results))
   
   # LOG THE TIMERS
   proglist.print_timers() 

if __name__ == '__main__':
   main()
