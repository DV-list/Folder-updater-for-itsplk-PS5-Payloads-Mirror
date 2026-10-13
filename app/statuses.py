"""Shared status identifiers used by reconciliation, services, and presentation.

Keeping the identifiers in a dependency-light module prevents presentation code from
importing a service implementation merely to compare status values.
"""

CURRENT = "CURRENT"
UPDATE_AVAILABLE = "UPDATE AVAILABLE"
UNMATCHED = "UNMATCHED"
SERVER_UNAVAILABLE = "SERVER UNAVAILABLE"
REMOVED_FROM_SERVER = "REMOVED FROM SERVER"
MANUAL = "MANUAL"
CONTROL_APP_DOWNLOAD = "DOWNLOAD"
