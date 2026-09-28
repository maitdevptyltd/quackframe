"""Compatibility imports for shared credential providers."""

from quackframe.credential_loading.providers.prefect.blocks import (
    AzureConnectionStringCredentials as AzureConnectionStringCredentials,
)
from quackframe.credential_loading.providers.prefect.blocks import (
    AzureManagedIdentityCredentials as AzureManagedIdentityCredentials,
)
from quackframe.credential_loading.providers.prefect.blocks import (
    MssqlCredentials as MssqlCredentials,
)
from quackframe.credential_loading.providers.prefect.blocks import (
    SshPrivateKeyCredentials as SshPrivateKeyCredentials,
)
