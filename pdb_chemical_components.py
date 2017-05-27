# software from PDBe: Protein Data Bank in Europe; http://pdbe.org
#
# Copyright 2017 EMBL - European Bioinformatics Institute
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
#
import os
from collections import namedtuple, OrderedDict


class PdbChemicalComponents(object):
    """
    deals with parsing the PDB chemical chemical component cif file.

    Notes
    Curently limited to parsing in the first cif definition in a file. Does not (yet) deal with multiple.
    """
    _chem_comp_atom_items = ('comp_id',
                             'atom_id',
                             'alt_atom_id',
                             'type_symbol',
                             'charge',
                             'pdbx_align',
                             'pdbx_aromatic_flag',
                             'pdbx_leaving_atom_flag',
                             'pdbx_stereo_config',
                             'model_Cartn_x',
                             'model_Cartn_y',
                             'model_Cartn_z',
                             'pdbx_model_Cartn_x_ideal',
                             'pdbx_model_Cartn_y_ideal',
                             'pdbx_model_Cartn_z_ideal',
                             'pdbx_component_atom_id',
                             'pdbx_component_comp_id',
                             'pdbx_ordinal')
    """list of the items used in _chem_comp_atom"""
    def __init__(self, file_name=None, cif_parser='auto'):
        """

        Args:
            file_name (str): filename
            cif_parser (str): the cif parser to use. One of 'auto' or 'mmcifIO'(EBI) or'CifFile' or 'test_hard_code_cmo'
        """
        self.chem_comp_id = None
        self.chem_comp_name = None
        self.chem_comp_pdbx_release_status = None
        self.inchikey = None
        self.atoms = []
        """list of ordered dictionary"""
        self.__atom_ids = None
        self.__elements = None
        self.Bond = namedtuple('Bond', 'atom_id_1 atom_id_2 value_order pdbx_aromatic_flag pdbx_stereo_config')
        self.bonds = []
        self.bond_atom_index_1 = []
        """list of int: one for each of self.bonds the index of the matching atom_id_1 in self.atoms"""
        self.bond_atom_index_2 = []
        """list of int: one for each of self.bonds the index of the matching atom_id_2 in self.atoms"""
        self.bond_order = []
        """list of int: one for each of self.bonds the bond order for the bond got from self.bonds value_order"""
        self.bond_aromatic = []
        """list of bool: one for each of self.bonds boolean conversion of pdbx_aromatic_flag (Y or N)"""
        self.cif_parser = cif_parser
        if cif_parser == 'test_hard_code_cmo':
            self.load_carbon_monoxide_hard_coded()
        elif file_name is not None:
            self.read_ccd_from_cif_file(file_name)
            self.setup_bond_lists()

    @staticmethod
    def empty_chem_comp_atom():
        """
        supply an empty chem_comp_atom - all items set to None

        Returns:
            OrderedDict: of items found in _chem_comp_atom_items
        """
        return OrderedDict([(k,None) for k in PdbChemicalComponents._chem_comp_atom_items])

    @property
    def atom_ids(self):
        """
        tuple of the atom_id's (aka atom names) in the chem_comp

        Returns:
            (str): the atom_id's
        """
        if self.__atom_ids is None:
            self.__atom_ids = []
            for atom in self.atoms:
                self.__atom_ids.append(atom['atom_id'])
            self.__atom_ids = tuple(self.__atom_ids)
        return self.__atom_ids

    @property
    def atom_elements(self):
        """
        the elements for the atoms in the chem_comp_atom list

        Returns:
            (str): the elements for each atom
        """
        if self.__elements is None:
            self.__elements = []
            for atom in self.atoms:
                type_symbol = atom['type_symbol']
                if type_symbol is None or len(type_symbol)==0:
                    raise RuntimeError('chem_comp_atom invalid type_symbol={}'.format(type_symbol))
                element = type_symbol[0]
                if len(type_symbol) > 1:
                    element += type_symbol[1].lower()
                self.__elements.append(element)
            self.__elements = tuple(self.__elements)
        return self.__elements

    @property
    def atom_stereo_configs(self):
        return NotImplemented

    @property
    def number_atoms(self):
        """
        The number of atoms in the chem_comp

        Returns:
            int: the number of atoms
        """
        return len(self.atoms)

    @property
    def number_bonds(self):
        """
        The number of bonds in the chem_comp

        Returns:
            int: the number of bonds
        """
        return len(self.bonds)

    def load_carbon_monoxide_hard_coded(self):
        """
        stub to produce a hard coded carbon monoxide ccd object for development idea/testing
        without file parsing

        Returns:
            None
        """
        # _chem_comp.id                                    CMO
        self.chem_comp_id = 'CMO'
        # _chem_comp.name                                  "CARBON MONOXIDE"
        self.chem_comp_name = 'CARBON MONOXIDE'
        # _chem_comp.chem_comp_pdbx_release_status                   REL
        self.chem_comp_pdbx_release_status = 'REL'
        #
        # loop_
        # _pdbx_chem_comp_descriptor.comp_id 
        # _pdbx_chem_comp_descriptor.type 
        # _pdbx_chem_comp_descriptor.program 
        # _pdbx_chem_comp_descriptor.program_version 
        # _pdbx_chem_comp_descriptor.descriptor 
        # CMO SMILES           ACDLabs              10.04 "[O+]#[C-]"                 
        # CMO SMILES_CANONICAL CACTVS               3.341 "[C-]#[O+]"                 
        # CMO SMILES           CACTVS               3.341 "[C-]#[O+]"                 
        # CMO SMILES_CANONICAL "OpenEye OEToolkits" 1.5.0 "[C-]#[O+]"                 
        # CMO SMILES           "OpenEye OEToolkits" 1.5.0 "[C-]#[O+]"                 
        # CMO InChI            InChI                1.03  InChI=1S/CO/c1-2            
        # CMO InChIKey         InChI                1.03  UGFAIRIUMAVXCW-UHFFFAOYSA-N 
        self.inchikey = 'UGFAIRIUMAVXCW-UHFFFAOYSA-N'
        # CMO C C C -1 1 N N N -0.296 8.526 17.112 0.607  0.000 0.000 C CMO 1
        # CMO O O O 1  1 N N N 0.023  7.997 18.053 -0.600 0.000 0.000 O CMO 2
        my_chem_comp_atom = self.empty_chem_comp_atom()
        my_chem_comp_atom['atom_id'] = 'C'
        my_chem_comp_atom['type_symbol'] = 'C'
        my_chem_comp_atom['pdbx_stereo_config'] = 'N'
        my_chem_comp_atom['pdbx_model_Cartn_x_ideal'] = '0.607'
        my_chem_comp_atom['pdbx_model_Cartn_y_ideal'] = '0.000'
        my_chem_comp_atom['pdbx_model_Cartn_y_ideal'] = '0.000'
        self.atoms.append(my_chem_comp_atom)
        my_chem_comp_atom = self.empty_chem_comp_atom()
        my_chem_comp_atom['atom_id'] = 'O'
        my_chem_comp_atom['type_symbol'] = 'O'
        my_chem_comp_atom['pdbx_stereo_config'] = 'N'
        my_chem_comp_atom['pdbx_model_Cartn_x_ideal'] = '-0.600'
        my_chem_comp_atom['pdbx_model_Cartn_y_ideal'] = '0.000'
        my_chem_comp_atom['pdbx_model_Cartn_y_ideal'] = '0.000'
        self.atoms.append(my_chem_comp_atom)
        # _chem_comp_bond.comp_id              CMO
        # _chem_comp_bond.atom_id_1            C
        # _chem_comp_bond.atom_id_2            O
        # _chem_comp_bond.value_order          TRIP
        # _chem_comp_bond.pdbx_aromatic_flag   N
        # _chem_comp_bond.pdbx_stereo_config   N
        # _chem_comp_bond.pdbx_ordinal         1
        this_bond = self.Bond(atom_id_1='C', atom_id_2='O', value_order='TRIP', 
                              pdbx_aromatic_flag='N', pdbx_stereo_config='N')
        self.bonds.append(this_bond)
        self.setup_bond_lists()

    def setup_bond_lists(self):
        self.bond_atom_index_1 = []
        self.bond_atom_index_2 = []
        self.bond_order = []
        self.bond_aromatic = []
        for bond in self.bonds:
            atom_id_1 = bond.atom_id_1
            index_atom_1 = self.find_atom_index(atom_id_1)
            self.bond_atom_index_1.append(index_atom_1)
            atom_id_2 = bond.atom_id_2
            index_atom_2 = self.find_atom_index(atom_id_2)
            self.bond_atom_index_2.append(index_atom_2)
            bond_order = self.map_value_order_to_int(bond.value_order)
            if bond_order == -1:
                raise RuntimeError('problem with bond order for bond {}'.format(bond))
            self.bond_order.append(bond_order)
            if bond.pdbx_aromatic_flag == 'Y':
                bond_aromatic = True
            else:
                bond_aromatic = False
            self.bond_aromatic.append(bond_aromatic)

    def find_atom_index(self, atom_id):
        for index in range(len(self.atoms)):
            this_atom = self.atoms[index]
            if atom_id == this_atom['atom_id']:
                return index
        return -1

    @staticmethod
    def map_value_order_to_int(value_order):
        if value_order == 'SING':
            return 1
        elif value_order == 'DOUB':
            return 2
        elif value_order == 'TRIP':
            return 3
        else:
            return -1

    def read_ccd_from_cif_file(self, file_name):
        """
        reads the ccd from a cif file

        Args:
            file_name (str): the filename

        Returns:
            None
        """
        if not os.path.isfile(file_name):
            raise ValueError('cannot read PDB chemical components from {} as file not found'.format(file_name))
        if self.cif_parser == 'auto':
            try:
                self.read_ccd_from_file_mmcifio(file_name)
            except ImportError:
                self.read_ccd_from_file_ciffile(file_name)
        elif self.cif_parser == 'mmcifIO':
            self.read_ccd_from_file_mmcifio(file_name)
        elif self.cif_parser == 'CifFile':
            self.read_ccd_from_file_ciffile(file_name)
        else:
            raise RuntimeError('unrecognized cif_parser {}'.format(self.cif_parser))

    def read_ccd_from_file_mmcifio(self, file_name):
        """
        reads the chemical component from file file_name using the mmcifIO parser
        https://github.com/glenveegee/PDBeCIF.git

        Args:
            file_name (str): the filename

        Returns:
            None

        Raises:
            ImportError: if the parser cannot be loaded.
            RuntimeError: if a new unrecognized item has appeared
        """
        import mmCif.mmcifIO as mmcifIO
        cif_parser = mmcifIO.CifFileReader(input='data', preserve_order=True)
        cif_obj = cif_parser.read(file_name, output='cif_wrapper')
        data_block = list(cif_obj.values())[0]
        chem_comp = data_block._chem_comp
        for thing in 'id', 'name', 'pdbx_release_status':
            value = chem_comp[thing][0]
            setattr(self, "chem_comp_" + thing, value)
        self.atoms = []
        chem_comp_atom = data_block._chem_comp_atom
        empty_atom = self.empty_chem_comp_atom()
        for atom in chem_comp_atom:
            self.atoms.append(atom)
            # check the no new attributes have been set
            for key in atom:
                if not key in empty_atom:
                    raise RuntimeError('unrecognized item "{}" in chem_comp_atom'.format(key))
        self.bonds = []
        chem_comp_bond = data_block._chem_comp_bond
        for bond in chem_comp_bond:
            atom_id_1 = bond['atom_id_1']
            atom_id_2 = bond['atom_id_2']
            value_order = bond['value_order']
            pdbx_aromatic_flag = bond['pdbx_aromatic_flag']
            pdbx_stereo_config = bond['pdbx_stereo_config']
            this_bond = self.Bond(atom_id_1=atom_id_1, atom_id_2=atom_id_2, value_order=value_order,
                                  pdbx_aromatic_flag=pdbx_aromatic_flag, pdbx_stereo_config=pdbx_stereo_config)
            self.bonds.append(this_bond)
        pdbx_chem_comp_descriptor = data_block._pdbx_chem_comp_descriptor
        for descriptor in pdbx_chem_comp_descriptor:
            if descriptor['type'] == 'InChIKey':
                self.inchikey = descriptor['descriptor']

    def read_ccd_from_file_ciffile(self, file_name):
        """
        reads the chemical component from file file_name using the pdbx_v2.core.CifFile parser

        Args:
            file_name (str): the filename

        Returns:
            None

        Raises:
            ImportError: if CifFile parser cannot be loaded.
        """
        from pdbx_v2.core.CifFile import CifFile
        # method based on calls made by
        # https://svn-dev.wwpdb.org/svn-wwpdb/py-validation/trunk/src/python/pdboi/pdbdata/mmcifapiconnector.py
        cif_file = CifFile(file_name, parseLogFileName=None).getCifFile()
        first_data_block = cif_file.GetBlock(cif_file.GetFirstBlockName())
        table_chem_comp = first_data_block.GetTable('chem_comp')
        for thing in 'id', 'name', 'pdbx_release_status':
            value = table_chem_comp(0, thing)
            setattr(self, "chem_comp_" + thing, value)
        self.atoms = []
        table_chem_comp_atom = first_data_block.GetTable('chem_comp_atom')
        number_atoms = table_chem_comp_atom.GetNumRows()
        for row_num in range(number_atoms):
            my_chem_comp_atom = self.empty_chem_comp_atom()
            for key in my_chem_comp_atom:
                my_chem_comp_atom[key] = table_chem_comp_atom(row_num, key)
            self.atoms.append(my_chem_comp_atom)
        table_pdbx_chem_comp_descriptor = first_data_block.GetTable('pdbx_chem_comp_descriptor')
        for row_num in range(table_pdbx_chem_comp_descriptor.GetNumRows()):
            if table_pdbx_chem_comp_descriptor(row_num, 'type') == 'InChIKey':
                self.inchikey = table_pdbx_chem_comp_descriptor(row_num, 'descriptor')
        self.bonds = []
        table_chem_comp_bond = first_data_block.GetTable('chem_comp_bond')
        number_bonds = table_chem_comp_bond.GetNumRows()
        for row_num in range(number_bonds):
            atom_id_1 = table_chem_comp_bond(row_num, 'atom_id_1')
            atom_id_2 = table_chem_comp_bond(row_num, 'atom_id_2')
            value_order = table_chem_comp_bond(row_num,'value_order')
            pdbx_aromatic_flag = table_chem_comp_bond(row_num,'pdbx_aromatic_flag')
            pdbx_stereo_config = table_chem_comp_bond(row_num,'pdbx_stereo_config')
            this_bond = self.Bond(atom_id_1=atom_id_1, atom_id_2=atom_id_2, value_order=value_order,
                                  pdbx_aromatic_flag=pdbx_aromatic_flag, pdbx_stereo_config=pdbx_stereo_config)
            self.bonds.append(this_bond)