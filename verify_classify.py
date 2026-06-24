import sys; sys.path.insert(0, "src")
from codesense_v1.summarizer.summarizer import _resolve_roots_and_aux

codesense_paths = ["src/codesense_v1/cache/cache.py","src/codesense_v1/llm/llm.py","tests/test_cache.py","scripts/validate.py"]
roots, aux = _resolve_roots_and_aux(codesense_paths)
print("CodesenseV1:")
print("  L1:", roots)
print("  L2:", [(a["name"], a["category"], a["file_count"]) for a in aux])

django_paths = ["django/core/models.py","django/utils/http.py","tests/test_core.py","js_tests/utils.js","scripts/build.py","docs/readme.md",".github/workflows/ci.yml"]
roots2, aux2 = _resolve_roots_and_aux(django_paths)
print("Django:")
print("  L1:", roots2)
print("  L2:", [(a["name"], a["category"], a["file_count"]) for a in aux2])

excalidraw_paths = ["packages/excalidraw/App.tsx","excalidraw-app/index.tsx","examples/demo.tsx","scripts/build.js","dev-docs/readme.md",".github/ci.yml","vitest.config.mts/vitest.config.mts"]
roots3, aux3 = _resolve_roots_and_aux(excalidraw_paths)
print("excalidraw:")
print("  L1:", roots3)
print("  L2:", [(a["name"], a["category"], a["file_count"]) for a in aux3])
