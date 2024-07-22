#!/usr/bin/env python3
#
# kcri.bap.shims.VirulenceFinder - service shim to the VirulenceFinder backend
#

import os, json, logging, tempfile
from pico.workflow.executor import Task
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException
from .versions import BACKEND_VERSIONS

# Our service name and current backend version
SERVICE, VERSION = "VirulenceFinder", BACKEND_VERSIONS['virulencefinder']

# Backend resource parameters: cpu, memory, disk, run time
MAX_CPU = 1
MAX_MEM = 1
MAX_TIM = 10 * 60


class VirulenceFinderShim:
    '''Service shim that executes the backend.'''

    def execute(self, sid, xid, blackboard, scheduler):
        '''Invoked by the executor.  Creates, starts and returns the Task.'''

        execution = VirulenceFinderExecution(SERVICE, VERSION, sid, xid, blackboard, scheduler)

        # Get the execution parameters from the blackboard
        try:
            db_path = execution.get_db_path('virulencefinder')
            params = [
                '-q',
                '-p', db_path,
#               '-db_vir_kma', db_path,
                '-t', execution.get_user_input('vf_i'),
                '-l', execution.get_user_input('vf_c'),
                '--overlap', execution.get_user_input('vf_o'),
                '-j', 'virulencefinder.json',
                '-o', '.' ]

            # Append files, backend has different args for fq and fa
            illufqs = execution.get_illufq_paths(list())
            if illufqs:
                params.append('-ifq')
                params.extend(illufqs)
            elif execution.get_contigs_path(""):
                params.extend(['-ifa', os.path.abspath(execution.get_contigs_path())])
            elif execution.get_nanofq_path(""):
                params.extend(['--nanopore', '-ifq', execution.get_nanofq_path()])
            else: # expect the unexpected
                raise UserException("no input data to analyse")

            search_list = list(filter(None, execution.get_user_input('vf_s', '').split(',')))
            if search_list:
                params.extend(['-d', ','.join(search_list)])

            execution.start(db_path, params, search_list)

        # Failing inputs will throw UserException
        except UserException as e:
            execution.fail(str(e))

        # Deeper errors additionally dump stack
        except Exception as e:
            logging.exception(e)
            execution.fail(str(e))

        return execution


class VirulenceFinderExecution(ServiceExecution):
    '''A single execution of the service, returned by the shim's execute().'''

    _service_name = 'virulencefinder'
    _search_dict = None
    _tmp_dir = None
    _job = None

    # Start the execution on the scheduler
    def start(self, db_path, params, search_list):
        '''Start a job for virulencefinder, with the given parameters.'''

        cfg_dict = parse_config(db_path)
        self._search_dict = find_databases(cfg_dict, search_list)

        job_spec = JobSpec('virulencefinder', params, MAX_CPU, MAX_MEM, MAX_TIM)
        self.store_job_spec(job_spec.as_dict())

        if self.state == Task.State.STARTED:
            self._tmp_dir = tempfile.TemporaryDirectory()
            job_spec.args.extend(['--tmp_dir', self._tmp_dir.name])
            self._job = self._scheduler.schedule_job('virulencefinder', job_spec, 'VirulenceFinder')

    # Collect the output produced by the backend service and store on blackboard
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        # Clean up the tmp dir used by backend
        self._tmp_dir.cleanup()
        self._tmp_dir = None

        res_out = dict()

        out_file = job.file_path('virulencefinder.json')
        try:
            with open(out_file, 'r') as f: json_in = json.load(f)
        except Exception as e:
            logging.exception(e)
            self.fail('failed to open or load JSON from file: %s' % out_file)
            return

        # VirulenceFinder since 3.0 has standardised JSON with these elements
        # that it shares with ResFinder:
        # - seq_regions (loci with virulence-associated genes or mutations)
        # - seq_variations (mutations keying into seq_regions)
        # - phenotypes (virulence, keying into above)

        # We include these but change them from objects to lists, so this:
        #   'seq_regions' : { 'XYZ': { ..., 'key' : 'XYZ', ...
        # becomes:
        #   'seq_regions' : [ { ..., 'key' : 'XYZ', ... }, ...]
        # This is cleaner design (they have list semantics, not object), and
        # avoids issues downstream with keys containing JSON delimiters.

        for k, v in json_in.items():
            if k in ['seq_regions','seq_variations','phenotypes']:
                res_out[k] = [ o for o in v.values() ]
            else:
                res_out[k] = v

        # Helpers to retrieve gene names g for regions r causing phenotype p
        r2g = lambda r: json_in.get('seq_regions',{}).get(r,{}).get('name')
        p2gs = lambda p: filter(None, map(r2g, p.get('seq_regions', [])))

        # Store the virulence genes for the detected phenotypes for the summary output
        # Note that a lot more information is present, including PMIDs and notes
        for p in res_out.get('phenotypes', []):
            for g in p2gs(p): self._blackboard.add_detected_virulence_gene(g)

        # Store on the blackboard
        self.store_results(res_out)


# Parse the config file into a dict of group->[database], or raise on error.
# Error includes the case where we find the same database (prefix) in two groups.
# Though this could theoretically be allowed, we error out as the backend doesn't
# (currently) handle this correctly: it counts the database in the first group only.

def parse_config(db_root):

    group_dbs = dict()
    databases = list()

    cfg = os.path.join(db_root, "config")
    if not os.path.exists(cfg):
        raise UserException('database config file missing: %s', cfg)

    with open(cfg) as f:
        for l in f:

            l = l.strip()
            if not l or l.startswith('#'): continue
            r = l.split('\t')
            if len(r) != 3:
                raise UserException('invalid database config line: %s', l)

            # See comment above, this should be possible in principle, but backend fails
            db = r[0].strip()
            if db in databases:
                raise UserException('non-unique database prefix in config: %s', db)
            databases.append(db)

            grp = r[1].strip()
            group_dbs[grp] = group_dbs.get(grp, []) + [db]

    return group_dbs


# Returns user-friendly string of databases (per group) from parsed config

def pretty_list_groups(cfg_dict):
    ret = ""
    for k, v in cfg_dict.items():
        ret += '%s (%s);' % (k, ', '.join(v))
    return ret

# If name matches a group, return tuple (group, [databases]) for that group,
# else if it matches a database inside some group, return (group, [name]),
# else error with the list of available groups and databases.

def find_database(cfg_dict, name):
    grp_dbs = cfg_dict.get(name)
    if grp_dbs is None:
        for grp in cfg_dict.keys():
            if name in cfg_dict.get(grp):
                return (grp,[name])
        raise UserException('unknown group or database: %s; available are: %s',
            name, pretty_list_groups(cfg_dict))
    else:
        return (name, grp_dbs)

# Return a dict group->[database] for the list of names.  Each name can name
# a group or database, as for find_database above.  If names is an empty list,
# returns the entire cfg_dict.

def find_databases(cfg_dict, names):
    db_dict = dict()
    for name in (names if names else cfg_dict.keys()):
        grp, dbs = find_database(cfg_dict, name)
        cur_dbs = db_dict.get(grp, [])
        for db in dbs:
            if db not in cur_dbs: cur_dbs.append(db)
        db_dict[grp] = cur_dbs
    return db_dict

