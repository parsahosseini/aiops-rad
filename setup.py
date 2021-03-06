from setuptools import setup


setup(
    name="rad",
    version="0.9.6",
    description="AI-Ops Red Hat Anomaly Detection (RAD)",
    author="Parsa Hosseini, Ph.D.",
    author_email="phossein@redhat.com",
    url="https://github.com/ManageIQ/aiops-rad",
    packages=["rad"],
    install_requires=["numpy>=1.14",
                      "scipy",
                      "matplotlib",
                      "pandas",
                      "pyarrow",
                      "s3fs",
                      "urllib3<1.25,>=1.20"],
    tests_require=['pytest',
                   'pytest-cov'],
    setup_requires=["pytest-runner"],
)
