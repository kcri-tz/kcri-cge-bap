#!/usr/bin/env python3
'''
################################################################################
##########                    CGE Service Wrapper                    ###########
################################################################################
'''
import sys, os, argparse, json, tempfile, datetime
from cgecore import (check_file_type, debug, proglist, Program)
import cgetools.SKESA

# SET GLOBAL VARIABLES, will be updated by update-service-versions.sh
service, version = "Assembler", "2.0"

# Available options
platform_choices = [ 'Illumina', 'LS454', 'SOLiD', 'IonTorrent' ]
pairing_choices = [ 'paired', 'single', 'mate-paired' ]
trim_choices = [ 'yes', 'no' ]
backend_choices = [ 'SKESA', 'SPAdes' ]

# Convert sequencing information to our sequencing schemas
# (plat, type): (seq_tech, setup_method)
technology_dict = {
    ('Illumina','single'): ("Illumina_SE", None),
    ('Illumina','paired'): ("Illumina_PE", None),
#    ('LS454','single'): ("454_SE", set_454_cmd),
#    ('LS454','paired'): ("454_PE", set_454_cmd),
#    ('SOLiD','single'): ("SOLiD_SE", set_solid_cmd),
#    ('SOLiD','paired'): ("SOLiD_PE", set_solid_cmd),
#    ('SOLiD','mate-paired'): ("SOLiD_MP", set_solid_cmd),
#    ('IonTorrent','single'): ("IonTorrent", set_ion_cmd),
}


def main():

    # Keep timestamps for output of datetimes
    start_time = datetime.datetime.now()

    # Parse arguments

    parser = argparse.ArgumentParser(description="CGE Assembler Service")
    parser.add_argument('-s', '--seq_platform', metavar='PLATFORM', required=True, choices=platform_choices, help="sequencing platform")
    parser.add_argument('-r', '--read_pairing', metavar='PAIRING', required=True, choices=pairing_choices, help="read pairing")
    parser.add_argument('-t', '--trim', metavar='TRIM', choices=trim_choices, help="set to override the default for BACKEND")
    parser.add_argument('-b', '--backend', metavar='BACKEND', help="set to override the default assembler backend")
    parser.add_argument('--version', action='version', version='%s %s' % (service, version), help="show program version")
    parser.add_argument('files', nargs='+', default=[], help="input file(s), optionally gzipped")
    args = parser.parse_args()

    # Validate arguments

    files = list()
    for f in args.files:
        if not os.path.exists(f):
            debug.graceful_exit("no such file: %s\n"%(f))
        files.append(os.path.abspath(f))

    seq_tech = None
    try: 
        seq_tech, setup_fn = technology_dict[(args.seq_platform,args.read_pairing)]
        debug.log("seq_tech: %s" % seq_tech)
    except: 
        debug.graceful_exit('combination of sequencing platform and read pairing not supported')
    
    backend = None
    if args.backend:
        backend = args.backend
    elif seq_tech in ["Illumina_SE","Illumina_PE"]:
        backend = 'SKESA'
    else:
        backend = 'SPAdes'
    debug.log("backend: %s" % backend)

    trim_reads = None
    if args.trim is None:
        if backend == 'SKESA':
            trim_reads = False
        elif backend == 'SPAdes':
            trim_reads = True
        else:
            trim_reads = False

    # Set up result object

    result = {
        'run_info': {
            'service': service,
            'version': version,
            'time': {
                'start': start_time.isoformat(timespec='seconds'),
                'end': start_time.isoformat(timespec='seconds'),
                'duration': 0
                },
            },
        'user_input': {
            'platform': args.seq_platform,
            'pairing': args.read_pairing,
            'backend': args.backend if args.backend else 'default (%s)' % backend,
            'trim': args.trim if args.trim is not None else 'default (%s)' % 'yes' if trim_reads else 'no',
            'files': args.files
            }
        }

    # Run the trimmer (@TODO@: IMPLEMENT)

    if trim_reads:
        # java -jar /path/to/trimmomatic.jar \
        # Illumina_PE, Illumina_SE, other
        debug.graceful_exit("Error: Assembler cannot yet do trimming\n")

    # Run the backed

    status = 'Failure'
    errors = list()

    if backend == 'SKESA':

        # We run SKESA component directly (no dispatch)
        outfile = os.path.abspath('contigs.fna')
        output = cgetools.SKESA.run(files, bool(seq_tech == 'Illumina_PE'), outfile)
        if 'results' in output:
            status = 'Done'
            result['results'] = output.get('results')
        else:
            result['errors'] = output.get('errors',[]).append("%s: backend %s failed" % (service,backend))

    elif backend == 'SPAdes':
        result['errors'] = ["Execution of SPAdes failed: not implemented"]
    else:
        result['errors'] = ["Execution of backend failed: not implemented: %s" % backend]

    # Add the status and timing info to the result object
    end_time = datetime.datetime.now()
    result['run_info']['time']['end'] = end_time.isoformat(timespec='seconds')
    result['run_info']['time']['duration'] = (end_time - start_time).total_seconds()
    result['run_info']['status'] = status

    # Dump the result to stdout

    json.dump(result, sys.stdout)

    # Return standard exit code

    return int(status != 'Done')


#
# ALL BELOW CURRENTLY UNUSED! ##############################################################################
#
    
def check_correct_number_of_files(file_count, seq_tech):
    ''' Checks wether or not the correct number of files have been submitted '''
    if file_count > 0:
        debug.log( "INPUT TYPE ::\t%s"%(seq_tech))
        if seq_tech in ["Illumina_PE", "SOLiD_SE"] and file_count != 2:
            debug.graceful_exit(("Input Error: Exactly 2 files are required, "
                                     "but %d files were submitted!")%(file_count))
        elif (seq_tech in ["SOLiD_MP", "SOLiD_PE"]
                and file_count != 4):
            debug.graceful_exit(("Input Error: Exactly 4 files are required, "
                                     "but %d files were submitted!")%(file_count))
        elif seq_tech in ["Illumina_SE", "454_SE"] and file_count > 1:
            debug.graceful_exit(("Input Error: Exactly 1 file is required, but %d "
                                     "files were submitted!")%(file_count))
    else:
        debug.graceful_exit("Input Error: No files were uploaded!")

def set_solid_cmd(prog, seq_tech, files, trim_reads=False):
    ''' This function will set the command for the SOLiD technology '''
    debug.log("Setting SOLiD Command...")
    # Adding Arguments to the assembly command
    prog.append_args(['solid'])
    
    r3 = r3q = f3 = f3q = f5 = f5q = "NA"
    f3_found = f3q_found = r3_found = r3q_found = f5q_found = f5_found = False
    genome_size = "5000000"
    
    if seq_tech=="SOLiD_SE": # SINGLE END SOLID
        if len(files) < 2:
            debug.graceful_exit("Input Error: At least 2 files are needed to SOLiD"
                                    " SE assembly\n")
        # now I have look for the quality ".qual" file and for the read ".csfasta"
        for index, el in enumerate(files):
            tmp_type = identify_solid_file_type(files[index])
            debug.log("FILE INDEX AND TYPE:\t"+ str(index) +" "+ tmp_type) 
            if tmp_type == "F3":
                if f3_found:
                    debug.graceful_exit("Error: More than one SOLiD read of type F3"
                                          " uploaded\n")
                f3_found = True
                f3 = files[index]
            elif tmp_type == "F3q":
                if f3q_found:
                    debug.graceful_exit("Error: More than one quality file of type"
                                          " F3 uploaded\n")
                f3q_found = True
                f3q = files[index]
        if f3 == "NA" or f3q == "NA":
            debug.graceful_exit("Error: quality file or read file not found\n")
        
        # Adding Arguments to the assembly command
        prog.append_args(['--se', f3, f3q])
    
    elif seq_tech=="SOLiD_PE": # PAIRED END SOLID
        if len(files) < 4:
            debug.graceful_exit("Error: less than four files uploaded\n")
        # now I have look for the quality ".qual" file and for the read ".csfasta"
        for index, el in enumerate(files):
            tmp_type = identify_solid_file_type(files[index])
            debug.log("FILE INDEX AND TYPE:\t%s %s"%(index, tmp_type))
            if tmp_type == "F3":
                if f3_found:
                    debug.graceful_exit("Error: more than one SOLiD read of type F3"
                                          " uploaded\n")
                f3_found = True
                f3 = files[index]
            elif tmp_type == "F3q":
                if f3q_found:
                    debug.graceful_exit("Error: more than one quality file of type "
                                          "F3 uploaded\n")
                f3q_found = True
                f3q = files[index]
            elif tmp_type == "F5":
                if f5_found:
                    debug.graceful_exit(("Error: more than one SOLiD read of type %s"
                                           " uploaded\n")%(tmp_type))
                f5_found = True
                f5 = files[index]
            elif tmp_type == "F5q":
                if f5q_found:
                    debug.graceful_exit(("Error: more than one SOLiD quality file of"
                                           " type %s uploaded\n")%(tmp_type))
                f5q_found = True
                f5q = files[index]
        if f3 == "NA" or f3q == "NA" or f5 == "NA" or f5q == "NA":
            debug.graceful_exit("Error: quality file or read file not found\n")
        
        # Adding Arguments to the assembly command
        prog.append_args(['--pe', f3, f3q, f5, f5q])
    
    elif seq_tech=="SOLiD_MP": # MATE PAIRED SOLID
        if len(files) < 4:
            debug.graceful_exit("Error: less than four files uploaded\n")
        # now I have look for the quality ".qual" file and for the read ".csfasta"
        for index, el in enumerate(files):
            tmp_type = identify_solid_file_type(files[index])
            debug.log("FILE INDEX AND TYPE:\t%s %s"%(index, tmp_type))
            if tmp_type == "F3":
                if f3_found:
                    debug.graceful_exit("Error: more than one SOLiD read of type F3"
                                          " uploaded\n")
                f3_found = True
                f3 = files[index]
            elif tmp_type == "F3q":
                if f3q_found:
                    debug.graceful_exit("Error: more than one quality file of type "
                                          "F3 uploaded\n")
                f3q_found = True
                f3q = files[index]
            elif tmp_type == "R3":
                if r3_found:
                    debug.graceful_exit(("Error: more than one SOLiD read of type %s"
                                           " uploaded\n")%(tmp_type))
                r3_found = True
                r3 = files[index]
            elif tmp_type == "R3q":
                if r3q_found:
                    debug.graceful_exit(("Error: more than one SOLiD quality file of"
                                           " type %s uploaded\n")%(tmp_type))
                r3q_found = True
                r3q = files[index]
        if f3 == "NA" or f3q == "NA" or r3 == "NA" or r3q == "NA":
            debug.graceful_exit("Error: quality file or read file not found\n")
        prog.append_args(['--mp', f3, f3q, r3, r3q])
    
    # Adding Arguments to the assembly command
    prog.append_args(['--rf', genome_size, '--sample', 'output',
                            '--add_solid', '\\"-NO_CORRECTION -NO_ANALYSIS\\"']) # , '--wait'

def identify_solid_file_type(fil):
    '''  '''
    debug.log("identifyFileType::START\nINPUT FILE: %s"%(fil))
    if not os.path.isfile(fil):
        debug.graceful_exit("Error: %s is not a valid file\n"%(fil))
    f_type = "NA" # it can f3q, f3, f5q, f5, r3q, r3
    tmp_type = ""
    # now we can open and nalyse the file
    with open(fil, "r") as fd:
        # we expect the files to have an ">" like fasta files and have a specific
        # two-characters at the and of the header, as follows
        #>...F3 -> F3 (SE) ".csfasta" or ".qual" file
        #>...F5 -> F5 (PE) ".csfasta" or ".qual" file
        #>...R3 -> R3 (Mate pairs) ".csfasta" or ".qual" file 
        #let's now analyse the file
        for index, line in enumerate(fd):
            if line[0] == ">": # then it is the header
                splitted = line.split("_")
                tmp_type = splitted[len(splitted)-1].strip() # get the type of file
            else: # then it is a line of the read or the quality file
                # if there are white-spaces it is a quality file otherwise it is a
                # read
                splitted = line.split(" ")
                if len(splitted) > 1: # then it is a quality file
                    f_type = tmp_type + "q"
                else:
                    f_type = tmp_type
            if f_type != "NA": # then we are done and can exit the for loop
                break
    
    debug.log("f_type :: %s\nidentifyFileType::END"%(f_type))
    return f_type

def set_454_cmd(prog, seq_tech, files, trim_reads=False):
    ''' This function will set the command for the 454 technology '''
    debug.log("Setting 454 Command...")
    # Adding Arguments to the assembly command
    prog.append_args(['newbler', '--datatype', '454'])
    
    if seq_tech=="454_SE":
        # Adding Arguments to the assembly command
        prog.append_args(['--se', files[0]])
    
    elif seq_tech=="454_PE":
        #check the input files format and decide the order
        files = ' '.join([x for x in files
                               if x.replace('.gz', '').split('.')[-1] in [
                                  'fasta','fna','fa','fsa','fq','fastq','sff']
                               ])
        if files == '': # ERROR CHECK
            debug.graceful_exit('Error: no compatible file uploaded\n')
        
        # Adding Arguments to the assembly command
        prog.append_args(['--pe', files])
    
    # Adding Arguments to the assembly command
    prog.append_args(['--sample', 'output']) #, '--wait'

def set_ion_cmd(prog, seq_tech, files, trim_reads=False):
    ''' This function will set the command for the Ion-Torrent technology '''
    debug.log("Setting Ion Command...")
    
    # Adding Arguments to the assembly command
    prog.append_args(['newbler', '--datatype', 'IonTorrent'])
    
    files = ' '.join([x for x in files
                            if x.replace('.gz', '').split('.')[-1] in [
                               'fq', 'fastq']
                            ])
    if files == "":
        debug.graceful_exit("Error: no compatible file uploaded\n")
    
    # Adding Arguments to the assembly command
    prog.append_args(['--se', files, '--sample', 'output']) # , '--wait'


if __name__ == '__main__':
    main()
