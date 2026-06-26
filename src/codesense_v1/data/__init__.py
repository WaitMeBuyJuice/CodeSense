"""CodeSense Data Layer — query CodeGraph's SQLite knowledge graph."""

from codesense_v1.data.aggregate import directory_dependencies
from codesense_v1.data.architecture import (
    ArchitectureFeatures,
    DirCentrality,
    architecture_features,
    compute_centrality,
    cross_dir_public_api,
    external_dependencies_by_dir,
    find_cycles,
    topological_layers,
)
from codesense_v1.data.db import CodeGraphDB
from codesense_v1.data.docstrings import (
    extract_file_docstring,
    extract_symbol_docstrings,
    is_enabled as docstrings_enabled,
)
from codesense_v1.data.files import directory_tree, list_files
from codesense_v1.data.hashes import (
    compute_architecture_hash,
    compute_dependencies_hash,
    compute_identity_hash,
    compute_structure_hash,
)
from codesense_v1.data.modules import (
    Module,
    ModuleEdge,
    list_modules,
    module_dependencies,
    to_file_dependency_dict,
    to_package_dependency_dict,
)
from codesense_v1.data.project_info import (
    IdentitySource,
    collect_identity_sources,
    extract_tech_stack_hint,
    read_readme,
)
from codesense_v1.data.structure import (
    AUXILIARY_CATEGORY,
    AUXILIARY_DIR_NAMES,
    TopLevelDir,
    auxiliary_category,
    classify_top_dirs,
    compute_tree_max_depth,
)

__all__ = [
    "ArchitectureFeatures",
    "AUXILIARY_CATEGORY",
    "AUXILIARY_DIR_NAMES",
    "CodeGraphDB",
    "DirCentrality",
    "IdentitySource",
    "Module",
    "ModuleEdge",
    "TopLevelDir",
    "architecture_features",
    "auxiliary_category",
    "classify_top_dirs",
    "collect_identity_sources",
    "compute_architecture_hash",
    "compute_centrality",
    "compute_dependencies_hash",
    "compute_tree_max_depth",
    "compute_identity_hash",
    "compute_structure_hash",
    "cross_dir_public_api",
    "directory_dependencies",
    "directory_tree",
    "docstrings_enabled",
    "extract_file_docstring",
    "extract_symbol_docstrings",
    "extract_tech_stack_hint",
    "external_dependencies_by_dir",
    "find_cycles",
    "list_files",
    "list_modules",
    "module_dependencies",
    "read_readme",
    "to_file_dependency_dict",
    "to_package_dependency_dict",
    "topological_layers",
]
