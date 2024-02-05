import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="firebase_user",
    version="0.0.21",
    author="Baptiste Ferrand",
    author_email="bferrand.maths@gmail.com",
    description="Client interface for the firebase REST API.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/B4PT0R/firebase_user",
    packages=setuptools.find_packages(),
    package_data={
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=[
        "objdict_bf",
        "requests"
    ],
    python_requires='>=3.6',
)
