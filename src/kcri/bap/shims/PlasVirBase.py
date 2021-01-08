#!/usr/bin/env python3
#
# kcri.bap.shims.PlasVirBase - common functionality of Plasmid- and VirulenceFinder
#
#   The PlasmidFinder and VirulenceFinder classes have backends that operate
#   almost identically.  The PlasVirBaseExecution class herein captures this.

import os, json, tempfile
from pico.workflow.executor import Execution
from pico.jobcontrol.job import JobSpec, Job
from .base import ServiceExecution, UserException

# Backend resource parameters: cpu, memory, disk, run time
MAX_CPU = 1
MAX_MEM = 1
MAX_SPC = 1
MAX_TIM = 10 * 60

# The shared base class of the VirulenceFinder and PlasmidFinder execution
class PlasVirBaseExecution(ServiceExecution):
    '''Base class for VirulenceFinderExecution and PlasmidFinderExecution.'''

    _service_name = None
    _search_dict = None
    _tmp_dir = None
    _job = None

    # Start the execution on the scheduler
    def start(self, svc_name, db_path, params, search_list, work_dir):
        '''Start a job for svc_name (virulence|plasmid)finder, with the given
           parameters work_dir.'''

        self._service_name = svc_name
        exe_name = svc_name + '.py'
        job_name = svc_name

        cfg_dict = parse_config(db_path)
        self._search_dict = find_databases(cfg_dict, search_list)

        job_spec = JobSpec(exe_name, params, MAX_CPU, MAX_MEM, MAX_SPC, MAX_TIM)
        self.store_job_spec(job_spec.as_dict())

        if self.state == Execution.State.STARTED:
            self._tmp_dir = tempfile.TemporaryDirectory()
            job_spec.args.extend(['--tmp_dir', self._tmp_dir.name])
            self._job = self._scheduler.schedule_job(job_name, job_spec, work_dir)

    # Collect the output produced by the backend service and store on blackboard
    def collect_output(self, job):
        '''Collect the job output and put on blackboard.
           This method is called by super().report() once job is done.'''

        # Clean up the tmp dir used by backend
        self._tmp_dir.cleanup()
        self._tmp_dir = None

        # Load the JSON and obtain the 'results' element.
        out_file = job.file_path('data.json')
        try:
            with open(out_file, 'r') as f: json_in = json.load(f)
        except:
            self.fail('failed to open or load JSON from file: %s' % out_file)
            return

        # JSON can be string "No hits found" we turn into an empty dict, or otherwise
        # a dict whose keys are the group names (column 2 in the config), with as value
        # a dict whose keys are the db names (col 1 in the config), with as value
        # a dict whose keys are the hit_ids (QUERY_CONTIG:QRY_POS..QRY_POS:TARGET_CTG:SCORE"), with as value
        # a dict having the fields we need
        # ... but we deconvolve all this for uniformity

        res_in = json_in.get(self._service_name, {}).get('results')
        if res_in is None:
            self.fail('no %s/results element in data.json' % self._service_name)
            return

        if type(res_in) is not dict: # fix backend's "No hits found" to be {}
            res_in = dict()

        # Make res_out a list of result objects, one per database that a search was
        # requested for (even if no results).  So we iterate over the search_dict
        # and pull results from res_in, rather than vice versa.
        # Also we change the group and db names from key to values.

        res_out = list()
 
        # Iterate over the groups and their databases search was requested for
        for grp, dbs in self._search_dict.items():

            dbs_in = res_in.get(grp, dict())
            dbs_in = dbs_in if type(dbs_in) is dict else dict()
            dbs_out = list()

            for db in dbs:

                hits_in = dbs_in.get(db, dict())
                hits_in = hits_in if type(hits_in) is dict else dict()
                hits_out = list()

                for hit in hits_in.values():

                    # Let the subclass do its specific work
                    h_out = self.process_hit(hit)

                    # Add the common fields to the dict
                    h_out.update({
                        'hit_id':     hit['hit_id'],
                        'group':      grp,
                        'database':   db,
                        'qry_ctg':    hit['contig_name'],
                        'qry_pos':    hit['positions_in_contig'],
                        'tgt_acc':    hit['accession'],
                        'tgt_len':    hit['template_length'],
                        'tgt_pos':    hit['position_in_ref'],
                        'hsp_len':    hit['HSP_length'],
                        'pct_cov':    hit['coverage'],
                        'pct_ident':  hit['identity'],
                        'quality':    hit['coverage'] * hit['identity'] / 100.0,
                        'note':       hit['note']
                        })

                    # Append the hit to the output list
                    hits_out.append(h_out)
     
                # Sort the hit list by descending goodness, and store under key db in dbs_out
                hits_out.sort(key=lambda l: l['quality'], reverse=True)
                dbs_out.append({ 'database': db, 'hits': hits_out })

            # Put the dbs_out object under key grp in the res_out object
            res_out.append({ 'group': grp, 'searches': dbs_out })

        # Store the results on the blackboard
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

