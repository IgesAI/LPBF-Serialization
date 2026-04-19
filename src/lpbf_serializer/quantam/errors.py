"""Exhaustive QuantAM error hierarchy.

Every failure mode the client can surface to callers is a subclass of
:class:`QuantAMError`. Callers catch the most specific class that matches
their response policy. There is no broad ``except Exception`` at the
caller boundary.
"""

from __future__ import annotations


class QuantAMError(Exception):
    """Base class for all QuantAM adapter errors."""


class QuantAMNotFoundError(QuantAMError):
    """QuantAM executable was not found at the configured path."""


class QuantAMVersionMismatchError(QuantAMError):
    """The installed QuantAM version does not match the expected version."""


class QuantAMLaunchError(QuantAMError):
    """QuantAM could not be launched or attached to."""


class QuantAMUnexpectedDialogError(QuantAMError):
    """An unexpected modal dialog blocked automation."""


class QuantAMExportFailedError(QuantAMError):
    """QuantAM did not produce a verifiable .mtt for the request."""


class QuantAMVerificationFailedError(QuantAMError):
    """The produced .mtt exists but does not match the request."""
