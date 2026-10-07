"""Host trust is checked before authentication and preserved across reconnects."""

from unittest.mock import Mock, patch

import pytest

pytest.importorskip("fsspec")
pytest.importorskip("paramiko")

from paramiko import AutoAddPolicy, RSAKey, SSHException

from quackframe.sql_functions.register_filesystem.sftp import (
    FingerprintPolicy,
    SerializedSFTPFileSystem,
)


@pytest.mark.parametrize("fingerprint", [None, "", "  "])
def test_missing_fingerprint_retains_automatic_acceptance(
    fingerprint: str | None,
) -> None:
    with (
        patch("quackframe.sql_functions.register_filesystem.sftp.SSHClient") as client,
        patch("quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPClient"),
    ):
        SerializedSFTPFileSystem(
            "files.test", host_key_fingerprint=fingerprint, skip_instance_cache=True
        )
    policy = client.return_value.set_missing_host_key_policy.call_args.args[0]
    assert isinstance(policy, AutoAddPolicy)
    client.return_value.connect.assert_called_once_with("files.test")


@pytest.mark.parametrize("fingerprint", ["MD5:invalid", "SHA256:short", "invalid"])
def test_malformed_fingerprint_fails_before_connecting(fingerprint: str) -> None:
    with (
        patch("quackframe.sql_functions.register_filesystem.sftp.SSHClient") as client,
        pytest.raises(ValueError, match="SHA256"),
    ):
        SerializedSFTPFileSystem(
            "files.test", host_key_fingerprint=fingerprint, skip_instance_cache=True
        )
    client.assert_not_called()


def test_policy_accepts_only_matching_server_key() -> None:
    key = RSAKey.generate(2048)
    FingerprintPolicy(key.fingerprint).missing_host_key(Mock(), "files.test", key)
    with pytest.raises(SSHException, match="does not match"):
        FingerprintPolicy("SHA256:" + "A" * 43).missing_host_key(
            Mock(), "files.test", key
        )


@pytest.mark.parametrize("failure", ["connect", "transport", "channel"])
def test_failed_reconnect_preserves_original_pair(failure: str) -> None:
    fingerprint = "SHA256:" + "A" * 43
    original, replacement = Mock(), Mock()
    original_ftp = Mock()
    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SSHClient",
            side_effect=[original, replacement],
        ),
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPClient"
        ) as sftp,
    ):
        sftp.from_transport.return_value = original_ftp
        filesystem = SerializedSFTPFileSystem(
            "files.test", host_key_fingerprint=fingerprint, skip_instance_cache=True
        )
        if failure == "connect":
            replacement.connect.side_effect = SSHException("host-key rejected")
        elif failure == "transport":
            replacement.get_transport.return_value = None
        else:
            sftp.from_transport.return_value = None
        with pytest.raises((SSHException, RuntimeError)):
            filesystem._connect()  # pyright: ignore[reportPrivateUsage]

    assert filesystem.client is original
    assert filesystem.ftp is original_ftp
    original.close.assert_not_called()
    original_ftp.close.assert_not_called()
    replacement.close.assert_called_once()
    for client in (original, replacement):
        policy = client.set_missing_host_key_policy.call_args.args[0]
        assert isinstance(policy, FingerprintPolicy)
        assert policy.fingerprint == fingerprint


@pytest.mark.parametrize("channel_close_fails", [False, True])
def test_successful_reconnect_closes_superseded_pair(channel_close_fails: bool) -> None:
    original, replacement = Mock(), Mock()
    original_ftp, replacement_ftp = Mock(), Mock()
    if channel_close_fails:
        original_ftp.close.side_effect = OSError("channel close failed")
    with (
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SSHClient",
            side_effect=[original, replacement],
        ),
        patch(
            "quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPClient"
        ) as sftp,
    ):
        sftp.from_transport.side_effect = [original_ftp, replacement_ftp]
        filesystem = SerializedSFTPFileSystem("files.test", skip_instance_cache=True)
        original.close.assert_not_called()
        original_ftp.close.assert_not_called()
        if channel_close_fails:
            with pytest.raises(OSError, match="channel close failed"):
                filesystem._connect()  # pyright: ignore[reportPrivateUsage]
        else:
            filesystem._connect()  # pyright: ignore[reportPrivateUsage]

    assert filesystem.client is replacement
    assert filesystem.ftp is replacement_ftp
    original_ftp.close.assert_called_once()
    original.close.assert_called_once()
    replacement.close.assert_not_called()
    replacement_ftp.close.assert_not_called()
