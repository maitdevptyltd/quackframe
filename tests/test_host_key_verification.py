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


def test_reconnect_keeps_fingerprint_and_failed_check_closes_client() -> None:
    key = RSAKey.generate(2048)
    with (
        patch("quackframe.sql_functions.register_filesystem.sftp.SSHClient") as client,
        patch("quackframe.sql_functions.register_filesystem.sftp.SerializedSFTPClient"),
    ):
        filesystem = SerializedSFTPFileSystem(
            "files.test", host_key_fingerprint=key.fingerprint, skip_instance_cache=True
        )
        client.return_value.connect.side_effect = SSHException("host-key rejected")
        with pytest.raises(SSHException):
            filesystem._connect()  # pyright: ignore[reportPrivateUsage]
        policies = client.return_value.set_missing_host_key_policy.call_args_list
        assert len(policies) == 2
        for call in policies:
            assert isinstance(call.args[0], FingerprintPolicy)
            assert call.args[0].fingerprint == key.fingerprint
        client.return_value.close.assert_called_once()
