"""The agent harness: context, the run loop, authorization, budget and tracing.

It is generic; agents are thin. The harness owns everything the model must not: tenancy, tool
dispatch, authorization, budget enforcement, structured-output parsing and persistence.
"""
