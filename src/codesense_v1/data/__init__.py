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
from codesense_v1.data.modules import (
    Module,
    ModuleEdge,
    list_modules,
    module_dependencies,
    to_file_dependency_dict,
    to_package_dependency_dict,
)

__all__ = [
    "ArchitectureFeatures",
    "CodeGraphDB",
    "DirCentrality",
    "Module",
    "ModuleEdge",
    "architecture_features",
    "compute_centrality",
    "cross_dir_public_api",
    "directory_dependencies",
    "directory_tree",
    "docstrings_enabled",
    "extract_file_docstring",
    "extract_symbol_docstrings",
    "external_dependencies_by_dir",
    "find_cycles",
    "list_files",
    "list_modules",
    "module_dependencies",
    "to_file_dependency_dict",
    "to_package_dependency_dict",
    "topological_layers",
]
