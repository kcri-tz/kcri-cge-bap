#!/usr/bin/env python3
#
# kcri.bap.services - Defines the services used by the BAP workflow
#
#   This module defines the SERVICES dict that maps each Service.* enum
#   defined in .workflow to a class (called a 'shim') that implements
#   the service.
#

# Import the Services enum
from .workflow import Services

# Import the shim classes that implement each service
from .shims.CholeraeFinder import CholeraeFinderShim
from .shims.GetReference import GetReferenceShim
from .shims.KCST import KCSTShim
from .shims.KmerFinder import KmerFinderShim
from .shims.MLSTFinder import MLSTFinderShim
from .shims.PlasmidFinder import PlasmidFinderShim
from .shims.pMLST import pMLSTShim
from .shims.PointFinder import PointFinderShim
from .shims.Quast import QuastShim
from .shims.ResFinder import ResFinderShim
from .shims.SKESA import SKESAShim
from .shims.VirulenceFinder import VirulenceFinderShim
from .shims.cgMLSTFinder import cgMLSTFinderShim
from .shims.base import UnimplementedService

SERVICES = {
    Services.READSMETRICS:      UnimplementedService(),
    Services.QUAST:             QuastShim(),
    Services.SKESA:             SKESAShim(),
    Services.SPADES:            UnimplementedService(),
    Services.KCST:              KCSTShim(),
    Services.MLSTFINDER:        MLSTFinderShim(),
    Services.KMERFINDER:        KmerFinderShim(),
    Services.GETREFERENCE:      GetReferenceShim(),
    Services.RESFINDER:         ResFinderShim(),
    Services.POINTFINDER:       PointFinderShim(),
    Services.VIRULENCEFINDER:   VirulenceFinderShim(),
    Services.PLASMIDFINDER:     PlasmidFinderShim(),
    Services.PMLSTFINDER:       pMLSTShim(),
    Services.CGMLSTFINDER:      cgMLSTFinderShim(),
    Services.CHOLERAEFINDER:    CholeraeFinderShim(),
    Services.PROKKA:            UnimplementedService()
}

# Check that every enum that is defined has a mapping to a service
for s in Services:
    assert s in SERVICES, "No service shim defined for service %s" % s

