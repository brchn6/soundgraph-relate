from setuptools import setup, find_packages

setup(
    name="soundgraph-relate",  # You can change this to match your project name
    version="0.1",
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    install_requires=[
        # List your dependencies here, for example:
        "requests",
        "tenacity",
        "ratelimit",
        "psycopg2-binary",
        "pandas",
        "pyarrow",
        "sqlalchemy",
        "pyyaml",
        "loguru"
        # Add other required libraries here
    ],
)
