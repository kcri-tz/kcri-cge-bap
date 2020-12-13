#!/usr/bin/env python3
#
# cge.flow.jobcontrol.subproc
#
#   Defines SubprocessScheduler and SubprocessJob.  This scheduler takes a JobSpec
#   and, depending on available resources, queues or spawns a system process using
#   the Python subprocess (Popen) mechanism.  It returns a SubprocessJob.
#
#   To keep life simple the implementation is single-threaded and uses polling.
#   Its usage pattern is as follows (see also the main() function below):
#
#   Create a scheduler instance:
#
#       js = SubprocessScheduler([resource-limits])
#
#   Submit any number of jobs:
#
#       for job in jobs-to-do:
#           js.schedule_job(name, jobspec, [wdir])
#
#   Then listen() on the scheduler:
#
#       while js.listen():
#           iterate over the job results
#           submit more jobs
#
#   The listen() periodically polls each job, which in turn polls its backend
#   process, and updates its status (QUEUED -> RUNNING -> COMPLETED|FAILED).
#
#   Listen() returns True if any job completed or failed, and False if no more jobs
#   are QUEUED or RUNNING.
#
#   The module has a main() function which can be used for simple CLI testing:
#
#       python3 -m cge.flow.jobcontrol.subproc --help
#       python3 -m cge.flow.jobcontrol.subproc sleep $((RANDOM / 1000))
#

import os, sys, psutil, time
from subprocess import Popen, DEVNULL
from datetime import datetime, timedelta
from .job import JobSpec, Job


### SubprocessJob
#
#   Backend job returned by SubprocessScheduler, based on Python's subprocess.Popen.

class SubprocessJob(Job):
    '''Backend job built on Python's Popen, starts an async system process.
       Inherits state and error properties from superclass Job, which also holds
       the JobSpec argument passed in the constructor.'''

    _name = None
    _wdir = None

    _proc = None
    _fout = None
    _ferr = None
    _deadline = None
    _ret_code = None

    def __init__(self, name, spec, wdir=None):
        super().__init__(spec)
        self._name = name
        self._wdir = wdir if wdir else '.'

    @property
    def name(self):
        return self._name

    @property
    def ret_code(self):
        '''The return code of the backend, None if still running.'''
        return self._ret_code

    @property
    def stdout(self):
        '''The name of the stdout file of the process.'''
        return os.path.join(self._wdir, self._name + '.out')

    @property
    def stderr(self):
        '''The name of the stderr file of the process.'''
        return os.path.join(self._wdir, self._name + '.err')

    def file_path(self, path):
        '''Return the path to path taking into account work dir.'''
        return os.path.join(self._wdir, path)

    def start(self):
        '''Setup and start a queued job, raise exception on failure.'''
        assert self.state == Job.State.QUEUED, "job must be queued to start"
        try:
            cmd = [ self.spec.command ] + list(map(lambda x: str(x), self.spec.args))
            os.makedirs(self._wdir, exist_ok = True)
            self._fout = open(self.stdout, 'w')
            self._ferr = open(self.stderr, 'w')
            self._deadline = datetime.now() + timedelta(seconds=self.spec.tim) if self.spec.tim else None
            self._proc = Popen(cmd, cwd=self._wdir, stdin=DEVNULL, stdout=self._fout, stderr=self._ferr)
            self._state = Job.State.RUNNING
        except Exception as e:
            if self._fout: self._fout.close()
            if self._ferr: self._ferr.close()
            self.fail(str(e))

    def poll(self):
        '''Check the job status at the backend and report it back.
           Terminate the backend job if it has exceeded its run time.'''
        if self.state == Job.State.RUNNING:
            ret_code = self._proc.poll()
            if ret_code is not None: # None means running
                self._ret_code = ret_code
                self._fout.close()
                self._ferr.close()
                if ret_code == 0:
                    self._state = Job.State.COMPLETED
                else:
                    self.fail('backend run failed, check its error log: %s', self.stderr)
            elif self._deadline and datetime.now() > self._deadline:
                self.stop('job exceeded its allowed run time (%ds)' % self.spec.tim)
        return self._state

    def stop(self, fail_msg):
        '''If job is QUEUED or RUNNING, dequeue or terminate it and set FAILED.'''
        if self._state == Job.State.QUEUED:
            self.fail('job did not run: %s', fail_msg)
        elif self._state == Job.State.RUNNING:
            self._proc.terminate()
            self._ret_code = -1
            self._fout.close()
            self._ferr.write('Error: job aborted: %s\n' % fail_msg)
            self._ferr.close()
            self.fail('job aborted: %s', fail_msg)


### SubprocessScheduler 
#
#   SubprocessScheduler spawns a SubprocessJob, a system command that runs in its
#   own process, using Python's Popen mechanism.

class SubprocessScheduler:
    '''Class that runs backend jobs, constrained by cpu, memory, disc space, and
       run time limits.  Its listen() method periodically polls the backend
       processes, and returns if any job has changed state.  When it returns false,
       no more jobs are QUEUED or RUNNING.'''

    _poll_interval = 5
    _quiet = True

    _tot_cpu = None     # count
    _tot_mem = None     # GB
    _tot_spc = None     # GB
    _tot_tim = None     # seconds

    _free_cpu = None
    _free_mem = None
    _free_spc = None
    _deadline = None

    _jobs = dict()
    _dirty = True


    def __init__(self, tot_cpu = None, tot_mem = None, tot_spc = None, tot_tim = None,
                 poll_interval = 5, quiet = True):
        '''Initialise the job scheduler with the given total number of processors,
           GB of memory, GB of disc space, and seconds of total wall clock run time.
           Defaults are: all cpu's, 90% of memory, 80% of disk space, unlimited time.
           The poll_interval is the time between backend polls in listen().
           Unset quiet to get updates written to stderr.'''

        self._tot_cpu = self._free_cpu = (tot_cpu if tot_cpu else psutil.cpu_count())
        self._tot_mem = self._free_mem = (tot_mem if tot_mem else 0.9 * psutil.virtual_memory().total / 10.0**9)
        self._tot_spc = self._free_spc = (tot_spc if tot_spc else 0.8 * psutil.disk_usage(os.getcwd()).free / 10.0**9)
        self._tot_tim = tot_tim
        self._poll_interval = poll_interval
        self._quiet = quiet
        self.emit('job scheduler started')

    @property
    def max_cpu(self):
        return self._tot_cpu

    @property
    def max_mem(self):
        return self._tot_mem

    def schedule_job(self, name, spec, wdir=None):
        '''Return scheduled job with unique identifier name, according to JobSpec
           spec, and running in wdir (default pwd).'''

        # Job names must be unique within the scheduler.
        if self._jobs.get(name):
            raise ValueError('not a unique job name: %s' % name)

        # If this is the first job scheduled, start clock for overall deadline
        if not self._jobs and self._tot_tim:
            self._deadline = datetime.now() + timedelta(seconds = self._tot_tim)
            self.emit('deadline: %s', self._deadline.isoformat(timespec='seconds'))

        # Create the job instance; currently we have just the subprocess
        job = SubprocessJob(name, spec, wdir)
        self._jobs[name] = job

        # If the job doesn't exceed the overall maxima, try start it
        if job.spec.cpu > self._tot_cpu or job.spec.mem > self._tot_mem or job.spec.spc > self._tot_spc:
            job.fail('job requirements exceed available system resources')
        else:
            self.try_start(job)

        # Mark dirty if the job is done already, so next listen() returns immediately
        self._dirty = self._dirty or job.state in [ Job.State.COMPLETED, Job.State.FAILED ]
        
        self.emit('job schedule: %s -> %s', job.name, job.state.value)

        return job


    def listen(self):
        '''Block until a job becomes COMPLETED/FAILED and return True, or return
           False if no more jobs are QUEUED/RUNNING.'''

        # Poll until we become dirty or no QUEUED/RUNNING jobs are left
        while not self._dirty \
              and any(j.state in [ Job.State.QUEUED, Job.State.RUNNING ]
                      for j in self._jobs.values()):
            
            # Sleep till next poll due and poll all jobs
            time.sleep(self._poll_interval)
            self.poll()

            # Terminate if scheduler exceeds its total run time
            if self._deadline and datetime.now() > self._deadline:
                self.stop('scheduler total run time (%ds) exceeded' % self._tot_tim)

        # Return the value of the dirty flag and unset it for the next listen.
        ret = self._dirty
        self._dirty = False

        self.emit('job listen: -> %s', ret)
        return ret


    def try_start(self, job):
        '''Start QUEUED job if its requirements are currently met.'''

        if job.spec.cpu <= self._free_cpu and job.spec.mem <= self._free_mem and job.spec.spc <= self._free_spc:
            job.start()
            if job.state == Job.State.RUNNING:
                self._free_cpu -= job.spec.cpu
                self._free_mem -= job.spec.mem
                self._free_spc -= job.spec.spc
            else: # mark ourselves dirty as a job has FAILED/COMPLETED
                self._dirty = True
            self.emit('job start: %s -> %s', job.name, job.state.value)


    def poll(self):
        '''Poll all RUNNING jobs and update their status, starting QUEUED jobs if
           resources have become available.'''

        for job in filter(lambda j: j.state == Job.State.RUNNING, self._jobs.values()):
            new_state = job.poll()
            if new_state != Job.State.RUNNING:
                self.emit('job poll: %s -> %s', job.name, new_state.value)
                self._free_cpu += job.spec.cpu
                self._free_mem += job.spec.mem
                self._free_spc += job.spec.spc
                self._dirty = True

        # If we became dirty, resources have been freed so try starting queued jobs
        if self._dirty:
            for job in filter(lambda j: j.state == Job.State.QUEUED, self._jobs.values()):
                self.try_start(job)


    def stop(self, fail_msg):
        '''Stop the scheduler, stopping all scheduled and running jobs in FAILED
           state with fail_msg as their error.'''

        self.emit('job stop: %s', fail_msg)

        for j in self._jobs.values():
            j.stop(fail_msg)

        self._dirty = True


    def emit(self, fmt, *args):
        '''Send string to stderr if we are not quiet.'''

        n_in_state = lambda s: sum(map(lambda x: x.state == s, self._jobs.values()))

        if not self._quiet:
            print('log:',  (fmt % args), 
                '[queue=%d running=%d done=%d fail=%d cpu=%d/%d mem=%d/%d spc=%d/%d]' % (
                    n_in_state(Job.State.QUEUED),
                    n_in_state(Job.State.RUNNING),
                    n_in_state(Job.State.COMPLETED),
                    n_in_state(Job.State.FAILED),
                    (self._tot_cpu - self._free_cpu), self._tot_cpu,
                    (self._tot_mem - self._free_mem), self._tot_mem,
                    (self._tot_spc - self._free_spc), self._tot_spc),
                file=sys.stderr, flush=True)

### MAIN
#
#   The main() function can be used for CLI testing of the job scheduler. For instance:
#
#   Do a simple 'ls -l' (needs the -- due to Python's non-POSIX option parsing):
#
#       python3 -m cge.flow.jobcontrol.subproc -- ls -l    # output will be in job.out
#
#   Run three parallel replicates of a sleep job in /tmp, polling each second:
#
#       time python3 -m cge.flow.jobcontrol.subproc -p 1 -r 3 -w /tmp -- sleep 2
#       # time will show about 2 seconds
#
#   Now force them sequential by limiting available CPU's to 1
#
#       time python3 -m cge.flow.jobcontrol.subproc --tot-cpu=1 -p 1 -r 3 -w /tmp -- sleep 2
#       # time now shows about 6 seconds
#
#   To see that happening in more detail (and with 5 jobs), set the verbose flag:
#
#       time python3 -m cge.flow.jobcontrol.subproc -v --tot-cpu=1 -p 1 -r 5 -w /tmp -- sleep 2
#
#   Fail due to scheduler total run time limit:
#
#       python3 -m cge.flow.jobcontrol.subproc --tot-tim 5 sleep 12
#
#   Fail single job due to it exceeding its run time limit
#
#       python3 -m cge.flow.jobcontrol.subproc -p 1 -t 3 sleep 5
#       cat job.err   # has an error message
#
#   Try to schedule a job exceeding system memory:
#
#       python3 -m cge.flow.jobcontrol.subproc -m 10000 -- ls
#
#   Verbosely run five replicates running for different times:
#
#       python3 -m cge.flow.jobcontrol.subproc -v -p 1 -w /tmp -r 5 -- \
#           bash -c 'S=$((RANDOM / 1000)); echo "Sleeping ${S}s"; sleep $S'
#       cat /tmp/job-*/*.{out,err}
#
#   And try this with an 8s time limit on each job
#
#       python3 -m cge.flow.jobcontrol.subproc -v -p 1 -w /tmp -r 5 -t 8 -- \
#           bash -c 'S=$((RANDOM / 1000)); echo "Sleeping ${S}s"; sleep $S'
#       cat /tmp/job-*/*.{out,err}


if __name__ == '__main__':

    import sys, argparse, textwrap

    def print_state(jobs):
        job_list = lambda state: ','.join(j.name for j in jobs if j.state == state)
        print('job_scheduler_cli: Q[%s] R[%s] C[%s] F[%s]' % (
            job_list(Job.State.QUEUED),
            job_list(Job.State.RUNNING),
            job_list(Job.State.COMPLETED),
            job_list(Job.State.FAILED)), file=sys.stderr, flush=True)

    parser = argparse.ArgumentParser(
        description=textwrap.dedent("""\
            JobSchedulerCLI is a simple command-line tester of the JobScheduler.
            It runs COUNT replicates of CMD with ARGS, taking into account CPU,
            memory and disc space constraints.
            The job is run in subdirectory NAME, or in arbitrary directory WDIR
            when specified with -w/--wdir.  When there are multiple replicates,
            they run in NAME-{1..COUNT} resp. WDIR-{1..COUNT}.
            The files NAME.out and NAME.err collect the stdout and stderr of the
            job.
        """))
    parser.add_argument('-n', '--name', metavar='NAME', default='job', help="base name of the job to run [job]")
    parser.add_argument('-r', '--replicates', metavar='COUNT', default=1, help="number of replicates to start")
    parser.add_argument('-w', '--wdir', metavar='WDIR', default='.', help="work dir base name to run job in [.]")
    parser.add_argument('-c', '--cpu', metavar='N', default=1, help="CPUs required by job [1]")
    parser.add_argument('-m', '--mem', metavar='GB', default=1, help="GB memory required by job [1]")
    parser.add_argument('-s', '--spc', metavar='GB', default=1, help="GB disc space required by job [1]")
    parser.add_argument('-t', '--tim', metavar='SECS', default=600, help="Maximum job runtime in seconds [600]")
    parser.add_argument('--tot-cpu', metavar='N', type=int, default=None, help="number of CPUs to allocate")
    parser.add_argument('--tot-mem', metavar='GB', type=int, default=None, help="GB of memory to allocate")
    parser.add_argument('--tot-spc', metavar='GB', type=int, default=None, help="GB of disc space to allocate")
    parser.add_argument('--tot-tim', metavar='SECS', type=int, default=None, help="Maximum total wall clock run time")
    parser.add_argument('-p', '--poll', metavar='SECS', type=int, default=1, help="seconds between backend polls [1]")
    parser.add_argument('-v', '--verbose', action='store_true', help="do not output scheduler verbose output")
    parser.add_argument('cmd', metavar='COMMAND', nargs=1, help="command to run, must be absolute or on the path")
    parser.add_argument('args', metavar='ARGS', nargs='*', default=[], help="arguments to the command")

    args = parser.parse_args()

    # Create the JobScheduler
    
    js = SubprocessScheduler(args.tot_cpu, args.tot_mem, args.tot_spc, args.tot_tim, args.poll, not args.verbose)
    jobs = []

    # Schedule the jobs

    jobspec = JobSpec(args.cmd[0], args.args, int(args.cpu), int(args.mem), int(args.spc), int(args.tim))

    if args.replicates == 1:
        jobs.append(js.schedule_job(args.name, jobspec, args.wdir))
    else:
        for r in range(1,int(args.replicates)+1):
            name = '%s-%d' % (args.name, r)
            wdir = os.path.join(args.wdir, name)
            jobs.append(js.schedule_job(name, jobspec, wdir))

    # Run the JobScheduler until done

    while js.listen():
        if args.verbose:
            print_state(jobs)

    # Show the end results
    for j in jobs:
        print('- %s: %s%s' % (j.name, j.state.value, ': ' + j.error if j.error else ''))

    # Exit code is the number of FAILED jobs (0 is success)

    n_fail = sum(map(lambda j: j.state == Job.State.FAILED, jobs))
    sys.exit(n_fail)

