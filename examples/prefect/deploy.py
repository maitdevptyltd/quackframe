"""Register a deployment using a project-owned, prebuilt image."""

from prefect.types.entrypoint import EntrypointType

from quackframe.integrations.prefect import quackframe_flow

if __name__ == "__main__":
    quackframe_flow.deploy(
        name="daily-reporting",
        work_pool_name="analytics",
        image="your-registry/reporting:1.0.0",
        build=False,
        push=False,
        entrypoint_type=EntrypointType.MODULE_PATH,
        parameters={"sql_files": ["sql/prepare.sql", "sql/report.sql"]},
    )
