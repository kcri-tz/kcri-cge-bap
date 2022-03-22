# KCRI CGE Bacterial Analysis Pipeline (BAP)


## Introduction

The KCRI CGE Bacterial Analysis Pipeline (BAP) is the standard analysis
pipeline for bacterial genomics at Kilimanjaro Clinical Research Institute
(KCRI).  The BAP is developed in collaboration with the Centre for Genomic
Epidemiology (CGE) at the Technical University of Danmark (DTU).

The BAP orchestrates a standard workflow that processes sequencing reads
and/or contigs, and produces the following:

 * Genome assembly (optional) (SKESA, Flye)
 * Basic QC metrics over reads a/o contigs (fastq-stats, uf-stats)
 * Species identification (KmerFinder, KCST)
 * MLST (KCST, MLSTFinder)
 * Resistance profiling (ResFinder, PointFinder)
 * Plasmid detection and typing (PlasmidFinder, pMLST)
 * Virulence gene finding (VirulenceFinder)
 * Core genome MLST (optional) (cgMLST)

The BAP comes with sensible default settings and a standard workflow, but
can be adjusted with command line parameters.

#### Supported Inputs

Since release 3.3.0, the BAP can process Illumina reads, Nanopore reads, or
assembled contigs.  You can pass it one of the following:

 * A single FASTA file with (assembled) contigs
 * A pair of Illumina paired-end reads files _or_ a single Illumina reads file
   (set `--paired` when single file is interleaved)
 * A single Nanopore reads file

Note that the BAP by default does not do assembly unless some service requires
contigs.  You can force assembly using the `-t/--target` option (see below).
Note that the assembly produced is the plain Flye output, and not polished.


## Usage

Default run on a genome assembly:

    BAP assembly.fna

Same but on paired-end Illumina reads:

    BAP read_1.fq.gz read_2.fq.gz

Same but also produce the assembled genome:

    BAP -t DEFAULT,assembly read_1.fq.gz read_2.fq.gz

#### Targets

The `-t/--target` parameter specifies the analyses the BAP must do.
When omitted, it has value `DEFAULT`, which implies these targets:
`species`, `resistance`, `plasmids`, `virulence`, `metrics`.

> Note how targets are 'logical' names for the tasks the BAP must do.
> The BAP will determine which services to involve, in what order,
> and what alternatives to try if a service fails.

See available targets:

    BAP --list-targets
    -> metrics species mlst resistance virulence plasmids ...

Perform _only_ assembly (by omitting the DEFAULT target)

    BAP -t assembly read_1.fq.gz read_2.fq.gz

Compute metrics only:

    BAP -t metrics read_1.fq.gz read_2.fq.gz

Do defaults but _exclude_ metrics:

    BAP -x metrics read_1.fq.gz read_2.fq.gz

#### Service parameters

Service parameters can be passed to individual services in the pipeline.
For instance, to change ResFinder's identity and coverage thresholds:

    BAP --rf-i=0.95 --rf-c=0.8 assembly.fna

For an overview of available parameters, use `--help`:

    BAP --help

#### Advanced Usage

Run a service in the container directly:

    bap-container-run kmerfinder --help
    bap-container-run kcst --help

Run a terminal shell in the container:

    bap-container-run


## Installation

The BAP was developed to run on a moderately high-end Linux workstation
(see [history](#history-and-credits) below).  It is most easily installed
in a Docker container.

The installation has two major steps: building the Docker image, and
downloading the databases.

#### Installation - Docker Image

Test that Docker is installed

    docker version
    docker run hello-world

Clone and enter this repository

    git clone https://github.com/zwets/kcri-cge-bap.git
    cd kcri-cge-bap

Download the backend services

    ext/update-backends.sh

Build the `kcri-cge-bap` Docker image

    ./build.sh

    # Or manually do what build.sh does:
    #docker build -t kcri-cge-bap "." | tee build.log

Smoke test the container

    # Run 'BAP --help' in the container, using the bin/BAP wrapper.
    # (We set BAP_DB_DIR to a dummy as we have no databases yet)

    BAP_DB_DIR=/tmp bin/BAP --help

Index the test databases

    # This uses the kma_index and kcst indexers in the freshly built
    # image to index test/databases/*:

    scripts/index-databases.sh test/databases

Run on test data against the test databases:

    # Test run BAP on an assembled sample genome
    test/test-01-fa.sh

    # Run BAP on a sample of paired-end reads
    test/test-02-fq.sh

    # Compute metrics over FASTA and FASTQ
    test/test-03-metrics.sh

    # Run BAP including assembly
    test/test-04-asm.sh

If the tests above all end with with `[OK]`, you are good to go.  (Note
the test reads are just a small subset of a normal run, so the run output
for tests 02 and 03 is not representative.)

#### Installation - CGE Databases

In the previous step we tested against the miniature test databases that
come with this repository.  In this step we install the real databases.

> NOTE: The download can take a _lot_ of time.  The KmerFinder and cgMLST
> databases in particular are very large (~100GB).  It is possible to run
> the BAP without these, but with loss of functionality.

Pick a location for the databases:

    # Remember to set this BAP_DB_DIR in bin/bap-container-run
    BAP_DB_DIR=/data/genomics/cge/db   # KCRI path, replace by yours

Clone the CGE database repositories:

    mkdir -p "$BAP_DB_DIR"
    scripts/clone-databases.sh "$BAP_DB_DIR"

You now have databases for all services except KmerFinder and cgMLST.  To
download these (or a subset), follow the instructions in the repositories.

    cd "$BAP_DB_DIR/kmerfinder"
    less README.md   # has instructions on download and installation

Run tests against the real databases (ignore failure "does not match expected
output" as there may have been additions to the CGE databases):

    # With BAP_DB_DIR pointing at the installed databases
    test/test-04-fa-live.sh
    test/test-05-fq-live.sh

#### Installation - Final Touches

If the tests succeeded, set `BAP_DB_DIR` in `bin/bap-container-run` to point
at the installed databases.

For convenience, add the `bin` directory to your `PATH` (edit your `~/.profile`),
or copy or symlink the `bin/BAP` script in `~/.local/bin` or `~/bin`.

Once this is done (you may need to logout and login), `BAP --help` should work.


## Development / Upgrades

* After updating databases, rerun `scripts/index-databases.sh DB_DIR` (note the
  `INSTALL.sh` script in the CGE databases may have already done this)

* To change the backend versions, set the requested versions in
  `ext/backend-versions.config` and run `ext/update-backends.sh`.

* To upgrade some backend to the latest on master (or some other branch),
  set their requested version to `master`, then run `ext/update-backends.sh`.

* Before committing a release to production, for reproducibility, run
  `ext/pin-backend-versions.sh` to record the actual versions.

* Run tests after upgrading backends:

        # Runs the tests we ran above
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
into a simple generic mechanism.  That code is now in <https://github.com/zwets/picoline>
whereas all BAP-specifics (the workflow definitions and service shims) are
in the `src/kcri/bap` package.

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

