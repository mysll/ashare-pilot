"""Public exception hierarchy for expected A-Share Pilot failures."""


class ASharePilotError(Exception):
    """Base class for expected failures exposed by public APIs."""


class WorkspaceError(ASharePilotError):
    """Raised when an A-Share Pilot workspace cannot be resolved."""
