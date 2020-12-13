#!/usr/bin/env python3
#
# cge.flow.workflow.executor - manages the execution of a Workflow
#
# Background
#
#   The Workflow and Executor classes were factored out of BAP.py when its
#   execution logic became too unwieldy.  They are simple implementations
#   of a generic workflow definition language and execution engine.
#
#   This module defines the Executor and Execution classes.  The Execution
#   is intended to be subclassed by each backend-specific shim.  The sub
#   classes must implement its report() method.
#
# How it works:
#
#   An Executor instance controls a single run of a pipeline from start to end.
#   It does this by starting services according to the state of a workflow,
#   encapsulated in the cge.flow.workflow.logic.Workflow object passed to it.
#
#   At any time, the Workflow will indicate which services are 'runnable'. The
#   executor then invokes the execute() method on the service, passing in the
#   blackboard and job scheduler.  The service returns an Execution object that
#   the executor monitors.
#
#   The Executor polls the scheduler, which polls the backends, for their actual
#   status, and updates the Workflow accordingly when they complete or fail.  The
#   Workflow object will then present new runnable services, until the execution
#   as a whole has completed or failed.
#
#   The implementation is poll-based because the legacy backends run as async
#   processes.  The Python docs warn against combining threads and processes,
#   otherwise a thread & event model would be better.  Polling frequency is set
#   in the JobScheduler.
#
# Conceptual mode of use:
#
#      blackboard = workflow.blackboard.Blackboard()
#      blackboard['inputs'] = { 'contigs': /path/to/inputs, ... }
#      workflow = workflow.logic.Workflow(deps, inputs, targets)
#      executor = workflow.executor.Executor(workflow, services, scheduler)
#
#      status = executor.execute(blackboard)
#      assert status == workflow.status        
#      results = blackboard.get(...)           
#

import enum
from cge.flow.workflow.logic import Workflow, Services as ServicesEnum


### class Execution
#
#   Base class for the service executions, i.e. objects returned from the shims'
#   execute() method.  Subclasses must implement its report() method to retrieve
#   the backend status and output, and wrangle this on to the black board.

class Execution:
    '''Base class for a single service execution, maintains the execution state.'''

    class State(enum.Enum):
        STARTED = 'STARTED'
        COMPLETED = 'COMPLETED'
        FAILED = 'FAILED'

    _state = None
    _ident = None
    _error = None

    def __init__(self, ident):
        '''Return a execution with the given execution id, which is the
           key it must report its results under.  Its state is None.'''
        self._ident = ident

    @property
    def ident(self):
        return self._ident

    @property
    def state(self):
        '''Current state of the Execution, an Execution.State value.'''
        return self._state

    @property
    def error(self):
        '''May hold an error string if the execution failed.'''
        return self._error

    def report(self):
        '''Pure virtual, here to signal that subclasses must implement this.'''
        raise NotImplementedError()

    def fail(self, err_fmt, *args):
        '''Transition this execution to FAILED and set its error message.
           Invokes self._transition(Execution.State.FAILED, err_fmt % args),
           which will conveniently be the subclass method if overridden.'''
        return self._transition(Execution.State.FAILED, err_fmt % args)

    def done(self):
        '''Mark this execution COMPLETED.
           Invokes self._transition(Execution.State.COMPLETED), which will
           conveniently be the subclass method if overridden .'''
        return self._transition(Execution.State.COMPLETED)

    def _transition(self, new_state, error = None):
        '''Update execution state to new_state, setting the error iff the new
           state is FAILED, intended for subclasses to extend.'''

        if new_state == Execution.State.FAILED and not error:
            raise ValueError('FAILED execution %s must set its error' % self.ident)

        self._state = new_state
        self._error = error if new_state == Execution.State.FAILED else None

        return new_state


### class Executor
#
#  Executes a Workflow. 

class Executor:
    '''Runs a Workflow from start to end, using a list of Service implementations.'''

    _workflow = None
    _services = None
    _scheduler = None

    _blackboard = None          # The data exchange mechanism between the services
    _executions = dict()        # Holds the running and completed service executions


    def __init__(self, workflow, services, scheduler):
        '''Construct executor instance to execute the given workflow using the given
           services (a dict of id -> WorkflowService mappings).'''

        # Type check our arguments to avoid confusion
        assert isinstance (workflow, Workflow)
        for k,v in services.items():
            assert isinstance(k, ServicesEnum)
            assert hasattr(v, 'execute')

        self._workflow = workflow
        self._services = services
        self._scheduler = scheduler


    def execute(self, blackboard):
        '''Execute the workflow.'''

        # Create the blackboard for communication between services
        self._blackboard = blackboard
        self._blackboard.log("execution starting")

        # Obtain the status of the Workflow object to control our execution
        wf_status = self._workflow.status
        self._blackboard.log("workflow status: %s", wf_status.value)
        assert wf_status != Workflow.Status.WAITING, "no services were started yet"

        # We run as long as there are runnable or running services in the Workflow
        while wf_status in [ Workflow.Status.RUNNABLE, Workflow.Status.WAITING ]:

            # Check that the Workflow and our idea of runnable and running match
            self.assert_cross_check()
            more_jobs = True

            # Pick the first runnable off the runnables list, if any
            runnable = self._workflow.list_runnable()
            if runnable:
                # Look up the service and start it
                svc_ident = runnable[0]
                self.start_service(svc_ident)

            else:
                # Nothing runnable, wait on the scheduler for job to end
                more_jobs = self._scheduler.listen()

                # Update all started executions with job state
                for svc_id, execution in self._executions.items():
                    if execution.state == Execution.State.STARTED:
                        self.poll_service(svc_id)

            # Update our status by querying the Workflow
            old_wf_status, wf_status = wf_status, self._workflow.status
            if old_wf_status != wf_status:
                self._blackboard.log("workflow status: %s", wf_status.value)

            # Defensive programming: if scheduler has no more job but we think we
            # are still WAITING we would get into a tight infinite loop
            if not more_jobs and wf_status == Workflow.Status.WAITING:
                raise Exception('fatal inconsistency between workflow and scheduler')

        # Workflow is done, log result
        str_done = ', '.join(map(lambda s: s.value, self._workflow.list_completed()))
        str_fail = ', '.join(map(lambda s: s.value, self._workflow.list_failed()))
        self._blackboard.log("workflow execution completed")
        self._blackboard.log("- done: %s", str_done if str_done else "(none)")
        self._blackboard.log("- failed/excluded: %s", str_fail if str_fail else "(none)")

        return wf_status


    def start_service(self, svc_id):
        '''Start the execution of a service.  Actual startup should be asynchronous,
           but the service shim will return a state we use to update our status.'''

        service = self._services.get(svc_id)
        if not service:
            raise ValueError("no implementation for service id: %s" % svc_id.value)

        self._blackboard.log("service start: %s" % svc_id.value)

        execution = service.execute(svc_id.value, self._blackboard, self._scheduler)
        self._executions[svc_id] = execution
        self.update_state(svc_id, execution.state)


    def poll_service(self, svc_id):
        '''Poll the service for its current status.  This is a non-blocking call on
           the execution to check whether the backend is done, failed, running.'''

        execution = self._executions.get(svc_id)
        if not execution:
            raise ValueError("no execution for service id: %s" % svc_id.value)

        old_state = execution.state
        new_state = execution.report()

        if new_state != old_state:
            self.update_state(svc_id, new_state)


    def update_state(self, svc_id, state):
        '''Update the executing/ed service and workflow with new state.'''

        self._blackboard.log("service state: %s %s", svc_id.value, state.value)
        if state == Execution.State.STARTED:
            self._workflow.mark_started(svc_id)
        elif state == Execution.State.COMPLETED:
            self._workflow.mark_completed(svc_id)
        elif state == Execution.State.FAILED:
            self._workflow.mark_failed(svc_id)
        else:
            raise ValueError("invalid service state for %s: %s" % (svc_id.value, state))


    def assert_cross_check(self):
        '''Cross check that the state maintained in Workflow matches the state of
           the services our executions.'''

        for r in self._workflow.list_runnable():
            assert r not in self._executions

        for r in self._workflow.list_started():
            assert self._executions[r].state == Execution.State.STARTED
        for r in self._workflow.list_failed():
            assert r not in self._executions or self._executions[r].state == Execution.State.FAILED
        for r in self._workflow.list_completed():
            assert r not in self._executions or self._executions[r].state == Execution.State.COMPLETED

        for j in self._executions.keys():
            state = self._executions[j].state
            if state == Execution.State.STARTED:
                assert j in self._workflow.list_started()
            elif state == Execution.State.FAILED:
                assert j in self._workflow.list_failed()
            elif state == Execution.State.COMPLETED:
                assert j in self._workflow.list_completed()
            else:
                assert False, "not a valid state"

