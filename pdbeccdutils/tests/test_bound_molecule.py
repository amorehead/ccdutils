"""Common fixtures shared among all the tests
"""
import pytest
from pdbeccdutils.core import bm_reader
from pdbeccdutils.core.fragment_library import FragmentLibrary
from pdbeccdutils.tests.tst_utilities import supply_list_of_sample_cifs

sample_ccd_cifs = supply_list_of_sample_cifs()
problematic_ids = ["UNL", "NA", "SY9", "10R", "ASX"]


@pytest.fixture(scope="session", params=sample_ccd_cifs)
def component(request):
    reader = bm_reader.read_pdb_cif_file(request.param)
    c = reader.component

    if c.id not in problematic_ids:
        assert reader.warnings == []

    return c


def test_write_bound_molecule(component, tmpdir_factory):
    wd = tmpdir_factory.mktemp("bm_test")
    for ideal in True, False:
        for remove_hs in True, False:
            suffix = f'{("" if remove_hs else "H")}'
            sdf_file = os.path.join(wd, f"{component.id}_{suffix}.sdf")
            conf_type = ConformerType.Ideal if ideal else ConformerType.Model
            ccd_writer.write_molecule(
                path=sdf_file,
                component=component,
                conf_type=conf_type,
                remove_hs=remove_hs,
            )
            rdkit_mol = component.mol_no_h if remove_hs else component.mol
            assert os.path.isfile(sdf_file)
            assert os.path.getsize(sdf_file) > 0
            mol = Chem.MolFromMolFile(sdf_file, sanitize=False)
            assert isinstance(mol, Chem.rdchem.Mol)
            assert mol.GetNumAtoms() == rdkit_mol.GetNumAtoms()


def test_valid_properties_bound_molecule(key):
    physchem_props = bm_reader.read_pdb_cif_file(
        cif_filename(key)
    ).component.physchem_properties

    assert test_inputs[key]["logp"] == round(physchem_props["CrippenClogP"], 3)
    assert test_inputs[key]["heavy_atom_count"] == physchem_props["NumHeavyAtoms"]
    assert test_inputs[key]["numH_acceptors"] == physchem_props["NumHBA"]
    assert test_inputs[key]["numH_donors"] == physchem_props["NumHBD"]
    assert test_inputs[key]["num_rotable_bonds"] == physchem_props["NumRotatableBonds"]
    assert test_inputs[key]["rings_count"] == physchem_props["NumRings"]
    assert test_inputs[key]["TPSA"] == round(physchem_props["tpsa"], 3)
    assert test_inputs[key]["molwt"] == round(physchem_props["exactmw"], 3)


def test_bound_molecule_conformer_is_broken_ion():
    mol = rdkit.Chem.RWMol()
    atom = rdkit.Chem.Atom("H")
    mol.AddAtom(atom)
    conformer = rdkit.Chem.Conformer(1)
    atom_position = rdkit.Chem.rdGeometry.Point3D(np.NaN, np.NaN, np.NaN)
    conformer.SetAtomPosition(0, atom_position)
    mol.AddConformer(conformer, assignId=True)
    m = mol.GetMol()
    c = m.GetConformer(0)
    fix_conformer(c)
    assert c.GetAtomPosition(0).x == 0.0
    assert c.GetAtomPosition(0).y == 0.0
    assert c.GetAtomPosition(0).z == 0.0


def test_bound_molecule_conformer_has_broken_atom():
    mol = rdkit.Chem.RWMol()
    o = rdkit.Chem.Atom("O")
    h = rdkit.Chem.Atom("H")
    mol.AddAtom(o)
    mol.AddAtom(h)
    mol.AddBond(0, 1, rdkit.Chem.rdchem.BondType(1))
    conformer = rdkit.Chem.Conformer(1)
    o_position = rdkit.Chem.rdGeometry.Point3D(1, 2, 3)
    h_position = rdkit.Chem.rdGeometry.Point3D(np.NaN, np.NaN, np.NaN)
    conformer.SetAtomPosition(0, o_position)
    conformer.SetAtomPosition(1, h_position)
    mol.AddConformer(conformer, assignId=True)
    m = mol.GetMol()
    c = m.GetConformer(0)
    fix_conformer(c)
    assert c.GetAtomPosition(0).x != 0.0
    assert c.GetAtomPosition(0).y != 0.0
    assert c.GetAtomPosition(0).z != 0.0
    assert c.GetAtomPosition(1).x == 0.0
    assert c.GetAtomPosition(1).y == 0.0
    assert c.GetAtomPosition(1).z == 0.0
