#!/usr/bin/env python3
#
# WorkflowLogic - Simple generic workflow control
#
# Background
#
#   This module was factored out of the BAP code as it is essentially a generic
#   mechanism to generate a workflow of service invocations based on dependencies
#   between services.  The BAPWorkflow module specialises this module for (the
#   current version of) our Bacterial Analysis Pipeline.
#
# What this module does:
#
#   The central concepts are "params", "user targets", and "services".  Params are
#   flags that signify the presence of certain inputs.  User targets are end points
#   that the user is interested in.  Services are responsible for for attaining
#   targets, by consuming inputs and producing outputs.
#
#   Given a set of dependencies, a set of flags marking the user params that are
#   provided, and a list of desired user targets, this module produces a Workflow
#   object than can be queried for the services that need to be executed at any
#   point in the workflow.
#
#   A separate "workflow executor" performs the actual service invocations, and
#   reports outcomes back to the Workflow object.  The Workflow objects updates
#   its playlist of "runnable" services based on its current state. The process
#   repeats until the workflow as a whole has completed or failed.
#
# What this module contains:
#
#   The module defines the object types needed to define dependency rules:
#
#   - Base enum classes for the four target types: Params, UserTargets, Services,
#     Checkpoints.  These are the bases for defining application-specific enums;
#     see the BAPWorkflow module for the idea.
#
#   - Classes that implement CONNECTORS that describe dependencies: ALL (all
#     targets must be met), SEQ (all must be met in this order), ONE (at least
#     one must be met), OPT (target must optionally be met), OIF (must be met
#     only if its dependencies were met).
#
#   And it defines the Workflow object that holds the state for a specific run.
#
# Dependency rule specification:
#
#   The dependency rules for a specific pipeline (such as the BAP) are defined
#   simply by a dict whose keys are dependants and values are dependencies:
#
#   sample_deps = {
#     UserTargets.DEFAULT: ALL(UserTargets.SPECIES, UserTargets.MLST, UserTargets.RESISTANCE, ...),
#     UserTargets.SPECIES: Checkpoints.SPECIES,
#     UserTargets.RESISTANCE: ALL(Services.RESFINDER, OPT(Services.PointFinder))
#     Checkpoint.CONTIGS: ONE(Params.CONTIGS, Services.ASSEMBLER),
#     Checkpoint.SPECIES: ONE(Params.SPECIES, Services.KMERFINDER, Services.KCST),
#     Services.KMERFINDER: ONE(Params.READS, Checkpoint.CONTIGS),
#     Services.MLST: ALL(Checkpoints.SPECIES, ONE(Params.READS, Checkpoints.CONTIGS))
#     Services.RESFINDER: ONE(Params.READS, Checkpoints.CONTIGS)
#     ... 
#   }
#
# How to use the module:
#
#   Construct a workflow object, passing it the dependency dict and lists of
#   Params and UserTargets (see BAPWorkflow for a worked example):
#
#      w = Workflow(
#           sample_deps,            # the dependency dict as above 
#           [Params.READS],         # list of Params enums marking provided inputs
#           [UserTargets.DEFAULT]   # list of UserTargets to attain
#           [UserTargets.CGMLST])   # list of UserTargets a/o Services to exclude
#
#   Query it for its initial status and runnable services:
#
#      w.status()       # -> "Incomplete" (or "Done" or "Failed")
#      w.runnables()    # -> Services.KMERFINDER, Services.RESFINDER
#
#   The executor should tell w when it starts running a service:
#
#      w.mark_started(Services.KMERFINDER)
#      w.runnables()    # -> Services.RESFINDER
#    
#   When a service has completed, the executor should tell Workflow:
#
#      w.mark_completed(Services.KMERFINDER)
#      w.runnables()    # -> Services.MLST, Services.RESFINDER, Services.PointFinder ...
#
#   Note how the runnables() list now contains services that depend on SPECIES,
#   and hence had to wait for KmerFinder to complete.
#

import enum, functools, operator


### Target definitions
#
# This section defines the Params, Checkpoints, Services, and UserTargets base
# classes.  Derive from these to create constants for a specific pipeline.
#
# All bases derive from a common base 'Target'.  Through this common base class,
# all enums have a 'runnables()' method that returns their current dependencies,
# by looking these up in the dependency 'rule book', taking into account the
# services that are already done or wont be done.

class Target(enum.Enum): 
    '''The base enum for our five types of targets.'''

    def runnables(self, deps, done, wont):
        '''Return the runnables up to this target.  Runnables are those services
           that don't depend on prerequisites that have not yet run.
           Parameters: deps is the dict holding dependencies, done is the list of
           completed targets, wont is the list of unattainable targets.
           Return value: None if we or our dependencies fail, an empty list if we
           and our dependencies are already done; a list of runnables otherwise.'''
        if self in done:
            return list()
        elif self in wont or isinstance(self,Params):
            return None
        else: # Obtain the list of runnables we depend on recursively
            dep = deps.get(self, None)
            pre = dep.runnables(deps, done, wont) if dep else list()
            if pre is None: # our dependencies fail, so we fail
                return None
            if pre:         # we depend on runnables, so we return those
                return pre
            else:           # we are the single runnable if we are a service
                return [self] if isinstance(self, Services) else list()

# The four subclasses (enums) of Target

class Params(Target): pass
class Checkpoints(Target): pass
class Services(Target): pass
class UserTargets(Target): pass


### Target connectors
#
# This section defines the target connectors.  Like the Targets, each of these
# has a runnables() method that return the list of runnable services.

class Connector:
    '''Base class for the ALL, SEQ, ONE, etc connectors.'''

    def set_clauses(self, *clauses):
        '''Store the clauses on self, catering for both lists and tuples,
           and check that all clauses are either of Target or Connector type.'''
        self.clauses = tuple(clauses[0] if len(clauses) == 1 else clauses)
        for c in self.clauses: 
            assert isinstance(c,(Target,Connector))

class ALL(Connector):
    '''Connector with clauses that must all be met, in any order.'''

    def __init__(self, *clauses): 
        self.set_clauses(*clauses)

    def runnables(self, deps, done, wont):
        '''Return the union of the runnables across the clauses, as they can run
           in parallel, but fail with None if any clause fails with None.'''
        ret = list()
        for sub in self.clauses:
            add = sub.runnables(deps, done, wont)
            if add is None:
                return None
            else:
                ret.extend(filter(lambda s: s not in ret, add))
        return ret

class SEQ(Connector):
    '''Connector with clauses that must all be met, and in the specified order.'''

    def __init__(self, *clauses): 
        self.set_clauses(*clauses)

    def runnables(self, deps, done, wont):
        '''Return the runnables from the first clause that has any, but fail
           if any clause is bound to fail.'''
        ret = None
        for sub in self.clauses:
            run = sub.runnables(deps, done, wont)
            if run is None:
                return None
            elif not ret:
                ret = run
        return ret

class ONE(Connector):
    '''Connector with clauses of which at least one must to be met.'''

    def __init__(self, *clauses): 
        self.set_clauses(*clauses)

    def runnables(self, deps, done, wont):
        '''Return the runnables from the first non-failing clause, but succeed
           with empty list if any clause has no prerequisites at all.'''
        ret = None
        for sub in self.clauses:
            run = sub.runnables(deps, done, wont)
            if run is not None and not run:
                return list()
            if ret is None:
                ret = run
        return ret

class OPT(Connector):
    '''Unary connector whose clause will be tried but is allowed to fail.'''

    def __init__(self, clause):
        self.clause = clause
        assert isinstance(clause,(Target,Connector))

    def runnables(self, deps, done, wont):
        '''Return the runnables or empty list both when none or clause fails.'''
        run = self.clause.runnables(deps, done, wont)
        if run is None:
            run = list()
        return run

class OIF(Connector):
    '''Unary connector which succeeds only if its clause succeeds.'''

    def __init__(self, clause):
        self.clause = clause
        assert isinstance(clause,(Target,Connector))

    def runnables(self, deps, done, wont):
        '''Return empty list when clause has no runnables, else fail with None'''
        run = self.clause.runnables(deps, done, wont)
        if run is None or run:
            return None
        else:
            return list()


### Workflow Class 
#
#   This section defines the actual Workflow class.

class Workflow:

    class Status(enum.Enum):
        RUNNABLE = 'RUNNABLE'
        WAITING = 'WAITING'
        COMPLETED = 'COMPLETED'
        FAILED = 'FAILED'

    # Original user inputs
    _deps = dict()
    _params = set()
    _usertargets = set()
    _excludes = set()

    # Current state of affairs
    _status = None
    _runnable = None
    _started = set()
    _completed = set()
    _failed = set()

    # Construct and initialise
    def __init__(self,deps,params,targets,excludes):
        '''Construct Workflow instance with given dependency rules and params, to
           produce the list of targets.  The excludes argument is for preventing 
           some target or service from being completed.'''

        # Check the input types
        assert(all(map(lambda i: isinstance(i, Params), params)))
        assert(all(map(lambda t: isinstance(t, UserTargets), targets)))
        assert(all(map(lambda x: isinstance(x, (Services, UserTargets)), excludes)))

        # Store the original inputs
        self._deps = deps
        self._params.update(params)
        self._usertargets.update(targets)
        self._excludes.update(excludes)

        # Setup the initial completed and failed sets with the params and excludes
        self._completed.update(params)
        self._failed.update(excludes)

        # And reassess to update self's status
        self._reassess()

    # Update internal state
    def _reassess(self):
        '''Internal method that reassesses the current state of affairs.  Recomputes
           the runnable services, and updates the state lists and status field.'''

        # Collect the runnable services
        self._runnable = ALL(self._usertargets).runnables(self._deps, self._completed, self._failed)

        # If None then the user targets are not resolvable and workflow fails
        if self._runnable is None:
            self._runnable = list()
            self._status = Workflow.Status.FAILED
        else:
            # First remove any already running service from the runnables
            for s in self._started:
                if s in self._runnable:
                    self._runnable.remove(s)
            # If no runnable services then status depends on whether s/thing still running
            if not self._runnable:
                self._status = Workflow.Status.COMPLETED if not self._started else self.Status.WAITING
            # Runnable services present so the workflow is Incomplete
            else:
                self._status = Workflow.Status.RUNNABLE

    # Query methods for the state of the Workflow

    @property
    def status(self):
        '''Returns the workflow status as a Workflow.Status enum.'''
        return self._status

    def list_runnable(self):
        '''Returns the list of currently runnable (but not started) services.'''
        return list(self._runnable)

    def list_started(self):
        '''Returns the list of started (and assumed to be running) services.'''
        return list(self._started)

    def list_completed(self):
        '''Returns the list of successfully completed services.'''
        return list(filter(lambda t: isinstance(t, Services), self._completed))

    def list_failed(self):
        '''Returns the list of unsuccessfully completed services.'''
        return list(filter(lambda t: isinstance(t, Services), self._failed))

    # Update methods for the state of the Workflow

    def mark_started(self, service):
        '''Marks service as having moved from runnable to started.'''
        if service in self._runnable:
            self._runnable.remove(service)
            self._started.add(service)
            self._reassess()
        elif service in self._started:
            pass
        else:
            raise(ValueError("service is not runnable: %s" % service))

    def mark_completed(self, service):
        '''Marks service as having moved from runnable or started to completed.'''
        if service in self._runnable:
            self._runnable.remove(service)
        elif service in self._started:
            self._started.remove(service)
        else:
            raise(ValueError("service was not runnable or started: %s" % service))
        self._completed.add(service)
        self._reassess()

    def mark_failed(self, service):
        '''Marks service as having moved from runnable or started to failed.'''
        if service in self._runnable:
            self._runnable.remove(service)
        elif service in self._started:
            self._started.remove(service)
        else:
            raise(ValueError("service was not runnable or started: %s" % service))
        self._failed.add(service)
        self._reassess()

