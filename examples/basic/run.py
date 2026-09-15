"""Run the basic SQL example through Quackframe's proposed Python API."""

from quackframe import run


result = run(["sql/hello.sql"])
print(result)
