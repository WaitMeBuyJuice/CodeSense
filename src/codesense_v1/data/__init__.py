"""CodeSense Data Layer — query CodeGraph's SQLite knowledge graph."""

from codesense_v1.data.aggregate import directory_dependencies
from codesense_v1.data.db import CodeGraphDB
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
    "CodeGraphDB",
    "Module",
    "ModuleEdge",
    "directory_dependencies",
    "directory_tree",
    "list_files",
    "list_modules",
    "module_dependencies",
    "to_file_dependency_dict",
    "to_package_dependency_dict",
]
