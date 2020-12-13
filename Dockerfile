# Dockerfile for the KCRI CGE Bacterial Analysis Pipeline (BAP)
# ======================================================================

# For full reproducibility, pin the package versions installed by apt
# and conda when releasing to production, using 'package=version'.
# The 'apt-get' and 'conda list' commands output the versions in use.


# Load base Docker image
# ----------------------------------------------------------------------

# Use miniconda3:4.9.2 (Python 3.8, channel 'defaults' only)
FROM continuumio/miniconda3:4.9.2


# System dependencies
# ----------------------------------------------------------------------

# Debian packages
# - gcc and libz-dev for kma
# - g++ and libboost-iostreams for kcst
# - g++ and the libboost packages for SKESA

ENV DEBIAN_FRONTEND noninteractive
RUN apt-get -qq update --fix-missing && \
    apt-get -qq install apt-utils && \
    dpkg --configure -a && \
    apt-get -qq install --no-install-recommends \
        make g++ gcc libc-dev libz-dev \
        gawk \
        libboost-program-options-dev \
        libboost-iostreams-dev \
        libboost-regex-dev \
        libboost-timer-dev \
        libboost-chrono-dev \
        libboost-system-dev \
    && \
    apt-get -qq clean && \
    rm -rf /var/lib/apt/lists/*


# Python dependencies
# ----------------------------------------------------------------------

# Python dependencies via Conda:
# - Install nomkl to prevent MKL being installed; we don't currently
#   use it, it's huge, and it is non-free (why does Conda pick it?)
# - Our jobcontrol module requires psutil
# - Biopython and tabulate are used by all CGE services
# - ResFinder requires python-dateutil and gitpython
# - Quast requires joblib and simplejson (plus a patch, see below)
# - Quast PDF output would require matplotlib, and for SV detection
#   gridss and Java; however we currently do not use these.
# - cgMLST requires ete3 in its make_nj_tree.py, which we don't use,
#   and spuriously in cgMLST.py, where we comment it out (see patch).

RUN conda install \
        nomkl \
	psutil \
	biopython tabulate \
	python-dateutil gitpython \
	joblib simplejson && \
    conda list && \
    conda clean -qy --tarballs


# Other dependencies
# ----------------------------------------------------------------------

# SKESA, BLAST, Quast are available in the 'bioconda' channel, but yield
# myriad dependency conflicts, hence we install them from source.

#RUN conda config --add channels bioconda && \
#    conda config --add channels defaults && \
#    conda config --set channel_priority strict && \
#    conda update --all && \
#    conda install blast skesa quast


# Install External Deps
#----------------------------------------------------------------------

# Installation root
RUN mkdir -p /usr/src/cge
WORKDIR /usr/src/cge

# Copy the externals to /usr/src/cge/ext
# Note the .dockerignore filters out a lot
COPY ext ext

# Install BLAST by putting its binaries on the PATH
ENV PATH $PATH:/usr/src/cge/ext/ncbi-blast

# Make and install skesa
RUN cd ext/skesa && \
    make clean && make -f Makefile.nongs && \
    mv skesa /usr/local/bin/ && \
    cd .. && rm -rf skesa

# Install quast (and patch deprecated Python 3.7 dependency)
RUN cd ext/quast && \
    python3 setup.py install && \
    cd .. && rm -rf quast && \
    cd '/opt/conda/lib/python3.8/site-packages/quast-5.0.2-py3.8.egg' && \
    sed -i -Ee 's@^import cgi@import html@;s@cgi.escape@html.escape@' \
        'quast_libs/site_packages/jsontemplate/jsontemplate.py'

# Make and install kcst
RUN cd ext/kcst/src && \
    make clean && make && \
    mv khc ../bin/kcst ../data/make-kcst-db.sh /usr/local/bin/ && \
    cd ../.. && rm -rf kcst

# Make and install kma
RUN cd ext/kma && \
    make clean && make && \
    cp kma kma_index kma_shm /usr/local/bin/ && \
    cd .. && rm -rf kma

# Install the cgecore module
RUN cd ext/cge_core_module && \
    python3 setup.py install && \
    cd .. && rm -rf cge_core_module


# Install CGE Services
#----------------------------------------------------------------------

# Patch cgmlstfinder ete3 dependency and directory bug
RUN sed -i -Ee 's@^from ete3 import@#from ete3 import@' \
        'ext/cgmlstfinder/cgMLST.py' && \
    sed -i -Ee 's@"-tmp", tmp_dir,@"-tmp", tmp_dir + "/"@' \
        'ext/cgmlstfinder/cgMLST.py'

# Precompile the services (optional)
RUN python3 -m compileall \
    ext/cgmlstfinder/* \
    ext/choleraefinder/* \
    ext/kmerfinder/* \
    ext/mlst/* \
    ext/plasmidfinder/* \
    ext/pmlst/* \
    ext/resfinder/* \
    ext/virulencefinder/*

# Add service script directories to PATH
ENV PATH $PATH""\
":/usr/src/cge/ext/cgmlstfinder"\
":/usr/src/cge/ext/choleraefinder"\
":/usr/src/cge/ext/kmerfinder"\
":/usr/src/cge/ext/mlst"\
":/usr/src/cge/ext/plasmidfinder"\
":/usr/src/cge/ext/pmlst"\
":/usr/src/cge/ext/resfinder"\
":/usr/src/cge/ext/virulencefinder"


# Install the BAP code
#----------------------------------------------------------------------

# Copy contents of src into /usr/src/cge
COPY src ./

# Install the CGE Flow generic workflow code
RUN cd cgeflow && \
    python3 setup.py install

# Install the KCRI BAP specific code
RUN cd kcribap && \
    python3 setup.py install


# Set up system and user settings
#----------------------------------------------------------------------

# Set services default path to mounted databases
ENV BAP_DB_ROOT /databases

# Stop container's bash from leaving .bash_histories everywhere
# and add convenience aliases for interactive (debugging) use
RUN echo "unset HISTFILE" >>/etc/bash.bashrc && \
    echo "alias ls='ls --color=auto' l='ls -CF' la='l -a' ll='l -l' lla='ll -a'" >>/etc/bash.bashrc

# Create user 'bapuser' and make container drop from root
RUN useradd --no-log-init --no-create-home --user-group -d /workdir bapuser
USER bapuser:bapuser

# Change to the mounted workdir by default
WORKDIR /workdir

# No ENTRYPOINT so that any binary on the PATH in the container can be
# simply run.  Set CMD so that without arguments, user sees BAP --help.
CMD ["BAP", "--help"]

