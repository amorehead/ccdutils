# software from PDBe: Protein Data Bank in Europe; http://pdbe.org
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
#
"""
Script for PDBeChem backend infrastructure.
Processes the wwPDB Chemical Components Dictionary file `components.cif`
producing files for:

http://ftp.ebi.ac.uk/pub/databases/msd/pdbechem/

To do this components.cif is split into individual PDB chemical component
definitions cif files, sdf files, pdb files and image files.
In addition creates chem_comp.xml and chem_comp.list for all components.
More detailed description can be found here:

https://gitlab.ebi.ac.uk/pdbe/release/pdbechem
"""
import argparse
import json
import logging
import os
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
from typing import Dict, Any, List

import rdkit

import pdbeccdutils
from pdbeccdutils.core import ccd_reader, ccd_writer
from pdbeccdutils.core.exceptions import CCDUtilsError
from pdbeccdutils.core.component import Component
from pdbeccdutils.core.depictions import DepictionManager
from pdbeccdutils.core.fragment_library import FragmentLibrary
from pdbeccdutils.core.models import ConformerType, DepictionSource
from pdbeccdutils.utils import PubChemDownloader, config

#region helper methods


def atom_mapping_as_xml_element(element, mapping, mapping_id):
    """Append atom mapping to a specified element.

    Args:
        element ([type]): Element to apend children with atom mapping.
        mapping (list of `str`): List with atom names
        mapping_id (int): Id of the mappping for db loading.
    """
    map_element = ET.SubElement(element, 'mapping', {'id': str(mapping_id)})

    for at_name in mapping:
        ET.SubElement(map_element, 'atom', {'name': at_name})


def write_xml_file(xml, path):
    """Write out XML representation of the components.cif file

    Args:
        chem_comp_xml (xml.etree.ElementTree.Element): xml object with
            the data.
        path (str): Path where the XML file is going to be saved.
    """
    xml_str = ET.tostring(xml, encoding='utf-8', method='xml')
    pretty = minidom.parseString(xml_str)

    with open(path, 'w') as f:
        f.write(pretty.toprettyxml(indent="  "))
# end region helper methods


class PDBeChemManager:
    """Manager orchestrating computation and generation of all parts of the
    PDBeChem update process.
    """

    def __init__(self, logger=None):
        """Initialize class properties

        Args:
            logger (logging.Logger, optional): Defaults to None. Application log
        """
        self.compounds: List[ccd_reader.CCDReaderResult] = []                                        # processed compounds
        self.ligands_to_process: int = 0                                                             # no. ligands to process
        self.output_dir: str = ''                                                                    # where the results will be written
        self.depictions: DepictionManager = None                                                     # helper class to get nice depictions
        self.pubchem: PubChemDownloader = None                                                       # helper class to download templates if needed
        self.fragment_library: FragmentLibrary = None                                                # Fragments library to get substructure amtches
        self.logger: logging.Logger = logger if logger is not None else logging.getLogger(__name__)  # log of the application
        self.ids: List[str] = []                                                                     # list of processed ids for `chem_comp.list` file
        self.chem_comp_xml: ET.Element = ET.Element('chemCompList')                                  # XML representation of the compounds metadata

    def run_pipeline(self, args):
        """Run PDBeChem pipeline

        Args:
            args (argparse.Namespace): Verified application arguments
        """
        self._init(args)
        self._process_data()
        self._wrap_up()

    def _init(self, args):
        """Initialize PDBeChem pipeline and necessary objects.

        Args:
            args (argparse.Namespace): Verified application arguments
        """
        self.logger.debug('Initializing calculation...')

        self.output_dir = args.output_dir
        self.depictions = DepictionManager(args.pubchem_templates, args.general_templates)
        self.pubchem = PubChemDownloader(args.pubchem_templates) if os.path.isdir(args.pubchem_templates) else None
        self.fragment_library = FragmentLibrary(args.library)

        self.logger.debug(f'Reading in {args.components_cif} file...')
        self.compounds = ccd_reader.read_pdb_components_file(args.components_cif)
        self.ligands_to_process = len(self.compounds) if args.test_first is None else args.test_first
        self.ids = sorted(list(self.compounds.keys())[: self.ligands_to_process])

        self.logger.debug('Initialization finished.')

    def _process_data(self):
        """Main part of the PDBeChem process. Update all the data.

        """
        for key, ccd_reader_result in self.compounds.items():
            try:
                self.logger.info(f'{key} | processing...')
                self.process_single_component(ccd_reader_result)
            except Exception as e:
                self.logger.error(f'{key} | FAILURE {str(e)}.')
            self.ligands_to_process -= 1

            self.compounds[key] = None

            if self.ligands_to_process == 0:
                break

    def process_single_component(self, ccd_reader_result):
        """Process single PDB-CCD component

        Args:
            ccd_reader_result (CCDReaderResult): pdbeccdutils parser output.
        """
        ccd_id = ccd_reader_result.component.id
        component = ccd_reader_result.component

        parent_dir = os.path.join(self.output_dir, ccd_id[0], ccd_id)
        os.makedirs(parent_dir, exist_ok=True)

        ideal_conformer = ConformerType.Ideal
        json_output = {'het_code': ccd_id}

        # check parsing and conformer degeneration
        self._check_component_parsing(ccd_reader_result)
        ideal_regenerated = self._check_ideal_structure(ccd_reader_result.component)

        if ideal_regenerated:
            ideal_conformer = ConformerType.Computed

        # download templates if the user wants them.
        if self.pubchem is not None:
            self._download_template(component)

        # search fragment library
        self._search_fragment_library(component, json_output)

        # get scaffolds
        self._compute_component_scaffolds(component, json_output)

        # write out files
        self._generate_depictions(component)
        self._export_structure_formats(component, ideal_conformer)

        # get xml representation
        xml_repr = ccd_writer.to_xml_xml(ccd_reader_result.component)
        self.chem_comp_xml.append(xml_repr)

        # write fragments and scaffolds
        with open(os.path.join(parent_dir, f'{ccd_id}_substructures.json'), 'w') as f:
            json.dump(json_output, f, sort_keys=True, indent=4)

        self._write_substructures_xml(json_output, os.path.join(parent_dir, f'{ccd_id}_substructures.xml'))

    def _check_component_parsing(self, ccd_reader_result):
        """Checks components parsing and highlights issues encountered with
        the molecule: errors/warnings during the parsing process,
        unrecoverable sanitization issues, inchikey mismatch between what
        was in the source file and is reproduced by rdkit.

        Args:
            ccd_reader_result (CCDReaderResult): Output of the parsing process.
        """

        if ccd_reader_result.warnings:
            self.logger.debug(f'warnings: {";".join(ccd_reader_result.warnings)}')

        if ccd_reader_result.errors:
            self.logger.debug(f'errors: {";".join(ccd_reader_result.errors)}')

        if not ccd_reader_result.component.sanitized:
            self.logger.debug('sanitization issue.')

        if not ccd_reader_result.component.inchikey_from_rdkit_matches_ccd():
            self.logger.debug('inchikey mismatch.')

    def _download_template(self, component: Component):
        """Attempts to download a pubchem template for the given component

        Args:
            component (Component): Component to be used.
        """
        logger = logging.getLogger(__name__)
        component_downloaded = self.pubchem.process_template(component)
        if component_downloaded:
            logger.debug('downloaded new pubchem template.')

    def _check_ideal_structure(self, component: Component):
        """Checks whether or not the component has degenerated ideal
        coordinates. If so, new conformer is attempted to be generated.

        Args:
            component (Component): Component to be
                processed.
        Return:
            bool: Whether the ideal coordinates have been succesfully
            recalculated, false otherwise.
        """
        if component.has_degenerated_conformer(ConformerType.Ideal):
            self.logger.debug('has degenerated ideal coordinates.')
            result = component.compute_3d()
            if not result:
                self.logger.debug('error in generating 3D conformation.')

            return result

        return False

    def _search_fragment_library(self, component: Component, json_output: Dict[str, Any]):
        """Search fragment library to find hits

        Args:
            component (Component): Component to be processed
            json_output (Dict[str, Any]): dictionary like structure with the
                results to be stored.
        """

        json_output['fragments'] = []
        matches = component.library_search(self.fragment_library)

        for k, v in component.fragments.items():
            json_output['fragments'].append({
                'name': k,
                'smiles': self.fragment_library.library[k].smiles,
                'mapping': v.mappings,
                'source': v.source
            })

        if matches > 0:
            self.logger.debug(f'{matches} matches found in the library `{self.fragment_library.name}`.')

    def _compute_component_scaffolds(self, component: Component, json_output: Dict[str, Any]):
        """Compute scaffolds for a given component.

        Args:
            component (Component): Component to be processed
            json_output (Dict[str, Any]): dictionary like structure with the
                results to be stored.
        """
        json_output['scaffolds'] = []

        try:
            scaffolds = component.get_scaffolds()
        except CCDUtilsError as e:
            self.logger.error(str(e))

            return

        for scaffold in scaffolds:
            atom_names = component.locate_fragment(scaffold)
            scaffold_atom_names = []
            for match in atom_names:
                scaffold_atom_names.append([i.GetProp('name') for i in match])

            json_output['scaffolds'].append({
                'smiles': rdkit.Chem.MolToSmiles(scaffold),
                'mapping': scaffold_atom_names
            })

        self.logger.debug(f'{len(scaffolds)} scaffold(s) were found.')

    def _generate_depictions(self, component: Component):
        """Generate nice 2D depictions for the component. Presently depictions
        are generated in the following resolutions (100,200,300,400,500) with
        and without atom names.

        Args:
            component (Component): Component to be depicted.
            depictions (DepictionManager): Helper class
                to carry out depiction process.
            parent_dir (str): Where the depiction should be stored
        """
        parent_dir = os.path.join(self.output_dir, component.id[0], component.id)

        depiction_result = component.compute_2d(self.depictions)

        if depiction_result.source == DepictionSource.Failed:
            self.logger.debug('failed to generate 2D image.')
        else:
            if depiction_result.score > 0.99:
                self.logger.debug('collision free image could not be generated.')
            self.logger.debug(f'2D generated using {depiction_result.source.name} with score {depiction_result.score}.')

        wedge_bonds = depiction_result.template_name != 'cube'

        for i in range(100, 600, 100):
            component.export_2d_svg(os.path.join(parent_dir, f'{component.id}_{i}.svg'), width=i, wedge_bonds=wedge_bonds)
            component.export_2d_svg(os.path.join(parent_dir, f'{component.id}_{i}_names.svg'), width=i, names=True, wedge_bonds=wedge_bonds)

        component.export_2d_annotation(os.path.join(parent_dir, f'{component.id}_annotation.json'), wedge_bonds=wedge_bonds)

    def _export_structure_formats(self, component: Component, ideal_conformer: ConformerType):
        """Writes out component in a different formats as required for the
        PDBeChem FTP area.

        Args:
            component (Component): Component being processed.
            parent_dir (str): Working directory.
            ideal_conformer (ConformerType): ConformerType
                to be used for ideal coordinates.
        """
        parent_dir = os.path.join(self.output_dir, component.id[0], component.id)

        self.__write_molecule(os.path.join(parent_dir, f'{component.id}_model.sdf'), component, False, ConformerType.Model)
        self.__write_molecule(os.path.join(parent_dir, f'{component.id}_ideal.sdf'), component, False, ideal_conformer)
        self.__write_molecule(os.path.join(parent_dir, f'{component.id}_ideal_alt.pdb'), component, True, ideal_conformer)
        self.__write_molecule(os.path.join(parent_dir, f'{component.id}_model_alt.pdb'), component, True, ConformerType.Model)
        self.__write_molecule(os.path.join(parent_dir, f'{component.id}_ideal.pdb'), component, False, ideal_conformer)
        self.__write_molecule(os.path.join(parent_dir, f'{component.id}_model.pdb'), component, False, ConformerType.Model)
        self.__write_molecule(os.path.join(parent_dir, f'{component.id}.cml'), component, False, ConformerType.Model)
        self.__write_molecule(os.path.join(parent_dir, f'{component.id}.cif'), component, False, ConformerType.Model)

    def _write_substructures_xml(self, data, path):
        """Write XML infromation for scaffolds and fragments so that they
        are easily loaded into PDBe database

        Args:
            data (dict): Data to be serialized
            path (str): Path where the XML is going to be stored
        """

        root = ET.Element('entry')
        root.set('id', data['het_code'])

        fragments = ET.SubElement(root, 'fragments')
        scaffolds = ET.SubElement(root, 'scaffolds')
        fragment_counter = 0
        scaffold_counter = 0

        for frag in data['fragments']:
            fragment_counter += 1
            fragment = ET.SubElement(fragments, 'fragment', {
                'id': str(fragment_counter),
                'name': frag['name'],
                'smiles': frag['smiles'],
                'source': frag['source']
            })
            mapping_id = 0
            for l in frag['mapping']:
                mapping_id += 1
                atom_mapping_as_xml_element(fragment, l, mapping_id)

        for sc in data['scaffolds']:
            scaffold_counter += 1
            scaffold = ET.SubElement(scaffolds, 'scaffold', {
                'id': str(scaffold_counter),
                'smiles': sc['smiles']
            })

            for l in sc['mapping']:
                atom_mapping_as_xml_element(scaffold, l, 1)

        write_xml_file(root, path)

    def __write_molecule(self, path, component, alt_names, conformer_type):
        """Write out deemed structure.

        Args:
            path str: Path where the molecule will be stored.
            component (Component): Component to be written.
            alt_names (bool): Whether or not molecule will be written with
                alternate names.
            conformer_type (Component): Conformer to be written.
        """
        try:
            ccd_writer.write_molecule(path, component, remove_hs=False, alt_names=alt_names,
                                      conf_type=conformer_type)
        except Exception:
            self.logger.error(f'error writing {path}.')

            with open(path, 'w') as f:
                f.write('')

    def _wrap_up(self):
        """Wrap up computation, save PDBeChem-wide related files and quit.
        """
        write_xml_file(self.chem_comp_xml, os.path.join(self.output_dir, "chem_comp_list.xml"))

        with open(os.path.join(self.output_dir, 'chem_comp.list'), 'w') as f:
            f.write("\n".join(self.ids))

        self.logger.debug('All is done!')


# region pre-light tasks
def create_parser():
    """
    Sets up parse the command line options.

    Returns:
         argparse.Namespace parser
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    add_arg = parser.add_argument
    add_arg('components_cif', help='Input PDB-CCD components.cif file (must be specified)')
    add_arg('--general_templates', default=config.general_templates, type=str,
            help='Path to the directory with general templates in sdf format.')
    add_arg('--pubchem_templates', default='',
            help='Path to the directory with pubchem templates in sdf format.')
    add_arg('--output_dir', '-o', required=True,
            help='Create an output directory with files suitable for PDBeChem ftp directory')
    add_arg('--test_first', type=int,
            help='Only process the first TEST_FIRST chemical component definitions (for testing).')
    add_arg('--library', default=config.fragment_library,
            help='Use this fragment library in place of the one supplied with the code.')
    add_arg('--debug', action='store_true', help='Turn on debug message logging output')

    return parser


def check_args(args):
    """Validate suplied arguments.

    Args:
        args (argparse.Namespace): an argparse namespace containing the
            required arguments
    """
    if not os.path.isfile(args.components_cif):
        print(f'{args.components_cif} does not exist', file=sys.stderr)
        sys.exit(os.EX_NOINPUT)

    if not os.path.isdir(args.output_dir):
        os.makedirs(args.output_dir)

    if args.test_first is not None:
        if args.test_first < 1:
            print(f'Test_first mode needs to have at least 1 component.', file=sys.stderr)
            sys.exit(os.EX_NOINPUT)


def _set_up_logger(args):
    """Set up application level logging.

    Args:
        args (argparse.Namespace): Parsed arguments.

    Returns:
        logging.Logger: Application logger
    """

    logger = logging.getLogger(__name__)
    level = logging.DEBUG if args.debug else logging.ERROR
    frm = '[%(asctime)-15s]  %(message)s'
    logging.basicConfig(level=level, format=frm, datefmt='%a, %d %b %Y %H:%M:%S')
    logger.info(f'PDBeChem pipeline using:')
    logger.info(f'pdbeccdutils core v. {pdbeccdutils.__version__}, RDKit v. {rdkit.__version__}')

    return logger
# endregion


def main():
    """Runs the PDBeChem pipeline
    """
    parser = create_parser()
    args = parser.parse_args()

    check_args(args)
    log = _set_up_logger(args)

    log.info('Settings:')
    for k, v in vars(args).items():
        log.info(f'{"":5s}{k:25s}{v}')

    pdbechem = PDBeChemManager(log)
    pdbechem.run_pipeline(args)
