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

import re
import sys
from datetime import date
from io import StringIO
from typing import Any, Dict, List, Optional, Tuple

import rdkit
import rdkit.Chem.Draw as Draw
from rdkit.Chem import BRICS, Descriptors
from rdkit.Chem.Scaffolds import MurckoScaffold

import pdbeccdutils.helpers.drawing as drawing
from pdbeccdutils.core.depictions import DepictionManager, DepictionResult
from pdbeccdutils.core.exceptions import CCDUtilsError
from pdbeccdutils.core.fragment_library import FragmentLibrary
from pdbeccdutils.core.models import (CCDProperties, ConformerType, Descriptor,
                                      FragmentHit, ReleaseStatus,
                                      ScaffoldingMethod)

METALS_SMART = '[Li,Na,K,Rb,Cs,F,Be,Mg,Ca,Sr,Ba,Ra,Sc,Ti,V,Cr,Mn,Fe,Co,Ni,Cu,Zn,Al,Ga,Y,Zr,Nb,Mo,'\
               'Tc,Ru,Rh,Pd,Ag,Cd,In,Sn,Hf,Ta,W,Re,Os,Ir,Pt,Au,Hg,Tl,Pb,Bi]'


class Component:
    """
    Wrapper for the rdkit.Chem.Mol object enabling some of its
    functionality and handling possible erroneous situations.

    Returns:
        Component: instance object
    """

    def __init__(self, mol: rdkit.Chem.rdchem.Mol, ccd_cif_dict: Dict[str, Any]=None,
                 properties: CCDProperties=None, descriptors: List[Descriptor]=None) -> None:

        self.mol = mol
        self._mol_no_h = None
        self.ccd_cif_dict = ccd_cif_dict
        self._fragments: Dict[str, FragmentHit] = {}
        self._2dmol = None
        self._descriptors: List[Descriptor] = []
        self._inchi_from_rdkit = ''
        self._inchikey_from_rdkit = ''
        self._sanitization_issues = self._sanitize()

        self.conformers_mapping = \
            {ConformerType.AllConformers: - 1,
             ConformerType.Ideal: 0,
             ConformerType.Model: 1 if len(mol.GetConformers()) == 2 else 1000,
             ConformerType.Computed: 2000}

        self.properties: Properties = Properties(self.mol, properties)

        if descriptors is not None:
            self._descriptors = descriptors

    # region properties
    @property
    def id(self) -> str:
        """
        Supply the unique identifier for the PDB-CCD,
        for example 'ATP'.
        Obtained from CCD's _chem_comp.id:

        http://mmcif.wwpdb.org/dictionaries/mmcif_std.dic/Items/_chem_comp.id.html

        If not defined then the empty string '' will be returned.

        Returns:
            str: the _chem_comp.id or ''.
        """
        return self.properties._id

    @property
    def name(self) -> str:
        """
        Supply the 'full name' of the PDB-CCD, for example 'ETHANOL'.
        Obtained from PDB-CCD's _chem_comp.name:

        http://mmcif.wwpdb.org/dictionaries/mmcif_std.dic/Items/_chem_comp.name.html

        If not defined then the empty string '' will be returned.

        Returns:
            str: the _chem_comp.name or ''.
        """
        return self.properties._name

    @property
    def formula(self) -> str:
        """
        Supply the chemical formula for the PDB-CCD,
        for example 'C2 H6 O'.
        Obtained from PDB-CCD's _chem_comp.formula:

        http://mmcif.wwpdb.org/dictionaries/mmcif_std.dic/Items/_chem_comp.formula.html

        If not defined then the empty string '' will be returned.

        Returns:
            str: the _chem_comp.formula or ''.
        """
        return self.properties._formula

    @property
    def pdbx_release_status(self) -> ReleaseStatus:
        """
        Supply the pdbx_release_status for the PDB-CCD.
        Obtained from PDB-CCD's _chem_comp.pdbx_rel_status:

        http://mmcif.wwpdb.org/dictionaries/mmcif_pdbx.dic/Items/_chem_comp.pdbx_release_status.html

        Returns:
            pdbeccdutils.core.enums.ReleaseStatus: enum of the release
            status (this includes NOT_SET if no value is defined).
        """
        return self.properties._pdbx_release_status

    @property
    def modified_date(self) -> Optional[date]:
        return self.properties._modified_date

    @property
    def descriptors(self) -> List[Descriptor]:
        return self._descriptors

    @property
    def inchikey(self) -> str:
        """
        Supply the InChIKey for the PDB-CCD.
        Obtained from `PDB-CCD's _pdbx_chem_comp_descriptor` table line
        with `_pdbx_chem_comp_descriptor.type=InChIKey`, see:

        http://mmcif.wwpdb.org/dictionaries/mmcif_pdbx.dic/Items/_pdbx_chem_comp_descriptor.type.html

        If not defined then the empty string '' will be returned.

        Returns:
            str: the InChIKey or ''.
        """
        return next((x.value for x in self._descriptors if x.type == 'InChIKey'), '')

    @property
    def inchi(self) -> str:
        return next((x.value for x in self._descriptors if x.type == 'InChI'), '')

    @property
    def inchi_from_rdkit(self) -> str:
        """
        Provides the InChI worked out by RDKit.

        Returns:
            str: the InChI or emptry '' if there was an error finding it.
        """
        if len(self._inchi_from_rdkit) == 0:
            try:
                self._inchi_from_rdkit = rdkit.Chem.inchi.MolToInchi(self.mol)
            except ValueError:
                self._inchi_from_rdkit = ''
        return self._inchi_from_rdkit

    @property
    def inchikey_from_rdkit(self) -> str:
        """
        Provides the InChIKey worked out by RDKit.

        Returns:
            str: the InChIKey or '' if there was an error finding it.
        """
        if len(self._inchikey_from_rdkit) == 0:
            inchi = self.inchi_from_rdkit
            if inchi != 'ERROR':
                self._inchikey_from_rdkit = rdkit.Chem.inchi.InchiToInchiKey(inchi)
            else:
                self._inchikey_from_rdkit = ''
            if self._inchikey_from_rdkit is None:
                self._inchikey_from_rdkit = ''
        return self._inchikey_from_rdkit

    @property
    def released(self) -> bool:
        """Tests pdbx_release_status is REL.

        Returns:
            bool: True if PDB-CCD has been released.
        """
        return self.properties._pdbx_release_status == ReleaseStatus.REL

    @property
    def mol_no_h(self) -> rdkit.Chem.rdchem.Mol:
        if self._mol_no_h is None:
            no_h = rdkit.Chem.RemoveHs(self.mol, sanitize=False)
            rdkit.Chem.SanitizeMol(no_h, catchErrors=True)
            self._mol_no_h = no_h
        
        return self._mol_no_h

    @property
    def number_atoms(self) -> int:
        """
        Supplies the number of atoms in the _chem_comp_atom table

        Returns:
            int: the number of atoms in the PDB-CCD
        """
        return self.mol.GetNumAtoms()

    @property
    def fragments(self) -> Dict[str, FragmentHit]:
        """Lists matched fragments and atom names.

        Returns:
            Dict[str, List[List[str]]]: Dictionary with fragment names
            and matched atoms.

        """
        res: Dict[str, FragmentHit] = {}

        for k, v in self._fragments.items():
            mappings = []

            for m in v.mappings:
                mappings.append(list(map(lambda idx: self.mol.GetAtomWithIdx(idx).GetProp('name'), m)))
            res[k] = FragmentHit(mappings, v.source)

        return res

    @property
    def atoms_ids(self) -> Tuple[Any, ...]:
        """
        Supplies a list of the atom_ids obtained from
        `_chem_comp_atom.atom_id`, see:

        http://mmcif.wwpdb.org/dictionaries/mmcif_pdbx.dic/Categories/chem_comp_atom.html

        The order will reflect the order in the input PDB-CCD.

        The atom_id is also also know as 'atom_name', standard amino
        acids have main chain atom names 'N CA C O'

        Returns:
            (:obj:`tuple` of :obj:`str`): `atom_id's` for the PDB-CCD
        """
        return tuple(atom.GetProp('name') for
                     atom in self.mol.GetAtoms())

    @property
    def sanitized(self):
        """Check whether sanitization process succeeded.

        Returns:
            bool: Whether or not the sanitization process has been succesfull
        """
        return self._sanitization_issues

    # endregion properties

    def inchikey_from_rdkit_matches_ccd(self, connectivity_only: bool=False) -> bool:
        """
        Checks whether inchikey matches between ccd and rdkit

        Args:
            connectivity_only (bool): restrict to the first 14 character - the connectivity information.

        Returns:
            bool: True for match
        """
        if self.inchikey is None or self.inchikey_from_rdkit == 'ERROR':
            return False
        if connectivity_only:
            if len(self.inchikey) < 14 or len(self.inchikey_from_rdkit) < 14:
                return False
            elif self.inchikey[:14] != self.inchikey_from_rdkit[:14]:
                return False
        elif self.inchikey != self.inchikey_from_rdkit:
            return False
        return True

    def compute_2d(self, manager: DepictionManager, remove_hs: bool=True) -> DepictionResult:
        """Compute 2d depiction of the component using DepictionManager
        instance.

        Args:
            manager (DepictionManager): Instance of the ligand depiction
                class.
            remove_hs (bool, optional): Defaults to True. Remove
                hydrogens prior to depiction.

        Returns:
            DepictionResult: Object with the details about depiction process.
        """
        mol_copy = rdkit.Chem.RWMol(self.mol)
        if remove_hs:
            mol_copy = rdkit.Chem.RemoveHs(mol_copy, updateExplicitCount=True, sanitize=False)
            rdkit.Chem.SanitizeMol(mol_copy, catchErrors=True)

        result_log = manager.depict_molecule(self.id, mol_copy)
        self._2dmol = result_log.mol

        return result_log

    def export_2d_svg(self, file_name: str, width: int=500, names: bool=False,
                      atom_highlight: Dict[Any, Tuple] = None,
                      bond_highlight: Dict[Tuple, Tuple]=None):
        """
        Save 2d depiction of the component as an SVG file.

        Args:
            file_name (str): path to store 2d depiction
            width (int, optional): Defaults to 500. Width of a frame in pixels.
            names (bool, optional): Defaults to False. Whether or not to
                include atom names in depiction. If atom name is not set, element symbol is used instead.
            atomHighlight (:obj:`dict` of :obj:`tuple` of :obj:`float`, optional):
                Defaults to None. Atoms names to be highlighted along
                with colors in RGB. e.g. {'CA': (0.5, 0.5, 0.5)} or {0: (0.5, 0.5, 0.5)}
            bondHighlight (:obj:`dict` of :obj:`tuple` of :obj:`float`, optional):
                Defaults to None. Bonds to be highlighted along with
                colors in RGB. e.g. {('CA', 'CB'): (0.5, 0.5, 0.5)} or {(0, 1): (0.5, 0.5, 0.5)}

        Raises:
            CCDUtilsError: If bond or atom does not exist.
        """
        if self._2dmol is None:
            drawing.save_no_image(file_name, width=width)
            return

        drawer = Draw.rdMolDraw2D.MolDraw2DSVG(width, width)
        atom_mapping = {self._get_atom_name(a): i for i, a in enumerate(self._2dmol.GetAtoms())}

        atom_highlight = {} if atom_highlight is None else atom_highlight
        bond_highlight = {} if bond_highlight is None else bond_highlight

        if all(isinstance(i, str) for i in atom_highlight.keys()):
            atom_highlight = {atom_mapping[k]: v for k, v in atom_highlight.items()}
        else:
            atom_highlight = {}

        if len(bond_highlight) > 0:
            if all(isinstance(i[0], str) and isinstance(i[1], str) for i in bond_highlight.keys()):
                temp_highlight = {}
                for k, v in bond_highlight.items():
                    bond = self._2dmol.GetBondBetweenAtoms(atom_mapping[k[0]], atom_mapping[k[1]])
                    if bond is None:
                        raise CCDUtilsError('Bond between {} and {} does not exist'.format(k[0], k[1]))
                    temp_highlight[bond.GetIdx()] = v
                bond_highlight = temp_highlight

        if names:
            options = drawer.drawOptions()
            for i, a in enumerate(self._2dmol.GetAtoms()):
                atom_name = self._get_atom_name(a)
                options.atomLabels[i] = atom_name
                a.SetProp('molFileAlias', atom_name)

        self._draw_molecule(drawer, file_name, width, atom_highlight, bond_highlight)

    def compute_3d(self) -> bool:
        """
        Generate 3D coordinates using ETKDGv2 method from RDKit.

        Returns:
            bool: Result of the structure generation process.
        """
        options = rdkit.Chem.AllChem.ETKDGv2()
        options.clearConfs = False

        try:
            conf_id = rdkit.Chem.AllChem.EmbedMolecule(self.mol, options)
            rdkit.Chem.AllChem.UFFOptimizeMolecule(self.mol, confId=conf_id, maxIters=1000)
            self.conformers_mapping[ConformerType.Computed] = conf_id
            return True
        except RuntimeError:
            return False  # Force field issue here
        except ValueError:
            return False  # sanitization issue here

    def _sanitize(self, fast: bool=False) -> bool:
        """
        Attempts to sanitize mol in place. RDKit's standard error can be
        processed in order to find out what went wrong with sanitization
        to fix the molecule.

        Args:
            fast (bool, optional): Defaults to False. If fast option is
                triggered original Oliver's sanitization process is run.


        Returns:
            bool: Result of the sanitization process.
        """
        rwmol = rdkit.Chem.RWMol(self.mol)
        try:
            success = self._fix_molecule_fast(rwmol) if fast else self._fix_molecule(rwmol)

            if not success:
                return False

            rdkit.Chem.Kekulize(rwmol)
            rdkit.Chem.rdmolops.AssignAtomChiralTagsFromStructure(rwmol)
            rdkit.Chem.rdmolops.AssignStereochemistry(rwmol)
            self.mol = rwmol.GetMol()
        except Exception as e:
            print(e, file=sys.stderr)
            return False

        return success

    def has_degenerated_conformer(self, type: ConformerType) -> bool:
        """
        Determine if given conformer has missing coordinates. This can
        be used to determine, whether or not the coordinates should be
        regenerated.

        Args:
            type (ConformerType): type of coformer
                to be inspected.

        Raises:
            ValueError: If given conformer does not exist.

        Returns:
            bool: true if more then 1 atom has coordinates [0, 0, 0]
        """
        conformer = self.mol.GetConformer(self.conformers_mapping[type])
        empty_coords = rdkit.Chem.rdGeometry.Point3D(0, 0, 0)
        counter = 0

        for i in range(conformer.GetNumAtoms()):
            pos = conformer.GetAtomPosition(i)
            if pos.Distance(empty_coords) == 0.0:
                counter += 1

        if counter > 1:
            return True
        return False

    def locate_fragment(self, mol: rdkit.Chem.rdchem.Mol) -> List[List[rdkit.Chem.rdchem.Atom]]:
        """
        Identify substructure match in the component.

        Args:
            mol (rdkit.Chem.rdchem.Mol): Fragment to be matched with
                structure

        Returns:
            (:obj:`list` of :obj:`list` of :obj:`rdkit.Chem.rdchem.Atom`):
                list of fragments identified in the component as a list
                of Atoms.
        """
        result = []
        if mol is None:
            return []

        matches = self.mol.GetSubstructMatches(mol)

        for m in matches:
            result.append(list(map(lambda idx: self.mol.GetAtomWithIdx(idx), m)))

        return result

    def library_search(self, fragment_library: FragmentLibrary) -> int:
        """Identify fragments from the fragment library in this component

        Args:
            fragment_library (FragmentLibrary):
                Fragment library.

        Returns:
            int: number of matches found
        """

        matches_found = 0
        for k, v in fragment_library.library.items():
            try:
                matches = self.mol_no_h.GetSubstructMatches(v.mol)
                matches_found += len(matches)

                if len(matches) > 0:
                    self._fragments[k] = FragmentHit(matches, v.source)
            except Exception:
                pass

        return matches_found

    def get_scaffolds(self, scaffolding_method=ScaffoldingMethod.MurckoScaffold):
        """Compute deemed scaffolds for a given compound.

        Args:
            scaffolding_method (ScaffoldingMethod, optional):
                Defaults to MurckoScaffold. Scaffolding method to use

        Returns:
            :obj:`list` of :obj:`rdkit.Chem.rdchem.Mol`: Scaffolds found in the component.
        """
        try:
            scaffold = None

            if scaffolding_method == ScaffoldingMethod.MurckoScaffold:
                scaffold = [(MurckoScaffold.GetScaffoldForMol(self.mol))]

            elif scaffolding_method == ScaffoldingMethod.MurckoGeneric:
                scaffold = [(MurckoScaffold.MakeScaffoldGeneric(self.mol))]

            elif scaffolding_method == ScaffoldingMethod.Brics:
                scaffold = BRICS.BRICSDecompose(self.mol)
                scaffold = list(map(lambda l: rdkit.Chem.MolFromSmiles(l), scaffold))
            return scaffold
        except (RuntimeError, ValueError):
            raise CCDUtilsError(f'Computing scaffolds using method {scaffolding_method.name} failed.')

    def _fix_molecule(self, rwmol: rdkit.Chem.rdchem.RWMol):
        """
        Single molecule sanitization process. Presently, only valence
        errors are taken care are of.

        Args:
            rwmol (rdkit.Chem.rdchem.RWMol): rdkit molecule to be
                sanitized

        Returns:
            bool: Whether or not sanitization succeeded
        """
        attempts = 10
        success = False
        saved_std_err = sys.stderr
        log = sys.stderr = StringIO()
        rdkit.Chem.WrapLogs()

        while ((not success) and attempts >= 0):
            sanitization_result = rdkit.Chem.SanitizeMol(rwmol, catchErrors=True)

            if sanitization_result == 0:
                sys.stderr = saved_std_err
                return True

            sanitization_failure = re.findall('[a-zA-Z]{1,2}, \\d+', log.getvalue())
            if len(sanitization_failure) == 0:
                sys.stderr = saved_std_err
                return False

            split_object = sanitization_failure[0].split(',')  # [0] element [1] valency
            element = split_object[0]
            valency = int(split_object[1].strip())

            smarts_metal_check = rdkit.Chem.MolFromSmarts(METALS_SMART + '~[{}]'.format(element))
            metal_atom_bonds = rwmol.GetSubstructMatches(smarts_metal_check)
            rdkit.Chem.SanitizeMol(rwmol, sanitizeOps=rdkit.Chem.SanitizeFlags.SANITIZE_CLEANUP)

            for (metal_index, atom_index) in metal_atom_bonds:
                metal_atom = rwmol.GetAtomWithIdx(metal_index)
                erroneous_atom = rwmol.GetAtomWithIdx(atom_index)

                # change the bond type to dative
                bond = rwmol.GetBondBetweenAtoms(metal_atom.GetIdx(), erroneous_atom.GetIdx())
                bond.SetBondType(rdkit.Chem.BondType.SINGLE)

                if erroneous_atom.GetExplicitValence() == valency:
                    erroneous_atom.SetFormalCharge(erroneous_atom.GetFormalCharge() + 1)
                    metal_atom.SetFormalCharge(metal_atom.GetFormalCharge() - 1)

            attempts -= 1

        sys.stderr = saved_std_err

        return False

    def _fix_molecule_fast(self, rwmol: rdkit.Chem.rdchem.Mol):
        """
        Fast sanitization process. Fixes just metal-N valence issues

        Args:
            rwmol (rdkit.Chem.rdchem.Mol): rdkit mol to be sanitized

        Returns:
            bool: Whether or not sanitization succeeded
        """
        smarts_metal_check = rdkit.Chem.MolFromSmarts(METALS_SMART + '~[N]')
        metal_atom_bonds = rwmol.GetSubstructMatches(smarts_metal_check)
        rdkit.Chem.SanitizeMol(rwmol, sanitizeOps=rdkit.Chem.SanitizeFlags.SANITIZE_CLEANUP)
        for (metal_index, atom_index) in metal_atom_bonds:
            metal_atom = rwmol.GetAtomWithIdx(metal_index)
            erroneous_atom = rwmol.GetAtomWithIdx(atom_index)

            # change the bond type to dative
            bond = rwmol.GetBondBetweenAtoms(metal_atom.GetIdx(), erroneous_atom.GetIdx())
            bond.SetBondType(rdkit.Chem.BondType.DATIVE)

            # change the valency
            if erroneous_atom.GetExplicitValence() == 4:
                erroneous_atom.SetFormalCharge(erroneous_atom.GetFormalCharge() + 1)
                metal_atom.SetFormalCharge(metal_atom.GetFormalCharge() - 1)

        sanitization_result = rdkit.Chem.SanitizeMol(rwmol, catchErrors=True)

        return sanitization_result == 0

    def _draw_molecule(self, drawer, file_name, width, atom_highlight, bond_highlight):
        try:
            copy = rdkit.Chem.Draw.rdMolDraw2D.PrepareMolForDrawing(self._2dmol, wedgeBonds=True,
                                                                    kekulize=True, addChiralHs=True)
        except (RuntimeError, ValueError):
            copy = rdkit.Chem.Draw.rdMolDraw2D.PrepareMolForDrawing(self._2dmol, wedgeBonds=False,
                                                                    kekulize=True, addChiralHs=True)

        if bond_highlight is None:
            drawer.DrawMolecule(copy, highlightAtoms=atom_highlight.keys(),
                                highlightAtomColors=atom_highlight)
        else:
            drawer.DrawMolecule(copy, highlightAtoms=atom_highlight.keys(),
                                highlightAtomColors=atom_highlight,
                                highlightBonds=bond_highlight.keys(), highlightBondColors=bond_highlight)
        drawer.FinishDrawing()

        with open(file_name, 'w') as f:
            svg = drawer.GetDrawingText()

            if width < 201:
                svg = re.sub('stroke-width:2px', 'stroke-width:1px', svg)
            f.write(svg)

    def _get_atom_name(self, atom: rdkit.Chem.rdchem.Atom):
        """Supplies atom_id obrained from `_chem_comp_atom.atom_id`, see:

        http://mmcif.wwpdb.org/dictionaries/mmcif_pdbx.dic/Categories/chem_comp_atom.html

        If there is no such atom name, it is created from the element
        symbol and atom index.

        Args:
            atom (rdkit.Chem.rdchem.Atom): rdkit atom

        Returns:
            str: atom name
        """
        return atom.GetProp('name') if atom.HasProp('name') else atom.GetSymbol() + str(atom.GetIdx())


class Properties:
    """Properties of the CCD component. Some of them are extracted from the input CCD
    others are computed by RDKit.
    """

    def __init__(self, mol: rdkit.Chem.rdchem.Mol, properties: Optional[CCDProperties]) -> None:
        self.mol = mol

        self._pdbx_release_status = ReleaseStatus.NOT_SET
        self._id = ''
        self._name = ''
        self._formula = ''
        self._modified_date = None

        if properties is not None:
            mod_date = properties.modified_date.split('-')
            self._id = properties.id
            self._name = properties.name
            self._formula = properties.formula
            self._pdbx_release_status = ReleaseStatus[properties.pdbx_release_status]
            self._modified_date: date = date(int(mod_date[0]), int(mod_date[1]), int(mod_date[2]))
        self._logP = None
        self._heavy_atom_count = None
        self._numH_acceptors = None
        self._numH_donors = None
        self._num_rotable_bonds = None
        self._ring_count = None
        self._TPSA = None
        self._molwt = None

    #region properties
    @property
    def logP(self) -> Optional[float]:
        """
        Wildman-Crippen LogP value defined by RDKit.

        Returns:
            Optional[float]: Wildman-Crippen LogP, or None if the
            calculation fails.
        """
        try:
            if self._logP is None:
                self._logP = Descriptors.MolLogP(self.mol)
        except ValueError:
            self._logP = None

        return self._logP

    @property
    def heavy_atom_count(self) -> Optional[int]:
        """
        Heavy atom count for defined by RDKit.

        Returns:
            Optional[int]: Number of heavy atoms, or None if the
            calculation fails.
        """

        try:
            if self._heavy_atom_count is None:
                self._heavy_atom_count = Descriptors.HeavyAtomCount(self.mol)
        except ValueError:
            self._heavy_atom_count = None

        return self._heavy_atom_count

    @property
    def numH_acceptors(self) -> Optional[int]:
        """
        Number of hydrogen bond acceptors defined by RDKit.

        Returns:
            Optional[int]: Number of H-bond acceptors, or None if the
            calculation fails.
        """

        try:
            if self._numH_acceptors is None:
                self._numH_acceptors = Descriptors.NumHAcceptors(self.mol)
        except ValueError:
            self._numH_acceptors = None

        return self._numH_acceptors

    @property
    def numH_donors(self) -> Optional[int]:
        """
        Number of hydrogen bond donors.

        Returns:
            Optional[int]: Number of H-bond donors, or None if the
            calculation fails.
        """

        try:
            if self._numH_donors is None:
                self._numH_donors = Descriptors.NumHDonors(self.mol)
        except ValueError:
            self._numH_donors = None

        return self._numH_donors

    @property
    def num_rotable_bonds(self) -> Optional[int]:
        """
        Number of rotatable bonds defined by RDKit.

        Returns:
            Optional[int]: Number of rotatable bonds, or None if the
            calculation fails.
        """

        try:
            if self._num_rotable_bonds is None:
                self._num_rotable_bonds = Descriptors.NumRotatableBonds(self.mol)
        except ValueError:
            self._num_rotable_bonds = None

        return self._num_rotable_bonds

    @property
    def ring_count(self) -> Optional[int]:
        """
        Number of rings defined by RDKit.

        Returns:
            Optional[int]: Number of rings, or None if the calculation
            fails.
        """

        try:
            if self._ring_count is None:
                self._ring_count = Descriptors.RingCount(self.mol)
        except ValueError:
            self._ring_count = None

        return self._ring_count

    @property
    def TPSA(self) -> Optional[float]:
        """
        Topological surface area defined by RDKit.

        Returns:
            Optional[float]: Topological surface area in A^2, or None if
            the calculation fails.
        """

        try:
            if self._TPSA is None:
                self._TPSA = round(Descriptors.TPSA(self.mol), 3)
        except ValueError:
            self._TPSA = None

        return self._TPSA

    @property
    def molwt(self) -> Optional[float]:
        """
        Molecular weight defined by RDKit.

        Returns:
            Optional[float]: Molecular weight, or None if the calculation
            fails.
        """

        try:
            if self._molwt is None:
                self._molwt = round(Descriptors.MolWt(self.mol), 3)
        except ValueError:
            self._molwt = None

        return self._molwt

    # endregion properties
