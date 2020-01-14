from setuptools import setup, find_packages

setup(
    name='one_s',
    version='1.0',
    packages=find_packages(),
    url='https://github.com/trubinov/one_s',
    license='no-license',
    author='trubinov',
    author_email='mrtrubinov@gmail.com',
    description='Work with 1C Application and Storage',
    long_description=open("README.md", "r", encoding='utf8').read(),
    long_description_content_type="text/markdown",
    install_requires=[
        'lxml>=4.4.2'
    ]
)
