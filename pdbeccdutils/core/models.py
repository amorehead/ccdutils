#!/usr/bin/env python
# software from PDBe: Protein Data Bank in Europe; https://pdbe.org
#
# Copyright 2018 EMBL - European Bioinformatics Institute
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

"""Module housing some of the dataclasses used throughout the
pdbeccdutils application.
"""

from dataclasses import dataclass

from enum import IntEnum
from typing import Any, List, NamedTuple

import rdkit


class DepictionSource(IntEnum):
    """Where does the depiction come from.

    Attributes:
        Pubchem - Pubchem layout used
        Template - general substructure used
        RDKit - RDKit functionality using Coordgen.
        Failed - Nothing worked.
    """
    PubChem = 1
    Template = 2
    RDKit = 3
    Failed = 4


class ConformerType(IntEnum):
    """Conformer type of the `Component` object.

    Attributes:
        Ideal
        Model
        Depiction: 2D conformation
        Computed
        AllConformers
    """
    Ideal = 1
    Model = 2
    Depiction = 3
    Computed = 4
    AllConformers = 5


class ReleaseStatus(IntEnum):
    """An enumeration for pdbx_release_status
    allowed values include REL and HOLD, see:
    http://mmcif.wwpdb.org/dictionaries/mmcif_pdbx.dic/Items/_chem_comp.pdbx_release_status.html

    Notes:
        An additional value 'NOT_SET' has been added for case where
        pdbx_release_status has not been set.
    """
    NOT_SET = 0
    DEL = 1
    HOLD = 2
    HPUB = 3
    OBS = 4
    REF_ONLY = 5
    REL = 6


class ScaffoldingMethod(IntEnum):
    """
    Rdkit scaffold methods
    """

    MurckoScaffold = 1
    MurckoGeneric = 2
    Brics = 3


class DepictionResult(NamedTuple):
    """
    Depictions result details.

    Args:
        source (DepictionSource): Source of the depiction.
        template_name (str): template name.
        mol (rdkit.Chem.rdchem.Mol): RDKit mol object.
        score (float): Quality of the depiction, lower is better.

    """
    source: DepictionSource
    template_name: str
    mol: rdkit.Chem.rdchem.Mol
    score: float


CCDProperties = NamedTuple('CCDProperties',
                           [('id', str),
                            ('name', str),
                            ('formula', str),
                            ('modified_date', str),
                            ('pdbx_release_status', str),
                            ('weight', str)])

CCDProperties.__doc__ = """
            Properties of the component comming from _chem_comp namespace.

            Args:
                id (str): _chem_comp.id
                name (str): _chem_comp.name
                formula (str): _chem_comp.formula
                modified_date (str): _chem_comp.pdbx_modified_date
                pdbx_release_status (str): _chem_comp.pdbx_release_status
                weight (str): _chem_comp.formula_weight
            """


class Descriptor(NamedTuple):
    """
    Descriptor obtained from the cif file. This is essentially
    _pdbx_chem_comp_descriptor field.

    Args:
        type (str): `_pdbx_chem_comp_descriptor.type` in CIF language.
        program (str): `_pdbx_chem_comp_descriptor.program` in CIF language.
        value (str): `_pdbx_chem_comp_descriptor.descriptor` in CIF language.
    """
    type: str
    program: str
    value: str


@dataclass
class FragmentEntry:
    """Fragment entry in the fragment library

    Args:
        name (str): Name or id of the fragment.
        source (str): where does this fragment come from.
        mol (rdkit.Chem.rdchem.Mol): rdkit mol object with the fragment.
    """

    name: str
    source: str
    mol: rdkit.Chem.rdchem.Mol


@dataclass
class SubstructureMapping:
    """Represents a fragment hit in the component

    Args:
        name (str): Name of the substructure.
        smiles (str): SMILES representation of the substructure
        source (str): Where does this fragment come from.
        mapping (List[List[Any]]): Mappings with atom names or indices.
    """

    name: str
    smiles: str
    source: str
    mappings: List[List[Any]]
