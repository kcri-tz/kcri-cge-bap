#!/usr/bin/env python3
'''
################################################################################
##########                    CGE Service Wrapper                    ###########
################################################################################
'''
import sys, os, json
from cgecore import (check_file_type, debug, get_arguments, proglist, Program,
                     mkpath, copy_file)

# SET GLOBAL VARIABLES
service, version = "SPAdes", "3.9"

def main():
   ''' MAIN '''
   # PARSE ARGUMENTS
   # Add service specific arguments using the following format:
   #  (OPTION, VARIABLE,  DEFAULT,  HELP)
   args = get_arguments([
      ('--sequencing_platform', 'sequencing_platform', None,
       ("Sequencing Platform")),
      ('--sequencing_type', 'sequencing_type', None, ("Sequencing Type")),
      ('--files', 'files', None, ("raw unassembled fastq files"))
      ])
   
   # VALIDATE REQUIRED ARGUMENTS
   if args.files is None or len(args.files) == 0:
      debug.graceful_exit("Input Error: No files were provided!\n")
   files = []
   args.files = args.files.split(',')
   for file in args.files:
      if not os.path.exists(file):
         debug.graceful_exit("Input Error: The specified file '%s' does not "
                             "exist!\n"%(file))
      elif check_file_type(file) != 'fastq':
         debug.graceful_exit(('Input Error: Invalid file format (%s)!\nOnly the'
                              ' fastq format is recognised as a proper format.'
                              '\n')%(check_file_type(file)))
      files.append(os.path.abspath(file))
   
   if args.sequencing_platform is None:
      debug.graceful_exit("Input Error: No sequencing platform was specified!"
                          "\n")
   elif args.sequencing_type is None:
      debug.graceful_exit("Input Error: No sequencing type was specified!\n")
   
   # Convert sequencing information to our sequencing schemas
   # (plat, type): (seq_tech, tech_setup_method)
   technology_dict = {
      ('unknown','unknown'): ("unknown", None),
      ('unknown','single'): ("unknown", None),
      ('unknown','paired'): ("unknown", None),
      ('Illumina','unknown'): ("unknown", None),
      ('Illumina','single'): ("Illumina", set_cmd),
      ('Illumina','paired'): ("Paired_End_Reads",  set_cmd),
      ('Ion Torrent','unknown'): ("unknown", None),
      ('Ion Torrent','single'): ("Ion_Torrent", set_cmd, "--iontorrent"),
      ('Ion Torrent','paired'): ("Ion_Torrent_paired", set_cmd, "--iontorrent")
   }
   try: seq_tech, tech_setup = technology_dict[(
      args.sequencing_platform,args.sequencing_type)]
   except: debug.graceful_exit('Input Error: The sequencing platform or type '
                               'was not recognised!')

   
   # Check whether seq_tech is known
   debug.log(seq_tech)
   if seq_tech == 'unknown':
      debug.graceful_exit("Input Error: We cannot assemble sequences from "
                          "unkown platforms!\n")
   
   # Checking if the correct number of files were submitted
   check_correct_number_of_files(len(files), seq_tech)
   
   # Create assembly dir
   mkpath('output')
   
   # Set output file path
   output_file = "output/contigs.fasta"
   
   # Prepare program
   progname = 'spades'
   prog = Program(path='bin/spades.py',
      name=progname, wait=True,
      args=[]
      )
   proglist.add2list(prog)
   
   # Set up assembly parameters
   tech_setup(prog, seq_tech, files)
   # prog.append_args(['--n', '1'])
   
   # Execute program
   prog.execute()
   
   # THE SUCCESS OF THE ASSEMBLER IS VALIDATED
   status = prog.get_status()
   if status != 'Done':
      debug.graceful_exit("Error: Execution of the program failed!\n")
   
   # Copying assembler output to contig file path
   contigs_filename = '%s/contigs.fsa'%(os.getcwd())
   copy_file(output_file, contigs_filename)
   
   if os.path.exists(contigs_filename):
      # Sumarise Results
      results = { 'contigs_file': os.path.abspath(contigs_filename) }
      # Print json to stdout
      sys.stdout.write('%s\n'%json.dumps(results))
   else:
      debug.graceful_exit("Error: The Assembler was unable to produce contigs!"
                          "\n")
   
   # LOG THE TIMERS
   proglist.print_timers() 

def check_correct_number_of_files(file_count, seq_tech):
   ''' Checks wether or not the correct number of files have been submitted '''
   if file_count > 0:
      debug.log( "INPUT TYPE ::\t%s"%(seq_tech))
      if (seq_tech in ["Paired_End_Reads", "Ion_Torrent_paired"]
            and file_count != 2):
         debug.graceful_exit(("Input Error: Exactly 2 files are required, "
                              "but %d files were submitted!")%(file_count))
      elif seq_tech in ["Illumina", "Ion_Torrent"] and file_count > 1:
         debug.graceful_exit(("Input Error: Exactly 1 file is required, but %d "
                              "files were submitted!")%(file_count))
   else:
      debug.graceful_exit("Input Error: No files were uploaded!")

def set_cmd(prog, seq_tech, files):
   ''' This function will set the command for the illumina and iontorrent technology '''
   debug.log("Setting Assembly Command...")
   # Adding Arguments to the assembly command
   # prog.append_args(['-m', '4', '-t', '1', '--tmp-dir', 'spades_tmp'])
   prog.append_args(['-m', '4', '-t', '1'])
   if (seq_tech in ["Illumina", "Ion_Torrent"]):
      prog.append_args(['-s', files[0]])
   elif (seq_tech in ["Paired_End_Reads", "Ion_Torrent_paired"]):
      prog.append_args(['-1', files[0], '-2', files[1]])
   prog.append_args(['--careful', '-o', 'output'])

#def set_illumina_cmd(prog, seq_tech, files, trim_reads=False):
#   ''' This function will set the command for the illumina technology '''
#   debug.log("Setting Illumina Command...")
#   # Adding Arguments to the assembly command
#   if seq_tech == "Illumina": prog.append_args(['--short', 'fastq', files[0]])
#   elif seq_tech == "Paired_End_Reads":
#      prog.append_args(['--shortPaired', 'fastq', files[0], files[1]])
#      if trim_reads: prog.append_args([" --trim"])
#   prog.append_args(['--add_velvetg', '-very_clean yes', '--sample',
#                     'output']) # , '--wait'



#def set_454_cmd(prog, seq_tech, files, trim_reads=False):
#   ''' This function will set the command for the 454 technology '''
#   debug.log("Setting 454 Command...")
#   # Adding Arguments to the assembly command
#   prog.append_args(['newbler', '--datatype', '454'])
#   
#   if seq_tech=="454":
#      # Adding Arguments to the assembly command
#      prog.append_args(['--se', files[0]])
#   
#   elif seq_tech=="454_Paired_End_Reads":
#      #check the input files format and decide the order
#      files = ' '.join([x for x in files
#                        if x.replace('.gz', '').split('.')[-1] in [
#                           'fasta','fna','fa','fsa','fq','fastq','sff']
#                        ])
#      if files == '': # ERROR CHECK
#         debug.graceful_exit('Error: no compatible file uploaded\n')
#      
#      # Adding Arguments to the assembly command
#      prog.append_args(['--pe', files])
#   
#   # Adding Arguments to the assembly command
#   prog.append_args(['--sample', 'output']) #, '--wait'

#def set_ion_cmd(prog, seq_tech, files, trim_reads=False):
#   ''' This function will set the command for the Ion-Torrent technology '''
#   debug.log("Setting Ion Command...")
#   
#   # Adding Arguments to the assembly command
#   prog.append_args(['newbler', '--datatype', 'IonTorrent'])
#   
#   files = ' '.join([x for x in files
#                     if x.replace('.gz', '').split('.')[-1] in [
#                        'fq', 'fastq']
#                     ])
#   if files == "":
#      debug.graceful_exit("Error: no compatible file uploaded\n")
#   
#   # Adding Arguments to the assembly command
#   prog.append_args(['--se', files, '--sample', 'output']) # , '--wait'

if __name__ == '__main__':
   main()
