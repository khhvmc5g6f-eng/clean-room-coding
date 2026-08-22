"""Part LXXXIV: predictable, documented exit codes for CI/CD consumption."""

from enum import IntEnum


class ExitCode(IntEnum):
    PASS = 0
    GENERAL_FAILURE = 1
    CONFIGURATION_ERROR = 2
    POLICY_FAILURE = 3
    CONTAMINATION_FAILURE = 4
    LICENCE_FAILURE = 5
    TEST_FAILURE = 6
    SIMILARITY_FAILURE = 7
    LEGAL_RED = 8
    MANUAL_REVIEW_REQUIRED = 9


class CleanRoomError(Exception):
    """Base error carrying the exit code the CLI should return."""

    exit_code: ExitCode = ExitCode.GENERAL_FAILURE

    def __init__(self, message: str, exit_code: ExitCode | None = None):
        super().__init__(message)
        if exit_code is not None:
            self.exit_code = exit_code


class ConfigurationError(CleanRoomError):
    exit_code = ExitCode.CONFIGURATION_ERROR


class PolicyFailure(CleanRoomError):
    exit_code = ExitCode.POLICY_FAILURE


class ContaminationFailure(CleanRoomError):
    exit_code = ExitCode.CONTAMINATION_FAILURE


class LicenceFailure(CleanRoomError):
    exit_code = ExitCode.LICENCE_FAILURE


class TestFailure(CleanRoomError):
    exit_code = ExitCode.TEST_FAILURE


class SimilarityFailure(CleanRoomError):
    exit_code = ExitCode.SIMILARITY_FAILURE


class LegalRed(CleanRoomError):
    exit_code = ExitCode.LEGAL_RED


class ManualReviewRequired(CleanRoomError):
    exit_code = ExitCode.MANUAL_REVIEW_REQUIRED
