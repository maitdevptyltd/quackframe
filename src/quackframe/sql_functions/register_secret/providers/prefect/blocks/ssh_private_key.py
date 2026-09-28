"""Compatibility imports for the shared credential provider."""

from quackframe.credential_providers.prefect.blocks.ssh_private_key import (
    SshPrivateKeyCredentials,
)

__all__ = ["SshPrivateKeyCredentials"]
