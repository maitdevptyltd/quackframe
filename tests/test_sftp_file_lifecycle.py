"""Direct fsspec handles close through the serialized, acknowledged path."""

from threading import RLock
from typing import Any, cast
from unittest.mock import Mock, patch

import pytest

pytest.importorskip("fsspec")
pytest.importorskip("paramiko")

from paramiko.sftp import CMD_CLOSE

from quackframe.sql_functions.register_filesystem.sftp import (
    SerializedSFTPFile,
    SerializedSFTPFileSystem,
)


@pytest.mark.parametrize("body_fails", [False, True])
@pytest.mark.parametrize("close_fails", [False, True])
def test_direct_fsspec_context_closes_and_preserves_primary_failure(
    body_fails: bool, close_fails: bool
) -> None:
    file = Mock(closed=False)
    ftp = Mock()
    ftp._exchange_lock = RLock()
    ftp.open.return_value = file
    if close_fails:
        ftp._request.side_effect = OSError("close rejected")
    with (
        patch("quackframe.sql_functions.register_filesystem.sftp.SSHClient"),
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPClient"
        ) as sftp,
    ):
        sftp.from_transport.return_value = ftp
        filesystem = SerializedSFTPFileSystem("files.test", skip_instance_cache=True)

    def write_in_context() -> None:
        with cast(Any, filesystem).open("/report.csv", "wb") as handle:
            assert isinstance(handle, SerializedSFTPFile)
            handle.write(b"header\n")
            if body_fails:
                raise ValueError("write failed")

    if body_fails:
        with pytest.raises(ValueError, match="write failed"):
            write_in_context()
    elif close_fails:
        with pytest.raises(OSError, match="close rejected"):
            write_in_context()
    else:
        write_in_context()

    file.write.assert_called_once_with(b"header\n")
    file.flush.assert_called_once()
    ftp._request.assert_called_once_with(CMD_CLOSE, file.handle)
    assert file._closed is True
    file.close.assert_not_called()
