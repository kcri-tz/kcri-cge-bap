# KCRI CGE Bacterial Analysis Pipeline (BAP)


## Introduction

The KCRI CGE Bacterial Analysis Pipeline (BAP) is the standard analysis
pipeline for bacterial genomics at Kilimanjaro Clinical Research Institute
(KCRI).  The BAP is developed in collaboration with the Centre for Genomic
Epidemiology (CGE) at the Technical University of Danmark (DTU).

The BAP orchestrates a standard workflow that processes sequencing reads
or contigs and produces the following:

 * Genome assembly (optional) (SKESA, SPAdes)
 * QC of reads and assembly (Quast)
 * Species identification (KmerFinder, KCST)
 * MLST (KCST, MLSTFinder)
 * Resistance profiling (ResFinder, PointFinder)
 * Virulence gene finding (VirulenceFinder)
 * Plasmid detection and typing (PlasmidFinder, pMLST)
 * Core genome MLST (optional) (cgMLST)

The BAP comes with sensible default settings and a standard workflow, but
can be configured with command line parameters.


#### Examples

Default run on a genome assembly:

    BAP assembly.fna

Same but on paired-end Illumina reads:

    BAP read_1.fq.gz read_2.fq.gz

Same but also produce the assembled genome:

    BAP -t DEFAULT,assembly read_1.fq.gz read_2.fq.gz

Note that when omitted, the `-t/--target` parameter has value `DEFAULT`.
This implies species, resistance, plasmids, virulence, and metrics.

Perform _only_ assembly (by omitting the DEFAULT target):

    BAP -t assembly read_1.fq.gz read_2.fq.gz

See what targets (values for the `-t` parameter) are available:

    BAP --list-targets
    -> metrics assembly species mlst resistance virulence plasmids ...

> Note that the targets are 'logical' names for what the BAP must do.
> The BAP will determine which services to involve, in what order, and
> what alternatives to try if a service fails.

Specific parameters can be passed to services in the pipeline.  For
instance, to change the identity and coverage thresholds for ResFinder:

    BAP --rf-i=0.95 --rf-c=0.8 assembly.fna

For an overview of all available parameters, use `--help`:

    BAP --help


## Installation

The BAP was developed to run on a moderately high-end Linux workstation
(see [history](#history-and-credits) below).  It is most easily installed
in a Docker container, but could also be set up in a Conda environment.


### Installation - Docker Image

Test that Docker is installed

    docker version
    docker run hello-world

Build the CGE Tools Docker image

    # Clone and enter this repository
    git clone https://github.com/zwets/kcri-cge-bap.git
    cd kcri-cge-bap

    # Download backend repositories and tarballs
    scripts/update-backend.sh

    # Build the CGETools docker image
    docker build -t kcri-cge-bap "." | tee Docker.build.log

Smoke test

    # Run 'BAP --help' in the container, using the bin/BAP wrapper
    # (Setting set BAP_DB_DIR to a dummy as we have no databases yet)

    BAP_DB_DIR=/tmp bin/BAP --help

Index the test databases

    # This uses the kma_index and kcst indexers in the freshly built
    # container to index all test/databases/*:

    test/databases/index-databases.sh

Maiden run against the test databases:

    # Test run BAP on an assembled sample genome
    test/test-01-fa.sh

    # Test run BAP on paired-end sample reads
    test/test-02-fq.sh

    # Same but additionally do assembly
    test/test-03-asm.sh


### Installation - CGE Databases

In the previous step we tested against the miniature test databases that
come with this repository.  In this step we install the real databases.

> NOTE: The download can take a _lot_ of time.  The KmerFinder and cgMLST
> databases in particular are huge.  It is possible to run the BAP without
> these, with some loss of functionality.  The BAP will use KCST to predict
> species (after assembly, because it runs against contigs only), but will
> not return a closest reference, and is limited to species for which an MLST
> scheme exists (KCST does species detection and MLST in one step).

Clone the CGE database repositories:

    # Pick your own location for installing the databases,
    # and set BAP_DB_DIR to its *absolute* path.
    BAP_DB_DIR=/data/genomics/cge/db   # your path here

    # Create the base directory and run the clone script
    mkdir -p "$BAP_DB_DIR"
    scripts/clone-databases.sh "$BAP_DB_DIR"

You now have databases for all services except but KmerFinder and cgMLST.
To download those, follow the instructions in their repositories.

Index the databases:

    @TODO@: adjust the test database index script to work for both

Run test against the real databases:

    # With BAP_DB_DIR pointing at the installed databases
    test/test-04-fa-live.sh
    test/test-05-fq-live.sh


## Usage

If you have set `BAP_DB_DIR` in `bin/bap-container-run`, you are all set
to go.

#### Points to remember when running the BAP container

* The container expects to find the databases mounted at `/databases`.  The
  `bin/BAP` and `bin/bap-container-run` scripts mount `$BAP_DB_DIR` at that
  mount point.  Set `BAP_DB_DIR` in `bin/bap-container-run`.

* The container expects a writeable work directory mounted at `/workdir`.
  The `bin/BAP` and `bin/bap-container-run` scripts mount `$PWD` there, as
  the user would expect.  For special use cases, this can be overridden by
  environment variable `BAP_WORK_DIR`.

* Keep in mind that inside the container, only paths inside the work dir
  can be seen.  This means that:
  * Input files must be located in or below the work directory
  * Relative paths to input files are interpreted relative to the work dir
  * Output will be produced in the work directory

#### Usage examples

It is most convenient from here to put the `bin` directory on the `PATH`:

    # Adds BAP and bap-container-run to PATH
    PATH="$PWD/bin:$PATH"

Check that all works:

    BAP --help

Run a terminal shell in the container:

    bap-container-run

Run the BAP on the test databases:

    BAP_DB_DIR=$PWD/test/databases BAP --help



## Development / Upgrades

* To change the backend versions, set the requested versions in
  `ext/backend-versions.config` and run `ext/update-backends.sh`.

* To upgrade some backend to the latest on master (or some other branch),
  set their requested version to `master`, then run `scripts/update-backends.sh`.

* Before committing a release to production, it aids reproducibility to run
  `scripts/pin-backend-versions.sh` which records the actual versions.

* Run tests after upgrading backends:

        # Runs the 5 tests we ran above
        test/run-all-tests.sh


## History, Credits, License

#### History

The KCRI BAP evolved from the CGE BAP (citation below), the original code of
which is at <https://bitbucket.org/genomicepidemiology/cge-tools-docker.git>.
The KCRI version initially lived on the `kcri` branch in that repository, but
moved to its own project after development of the BAP master stopped.

The KCRI BAP was developed to run on modest hardware, independent of an HPC
batch submission system.  It ran at KCRI for several years on a cluster of
four 8 core, 32GB Dell Precision M4700 laptop workstations.

As the BAP evolved, its workflow logic became unwieldy and was factored out
into a simple generic mechanism.  That code is now in the `src/cgeflow`
package, whereas all BAP-specifics (workflow definitions and service shims)
are in the `src/kcribap` package.

The next generation BAP "2.0" is under development at CGE, and is based on
the NextFlow workflow control engine.  We envisage migrating KCRI BAP to that
foundation once it is operational.

#### Citation

For publications please cite the URL <https://github.com/zwets/kcri-cge-bap>
of this repository, and the paper on the original concept:

_A Bacterial Analysis Platform: An Integrated System for Analysing Bacterial
Whole Genome Sequencing Data for Clinical Diagnostics and Surveillance._
Martin Christen Frølund Thomsen, Johanne Ahrenfeldt, Jose Luis Bellod Cisneros,
Vanessa Jurtz, Mette Voldby Larsen, Henrik Hasman, Frank Møller Aarestrup,
Ole Lund; PLoS One. 2016; 11(6): e0157718.

#### Licence

Copyright 2016-2019 Center for Genomic Epidemiology, Technical University of Denmark  
Copyright 2018-2020 Kilimanjaro Clinical Research Institute, Tanzania  

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

